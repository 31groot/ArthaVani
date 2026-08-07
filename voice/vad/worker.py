import asyncio

from config.constants import VAD_FRAME_SAMPLES
from config.logger import logger

from voice.vad.buffer import AudioBuffer
from voice.vad.detector import SpeechDetector
from voice.vad.events import ConversationEvent
from voice.vad.silero import SileroVAD


class VADWorker:

    def __init__(
        self,
        vad: SileroVAD,
        detector: SpeechDetector,
        audio_queue: asyncio.Queue[bytes],
        conversation_queue: asyncio.Queue[ConversationEvent],
    ):

        self.vad = vad
        self.detector = detector

        self.audio_queue = audio_queue
        self.conversation_queue = conversation_queue

        self.buffer = AudioBuffer(
            frame_samples=VAD_FRAME_SAMPLES,
        )

        self._task: asyncio.Task | None = None

    async def run(self):

        logger.info("Starting VAD Worker...")

        try:

            while True:

                chunk = await self.audio_queue.get()

                self.buffer.append(chunk)

                frames = self.buffer.pop_frames()

                for frame in frames:

                    probability = self.vad.predict(frame)
                    event = self.detector.update(probability)

                    if event is not None:

                        await self.conversation_queue.put(event)

        except asyncio.CancelledError:

            logger.info("VAD Worker stopped.")

            raise

    def start(self):

        if self._task is not None:
            raise RuntimeError(
                "VAD Worker already started."
            )

        self._task = asyncio.create_task(
            self.run()
        )

    async def stop(self):

        if self._task is None:
            return None

        self._task.cancel()

        try:
            await self._task

        except asyncio.CancelledError:
            pass

        self.buffer.clear()

        self._task = None

        logger.info("VAD Worker stopped.")