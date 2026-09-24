import asyncio

from config.logger import logger

from voice.stt.deepgram import DeepgramClient
from voice.stt.events import TranscriptEvent


class STTWorker:

    def __init__(
        self,
        deepgram: DeepgramClient,
        audio_queue: asyncio.Queue[bytes],
        transcript_queue: asyncio.Queue[TranscriptEvent],
        on_transcript=None,
    ):

        # DeepgramClient is responsible for the actual Deepgram
        # connection, sending audio, and receiving transcript events.
        #
        # STTWorker mainly coordinates the data flow between queues
        # and DeepgramClient.
        self.deepgram = deepgram

        # Queue containing processed microphone audio.
        
        self.audio_queue = audio_queue

        # Queue where transcript events are placed after they are
        # received from Deepgram.
 
        self.transcript_queue = transcript_queue

        # Optional callback invoked for every transcript event.
        # Browser voice uses this to render interim words without
        # changing the final transcript flow consumed by the LLM.
        self.on_transcript = on_transcript

        # Main worker task.
        #
        # This task runs run(), which starts both the send and receive
        # loops.
        self._task: asyncio.Task | None = None
        self._ready_event = asyncio.Event()
        self._startup_error: Exception | None = None

    async def _send_audio_loop(self) -> None:

        logger.info(
            "STT Send Loop started."
        )

        # Continuously wait for audio from the microphone queue.
        #
        # This loop is responsible for:
        #
        #     Microphone to audio_queue to Deepgram      
        while True:

            # Wait until another microphone audio chunk becomes available.
            #
            # No CPU is wasted while the queue is empty; asyncio simply
            # suspends this task until audio arrives.
            chunk = await self.audio_queue.get()

            # Give the audio to DeepgramClient.
            #
            # DeepgramClient.send_audio() handles its own buffering and
            # converts the incoming small chunks into approximately
            # 100 ms frames before sending them over the WebSocket.
            await self.deepgram.send_audio(
                chunk
            )

    async def _receive_loop(self) -> None:

        logger.info(
            "STT Receive Loop started."
        )

        # Continuously wait for transcript events coming back
        # from Deepgram.
        #
        # This loop is responsible for:
        #
        #     Deepgram to DeepgramClient to transcript_queue
        while True:

            # Wait for the next TranscriptEvent from DeepgramClient.
            event = await self.deepgram.receive()

            if self.on_transcript is not None:
                result = self.on_transcript(event)
                if asyncio.iscoroutine(result):
                    await result

            # Put the event into the queue consumed by LLMWorker.
            #
            # This keeps STT independent from the LLM layer.
            await self.transcript_queue.put(
                event
            )

    async def run(self) -> None:

        logger.info(
            "Starting STT Worker..."
        )

        # Connect to Deepgram before starting either loop.
        try:
            await self.deepgram.connect()
            self._startup_error = None
            self._ready_event.set()
        except Exception as exc:
            self._startup_error = exc
            self._ready_event.set()
            logger.exception("Deepgram connection failed during STT startup.")
            raise

        # Start the send and receive loops concurrently.
        #
        # They must run at the same time because:
        #
        #     send loop:
        #         microphone to Deepgram
        #
        #     receive loop:
        #         Deepgram to transcript
        #
        # Neither loop should block the other.
        send_task = asyncio.create_task(
            self._send_audio_loop()
        )

        receive_task = asyncio.create_task(
            self._receive_loop()
        )

        try:

            # Wait for either worker loop to finish with an exception.
            #
            # FIRST_EXCEPTION means that if one loop crashes,
            # we should stop the other loop as well.
            done, pending = await asyncio.wait(
                {
                    send_task,
                    receive_task,
                },
                return_when=asyncio.FIRST_EXCEPTION,
            )

            # If one loop failed, stop any loop that is still running.
            for task in pending:
                task.cancel()

            # Wait for cancelled tasks to actually finish.
            #
            # return_exceptions=True prevents a cancellation exception
            # from interrupting cleanup.
            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )

            # Check the tasks that finished.
            #
            # If one of them ended because of an actual exception,
            # re-raise it so the main STT worker also fails visibly.
            for task in done:

                exc = task.exception()

                if exc is not None:
                    raise exc

        finally:

            # Always close the Deepgram connection when the worker
            # stops, whether that happens because of:
            #
            #   - normal shutdown
            #   - cancellation
            #   - an exception
            #
            # This prevents the WebSocket/network resources from
            # being left open.
            await self.deepgram.close()

    async def wait_until_ready(self, timeout: float = 15.0) -> None:
        """Wait until the Deepgram connection is established or failed."""
        await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
        if self._startup_error is not None:
            raise RuntimeError("Deepgram STT could not start.") from self._startup_error
        if self.deepgram.connection is None:
            raise RuntimeError("Deepgram STT did not establish a connection.")

    def start(self) -> None:

        # Prevent accidentally starting two copies of the same worker.
        if self._task is not None:

            raise RuntimeError(
                "STT Worker already started."
            )

        self._ready_event.clear()
        self._startup_error = None

        # Start the main worker as a background asyncio task.
        #
        # run() will then:
        #
        #     1. connect to Deepgram
        #     2. start send loop
        #     3. start receive loop
        self._task = asyncio.create_task(
            self.run()
        )

    async def stop(self) -> None:

        # Nothing to stop if the worker was never started.
        if self._task is None:
            return

        # Cancel the main worker.
        #
        # run() will unwind and execute its finally block,
        # which closes the Deepgram connection.
        self._task.cancel()

        try:

            # Wait for the worker to finish its shutdown.
            await self._task

        except asyncio.CancelledError:

            # Cancellation during shutdown is expected.
            pass

        self._ready_event.clear()
        self._startup_error = None

        # Clear the task reference so the worker can be started again.
        self._task = None

        logger.info(
            "STT Worker stopped."
        )