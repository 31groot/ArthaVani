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
    ):

        self.deepgram = deepgram

        self.audio_queue = audio_queue

        self.transcript_queue = transcript_queue

        self._task: asyncio.Task | None = None

    async def _send_audio_loop(self) -> None:

        logger.info("STT Send Loop started.")

        # Continuously take audio from the queue and send it to Deepgram
        while True:

            # Wait until the next audio chunk is available
            chunk = await self.audio_queue.get()
            await self.deepgram.send_audio(
                chunk
            )

    async def _receive_loop(self) -> None:

        logger.info("STT Receive Loop started.")

        # Continuously wait for transcripts from Deepgram
        while True:

            event = await self.deepgram.receive()

            await self.transcript_queue.put(
                event
            )

    async def run(self) -> None:

        logger.info("Starting STT Worker...")

        # Establish the Deepgram connection before starting the loops
        await self.deepgram.connect()

        # Run sending and receiving concurrently
        send_task = asyncio.create_task(
            self._send_audio_loop()
        )
        receive_task = asyncio.create_task(
            self._receive_loop()
        )

        try:
            # Keep both loops running until one of them raises an exception
            done, pending = await asyncio.wait(
                {send_task, receive_task},
                return_when=asyncio.FIRST_EXCEPTION,
            )
            # Stop the other loop if one loop fails
            for task in pending:
                task.cancel()

            # Wait for the cancelled tasks to finish
            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )

            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc

        finally:

            # close Deepgram when the worker stops or fails
            await self.deepgram.close()

    def start(self) -> None:

        if self._task is not None:

            raise RuntimeError(
                "STT Worker already started."
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

        logger.info(
            "STT Worker stopped."
        )