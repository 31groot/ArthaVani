from config.constants import VAD_FRAME_SAMPLES


class AudioBuffer:

    def __init__(
        self,
        frame_samples=VAD_FRAME_SAMPLES,
        sample_width: int = 2,
    ):

        # Number of audio samples required to create one complete frame.
        #
        # Example:
        #   160 samples at 16 kHz = 10 ms of audio.
        self.frame_samples = frame_samples

        # Number of bytes used to represent one audio sample.
        #
        # int16 audio uses:
        #   16 bits = 2 bytes
        self.sample_width = sample_width

        # Total number of bytes required for one complete frame.
        #
        # Example:
        #   160 samples × 2 bytes/sample = 320 bytes
        self.frame_size = (
            frame_samples * sample_width
        )

        # Stores incoming audio bytes until enough data exists
        # to create one or more complete frames.
        #
        # Example:
        #
        #   VAD needs 320 bytes
        #   microphone gives 100 bytes
        #
        #   _buffer = 100 bytes
        #
        # More audio is added on later calls until a full frame exists.
        self._buffer = bytearray()

    def append(
        self,
        audio: bytes,
    ) -> None:

        # Ignore empty audio chunks.
        if not audio:
            return

        # Add the new audio to whatever audio is already buffered.
        #
        # The buffer may now contain:
        #
        #   previous leftover audio
        #   +
        #   new microphone audio
        self._buffer.extend(
            audio
        )

    def pop_frames(
        self,
    ) -> list[bytes]:

        # Store complete frames that we extract from the buffer.
        frames: list[bytes] = []

        # Keep extracting frames while enough bytes are available.
        #
        # This allows one call to return multiple complete frames.
        #

        while len(self._buffer) >= self.frame_size:

            # Take exactly one frame-sized portion of the buffer.
            #
            # Convert it from bytearray to immutable bytes.
            frame = bytes(
                self._buffer[
                    :self.frame_size
                ]
            )

            # Remove the frame we just consumed from the buffer.
            #
            # Any remaining bytes stay in the buffer and can be
            # combined with future microphone audio.
            del self._buffer[
                :self.frame_size
            ]

            # Store the complete frame in the result list.
            frames.append(
                frame
            )

        # Return all complete frames.
        #
        # Any incomplete audio remains in self._buffer.
        return frames

    def clear(
        self,
    ) -> None:

        # Discard all buffered audio.
        #
        # Useful when resetting VAD or starting a new audio session.
        self._buffer.clear()

    @property
    def buffered_bytes(
        self,
    ) -> int:

        # Return the number of raw audio bytes currently waiting
        # in the internal buffer.
        return len(
            self._buffer
        )

    @property
    def buffered_samples(
        self,
    ) -> int:

        # Convert the buffered byte count back into the number
        # of complete audio samples.
        #
        # Example:
        #
        #   400 bytes / 2 bytes per int16 sample
        #   = 200 samples
        #
        # Integer division is used because we only count complete
        # samples.
        return (
            len(self._buffer)
            // self.sample_width
        )