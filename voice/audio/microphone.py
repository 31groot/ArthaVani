import asyncio

import numpy as np
import sounddevice as sd

from config.constants import (
    APPLICATION_SAMPLE_RATE,
    CHANNELS,
    CHUNK_SIZE,
    MAX_QUEUE_SIZE,
    MIC_SAMPLE_RATE,
    MIC_INPUT_GAIN,
)
from config.logger import logger
from config.settings import settings
from voice.audio.resampler import AudioResampler


class Microphone:

    def __init__(
        self,
        echo_canceller=None,
    ) -> None:

        # Holds the SoundDevice microphone stream.
        self.stream: sd.InputStream | None = None

        # WebRTC echo canceller.
        self.echo_canceller = echo_canceller

        # Queue for raw microphone chunks coming directly from SoundDevice.

        self.raw_audio_queue: asyncio.Queue[np.ndarray] = asyncio.Queue(
            MAX_QUEUE_SIZE
        )

        # Queue containing audio that has already been resampled,
        # gain-adjusted, optionally echo-cancelled, and converted to bytes.
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(
            MAX_QUEUE_SIZE
        )

        # Reference to the asyncio event loop.
        #
        # SoundDevice's callback can run outside the asyncio thread,
        # so we store the event loop and later use call_soon_threadsafe()
        # to safely send microphone data into the asyncio side.
        self.loop: asyncio.AbstractEventLoop | None = None

        # Converts microphone audio from MIC_SAMPLE_RATE
        # to the sample rate used by the rest of the application.
        self.resampler = AudioResampler(
            input_rate=MIC_SAMPLE_RATE,
            output_rate=APPLICATION_SAMPLE_RATE,
        )

        # Background asyncio task responsible for processing the raw
        # microphone audio.
        self._resample_task: asyncio.Task | None = None

        # Number of microphone chunks dropped because the raw queue
        # became full.
        self._dropped_chunk_count = 0

        # Used to prevent excessive "queue full" log messages.
        # We only log dropped chunks approximately once per second.
        self._last_drop_log_time = 0.0

    def _audio_callback(
        self,
        indata,
        frames,
        time,
        status,
    ) -> None:

        # SoundDevice reports microphone/device problems through "status".
        # Log them, but don't immediately stop the microphone.
        if status:
            logger.warning(
                f"Microphone status: {status}"
            )

        # If the asyncio loop isn't available, there is nowhere safe
        # to send the microphone audio.
        if self.loop is None:
            return

        # SoundDevice owns the original input buffer.
        # Make a copy so the data remains valid after this callback returns.
        audio = indata.copy()

        # The SoundDevice callback may run outside the asyncio thread.

        self.loop.call_soon_threadsafe(
            self._enqueue_raw_audio,
            audio,
        )

    def _enqueue_raw_audio(
        self,
        audio: np.ndarray,
    ) -> None:

        try:

            # put_nowait() is used because the callback pipeline should
            # never block waiting for space in the queue.
            self.raw_audio_queue.put_nowait(
                audio
            )

        except asyncio.QueueFull:

            # If the queue is full, this audio chunk is dropped.

            self._dropped_chunk_count += 1

            # Only log once per second, no matter how many chunks
            # get dropped in that window, 
            now = asyncio.get_event_loop().time()

            if now - self._last_drop_log_time >= 1.0:

                logger.warning(
                    f"Raw microphone queue full. Dropped "
                    f"{self._dropped_chunk_count} chunk(s) in the last second. "
                )

                # Reset the counter after reporting the drops.
                self._dropped_chunk_count = 0

                # Remember when the last warning was logged.
                self._last_drop_log_time = now

    async def _resample_loop(self) -> None:

        logger.info(
            "Microphone resampler started."
        )

        try:

            # This task runs continuously in the background.
            
            while True:

                # Wait until a microphone chunk is available.

                audio = (
                    await self.raw_audio_queue.get()
                )

                # Convert the microphone sample rate to the application's
                # required sample rate.
                resampled = self.resampler.process(
                    audio
                )

                # Resampling may occasionally produce no output.
                # In that case, simply wait for the next chunk.
                if resampled.size == 0:
                    continue

                # Convert to float32 before applying gain.
                #
                # Using float32 makes it safer to perform multiplication
                # without integer overflow.
                #
                # MIC_INPUT_GAIN:
                #   1.0 -> unchanged
                #   >1.0 -> amplify
                #   <1.0 -> reduce volume
                scaled = (
                    resampled.astype(np.float32)
                    * MIC_INPUT_GAIN
                )

                # Convert the processed audio back to int16 PCM.
                #
                # np.round():
                #   Converts floating-point values to whole-number samples.
                #
                # np.clip():
                #   Prevents values from exceeding the int16 range:
                #   -32768 to 32767
                #
                # astype(np.int16):
                #   Converts the final samples into 16-bit PCM audio.
                resampled = (
                    np.clip(
                        np.round(scaled),
                        -32768,
                        32767,
                    )
                    .astype(np.int16)
                )

                # Only run echo cancellation while the assistant is
                # actually playing audio.
                #
                # If the speakers are silent, there is no speaker echo
                # that needs to be removed.
                if (
                    self.echo_canceller is not None
                    and self.echo_canceller.is_playback_active()
                ):

                    # Get the currently running asyncio event loop.
                    loop = asyncio.get_running_loop()

                    try:

                        # The echo canceller may be implemented as
                        # blocking/native code.
                        #
                        # run_in_executor() moves that work to a thread
                        # so that the asyncio event loop remains responsive.
                        #
                        # wait_for(..., timeout=0.15) means:
                        # "Don't wait more than 150 ms for AEC."
                        resampled = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                self.echo_canceller.process,
                                resampled,
                            ),
                            timeout=0.15,
                        )

                    except asyncio.TimeoutError:

                        # If AEC is too slow, don't block the microphone.
                        #
                        # resampled still contains the microphone audio
                        # processed before AEC, so we simply continue
                        # with that audio.
                        logger.warning(
                            "WebRTC AEC timed out; passing microphone audio through."
                        )

                # Convert the NumPy int16 array into raw bytes.
                #
                # This is the format expected by the next stage of the
                # audio pipeline, such as speech recognition/Deepgram.
                audio_bytes = resampled.tobytes()

                # Put the processed audio into the output queue.
                #
                # read() later retrieves audio from this queue.
                await self.audio_queue.put(
                    audio_bytes
                )

        except asyncio.CancelledError:

            # Cancellation is expected when stop() shuts down
            # the microphone.
            logger.info(
                "Microphone resampler stopped."
            )

            # Re-raise CancelledError so asyncio knows the task
            # was properly cancelled.
            raise

        except Exception:

            # Unexpected processing errors are logged with traceback.
            logger.exception(
                "Microphone resampler crashed."
            )

            # Re-raise so the task is considered failed rather than
            # silently continuing in a broken state.
            raise

    async def start(self) -> None:

        # Prevent starting the same microphone twice.
        if self.stream is not None:
            raise RuntimeError(
                "Microphone already started."
            )

        logger.info(
            "Opening microphone..."
        )

        # Save the current asyncio event loop.
        #
        # _audio_callback() runs separately from normal asyncio code,
        # so it uses this loop to safely enqueue audio.
        self.loop = (
            asyncio.get_running_loop()
        )

        # Create the SoundDevice input stream.
        self.stream = sd.InputStream(
            # Number of samples captured per second.
            samplerate=MIC_SAMPLE_RATE,

            # Number of audio channels.
            # Usually 1 for microphone speech.
            channels=CHANNELS,

            # Capture samples as signed 16-bit PCM.
            dtype="int16",

            # Number of samples passed to the callback per chunk.
            blocksize=CHUNK_SIZE,

            # Function called by SoundDevice whenever a new
            # microphone chunk is available.
            callback=self._audio_callback,
        )

        # Start actual microphone capture.
        self.stream.start()

        # Start the background task that processes the raw audio.
        self._resample_task = (
            asyncio.create_task(
                self._resample_loop()
            )
        )

        logger.info(
            "Microphone started."
        )

    async def read(self) -> bytes:

        # Wait for and return the next fully processed audio chunk.
        
        return await self.audio_queue.get()

    async def stop(self) -> None:

        # If the microphone isn't running, there is nothing to stop.
        if self.stream is None:
            return

        logger.info(
            "Stopping microphone..."
        )

        # Stop the background processing task first.
        if self._resample_task is not None:

            # Request cancellation of _resample_loop().
            self._resample_task.cancel()

            try:

                # Wait for the task to actually finish cancellation.
                await self._resample_task

            except asyncio.CancelledError:
                # Cancellation here is expected, so ignore it.
                pass

            # Clear the task reference after shutdown.
            self._resample_task = None

        # Stop microphone capture.
        self.stream.stop()

        # Release the underlying audio device resources.
        self.stream.close()

        # Reset state so the microphone can be started again later.
        self.stream = None
        self.loop = None

        logger.info(
            "Microphone stopped."
        )
