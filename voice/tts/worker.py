import asyncio

from config.logger import logger
from voice.text.events import SentenceEvent
from voice.tts.edge import EdgeTTS


class TTSWorker:

    def __init__(
        self,
        tts: EdgeTTS,
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

                logger.info("TTS sentence queued: %r", text)

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

    async def _speak(
        self,
        text: str,
    ) -> None:

        first_chunk = True
        chunk_count = 0
        total_bytes = 0

        async for audio_chunk in self.tts.stream(text):

            if first_chunk:
                logger.info("TTS first audio chunk received.")
                first_chunk = False

            chunk_count += 1
            total_bytes += len(audio_chunk)

            await self.audio_queue.put(
                audio_chunk
            )

        logger.info(
            "TTS audio stream queued: %d chunks / %d bytes.",
            chunk_count,
            total_bytes,
        )

    async def interrupt(self) -> None:

        # Remove sentences waiting to be synthesized.
        while True:

            try:
                self.sentence_queue.get_nowait()

            except asyncio.QueueEmpty:
                break

        # Cancel current synthesis.
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