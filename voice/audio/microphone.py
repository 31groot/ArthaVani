import asyncio

import sounddevice as sd

from config.constants import (
    CHANNELS,
    CHUNK_SIZE,
    SAMPLE_RATE,
    MAX_QUEUE_SIZE,
)
from config.logger import logger


class Microphone:


    def __init__(self):

        self.stream: sd.InputStream | None = None

        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

        self.loop: asyncio.AbstractEventLoop | None = None

    def _audio_callback(
        self,
        indata,
        frames,
        time,
        status,
    ):

        if status:
            logger.warning(f"Audio callback status: {status}")

        if self.loop is None:
            return

        audio_bytes = indata.copy().tobytes()

        def _enqueue_audio(self, audio_bytes: bytes):
            try:
                self.audio_queue.put_nowait(audio_bytes)
            except asyncio.QueueFull:
                logger.warning("Audio queue full. Dropping audio chunk.")

        self.loop.call_soon_threadsafe(
            self._enqueue_audio,
            audio_bytes,
        )

    async def start(self):

        logger.info("Opening microphone...")

        self.loop = asyncio.get_running_loop()

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )

        self.stream.start()

        logger.info("Microphone started.")

    async def read(self) -> bytes:

        return await self.audio_queue.get()

    async def stop(self):

        if self.stream is None:
            return

        logger.info("Stopping microphone...")

        self.stream.stop()
        self.stream.close()

        self.stream = None

        logger.info("Microphone stopped.")