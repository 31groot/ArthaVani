import asyncio
from collections.abc import Awaitable, Callable

from config.logger import logger

from finance_agent.conversation import ConversationIdentity
from finance_agent.errors import LLMProviderError, LLMRateLimitError
from finance_agent.runner import FinanceAgentRunner
from finance_agent.user_context import user_scope
from voice.stt.events import TranscriptEvent
from voice.text.text_splitter import SentenceSplitter


class LLMWorker:

    def __init__(
        self,
        splitter: SentenceSplitter,
        transcript_queue: asyncio.Queue[TranscriptEvent],
        conversation_identity: ConversationIdentity,
        on_user_text: Callable[[str], Awaitable[None] | None] | None = None,
        on_assistant_text: Callable[[str], Awaitable[None] | None] | None = None,
        agent_runner: FinanceAgentRunner | None = None,
    ):
        # Identifies this voice session's conversation to the
        # AsyncPostgresSaver checkpointer, so every turn is appended to
        # the same persisted thread instead of starting a fresh one.
        # Pass an explicit thread_id (e.g. a logged-in user's session id)
        # to resume a specific prior conversation; otherwise the configured
        # CONVERSATION_THREAD_ID is used.

        self.conversation_identity = conversation_identity

        # Optional transport callbacks used by the browser voice session.
        # The desktop pipeline leaves these as None.
        self.on_user_text = on_user_text
        self.on_assistant_text = on_assistant_text

        # Use the injected runner if given; otherwise create and own one.
        self._owns_runner = agent_runner is None
        self.agent_runner = agent_runner or FinanceAgentRunner()

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

        # Main long-running task that listens for transcripts.
        self._task: asyncio.Task | None = None

        # Task for the currently running LLM generation.
        self._generation_task: asyncio.Task | None = None

    async def run(self) -> None:
        try:
            logger.info("Starting LLM Worker...")

            while True:
                event = await self.transcript_queue.get()

                if not event.is_final:
                    continue

                text = event.text.strip()

                if not text:
                    continue

                # Kept for local logging/inspection only. The actual
                # conversation context the agent sees now comes from
                # AsyncPostgresSaver, keyed by self.thread_id -- we no
                # longer need to replay the full history on every turn.
                logger.info(
                    "User: %s",
                    text,
                )

                if self.on_user_text is not None:
                    result = self.on_user_text(text)
                    if asyncio.iscoroutine(result):
                        await result

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
                    self._generate(text)
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
            
            # Close the FinanceAgentRunner/checkpointer connection
            # from this SAME worker task that started it.
            if self._owns_runner:
                await self.agent_runner.stop()


    async def _generate(self, user_text: str) -> None:

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
            #
            # Only the new user message is sent -- AsyncPostgresSaver
            # loads the rest of this thread_id's conversation from
            # Postgres automatically inside the graph.
            # Finance tools resolve the authenticated user through a ContextVar.
            # HTTP chat already sets this scope; browser voice must do it too.
            with user_scope(self.conversation_identity.user_id):
                async for text_chunk in self.agent_runner.astream_text(
                    user_text,
                    thread_id=self.conversation_identity.thread_id,
                ):

                    # Keep the chunk so the full response can be rebuilt later.
                    assistant_response.append(
                        text_chunk
                    )

                    # Immediately send the chunk into the sentence splitter.
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
            raise

        except LLMRateLimitError as exc:
            # Distinct from the generic provider-failure branch below: this
            # is a known, transient cause (the provider's usage/rate limit),
            # already retried with backoff in the graph, so tell the user
            # something accurate instead of a generic "trouble reaching" line.
            logger.error("LLM rate limit exhausted: %s", exc)

            try:
                await self.splitter.feed(
                    "The finance assistant is a bit busy right now. "
                    "Please try again in a moment."
                )
                await self.splitter.flush()
            except Exception:
                logger.exception(
                    "Failed to speak the LLM rate-limit error message."
                )

            return

        except LLMProviderError as exc:
            logger.error("LLM provider failure: %s", exc)

            try:
                await self.splitter.feed(
                    "I'm having trouble reaching the finance assistant right now."
                )
                await self.splitter.flush()
            except Exception:
                logger.exception(
                    "Failed to speak the LLM provider error message."
                )

            return

        except Exception:
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

        if self.on_assistant_text is not None:
            result = self.on_assistant_text(assistant_text)
            if asyncio.iscoroutine(result):
                await result


    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("LLM Worker already started.")

        # Initialize the agent before creating the background task so that
        # PostgreSQL/Groq startup failures reach VoicePipeline.start().
        await self.agent_runner.start()

        self._task = asyncio.create_task(self.run())

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