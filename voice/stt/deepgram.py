import asyncio

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v2.types import ListenV2TurnInfo

from config.constants import SAMPLE_RATE
from config.logger import logger
from config.settings import settings

from voice.stt.events import TranscriptEvent


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

    async def connect(self) -> None:

        logger.info("Connecting to Deepgram...")

        self.loop = asyncio.get_running_loop()

        self._connection_context = (
            self.client.listen.v2.connect(
                model=settings.DEEPGRAM_MODEL,
                encoding="linear16",
                sample_rate=SAMPLE_RATE,
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

        await self.connection.send_media(
            audio
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

        # Ignore messages that are not turn-info results
        if not isinstance(message, ListenV2TurnInfo):
            return

        transcript = message.transcript

        # Ignore empty transcription results
        if not transcript:
            return

        # v2 (Flux) reports turn state via `event`, not a per-word
        # `is_final` flag like v1 did. EndOfTurn is the point where
        # the user has finished speaking for this turn, which is
        # the equivalent of a "final" transcript downstream.
        is_final = message.event == "EndOfTurn"

        # Convert Deepgram's response into our application's event
        event = TranscriptEvent(
            text=transcript,
            confidence=message.end_of_turn_confidence,
            is_final=is_final,
        )

        # Safely put the event into the asyncio queue
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                self._events.put_nowait,
                event,
            )
