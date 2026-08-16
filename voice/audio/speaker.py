import asyncio
import queue
import threading

import numpy as np
import sounddevice as sd

from config.constants import (
    CHANNELS,
    CHUNK_SIZE,
    MAX_QUEUE_SIZE,
    SAMPLE_RATE,
)
from config.logger import logger


class Speaker:

    def __init__(
        self,
        audio_queue: asyncio.Queue[bytes],
        echo_canceller=None,
    ):
        self.audio_queue = audio_queue

        self.echo_canceller = echo_canceller

        self.stream: sd.OutputStream | None = None

        self._playback_queue: queue.Queue[bytes] = queue.Queue(
            maxsize=MAX_QUEUE_SIZE
        )
        self._buffer = bytearray()

        self._buffer_lock = threading.Lock()

        self._task: asyncio.Task | None = None

    async def start(self) -> None:

        if self.stream is not None:
            raise RuntimeError("Speaker already started.")

        logger.info("Opening speaker...")

        self.stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )

        self.stream.start()

        self._task = asyncio.create_task(
            self._audio_bridge()
        )

        logger.info("Speaker started.")

    async def _audio_bridge(self) -> None:

        try:

            while True:

                audio = await self.audio_queue.get()

                loop = asyncio.get_running_loop()

                await loop.run_in_executor(
                    None,
                    self._playback_queue.put,
                    audio,
                )

        except asyncio.CancelledError:

            raise

    def _audio_callback(
        self,
        outdata,
        frames,
        time,
        status,
    ) -> None:

        if status and not status.output_underflow:
            logger.warning(
                f"Speaker callback status: {status}"
            )

        bytes_per_sample = np.dtype(
            np.int16
        ).itemsize

        required_bytes = (
            frames
            * CHANNELS
            * bytes_per_sample
        )

        with self._buffer_lock:

            while len(self._buffer) < required_bytes:

                try:

                    audio = self._playback_queue.get_nowait()

                except queue.Empty:

                    break

                self._buffer.extend(audio)

            if len(self._buffer) >= required_bytes:

                chunk = self._buffer[:required_bytes]

                del self._buffer[:required_bytes]

                audio_array = np.frombuffer(
                    chunk,
                    dtype=np.int16,
                )

                audio_array = audio_array.reshape(
                    frames,
                    CHANNELS,
                )

                outdata[:] = audio_array

                if self.echo_canceller is not None:
                    self.echo_canceller.push_reference(
                        audio_array.reshape(-1)
                    )

                return

            outdata.fill(0)

            if not self._buffer:
                return

            available_bytes = len(self._buffer)

            available_samples = (
                available_bytes
                // bytes_per_sample
            )

            available_frames = (
                available_samples
                // CHANNELS
            )

            if available_frames <= 0:
                return

            chunk_bytes = (
                available_frames
                * CHANNELS
                * bytes_per_sample
            )

            chunk = self._buffer[:chunk_bytes]

            del self._buffer[:chunk_bytes]

            audio_array = np.frombuffer(
                chunk,
                dtype=np.int16,
            )

            audio_array = audio_array.reshape(
                available_frames,
                CHANNELS,
            )

            outdata[:available_frames] = audio_array

            if self.echo_canceller is not None:
                self.echo_canceller.push_reference(
                    audio_array.reshape(-1)
                )

    async def clear(self) -> None:

        with self._buffer_lock:
            self._buffer.clear()

        while True:

            try:

                self._playback_queue.get_nowait()

            except queue.Empty:

                break

        while True:

            try:

                self.audio_queue.get_nowait()

            except asyncio.QueueEmpty:

                break

    async def stop(self) -> None:

        if self.stream is None:
            return

        logger.info("Stopping speaker...")

        if self._task is not None:

            self._task.cancel()

            try:

                await self._task

            except asyncio.CancelledError:

                pass

            self._task = None

        self.stream.stop()
        self.stream.close()

        self.stream = None

        with self._buffer_lock:
            self._buffer.clear()

        while True:

            try:

                self._playback_queue.get_nowait()

            except queue.Empty:

                break

        logger.info("Speaker stopped.")