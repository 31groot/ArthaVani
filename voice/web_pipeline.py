"""Browser voice transport built on the same VAD/STT/LLM/TTS pipeline.

The desktop pipeline owns a physical microphone/speaker. The web pipeline
keeps the exact same processing stages but replaces the hardware endpoints
with WebSocket audio in/out, so browser voice gets the same streaming
Deepgram + Silero VAD + Edge-TTS + barge-in behaviour.
"""
from __future__ import annotations

import asyncio
import json
import time

from config.constants import MAX_QUEUE_SIZE
from config.logger import logger
from finance_agent.conversation import ConversationIdentity
from voice.llm.worker import LLMWorker
from voice.stt.deepgram import DeepgramClient
from voice.stt.worker import STTWorker
from voice.text.text_splitter import SentenceSplitter
from voice.tts.edge import EdgeTTS
from voice.tts.worker import TTSWorker
from voice.vad.detector import SpeechDetector
from voice.vad.events import ConversationEvent, SpeechState
from voice.vad.silero import SileroVAD
from voice.vad.worker import VADWorker


class BrowserVoicePipeline:
    """Streaming ArthaVani voice session for browser WebSocket clients."""

    def __init__(
        self,
        *,
        user_id: str,
        conversation_id: str,
    ) -> None:
        self.conversation_identity = ConversationIdentity(
            user_id=user_id,
            conversation_id=conversation_id,
        )

        self.audio_input_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )
        self.vad_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )
        self.stt_audio_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )
        self.transcript_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.sentence_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.audio_output_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=MAX_QUEUE_SIZE
        )
        self.conversation_queue: asyncio.Queue[ConversationEvent] = asyncio.Queue()

        self.deepgram = DeepgramClient()
        self.stt_worker = STTWorker(
            deepgram=self.deepgram,
            audio_queue=self.stt_audio_queue,
            transcript_queue=self.transcript_queue,
            on_transcript=self._on_transcript,
        )

        self.silero_vad = SileroVAD()
        self.speech_detector = SpeechDetector()
        self.vad_worker = VADWorker(
            vad=self.silero_vad,
            detector=self.speech_detector,
            audio_queue=self.vad_queue,
            conversation_queue=self.conversation_queue,
        )

        self.edge_tts = EdgeTTS()
        self.tts_worker = TTSWorker(
            tts=self.edge_tts,
            sentence_queue=self.sentence_queue,
            audio_queue=self.audio_output_queue,
            on_audio_started=self._on_tts_started,
            on_audio_finished=self._on_tts_finished,
            on_error=self._on_tts_error,
        )

        self.sentence_splitter = SentenceSplitter(
            sentence_queue=self.sentence_queue,
        )

        self.llm_worker = LLMWorker(
            splitter=self.sentence_splitter,
            transcript_queue=self.transcript_queue,
            conversation_identity=self.conversation_identity,
            on_user_text=self._on_user_text,
            on_assistant_text=self._on_assistant_text,
        )

        self._audio_fanout_task: asyncio.Task | None = None
        self.outbound_queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        self._audio_bridge_task: asyncio.Task | None = None
        self._barge_in_task: asyncio.Task | None = None
        self._started = False
        self._closed = False
        self._received_audio_bytes = 0
        self._tts_active = False
        self._tts_interrupt_ready_at = 0.0

    async def _on_transcript(self, event) -> None:
        # Only non-final Deepgram hypotheses are preview text. Final text
        # is emitted through the existing user_text callback after turn
        # finalization, so it is not duplicated in the UI.
        if not event.text or event.is_final:
            return
        await self._queue_event({"type": "interim_text", "text": event.text})

    async def _on_user_text(self, text: str) -> None:
        await self._queue_event({"type": "user_text", "text": text})

    async def _on_assistant_text(self, text: str) -> None:
        await self._queue_event({"type": "assistant_text", "text": text})

    async def _on_tts_started(self) -> None:
        # Do not let microphone echo immediately cancel the first TTS
        # audio packet.  The short grace window gives browser AEC and the
        # playback path time to settle before a genuine interruption can
        # be confirmed.
        self._tts_active = True
        self._tts_interrupt_ready_at = time.monotonic() + 0.20
        await self._queue_event({"type": "tts_started"})

    async def _on_tts_finished(self) -> None:
        self._tts_active = False
        self._tts_interrupt_ready_at = 0.0
        await self._queue_event({"type": "tts_finished"})

    async def _on_tts_error(self, message: str) -> None:
        await self._queue_event({
            "type": "tts_error",
            "message": message or "Text-to-speech failed.",
        })

    async def _queue_event(self, event: dict) -> None:
        await self.outbound_queue.put(("json", event))

    async def start(self) -> None:
        if self._started:
            raise RuntimeError("Browser voice pipeline already started.")

        await self.llm_worker.start()
        self.stt_worker.start()
        await self.stt_worker.wait_until_ready()
        self.vad_worker.start()
        self.tts_worker.start()

        self._audio_fanout_task = asyncio.create_task(self._fanout_loop())
        self._audio_bridge_task = asyncio.create_task(self._audio_bridge_loop())
        self._barge_in_task = asyncio.create_task(self._barge_in_loop())
        self._started = True

        await self._queue_event(
            {
                "type": "ready",
                "sample_rate": 16_000,
                "audio_format": "pcm_s16le",
                "channels": 1,
                "barge_in": True,
            }
        )

        logger.info(
            "Browser voice pipeline started for user=%s conversation=%s",
            self.conversation_identity.user_id,
            self.conversation_identity.conversation_id,
        )

    async def _fanout_loop(self) -> None:
        while True:
            chunk = await self.audio_input_queue.get()
            await self.vad_queue.put(chunk)
            await self.stt_audio_queue.put(chunk)

    async def _audio_bridge_loop(self) -> None:
        while True:
            audio = await self.audio_output_queue.get()
            await self.outbound_queue.put(("audio", audio))

    async def _barge_in_loop(self) -> None:
        while True:
            event = await self.conversation_queue.get()

            if event.state == SpeechState.POSSIBLE_STARTED:
                await self._queue_event({"type": "speech_detected"})
                continue

            if event.state == SpeechState.POSSIBLE_ENDED:
                continue

            if event.state == SpeechState.STARTED:
                # User speech is normal while the assistant is idle or
                # thinking.  Only treat it as barge-in once TTS is actually
                # producing browser audio.  This prevents the initial user
                # turn (and mic/AEC noise) from cancelling TTS before the
                # browser receives its first audio chunk.
                if not self._tts_active:
                    logger.debug(
                        "Ignoring speech STARTED event because browser TTS is not active."
                    )
                    continue

                if time.monotonic() < self._tts_interrupt_ready_at:
                    logger.debug(
                        "Ignoring speech STARTED event during browser TTS startup grace period."
                    )
                    continue

                logger.info("Browser barge-in confirmed while TTS is active.")
                await self.llm_worker.interrupt()
                await self.tts_worker.interrupt()
                self._tts_active = False
                self._tts_interrupt_ready_at = 0.0
                self.clear_audio_output()
                self.clear_pending_audio_messages()
                await self._queue_event({"type": "barge_in"})
                continue

            if event.state == SpeechState.ENDED:
                asyncio.create_task(self._finalize_watchdog())

    async def _finalize_watchdog(self) -> None:
        await asyncio.sleep(3.0)
        await self.deepgram.force_finalize()

    async def feed_audio(self, audio: bytes) -> None:
        if not audio:
            return
        if self._closed:
            return
        self._received_audio_bytes += len(audio)
        await self.audio_input_queue.put(audio)

    async def next_outbound(self) -> tuple[str, object]:
        return await self.outbound_queue.get()

    def clear_audio_output(self) -> None:
        while True:
            try:
                self.audio_output_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def clear_pending_audio_messages(self) -> None:
        """Drop already-bridged audio while preserving JSON control events."""
        preserved: list[tuple[str, object]] = []
        while True:
            try:
                item = self.outbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item[0] != "audio":
                preserved.append(item)

        for item in preserved:
            self.outbound_queue.put_nowait(item)

    async def stop(self) -> None:
        if self._closed:
            return

        self._closed = True

        for task_name in ("_audio_fanout_task", "_audio_bridge_task", "_barge_in_task"):
            task = getattr(self, task_name)
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            setattr(self, task_name, None)

        await self.vad_worker.stop()
        await self.stt_worker.stop()
        await self.llm_worker.stop()
        await self.tts_worker.stop()
        self.clear_audio_output()

        logger.info("Browser voice pipeline stopped.")


async def run_browser_voice_session(
    websocket,
    *,
    user_id: str,
    conversation_id: str,
) -> None:
    """Run a full duplex WebSocket voice session."""

    send_lock = asyncio.Lock()
    pipeline: BrowserVoicePipeline | None = None
    sender_task: asyncio.Task | None = None

    try:
        pipeline = BrowserVoicePipeline(
            user_id=user_id,
            conversation_id=conversation_id,
        )
        await pipeline.start()

        async def sender() -> None:
            audio_chunks_sent = 0
            audio_bytes_sent = 0
            while True:
                kind, payload = await pipeline.next_outbound()
                async with send_lock:
                    if kind == "audio":
                        await websocket.send_bytes(payload)
                        audio_chunks_sent += 1
                        audio_bytes_sent += len(payload)
                        if audio_chunks_sent == 1:
                            logger.info(
                                "Browser voice sent first TTS PCM chunk: %d bytes.",
                                len(payload),
                            )
                        elif audio_chunks_sent % 25 == 0:
                            logger.debug(
                                "Browser voice TTS transport: %d chunks / %d bytes sent.",
                                audio_chunks_sent,
                                audio_bytes_sent,
                            )
                    else:
                        await websocket.send_json(payload)

        sender_task = asyncio.create_task(sender())

        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                await pipeline.feed_audio(message["bytes"])
                continue

            text = message.get("text")
            if not text:
                continue

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await pipeline._queue_event({"type": "error", "message": "Invalid voice message."})
                continue

            message_type = payload.get("type")
            if message_type == "ping":
                await pipeline._queue_event({"type": "pong"})
            elif message_type == "stop":
                break
            else:
                await pipeline._queue_event(
                    {"type": "error", "message": "Unknown voice message type."}
                )

    finally:
        if sender_task is not None:
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass
        if pipeline is not None:
            await pipeline.stop()
