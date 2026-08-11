from config.constants import VAD_FRAME_SAMPLES
class AudioBuffer:

    def __init__(
        self,
        frame_samples = VAD_FRAME_SAMPLES,
        sample_width: int = 2,
    ):
        # Number of audio samples required to make one frame
        self.frame_samples = frame_samples

        # Number of bytes used by each audio sample
        self.sample_width = sample_width

        # Total number of bytes required for one frame
        self.frame_size = frame_samples * sample_width

        # Store incoming audio until enough data exists to make full frames
        self._buffer = bytearray()

    def append(self, audio: bytes):

        if not audio:
            return None

        # Add incoming audio to the existing buffer
        self._buffer.extend(audio)

    def pop_frames(self) -> list[bytes]:

        frames: list[bytes] = []

        while len(self._buffer) >= self.frame_size:

            frame = bytes(self._buffer[: self.frame_size])

            # Remove the frame that was just extracted
            del self._buffer[: self.frame_size]

            frames.append(frame)

        return frames

    def clear(self):

        # Remove all audio currently stored in the buffer
        self._buffer.clear()

    @property
    def buffered_bytes(self) -> int:

        # Return the number of bytes currently waiting in the buffer
        return len(self._buffer)

    @property
    def buffered_samples(self) -> int:

        # Convert buffered bytes back into the number of audio samples
        return len(self._buffer) // self.sample_width