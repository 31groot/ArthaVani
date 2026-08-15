import asyncio

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

        self.buffer = AudioBuffer()

        self._task: asyncio.Task | None = None

    async def run(self):

        logger.info("Starting VAD Worker...")

        try:

            while True:

                chunk = await self.audio_queue.get()

                self.buffer.append(chunk)

                frames = self.buffer.pop_frames()

                for frame in frames:

                    probability = await self.vad.is_speech(frame)
                    # debug 
                    logger.info(f"VAD prob: {probability:.3f}")


                    event = self.detector.update(probability)

                    if event is not None:
                        await self.conversation_queue.put(event)

        except asyncio.CancelledError:

            logger.info("VAD Worker stopped.")
            raise

        except Exception:

            logger.exception("VAD Worker crashed.")
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

        # Request cancellation of the background task
        self._task.cancel()

        try:
            # Wait until the worker has actually stopped
            await self._task

        except asyncio.CancelledError:
            # Cancellation was expected, so ignore it here
            pass

        # Remove any audio left in the buffer
        self.buffer.clear()

        # Mark the worker as stopped
        self._task = None

        logger.info("VAD Worker stopped.")

