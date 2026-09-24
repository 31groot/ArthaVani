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

from config.constants import DROPPED_VOL, MAX_QUEUE_SIZE
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
        # Tracks the full response lifecycle rather than one sentence.
        # TTSWorker emits on_audio_finished after each sentence, so treating
        # that callback as the end of the whole response can disable barge-in
        # between sentences while the assistant is still speaking.
        self._response_active = False
        self._response_generation_done = False
        self._tts_idle_task: asyncio.Task | None = None
        self._user_speech_active = False
        self._possible_speech_active = False
        self._tts_barge_in_armed = False
        self._barge_in_in_progress = False
        self._browser_playback_drained = asyncio.Event()
        self._server_tts_drained = False

    async def _on_transcript(self, event) -> None:
        # Only non-final Deepgram hypotheses are preview text. Final text
        # is emitted through the existing user_text callback after turn
        # finalization, so it is not duplicated in the UI.
        if not event.text or event.is_final:
            return

        text = event.text.strip()
        await self._queue_event({"type": "interim_text", "text": text})

        # Browser AEC/noise suppression can make Silero's confirmed STARTED
        # transition conservative while the assistant is speaking. Once the
        # assistant is actively playing, a sufficiently confident Deepgram
        # interim transcript is itself a strong user-intent signal. Do not
        # require POSSIBLE_STARTED here; otherwise STT can clearly hear the
        # user while barge-in still fails because Silero stayed below its
        # confirmation threshold.
        if (
            self._tts_active
            and self._tts_barge_in_armed
            and not self._barge_in_in_progress
            and time.monotonic() >= self._tts_interrupt_ready_at
            and float(getattr(event, "confidence", 0.0) or 0.0) >= 0.72
            and len(text) >= 3
        ):
            await self._queue_event({"type": "duck", "level": DROPPED_VOL})
            await self._confirm_barge_in("Deepgram interim transcript")

    async def _confirm_barge_in(self, reason: str) -> None:
        if self._barge_in_in_progress:
            return
        if not self._tts_active or not self._tts_barge_in_armed:
            return

        self._barge_in_in_progress = True
        logger.info("Browser barge-in confirmed: %s", reason)

        # Cut browser playback FIRST. The old implementation waited for
        # LLM cancellation before notifying the browser, which let already
        # buffered PCM continue playing for seconds after the user spoke.
        await self._cancel_tts_idle_check()
        self._tts_active = False
        self._tts_interrupt_ready_at = 0.0
        self._tts_barge_in_armed = False
        self._response_active = False
        self._response_generation_done = True
        self._server_tts_drained = False
        self._browser_playback_drained.set()

        # Clear anything already buffered on the server before the control
        # message is sent. Then send barge_in immediately so the browser
        # clears its own playback ring without waiting for backend cleanup.
        self.clear_audio_output()
        self.clear_all_outbound_messages()
        await self._queue_event({"type": "barge_in"})

        # Cancel LLM/TTS in the background. Do not make the browser wait for
        # these potentially slow cancellations.
        asyncio.create_task(self._finish_barge_in_interrupt())

    async def _finish_barge_in_interrupt(self) -> None:
        results = await asyncio.gather(
            self.llm_worker.interrupt(),
            self.tts_worker.interrupt(),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.exception("Barge-in cleanup failed: %s", result)

    async def _on_user_text(self, text: str) -> None:
        # A new user turn means a new assistant response is expected. Keep
        # barge-in eligible across sentence boundaries until the complete
        # LLM response has finished and all TTS audio has drained.
        self._response_active = True
        self._response_generation_done = False
        await self._queue_event({"type": "user_text", "text": text})

    async def _on_assistant_text(self, text: str) -> None:
        # The LLM has finished producing the complete response. TTS may still
        # have multiple sentences left to synthesize/play, so we do not mark
        # the response idle until those queues drain.
        self._response_generation_done = True
        await self._queue_event({"type": "assistant_text", "text": text})

    async def _on_tts_started(self) -> None:
        # A stale sentence can race with barge-in cleanup. Do not resurrect
        # TTS state after an interruption until the next user turn is active.
        if self._barge_in_in_progress or not self._response_active:
            logger.debug("Ignoring stale TTS start after barge-in.")
            return

        # Do not let microphone echo immediately cancel the first TTS
        # audio packet.  The short grace window gives browser AEC and the
        # playback path time to settle before a genuine interruption can
        # be confirmed.
        await self._cancel_tts_idle_check()
        self._tts_active = True
        self._barge_in_in_progress = False
        self._tts_interrupt_ready_at = time.monotonic() + 0.35
        self._browser_playback_drained.clear()
        self._server_tts_drained = False
        # Arm barge-in only for a response that follows the initial user turn.
        # The VAD state prevents the original turn from interrupting its own TTS.
        self._tts_barge_in_armed = not self._user_speech_active
        await self._queue_event({"type": "tts_started"})

    async def _mark_tts_idle_when_drained(self) -> None:
        # Server-side queues can empty several seconds before the browser has
        # physically played its buffered PCM. Keep barge-in armed until the
        # browser explicitly acknowledges playback drain.
        try:
            stable_since: float | None = None
            while not self._closed:
                synthesis_task = self.tts_worker._synthesis_task
                synthesis_running = (
                    synthesis_task is not None
                    and not synthesis_task.done()
                )
                pending_sentences = not self.sentence_queue.empty()
                pending_audio = not self.audio_output_queue.empty()

                server_drained = (
                    self._response_generation_done
                    and not synthesis_running
                    and not pending_sentences
                    and not pending_audio
                )

                if server_drained:
                    now = time.monotonic()
                    if stable_since is None:
                        stable_since = now
                        if not self._server_tts_drained:
                            self._server_tts_drained = True
                            await self._queue_event({"type": "tts_server_drained"})
                    elif (
                        now - stable_since >= 0.25
                        and self._browser_playback_drained.is_set()
                    ):
                        self._tts_active = False
                        self._tts_interrupt_ready_at = 0.0
                        self._tts_barge_in_armed = False
                        self._barge_in_in_progress = False
                        self._response_active = False
                        await self._queue_event({"type": "tts_finished"})
                        logger.info(
                            "Browser TTS fully drained on client; barge-in disarmed."
                        )
                        return
                else:
                    stable_since = None
                    self._server_tts_drained = False

                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise

    async def notify_browser_playback_drained(self) -> None:
        if self._closed:
            return
        self._browser_playback_drained.set()
        logger.debug("Browser playback drain acknowledged by client.")

    async def _cancel_tts_idle_check(self) -> None:
        task = self._tts_idle_task
        self._tts_idle_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _on_tts_finished(self) -> None:
        # This callback is sentence-level. Do not mark the whole response as
        # finished here, otherwise a multi-sentence answer creates a window in
        # which STARTED events are ignored and the remaining paragraph cannot
        # be interrupted.
        await self._cancel_tts_idle_check()
        self._tts_idle_task = asyncio.create_task(
            self._mark_tts_idle_when_drained()
        )

    async def _on_tts_error(self, message: str) -> None:
        await self._cancel_tts_idle_check()
        self._tts_active = False
        self._tts_interrupt_ready_at = 0.0
        self._tts_barge_in_armed = False
        self._response_active = False
        self._response_generation_done = True
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
            if self._barge_in_in_progress:
                # TTS cancellation can race with this bridge. Never forward
                # stale PCM from a response that has already been interrupted.
                continue
            await self.outbound_queue.put(("audio", audio))

    async def _barge_in_loop(self) -> None:
        while True:
            event = await self.conversation_queue.get()

            if event.state == SpeechState.POSSIBLE_STARTED:
                self._possible_speech_active = True
                await self._queue_event({
                    "type": "duck",
                    "level": DROPPED_VOL,
                })
                await self._queue_event({"type": "speech_detected"})
                continue

            if event.state == SpeechState.POSSIBLE_ENDED:
                # Candidate speech faded before confirmation; restore volume.
                self._possible_speech_active = False
                await self._queue_event({"type": "unduck"})
                continue

            if event.state == SpeechState.STARTED:
                self._user_speech_active = True

                # Treat the original user utterance normally. During a live
                # assistant response, however, keep barge-in armed across
                # sentence boundaries. `_tts_active` intentionally remains
                # true until the entire response has drained.
                if not self._tts_active or not self._tts_barge_in_armed:
                    logger.debug(
                        "Ignoring speech STARTED event (tts_active=%s, barge_in_armed=%s).",
                        self._tts_active,
                        self._tts_barge_in_armed,
                    )
                    continue

                if time.monotonic() < self._tts_interrupt_ready_at:
                    logger.debug(
                        "Ignoring speech STARTED event during browser TTS startup grace period."
                    )
                    continue

                # Re-send duck at confirmed speech so the browser is
                # guaranteed to lower output even if the early candidate
                # event was missed or arrived before TTS became active.
                await self._queue_event({"type": "duck", "level": DROPPED_VOL})
                await self._confirm_barge_in("Silero STARTED event")
                # Keep browser output ducked until ENDED.
                continue

            if event.state == SpeechState.ENDED:
                self._user_speech_active = False
                self._possible_speech_active = False
                self._barge_in_in_progress = False
                # Once the original user turn ends, any assistant speech that
                # is currently active becomes interruptible. This is the key
                # re-arm step for barge-in after the first turn.
                if self._tts_active and self._response_active:
                    self._tts_barge_in_armed = True
                    logger.debug("Browser barge-in armed after user turn ended.")
                await self._queue_event({"type": "unduck"})
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

    def clear_all_outbound_messages(self) -> None:
        """Drop all queued outbound messages during immediate barge-in."""
        while True:
            try:
                self.outbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def stop(self) -> None:
        if self._closed:
            return

        self._closed = True

        if self._tts_idle_task is not None:
            self._tts_idle_task.cancel()
            try:
                await self._tts_idle_task
            except asyncio.CancelledError:
                pass
            self._tts_idle_task = None

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
            elif message_type == "tts_playback_drained":
                await pipeline.notify_browser_playback_drained()
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
