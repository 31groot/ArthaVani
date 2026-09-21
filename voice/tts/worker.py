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

        # EdgeTTS is responsible for converting text into speech
        # and returning PCM audio chunks.
        #
        # TTSWorker only coordinates when and how it is called.
        self.tts = tts

        # Queue containing complete sentences produced by
        # SentenceSplitter.
        
        self.sentence_queue = sentence_queue

        # Queue containing synthesized PCM audio chunks.
        #
        # Speaker consumes this queue.
        
        self.audio_queue = audio_queue

        # Main worker task.
        #
        # This runs run(), which continuously waits for
        # sentences to synthesize.
        self._task: asyncio.Task | None = None

        # Task for the sentence that is currently being synthesized.
        #
        # Keeping this separately allows interrupt() to cancel
        # the current TTS operation.
        self._synthesis_task: asyncio.Task | None = None

    async def run(self) -> None:

        logger.info(
            "Starting TTS Worker..."
        )

        try:

            # Continuously wait for sentences from SentenceSplitter.
            while True:

                # Wait until a complete sentence is available.
                sentence = await self.sentence_queue.get()

                # Remove leading/trailing whitespace.
                text = sentence.text.strip()

                # Ignore empty sentences.
                if not text:
                    continue

                logger.info(
                    "TTS sentence queued: %r",
                    text,
                )

                # Start synthesizing this sentence in a separate task.
                #
                # Keeping the current synthesis task separately means
                # interrupt() can cancel it later.
                self._synthesis_task = asyncio.create_task(
                    self._speak(text)
                )

                try:

                    # Wait for this sentence to finish before taking
                    # the next sentence from sentence_queue.
                    #
                    # This keeps speech sequential:
                    #
                    # Sentence 1
                    #     ↓
                    # finish
                    #     ↓
                    # Sentence 2
                    await self._synthesis_task

                except asyncio.CancelledError:

                    # Cancellation is expected when the user interrupts
                    # the assistant or the worker is stopped.
                    pass

                finally:

                    # The current synthesis task is no longer active.
                    self._synthesis_task = None

        except asyncio.CancelledError:

            logger.info(
                "TTS Worker cancelled."
            )

            # Re-raise cancellation so asyncio knows the worker
            # was intentionally stopped.
            raise

        except Exception:

            # Log unexpected failures.
            logger.exception(
                "TTS Worker crashed."
            )

            raise

    async def _speak(
        self,
        text: str,
    ) -> None:

        # Track information about the generated audio stream.
        first_chunk = True
        chunk_count = 0
        total_bytes = 0

        # EdgeTTS streams audio progressively.
        #
        # It does not wait for the entire sentence to finish
        # before giving us audio.
        async for audio_chunk in self.tts.stream(
            text
        ):

            # Log the moment the first usable audio arrives.
            #
            # This is useful for measuring TTS latency.
            if first_chunk:

                logger.info(
                    "TTS first audio chunk received."
                )

                first_chunk = False

            # Track statistics for debugging/monitoring.
            chunk_count += 1
            total_bytes += len(
                audio_chunk
            )

            # Send the PCM audio chunk to the Speaker pipeline.
            #
            # Speaker will eventually read this from audio_queue
            # and send it to the physical audio device.
            await self.audio_queue.put(
                audio_chunk
            )

        # TTS has finished generating the entire sentence.
        logger.info(
            "TTS audio stream queued: %d chunks / %d bytes.",
            chunk_count,
            total_bytes,
        )

    async def interrupt(self) -> None:

        # Remove all sentences that have not started being synthesized.
        #
        # Example:
        #
        # sentence_queue:
        #     Sentence 2
        #     Sentence 3
        #     Sentence 4
        #
        # After this:
        #
        #     sentence_queue = empty
        #
        # This prevents pending assistant speech from continuing
        # after the user interrupts.
        while True:

            try:

                self.sentence_queue.get_nowait()

            except asyncio.QueueEmpty:

                # Queue is empty, so there is nothing more to remove.
                break

        # Cancel the sentence that is currently being synthesized.
        #
        # This stops the Edge TTS streaming operation if it is
        # still running.
        if (
            self._synthesis_task is not None
            and not self._synthesis_task.done()
        ):

            self._synthesis_task.cancel()

    def start(self) -> None:

        # Prevent multiple copies of the TTS worker from running.
        if self._task is not None:

            raise RuntimeError(
                "TTS Worker already started."
            )

        # Start the main TTS worker loop in the background.
        self._task = asyncio.create_task(
            self.run()
        )

    async def stop(self) -> None:

        # Nothing to stop if the worker hasn't been started.
        if self._task is None:
            return

        # Cancel the main worker task.
        self._task.cancel()

        try:

            # Wait for the worker to finish shutting down.
            await self._task

        except asyncio.CancelledError:

            # Cancellation during shutdown is expected.
            pass

        # Clear the task reference so the worker can be started again.
        self._task = None

        logger.info(
            "TTS Worker stopped."
        )
