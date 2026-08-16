import threading

import numpy as np


class EchoCanceller:
    """
    Single-channel Normalized Least Mean Squares (NLMS) acoustic
    echo canceller.

    The speaker's played-back audio ("far-end" signal) is fed in
    continuously via `push_reference()`. Microphone audio ("near-end"
    signal) is passed through `process()`, which predicts how much
    of it is an echo of recently-played audio and subtracts that
    prediction before returning it.

    This is an approximation, not a full WebRTC-grade AEC: delay
    between the reference and the mic pickup is a fixed, tunable
    estimate rather than auto-detected. `delay_samples` and
    `filter_length` are the two parameters worth tuning if echo
    isn't fully cancelled.
    """

    def __init__(
        self,
        filter_length: int = 2048,
        delay_samples: int = 1600,
        mu: float = 0.4,
        reference_buffer_seconds: float = 3.0,
        sample_rate: int = 16000,
    ) -> None:

        self.filter_length = filter_length
        self.delay_samples = delay_samples
        self.mu = mu

        self._weights = np.zeros(filter_length, dtype=np.float32)

        # Circular reference buffer holding recently played audio,
        # in the same units/scale as the mic signal (normalized
        # float32, -1..1).
        self._ref_capacity = int(
            reference_buffer_seconds * sample_rate
        )
        self._ref_buffer = np.zeros(
            self._ref_capacity, dtype=np.float32
        )
        self._ref_write_index = 0
        self._ref_total_written = 0

        self._lock = threading.Lock()

        # Tracks how many near-end samples have been processed, so
        # we know which reference samples correspond to "now minus
        # delay".
        self._near_total_processed = 0

    def push_reference(self, audio: np.ndarray) -> None:
        """
        Feed audio that was just sent to the speaker hardware.
        `audio` should be int16 or float32 mono samples.
        """

        samples = self._to_float(audio)

        n = len(samples)

        if n == 0:
            return

        if n >= self._ref_capacity:
            # Reference chunk bigger than the whole buffer; just
            # keep the tail.
            samples = samples[-self._ref_capacity:]
            n = len(samples)

        with self._lock:

            end = self._ref_write_index + n

            if end <= self._ref_capacity:
                self._ref_buffer[self._ref_write_index:end] = (
                    samples
                )
            else:
                first_part = (
                    self._ref_capacity - self._ref_write_index
                )
                self._ref_buffer[self._ref_write_index:] = (
                    samples[:first_part]
                )
                self._ref_buffer[:n - first_part] = (
                    samples[first_part:]
                )

            self._ref_write_index = end % self._ref_capacity
            self._ref_total_written += n

    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        Run near-end (microphone) audio through echo cancellation.
        Returns int16 samples with predicted echo removed.
        """

        near = self._to_float(audio)

        n = len(near)

        output = np.empty(n, dtype=np.float32)

        for i in range(n):

            sample_index = self._near_total_processed + i

            with self._lock:

                far_index = (
                    self._ref_total_written
                    - self.delay_samples
                    - (n - i)
                )

                ref_total_written = self._ref_total_written

                if (
                    far_index >= self.filter_length
                    and ref_total_written >= self.delay_samples
                ):
                    x = self._get_reference_window(far_index)
                else:
                    x = None

            if x is None:
                # Not enough reference history yet (e.g. right at
                # startup, or nothing has been played recently) —
                # pass the sample through unmodified.
                output[i] = near[i]
                continue

            echo_estimate = float(np.dot(self._weights, x))

            error = near[i] - echo_estimate

            output[i] = error

            norm = float(np.dot(x, x)) + 1e-6

            self._weights += (
                self.mu * error / norm
            ) * x

        self._near_total_processed += n

        clipped = np.clip(output * 32768.0, -32768, 32767)

        return clipped.astype(np.int16)

    def _get_reference_window(self, end_index: int) -> np.ndarray:

        start_index = end_index - self.filter_length

        start_pos = start_index % self._ref_capacity
        end_pos = end_index % self._ref_capacity

        if start_pos < end_pos:
            return self._ref_buffer[start_pos:end_pos]

        return np.concatenate(
            (
                self._ref_buffer[start_pos:],
                self._ref_buffer[:end_pos],
            )
        )

    @staticmethod
    def _to_float(audio: np.ndarray) -> np.ndarray:

        # Mic/speaker audio can arrive as a 2D array (frames, 1) for
        # mono. Flatten to 1D so per-sample indexing below returns
        # plain scalars, not length-1 arrays.
        flat = audio.reshape(-1)

        if flat.dtype == np.int16:
            return flat.astype(np.float32) / 32768.0

        return flat.astype(np.float32)