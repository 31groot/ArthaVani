import asyncio

from config.logger import logger


class AudioFanout:

    def __init__(
        self,
        input_queue: asyncio.Queue[bytes],
        output_queues: list[asyncio.Queue[bytes]],
    ):
        # Queue containing audio chunks coming from the microphone
        self.input_queue = input_queue

        # Queues belonging to the different consumers
        self.output_queues = output_queues

        self._task: asyncio.Task | None = None

    async def run(self):

        logger.info("Audio Fanout started.")

        try:
            while True:

                chunk = await self.input_queue.get()

                for queue in self.output_queues:
                    await queue.put(chunk)

        except asyncio.CancelledError:

            logger.info("Audio Fanout stopped.")
            raise

    def start(self):

        # Prevent starting the same worker more than once
        if self._task is not None:
            raise RuntimeError(
                "Audio Fanout already started."
            )

        self._task = asyncio.create_task(
            self.run()
        )

    async def stop(self):

        if self._task is None:
            return None

        self._task.cancel()

        try:
            # Wait for the task to actually finish
            await self._task

        except asyncio.CancelledError:
            # Cancellation is expected when stopping the worker
            pass

        self._task = None