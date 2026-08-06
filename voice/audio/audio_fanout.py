import asyncio
from config.logger import logger


class AudioFanout:

    def __init__(
        self,
        input_queue: asyncio.Queue[bytes],
        output_queues: list[asyncio.Queue[bytes]],
    ):
        self.input_queue = input_queue
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
        self._task = asyncio.create_task(self.run())

    async def stop(self):
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None