import asyncio

from config.logger import logger

from voice.llm.azure import AzureLLM
from voice.llm.prompt_builder import PromptBuilder
from voice.memory.history import ConversationHistory
from voice.stt.events import TranscriptEvent
from voice.text.text_splitter import SentenceSplitter


class LLMWorker:

    def __init__(
        self,
        llm: AzureLLM,
        splitter: SentenceSplitter,
        transcript_queue: asyncio.Queue[TranscriptEvent],
        on_new_turn=None,
    ):

        self.llm = llm
        self.splitter = splitter
        self.transcript_queue = transcript_queue
        self.on_new_turn = on_new_turn

        self.history = ConversationHistory()

        self._task: asyncio.Task | None = None
        self._generation_task: asyncio.Task | None = None

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

                # A new final transcript means the user has started a
                # new turn. If we're still generating/speaking a
                # previous response, cancel it and clear whatever's
                # queued downstream instead of piling this turn up
                # behind it.
                if (
                    self._generation_task is not None
                    and not self._generation_task.done()
                ):

                    logger.info(
                        "New input received, cancelling in-progress "
                        "response."
                    )

                    await self.interrupt()

                    if self.on_new_turn is not None:
                        await self.on_new_turn()

                logger.info(f"User: {text}")

                self.history.add_user(text)

                self._generation_task = asyncio.create_task(
                    self._generate()
                )

        except asyncio.CancelledError:

            if (
                self._generation_task is not None
                and not self._generation_task.done()
            ):
                self._generation_task.cancel()

            logger.info("LLM Worker cancelled.")

            raise

        except Exception:

            logger.exception("LLM Worker crashed.")

            raise

    async def _generate(self) -> None:

        messages = PromptBuilder.build(
            self.history.messages()
        )

        assistant_response: list[str] = []

        try:

            async for token in self.llm.stream(messages):

                assistant_response.append(token.text)

                await self.splitter.feed(
                    token.text
                )

            await self.splitter.flush()

        except asyncio.CancelledError:
            raise

        assistant_text = "".join(
            assistant_response
        ).strip()

        if not assistant_text:
            logger.warning(
                "Azure GPT returned an empty response."
            )

        if assistant_text:

            self.history.add_assistant(
                assistant_text
            )

    async def interrupt(self) -> None:

        # Cancel any in-flight generation and clear the sentence
        # splitter's buffer. Used both when a new final transcript
        # arrives and when VAD detects the user has started
        # speaking again (barge-in).
        if (
            self._generation_task is not None
            and not self._generation_task.done()
        ):

            self._generation_task.cancel()

            try:
                await self._generation_task
            except asyncio.CancelledError:
                pass

            self.splitter.clear()

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