import asyncio

import numpy as np
import sounddevice as sd

from config.constants import (
    APPLICATION_SAMPLE_RATE,
    CHANNELS,
    CHUNK_SIZE,
    MAX_QUEUE_SIZE,
    MIC_SAMPLE_RATE,
)
from config.logger import logger
from voice.audio.resampler import AudioResampler



class Microphone:

    def __init__(
        self,
        echo_canceller=None,
    ) -> None:

        self.stream: sd.InputStream | None = None

        self.echo_canceller = echo_canceller

        self.raw_audio_queue: asyncio.Queue[
            np.ndarray
        ] = asyncio.Queue(
            MAX_QUEUE_SIZE
        )

        self.audio_queue: asyncio.Queue[
            bytes
        ] = asyncio.Queue(
           MAX_QUEUE_SIZE
        )

        self.loop: asyncio.AbstractEventLoop | None = None

        self.resampler = AudioResampler(
            input_rate=MIC_SAMPLE_RATE,
            output_rate=APPLICATION_SAMPLE_RATE,
        )

        self._resample_task: asyncio.Task | None = None

        self._dropped_chunk_count = 0
        self._last_drop_log_time = 0.0

    def _audio_callback(
        self,
        indata,
        frames,
        time,
        status,
    ) -> None:

        if status:
            logger.warning(
                f"Microphone status: {status}"
            )

        if self.loop is None:
            return

        audio = indata.copy()

        self.loop.call_soon_threadsafe(
            self._enqueue_raw_audio,
            audio,
        )

    def _enqueue_raw_audio(
        self,
        audio: np.ndarray,
    ) -> None:

        try:

            self.raw_audio_queue.put_nowait(
                audio
            )

        except asyncio.QueueFull:

            self._dropped_chunk_count += 1

            # Only log once per second, no matter how many chunks
            # get dropped in that window, so a real backlog doesn't
            # flood the terminal.
            now = asyncio.get_event_loop().time()

            if now - self._last_drop_log_time >= 1.0:

                logger.warning(
                    f"Raw microphone queue full. Dropped "
                    f"{self._dropped_chunk_count} chunk(s) in the "
                    f"last second."
                )

                self._dropped_chunk_count = 0
                self._last_drop_log_time = now

    async def _resample_loop(self) -> None:

        logger.info(
            "Microphone resampler started."
        )

        try:

            while True:

                audio = (
                    await self.raw_audio_queue.get()
                )

                resampled = self.resampler.process(
                    audio
                )

                if resampled.size == 0:
                    continue

                if self.echo_canceller is not None:

                    loop = asyncio.get_running_loop()

                    resampled = await loop.run_in_executor(
                        None,
                        self.echo_canceller.process,
                        resampled,
                    )

                audio_bytes = (
                    resampled.tobytes()
                )

                await self.audio_queue.put(
                    audio_bytes
                )

        except asyncio.CancelledError:

            logger.info(
                "Microphone resampler stopped."
            )

            raise

    async def start(self) -> None:

        if self.stream is not None:
            raise RuntimeError(
                "Microphone already started."
            )

        logger.info(
            "Opening microphone..."
        )

        self.loop = (
            asyncio.get_running_loop()
        )

        self.stream = sd.InputStream(
            samplerate=MIC_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )

        self.stream.start()

        self._resample_task = (
            asyncio.create_task(
                self._resample_loop()
            )
        )

        logger.info(
            "Microphone started."
        )

    async def read(self) -> bytes:

        return await self.audio_queue.get()

    async def stop(self) -> None:

        if self.stream is None:
            return

        logger.info(
            "Stopping microphone..."
        )

        if self._resample_task is not None:

            self._resample_task.cancel()

            try:

                await self._resample_task

            except asyncio.CancelledError:
                pass

            self._resample_task = None

        self.stream.stop()
        self.stream.close()

        self.stream = None
        self.loop = None

        logger.info(
            "Microphone stopped."
        )