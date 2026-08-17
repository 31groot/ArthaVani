import threading
import time
import numpy as np
from config.constants import (
     SAMPLE_RATE,
     FILTER_LENGTH,
     DELAY_SAMPLES,
     MU,
     REFERENCE_BUFFER_SECONDS,
)

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
        filter_length: int = FILTER_LENGTH,
        delay_samples: int = DELAY_SAMPLES,
        mu: float = MU,
        reference_buffer_seconds: float = REFERENCE_BUFFER_SECONDS,
        sample_rate: int = SAMPLE_RATE,
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

        self._last_reference_time = 0.0
        self._silence_bypass_seconds = 0.6

        # Rolling peak of recently played (far-end) audio, used by
        # the double-talk detector below.
        self._recent_far_peak = 0.0
        self._far_peak_decay = 0.995

        # If the near-end (mic) signal is louder than this fraction
        # of the recent far-end peak, assume the user is talking
        # over the assistant (double-talk) and bypass cancellation
        # for that block rather than risk attenuating real speech.
        self.double_talk_threshold = 0.5

        # Tracks how many near-end samples have been processed, so
        # we know which reference samples correspond to "now minus
        # delay".
        self._near_total_processed = 0

    def notify_playback_stopped(self) -> None:
        """
        Call this when playback is forcibly stopped/cleared (e.g.
        barge-in). Immediately treats any further mic audio as
        having no recent echo to cancel, instead of waiting for the
        normal silence-bypass timer to elapse — otherwise the
        filter keeps actively (and stale-ly) filtering right after
        an abrupt stop, which can end up attenuating the user's
        actual next words.
        """

        with self._lock:
            self._last_reference_time = 0.0

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
            self._last_reference_time = time.monotonic()

            block_peak = float(np.max(np.abs(samples))) if n else 0.0

            # Exponentially-decaying peak tracker: jumps up
            # immediately on loud playback, decays gradually after,
            # so "recent far-end loudness" reflects what's actually
            # been coming out of the speaker very recently.
            self._recent_far_peak = max(
                block_peak,
                self._recent_far_peak * self._far_peak_decay,
            )

    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        Run near-end (microphone) audio through echo cancellation.
        Returns int16 samples with predicted echo removed.
        """

        near = self._to_float(audio)

        n = len(near)

        with self._lock:
            seconds_since_playback = (
                time.monotonic() - self._last_reference_time
            )

        if seconds_since_playback > self._silence_bypass_seconds:
            # Nothing has been played recently, so there's no echo
            # to cancel. Pass audio through untouched rather than
            # risk an already-adapted filter attenuating real
            # speech during quiet periods.
            self._near_total_processed += n
            clipped = np.clip(near * 32768.0, -32768, 32767)
            return clipped.astype(np.int16)

        near_peak = float(np.max(np.abs(near))) if n else 0.0

        with self._lock:
            recent_far_peak = self._recent_far_peak

        double_talk = (
            recent_far_peak > 0
            and near_peak
            > self.double_talk_threshold * recent_far_peak
        )

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

            if double_talk:
                # Likely double-talk: still subtract the filter's
                # current best echo estimate (better than passing
                # the raw echo+voice mix straight to STT), but don't
                # adapt the filter on this block — updating weights
                # from a signal that's genuinely a mix of echo and
                # real speech would corrupt the filter's model of
                # the room's actual echo path.
                continue

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