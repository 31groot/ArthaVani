import asyncio
import queue
import threading

import numpy as np
import sounddevice as sd

from config.constants import (
    CHANNELS,
    CHUNK_SIZE,
    DROPPED_VOL,
    INITIAL_VOL,
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
        # This is the asyncio queue where the TTS layer
        # places audio that needs to be played.
        self.audio_queue = audio_queue

        # Echo canceller.
        #
        # The Speaker tells the echo canceller when audio is being played
        # and provides the speaker audio as a reference signal.
        self.echo_canceller = echo_canceller

        # SoundDevice output stream.
        #
        # None means the speaker is not currently running.
        self.stream: sd.OutputStream | None = None

        # Thread-safe queue used between the asyncio world and the
        # SoundDevice callback world.
        #
        # _audio_bridge() takes audio from audio_queue and puts it here.
        self._playback_queue: queue.Queue[bytes] = queue.Queue(
            maxsize=MAX_QUEUE_SIZE
        )

        # Byte buffer containing audio that has not yet been sent
        # to the speaker.
        #
        # This is needed because the amount of audio received from TTS
        # does not necessarily match the exact number of bytes that
        # SoundDevice requests in each callback.
        self._buffer = bytearray()

        # Protects _buffer from simultaneous access by different
        # threads/functions such as _audio_callback() and clear().
        self._buffer_lock = threading.Lock()

        # Current playback volume level.
        self._volume = INITIAL_VOL

        # Used to track whether real, non-silent audio is currently
        # being played.
        self._playback_active = False

        # Prevents logging "playback started" on every callback.
        self._logged_playback_start = False

        # Background asyncio task that transfers audio from the
        # asyncio queue to the thread-safe playback queue.
        self._task: asyncio.Task | None = None

    async def start(self) -> None:

        # Prevent accidentally starting the same speaker twice.
        if self.stream is not None:
            raise RuntimeError("Speaker already started.")

        logger.info("Opening speaker...")

        # Create the SoundDevice output stream.
        #
        # samplerate:
        #     Number of audio samples per second.
        #
        # channels:
        #     Number of audio channels, usually 1 for speech.
        #
        # dtype:
        #     Audio samples are 16-bit signed PCM.
        #
        # blocksize:
        #     Number of frames requested during each callback.
        #
        # callback:
        #     SoundDevice calls this function whenever it needs
        #     another chunk of speaker audio.
        self.stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )

        # Start the physical speaker stream.
        self.stream.start()

        # Start a background task that transfers audio from the
        # application's asyncio queue into the normal thread-safe
        # playback queue.
        self._task = asyncio.create_task(
            self._audio_bridge()
        )

        logger.info("Speaker started.")

    async def _audio_bridge(self) -> None:

        try:

            # Continuously wait for audio from the TTS layer.
            while True:

                # Get the next audio chunk from the asyncio queue.
                audio = await self.audio_queue.get()

                # Get the current asyncio event loop.
                loop = asyncio.get_running_loop()

                # queue.Queue.put() is a normal blocking operation,
                # so run it in an executor rather than blocking
                # the asyncio event loop.
                #
                # This transfers the audio into _playback_queue,
                # which is accessed by the SoundDevice callback.
                await loop.run_in_executor(
                    None,
                    self._playback_queue.put,
                    audio,
                )

        except asyncio.CancelledError:

            # Cancellation is expected when stop() shuts the speaker down.
            raise

    def _audio_callback(
        self,
        outdata,
        frames,
        time,
        status,
    ) -> None:

        # SoundDevice may report output problems here.
        #
        # We ignore normal underflow notifications because the
        # callback handles missing audio by outputting silence.
        if status and not status.output_underflow:
            logger.warning(
                f"Speaker callback status: {status}"
            )

        # int16 uses exactly 2 bytes per audio sample.
        bytes_per_sample = np.dtype(
            np.int16
        ).itemsize

        # Calculate how many bytes SoundDevice needs for this callback.
        required_bytes = (
            frames * CHANNELS * bytes_per_sample
        )

        # Protect _buffer while we read from and modify it.
        with self._buffer_lock:

            # Keep taking queued audio until the buffer contains
            # enough data to satisfy this SoundDevice callback.
            while len(self._buffer) < required_bytes:

                try:

                    # Get audio from the thread-safe playback queue.
                    #
                    # get_nowait() is used because the real-time callback
                    # should never block waiting for more audio.
                    audio = self._playback_queue.get_nowait()

                except queue.Empty:

                    # No more audio is currently available.
                    # We'll handle the missing audio below by
                    # outputting silence.
                    break

                # Append the newly received audio to the internal buffer.
                self._buffer.extend(audio)

            # Case 1:
            # We have enough audio to completely fill this callback.
            if len(self._buffer) >= required_bytes:

                # Take exactly the number of bytes SoundDevice requested.
                chunk = self._buffer[:required_bytes]

                # Remove those bytes from the internal buffer.
                #
                # Any extra audio remains available for the next callback.
                del self._buffer[:required_bytes]

                # Convert raw int16 PCM bytes back into a NumPy array.
                #
                # reshape(frames, CHANNELS) produces the shape expected
                # by SoundDevice.
                #
                # copy() creates an independent writable array.
                audio_array = np.frombuffer(
                    chunk,
                    dtype=np.int16,
                ).reshape(frames, CHANNELS).copy()

            else:

                # Case 2:
                # We don't have enough audio to completely fill
                # the SoundDevice callback.
                #
                # In this situation, we'll output the available audio
                # followed by silence.
                available_bytes = len(self._buffer)

                # Convert available bytes into the number of int16 samples.
                available_samples = (
                    available_bytes // bytes_per_sample
                )

                # Convert samples into complete audio frames.
                available_frames = (
                    available_samples // CHANNELS
                )

                # Create a complete callback-sized buffer filled with
                # silence (zeros).
                audio_array = np.zeros(
                    (frames, CHANNELS),
                    dtype=np.int16,
                )

                if available_frames > 0:

                    # Calculate the number of bytes belonging to the
                    # complete frames that we actually have.
                    chunk_bytes = (
                        available_frames
                        * CHANNELS
                        * bytes_per_sample
                    )

                    # Take those bytes from the internal buffer.
                    chunk = self._buffer[:chunk_bytes]

                    # Remove the consumed audio from the buffer.
                    del self._buffer[:chunk_bytes]

                    # Convert the available bytes into an int16 NumPy array.
                    partial = np.frombuffer(
                        chunk,
                        dtype=np.int16,
                    ).reshape(available_frames, CHANNELS)

                    # Place the available audio at the beginning of
                    # the callback buffer.
                    #
                    # The remaining frames stay as zeros (silence).
                    audio_array[:available_frames] = partial

            # Apply the current speaker volume.
            #
            # During barge-in this drops the assistant volume so the
            # user's speech is easier to hear.
            if self._volume != INITIAL_VOL:
                audio_array = (
                    audio_array.astype(np.float32)
                    * self._volume
                ).clip(
                    -32768,
                    32767,
                ).astype(
                    np.int16
                )

            # Give the completed audio buffer to SoundDevice.
            #
            # This is what ultimately sends the samples to the speaker.
            outdata[:] = audio_array

            # Determine whether the callback contains actual audio
            # or only silence.
            #
            # np.any() returns True if at least one sample is non-zero.
            playback_active = bool(np.any(audio_array))

            # Log the transition from silence to active playback.
            if playback_active and not self._logged_playback_start:
                logger.info("Speaker playback started.")
                self._logged_playback_start = True

            # Log the transition from active playback → silence.
            elif not playback_active and self._logged_playback_start:
                logger.info("Speaker playback ended.")
                self._logged_playback_start = False

            # If an echo canceller exists, keep it informed about
            # what the speaker is currently doing.
            if self.echo_canceller is not None:

                # Tell AEC whether the speaker is actively rendering
                # non-zero audio.
                self.echo_canceller.set_playback_active(
                    playback_active
                )

                if playback_active:

                    # Give the AEC the speaker audio as its reference signal.
                    #
                    # reshape(-1) converts:
                    #
                    #     (frames, channels)
                    #
                    # into:
                    #
                    #     (samples,)
                    #
                    self.echo_canceller.push_reference(
                        audio_array.reshape(-1)
                    )

    def duck(
        self,
        level: float = DROPPED_VOL,
    ) -> None:

        level = max(
            0.0,
            min(1.0, float(level)),
        )

        with self._buffer_lock:
            self._volume = level

        logger.info(
            "Speaker ducked to %.0f%%.",
            level * 100,
        )

    def unduck(self) -> None:

        with self._buffer_lock:
            self._volume = INITIAL_VOL

        logger.info(
            "Speaker unducked to normal volume.",
        )

    async def clear(self) -> None:

        # Clear the internal byte buffer so no old audio remains
        # waiting to be played.
        with self._buffer_lock:

            self._buffer.clear()

            # Mark playback as inactive.
            self._playback_active = False
            self._logged_playback_start = False

        # Empty the thread-safe playback queue.
        #
        # This removes audio that has already been transferred from
        # the asyncio queue but has not yet been played.
        while True:

            try:

                self._playback_queue.get_nowait()

            except queue.Empty:

                # Queue is now empty.
                break

        # Also empty the original asyncio audio queue.
        #
        # This removes TTS/audio chunks that are waiting to be
        # transferred to the playback queue.
        while True:

            try:

                self.audio_queue.get_nowait()

            except asyncio.QueueEmpty:

                # Queue is now empty.
                break

        # Tell the echo canceller that speaker playback has stopped.
        if self.echo_canceller is not None:
            self.echo_canceller.notify_playback_stopped()

    async def stop(self) -> None:

        # If the speaker is not running, there is nothing to stop.
        if self.stream is None:
            return

        logger.info("Stopping speaker...")

        # Cancel the background asyncio task that transfers
        # audio from audio_queue to _playback_queue.
        if self._task is not None:

            self._task.cancel()

            try:

                # Wait for the task to finish cancellation.
                await self._task

            except asyncio.CancelledError:

                # Cancellation here is expected.
                pass

            self._task = None

        # Stop the SoundDevice output stream.
        self.stream.stop()

        # Release the underlying speaker/audio device resources.
        self.stream.close()

        self.stream = None

        # Clear any audio that is still buffered.
        with self._buffer_lock:
            self._buffer.clear()

        # Empty the remaining playback queue.
        while True:

            try:

                self._playback_queue.get_nowait()

            except queue.Empty:

                # Queue is empty.
                break

        logger.info("Speaker stopped.")