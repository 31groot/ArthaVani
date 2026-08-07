import asyncio

from config.logger import logger

from voice.llm.azure import AzureLLM
from voice.llm.events import TokenEvent
from voice.llm.prompt_builder import PromptBuilder
from voice.stt.events import TranscriptEvent


class LLMWorker:

    def __init__(
        self,
        llm: AzureLLM,
        transcript_queue: asyncio.Queue[TranscriptEvent],
        token_queue: asyncio.Queue[TokenEvent],
    ):

        self.llm = llm

        self.transcript_queue = transcript_queue
        self.token_queue = token_queue

        self._task: asyncio.Task | None = None

    async def run(self):

        logger.info("Starting LLM Worker...")

        try:

            while True:

                transcript = await self.transcript_queue.get()

                if not transcript.is_final:
                    continue

                if not transcript.text.strip():
                    continue

                logger.info(
                    f"User: {transcript.text}"
                )

                messages = PromptBuilder.build(
                    transcript.text
                )

                async for token in self.llm.stream(messages):

                    await self.token_queue.put(token)

        except asyncio.CancelledError:

            logger.info("LLM Worker cancelled.")

            raise

        except Exception:

            logger.exception("LLM Worker crashed.")

            raise

    def start(self):

        if self._task is not None:
            raise RuntimeError(
                "LLM Worker already started."
            )

        self._task = asyncio.create_task(
            self.run()
        )

    async def stop(self):

        if self._task is None:
            return

        self._task.cancel()

        try:

            await self._task

        except asyncio.CancelledError:
            pass

        self._task = None

        logger.info("LLM Worker stopped.")