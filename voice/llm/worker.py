import asyncio

from config.logger import logger

from finance_agent.runner import FinanceAgentRunner
from voice.memory.history import ConversationHistory
from voice.stt.events import TranscriptEvent
from voice.text.text_splitter import SentenceSplitter


class LLMWorker:

    def __init__(
        self,
        splitter: SentenceSplitter,
        transcript_queue: asyncio.Queue[TranscriptEvent],
    ):

        # Converts streamed LLM text into sentence-sized pieces
        # that can be sent to the TTS pipeline incrementally.
        #
        # Example:
        #
        # LLM stream:
        # "Your current balance is ₹20,000."
        #
        # Splitter may emit:
        # "Your current balance is ₹20,000."
        #
        # This allows TTS to start speaking before the full LLM
        # response is necessarily finished.
        self.splitter = splitter

        # Queue containing transcript events produced by the
        # speech-to-text system.
        self.transcript_queue = transcript_queue

        # Stores the conversation so the finance agent can see
        # previous user and assistant messages.
        self.history = ConversationHistory()

        # FinanceAgentRunner is responsible for actually calling
        # the LLM and available finance tools.
        self.agent_runner = FinanceAgentRunner()

        # Main long-running task that listens for transcripts.
        self._task: asyncio.Task | None = None

        # Task for the currently running LLM generation.
        self._generation_task: asyncio.Task | None = None

    async def run(self) -> None:
        try:
            logger.info("Starting LLM Worker...")

            # Start the finance agent and its MCP connection
            # inside this long-lived worker task.
            await self.agent_runner.start()

            while True:
                event = await self.transcript_queue.get()

                if not event.is_final:
                    continue

                text = event.text.strip()

                if not text:
                    continue

                self.history.add_user(text)

                logger.info(
                    "User: %s",
                    text,
                )

                # Cancel/replace old generation if needed.
                if (
                    self._generation_task is not None
                    and not self._generation_task.done()
                ):
                    self._generation_task.cancel()

                    try:
                        await self._generation_task
                    except asyncio.CancelledError:
                        pass

                self._generation_task = asyncio.create_task(
                    self._generate()
                )

        except asyncio.CancelledError:
            logger.info("LLM Worker cancelled.")
            raise

        finally:
            # First stop any active generation.
            if (
                self._generation_task is not None
                and not self._generation_task.done()
            ):
                self._generation_task.cancel()

                try:
                    await self._generation_task
                except asyncio.CancelledError:
                    pass

            # IMPORTANT:
            #
            # Close the FinanceAgentRunner/MCP connection
            # from this SAME worker task that started it.
            await self.agent_runner.stop()

    async def _generate(self) -> None:

        # Store every streamed LLM chunk so we can reconstruct
        # the complete assistant response at the end.
        assistant_response: list[str] = []

        try:

            logger.info(
                "Finance agent generating response..."
            )

            # Stream the response from the finance agent.
            #
            # Instead of waiting for the entire answer, the agent
            # yields text chunks as they are generated.
            async for text_chunk in self.agent_runner.astream_text(
                self.history.messages()
            ):

                # Keep the chunk so the full response can be rebuilt later.
                assistant_response.append(
                    text_chunk
                )

                # Immediately send the chunk into the sentence splitter.
                #
                # This allows downstream TTS to begin speaking while
                # the LLM is still generating the remaining response.
                await self.splitter.feed(
                    text_chunk
                )

            # The LLM stream has ended.
            #
            # Flush any text still waiting inside the sentence splitter.
            await self.splitter.flush()

        except asyncio.CancelledError:

            # Allow cancellation to propagate normally.
            raise

        except Exception:

            # _generate() is launched with asyncio.create_task(),
            # so it runs as a background task.
            #
            # Log errors explicitly so failures such as:
            #
            # - invalid API credentials
            # - unavailable model
            # - MCP server failure
            # - network errors
            #
            # do not disappear silently.
            logger.exception(
                "Finance agent generation failed; no response will "
                "be spoken for this turn."
            )

            return

        # Join all streamed chunks into one complete assistant response.
        assistant_text = (
            "".join(
                assistant_response
            ).strip()
        )

        # Protect against an empty model response.
        if not assistant_text:

            logger.warning(
                "Finance agent returned an empty response."
            )

            return

        logger.info(
            "LLM generation finished: %d chars.",
            len(assistant_text),
        )

        # Store the complete assistant response in conversation history
        # so future questions have access to the context.
        self.history.add_assistant(
            assistant_text
        )

    def start(self) -> None:

        # Prevent starting multiple copies of the main worker.
        if self._task is not None:

            raise RuntimeError(
                "LLM Worker already started."
            )

        # Start the long-running transcript listener.
        self._task = asyncio.create_task(
            self.run()
        )

    async def interrupt(self) -> None:

        # Interrupt the currently running finance-agent generation.
        #
        # This is used by barge-in when the user starts speaking
        # while the assistant is still generating a response.
        if (
            self._generation_task is not None
            and not self._generation_task.done()
        ):

            logger.info(
                "Barge-in: cancelling active LLM generation."
            )

            self._generation_task.cancel()

            try:

                await self._generation_task

            except asyncio.CancelledError:

                # Cancellation is expected here.
                pass

        self._generation_task = None

        # Discard any incomplete sentence that the LLM had streamed
        # but which has not yet been sent to TTS.
        self.splitter.clear()

    async def stop(self) -> None:

        # Nothing to stop if the worker has not been started.
        if self._task is None:
            return

        # Request cancellation of the main worker.
        #
        # run() will then also cancel and wait for any active
        # generation task.
        self._task.cancel()

        try:

            # Wait for the worker to finish shutting down.
            await self._task

        except asyncio.CancelledError:

            # Cancellation here is expected.
            pass

        # Remove the task reference so the worker can be started again.
        self._task = None

        logger.info(
            "LLM Worker stopped."
        )