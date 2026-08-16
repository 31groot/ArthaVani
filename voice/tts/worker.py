import asyncio

from config.logger import logger
from voice.text.events import SentenceEvent
from voice.tts.elevenlabs import ElevenLabsTTS

class TTSWorker:

    def __init__(
        self,
        tts: ElevenLabsTTS,
        sentence_queue: asyncio.Queue[SentenceEvent],
        audio_queue: asyncio.Queue[bytes],
    ):

        self.tts = tts

        self.sentence_queue = sentence_queue
        self.audio_queue = audio_queue

        self._task: asyncio.Task | None = None
        self._synthesis_task: asyncio.Task | None = None

    async def run(self) -> None:

        logger.info("Starting TTS Worker...")

        try:

            while True:

                sentence = await self.sentence_queue.get()

                text = sentence.text.strip()

                if not text:
                    continue

                logger.info(
                    f"TTS sentence: {text}"
                )

                self._synthesis_task = asyncio.create_task(
                    self._speak(text)
                )

                try:
                    await self._synthesis_task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._synthesis_task = None

        except asyncio.CancelledError:

            logger.info("TTS Worker cancelled.")

            raise

        except Exception:

            logger.exception(
                "TTS Worker crashed."
            )

            raise

    async def _speak(self, text: str) -> None:

        async for audio_chunk in self.tts.stream(text):

            await self.audio_queue.put(
                audio_chunk
            )


    async def interrupt(self) -> None:

        # Drop any sentences still waiting to be spoken.
        while True:
            try:
                self.sentence_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Stop whatever's currently being synthesized/played.
        if (
            self._synthesis_task is not None
            and not self._synthesis_task.done()
        ):
            self._synthesis_task.cancel()

    def start(self) -> None:

        if self._task is not None:
            raise RuntimeError(
                "TTS Worker already started."
            )

        self._task = asyncio.create_task(
            self.run()
        )

    async def stop(self) -> None:

        if self._task is None:
            return

        self._task.cancel()

        try:

            await self._task

        except asyncio.CancelledError:
            pass

        self._task = None

        logger.info("TTS Worker stopped.")