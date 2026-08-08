import asyncio

from config.logger import logger

from voice.llm.azure import AzureLLM
from voice.llm.prompt_builder import PromptBuilder
from voice.memory.history import ConversationHistory
from voice.stt.events import TranscriptEvent
from voice.text.splitter import SentenceSplitter


class LLMWorker:

    def __init__(
        self,
        llm: AzureLLM,
        splitter: SentenceSplitter,
        transcript_queue: asyncio.Queue[TranscriptEvent],
    ):

        self.llm = llm
        self.splitter = splitter
        self.transcript_queue = transcript_queue

        self.history = ConversationHistory()

        self._task: asyncio.Task | None = None

    async def run(self) -> None:

        logger.info("Starting LLM Worker...")

        try:

            while True:

                transcript = await self.transcript_queue.get()

                if not transcript.is_final:
                    continue

                text = transcript.text.strip()

                if not text:
                    continue

                logger.info(f"User: {text}")

                self.history.add_user(text)

                messages = PromptBuilder.build(
                    self.history.messages()
                )

                assistant_response: list[str] = []

                async for token in self.llm.stream(messages):

                    assistant_response.append(token.text)

                    await self.splitter.feed(
                        token.text
                    )

                await self.splitter.flush()

                assistant_text = "".join(
                    assistant_response
                ).strip()

                if assistant_text:

                    self.history.add_assistant(
                        assistant_text
                    )

        except asyncio.CancelledError:

            logger.info("LLM Worker cancelled.")

            raise

        except Exception:

            logger.exception("LLM Worker crashed.")

            raise

    def start(self) -> None:

        if self._task is not None:
            raise RuntimeError(
                "LLM Worker already started."
            )

        self._task = asyncio.create_task(
            self.run()
        )

    async def stop(self) -> None:

        if self._task is None:
            return None

        self._task.cancel()

        try:

            await self._task

        except asyncio.CancelledError:
            pass

        self._task = None

        logger.info("LLM Worker stopped.")