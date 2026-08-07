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
            api_key=settings.deepgram.api_key,
        )
        self.connection = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._events: asyncio.Queue[TranscriptEvent] = asyncio.Queue()

    async def connect(self):
        logger.info("Connecting to Deepgram...")

        self.loop = asyncio.get_running_loop()

        self.connection = await self.client.listen.v2.connect(
            model=settings.deepgram.model,
            encoding="linear16",
            sample_rate=SAMPLE_RATE,
        )

        self.connection.on(
            EventType.OPEN,
            lambda _: logger.info("Deepgram connection opened."),
        )

        self.connection.on(
            EventType.CLOSE,
            lambda _: logger.info("Deepgram connection closed."),
        )

        self.connection.on(
            EventType.ERROR,
            lambda error: logger.error(f"Deepgram error: {error}"),
        )

        self.connection.on(
            EventType.MESSAGE,
            self._on_message,
        )

        await self.connection.start_listening()
        logger.info("Deepgram connected.")

    async def send_audio(self, audio: bytes):
        if self.connection is None:
            raise RuntimeError("Deepgram client is not connected.")
        await self.connection.send_media(audio)

    async def receive(self) -> TranscriptEvent:
        return await self._events.get()

    async def close(self):
        if self.connection is None:
            return None

        await self.connection.send_close_stream()
        logger.info("Deepgram connection teardown initiated.")

    def _on_message(self, message):

        if not isinstance(message, ListenV2TurnInfo):
            return None

        alternative = message.channel.alternatives[0]
        transcript = alternative.transcript

        if not transcript:
            return None

        event = TranscriptEvent(
            text=transcript,
            confidence=getattr(alternative, "confidence", 0.0),
            is_final=message.is_final,
        )

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                self._events.put_nowait,
                event,
            )