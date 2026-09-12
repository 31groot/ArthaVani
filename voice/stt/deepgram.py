import asyncio
import time

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types import ListenV1Results, ListenV1UtteranceEnd

from config.constants import SAMPLE_RATE
from config.logger import logger
from config.settings import settings

from voice.stt.events import TranscriptEvent

# Target size (in bytes) of each frame sent to Deepgram. int16 mono
# @ 16kHz => 32000 bytes/sec, so 100ms == 3200 bytes. Batching small
# mic callbacks into steadier ~100ms frames avoids being needlessly
# chatty over the WebSocket.
SEND_CHUNK_BYTES = int(SAMPLE_RATE * 2 * 0.1)


class DeepgramClient:

    def __init__(self):

        self.client = AsyncDeepgramClient(
            api_key=settings.DEEPGRAM_API_KEY,
        )

        # Will hold the active Deepgram connection after connect()
        self.connection = None

        self.loop: asyncio.AbstractEventLoop | None = None

        self._events: asyncio.Queue[TranscriptEvent] = asyncio.Queue()

        # Keep the connection context alive until close() is called
        self._connection_context = None

        self._listen_task: asyncio.Task | None = None

        # Nova-3's `speech_final` flag on Results messages is
        # unreliable in practice -- it can simply never fire even
        # after a long pause. Instead we track the latest (highest
        # confidence / most complete) interim transcript here, and
        # treat Deepgram's separate UtteranceEnd message (driven by
        # utterance_end_ms below) as the real "the user is done
        # talking" signal that promotes it to final.
        self._last_interim: TranscriptEvent | None = None
        self._turn_finalized = True
        self._last_interim_time = 0.0

        # Buffer used to batch small audio chunks into
        # larger, steadier frames before sending to Deepgram.
        self._send_buffer = bytearray()

    async def connect(self) -> None:

        logger.info("Connecting to Deepgram...")

        self.loop = asyncio.get_running_loop()

        self._connection_context = (
            self.client.listen.v1.connect(
                model=settings.DEEPGRAM_MODEL,
                encoding="linear16",
                sample_rate=SAMPLE_RATE,
                channels=1,
                interim_results=True,
                smart_format=True,
                punctuate=True,
                endpointing=300,
                utterance_end_ms=1000,
                vad_events=True,
            )
        )

        # Enter the connection context and get the active connection
        self.connection = (
            await self._connection_context.__aenter__()
        )

        self.connection.on(
            EventType.OPEN,
            lambda _: logger.info(
                "Deepgram connection opened."
            ),
        )

        self.connection.on(
            EventType.CLOSE,
            lambda _: logger.info(
                "Deepgram connection closed."
            ),
        )

        self.connection.on(
            EventType.ERROR,
            lambda error: logger.error(
                f"Deepgram error: {error}"
            ),
        )

        self.connection.on(
            EventType.MESSAGE,
            self._on_message,
        )

        self._listen_task = asyncio.create_task(
            self.connection.start_listening()
        )

        logger.info("Deepgram connected.")

    async def send_audio(
        self,
        audio: bytes,
    ) -> None:

        if self.connection is None:
            raise RuntimeError(
                "Deepgram client is not connected."
            )

        # Batch small chunks into steadier ~100ms frames before
        # sending. See SEND_CHUNK_BYTES for why.
        self._send_buffer.extend(audio)

        while len(self._send_buffer) >= SEND_CHUNK_BYTES:

            frame = bytes(self._send_buffer[:SEND_CHUNK_BYTES])
            del self._send_buffer[:SEND_CHUNK_BYTES]

            await self.connection.send_media(
                frame
            )

    async def receive(
        self,
    ) -> TranscriptEvent:

        return await self._events.get()

    async def close(self) -> None:

        logger.info("Closing Deepgram connection...")

        if self._listen_task is not None:

            self._listen_task.cancel()

            try:
                await self._listen_task

            except asyncio.CancelledError:
                pass

            self._listen_task = None

        if self._connection_context is not None:

            try:

                await self._connection_context.__aexit__(
                    None,
                    None,
                    None,
                )

            finally:

                self._connection_context = None
                self.connection = None

        logger.info("Deepgram connection closed.")

    def _on_message(self, message) -> None:

        if isinstance(message, ListenV1UtteranceEnd):
            self._on_utterance_end()
            return

        if not isinstance(message, ListenV1Results):
            return

        alternatives = message.channel.alternatives

        transcript = (
            alternatives[0].transcript
            if alternatives
            else ""
        )

        confidence = (
            alternatives[0].confidence
            if alternatives
            else 0.0
        )

        # Ignore empty transcription results
        if not transcript:
            return

        # Track this as the latest interim candidate regardless of
        # Deepgram's own is_final/speech_final flags -- finalization
        # is driven entirely by the separate UtteranceEnd message
        # (see _on_utterance_end), since speech_final is unreliable.
        event = TranscriptEvent(
            text=transcript,
            confidence=confidence,
            is_final=False,
        )

        logger.info(
            "STT interim: text=%r confidence=%.3f is_final=%s "
            "speech_final=%s",
            transcript,
            confidence,
            message.is_final,
            message.speech_final,
        )

        self._last_interim = event
        self._turn_finalized = False
        self._last_interim_time = time.monotonic()

        # Safely put the event into the asyncio queue
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                self._events.put_nowait,
                event,
            )

    def _on_utterance_end(self) -> None:

        if self._turn_finalized or self._last_interim is None:
            return

        transcript = self._last_interim.text
        confidence = self._last_interim.confidence

        logger.info(
            "STT final: text=%r confidence=%.3f (via UtteranceEnd)",
            transcript,
            confidence,
        )

        final_event = TranscriptEvent(
            text=transcript,
            confidence=confidence,
            is_final=True,
        )

        self._turn_finalized = True
        self._last_interim = None
        self._last_interim_time = 0.0

        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                self._events.put_nowait,
                final_event,
            )

    async def force_finalize(self) -> None:

        if self._turn_finalized or self._last_interim is None:
            return

        if time.monotonic() - self._last_interim_time < 2.5:
            return

        forced_event = TranscriptEvent(
            text=self._last_interim.text,
            confidence=self._last_interim.confidence,
            is_final=True,
        )

        self._turn_finalized = True
        self._last_interim = None

        await self._events.put(forced_event)