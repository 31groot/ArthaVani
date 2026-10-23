"""Server-side AEC for browser audio.

The browser sends each 20 ms packet as ``[mic int16 x N][reference int16 x N]``
where the reference is the exact (post-ducking) signal its playback graph
produced in the same render quantum. That makes the two streams sample
aligned, which is the same situation the desktop pipeline gets from the
sounddevice callbacks -- the reason the desktop AEC works.
"""
from __future__ import annotations

import numpy as np

from config.constants import (
    BROWSER_AEC_DEFAULT_DELAY_MS,
    BROWSER_AEC_MAX_DELAY_MS,
    BROWSER_AEC_MIN_DELAY_MS,
    BROWSER_AEC_TAIL_MS,
    FRAME_SAMPLES,
    SAMPLE_RATE,
)
from config.logger import logger


class BrowserEchoProcessor:
    def __init__(self, canceller, *, tail_ms: int = BROWSER_AEC_TAIL_MS) -> None:
        self._aec = canceller
        self._tail_total = SAMPLE_RATE * tail_ms // 1000
        self._tail_left = 0
        self._active = False
        self._sq = [0.0, 0.0, 0.0]
        self._n = 0

    def pop_levels(self) -> tuple[float, float, float]:
        """RMS of (mic in, mic out, reference) since the last call."""
        n = max(self._n, 1)
        out = tuple(float((v / n) ** 0.5) for v in self._sq)
        self._sq = [0.0, 0.0, 0.0]
        self._n = 0
        return out

    def _track(self, mic, out, ref) -> None:
        for i, arr in enumerate((mic, out, ref)):
            a = np.asarray(arr, dtype=np.float64)
            self._sq[i] += float(np.mean(a * a)) * len(a) if len(a) else 0.0
        self._n += len(mic)

    def set_delay_ms(self, delay_ms: float | None) -> int:
        value = BROWSER_AEC_DEFAULT_DELAY_MS if delay_ms is None else int(delay_ms)
        value = max(BROWSER_AEC_MIN_DELAY_MS, min(BROWSER_AEC_MAX_DELAY_MS, value))
        self._aec.set_stream_delay(value)
        return value

    def process(self, mic: bytes, ref: bytes) -> bytes:
        mic_np = np.frombuffer(mic, dtype="<i2")
        ref_np = np.frombuffer(ref, dtype="<i2")
        n = min(mic_np.size, ref_np.size)
        if n == 0:
            return b""
        mic_np, ref_np = mic_np[:n], ref_np[:n]
        try:
            ref_active = bool(np.max(np.abs(ref_np.astype(np.int32))) >= 2)
            if ref_active:
                self._tail_left = self._tail_total
            else:
                self._tail_left = max(0, self._tail_left - n)
            active = ref_active or self._tail_left > 0
            if active != self._active:
                if active:
                    self._aec.set_playback_active(True)
                else:
                    self._aec.notify_playback_stopped()
                self._active = active
            if not active:
                return mic_np.tobytes()

            pad = (-n) % FRAME_SAMPLES
            if pad:
                mic_np = np.concatenate((mic_np, np.zeros(pad, np.int16)))
                ref_np = np.concatenate((ref_np, np.zeros(pad, np.int16)))
            self._aec.push_reference(ref_np)
            out = self._aec.process(mic_np)
            if pad and out.size >= n:
                out = out[:n]
            out = np.asarray(out, dtype="<i2")
            self._track(mic_np[:n], out[:n], ref_np[:n])
            return out.tobytes()
        except Exception:
            logger.exception("Browser AEC failed; passing microphone audio through.")
            return mic_np.tobytes()


def create_browser_echo_processor() -> BrowserEchoProcessor | None:
    try:
        from voice.audio.webrtc_aec import EchoCanceller
        return BrowserEchoProcessor(EchoCanceller())
    except Exception:
        logger.warning("Server-side browser AEC unavailable; using browser AEC only.",
                       exc_info=True)
        return None
