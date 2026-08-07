class AudioBuffer:

    def __init__(
        self,
        frame_samples: int,
        sample_width: int = 2,
    ):


        self.frame_samples = frame_samples
        self.sample_width = sample_width

        self.frame_size = frame_samples * sample_width

        self._buffer = bytearray()

    def append(self, audio: bytes):

        if not audio:
            return None
        
        self._buffer.extend(audio)

    def pop_frames(self) -> list[bytes]:

        frames: list[bytes] = []

        while len(self._buffer) >= self.frame_size:

            frame = bytes(self._buffer[: self.frame_size])

            del self._buffer[: self.frame_size]

            frames.append(frame)

        return frames

    def clear(self):

        self._buffer.clear()

    @property
    def buffered_bytes(self) -> int:

        return len(self._buffer)

    @property
    def buffered_samples(self) -> int:

        return len(self._buffer) // self.sample_width

    def __len__(self) -> int:

        return len(self._buffer)