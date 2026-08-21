import threading

import numpy as np

import webrtc_audio_processing as wap

from config.constants import (
    SAMPLE_RATE,
    CHANNELS,
    REFERENCE_BUFFER_SECONDS,
    FRAME_MS,
    FRAME_SAMPLES,
    _AEC_TYPE_DESKTOP,
    _INITIAL_SYSTEM_DELAY_MS,
)
from config.logger import logger


class EchoCanceller:

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        stream_delay_ms: int = _INITIAL_SYSTEM_DELAY_MS,
        reference_buffer_seconds: float = REFERENCE_BUFFER_SECONDS,
    ) -> None:

        if channels != 1:
            raise ValueError(
                "webrtc_aec currently only supports mono audio."
            )

        self.sample_rate = sample_rate
        self.channels = channels

        self._lock = threading.Lock()

        self._apm = wap.AudioProcessingModule(
            aec_type=_AEC_TYPE_DESKTOP,
            enable_ns=True,
            agc_type=0,
            enable_vad=False,
        )

        self._apm.set_stream_format(sample_rate, channels)
        self._apm.set_reverse_stream_format(sample_rate, channels)
        self._apm.set_system_delay(stream_delay_ms)

        # Leftover samples that didn't fill a complete 10ms frame
        # yet, kept between calls.
        self._near_leftover = np.zeros(0, dtype=np.int16)
        self._far_leftover = np.zeros(0, dtype=np.int16)

    
        self._last_has_echo = False
        logger.info("WebRTC AEC initialized.")

        self._silence_bypass_seconds = reference_buffer_seconds
        self._playback_active = False


    def set_playback_active(self, active: bool) -> None:
        with self._lock:
            self._playback_active = bool(active)

    def is_playback_active(self) -> bool:
        with self._lock:
            return self._playback_active

    def push_reference(self, audio) -> None:

        samples = self._to_int16(audio)

        if samples.size == 0:
            return

        with self._lock:
            if not self._playback_active:
                return

            buf = np.concatenate((self._far_leftover, samples))

            n_frames = buf.size // FRAME_SAMPLES

            for i in range(n_frames):

                frame = buf[
                    i * FRAME_SAMPLES: (i + 1) * FRAME_SAMPLES
                ]

                try:
                    self._apm.process_reverse_stream(
                        frame.tobytes()
                    )
                except Exception:
                    logger.exception(
                        "WebRTC AEC failed to process reverse "
                        "(reference) stream."
                    )

            self._far_leftover = buf[n_frames * FRAME_SAMPLES:]

    def process(self, audio):

        near = self._to_int16(audio)

        if near.size == 0:
            return near

        with self._lock:
            if not self._playback_active:
                return near


            buf = np.concatenate((self._near_leftover, near))

            n_frames = buf.size // FRAME_SAMPLES

            out_frames = []

            for i in range(n_frames):

                frame = buf[
                    i * FRAME_SAMPLES: (i + 1) * FRAME_SAMPLES
                ]

                try:

                    processed = self._apm.process_stream(
                        frame.tobytes()
                    )

                    out_frames.append(
                        np.frombuffer(processed, dtype=np.int16)
                    )

                    self._last_has_echo = self._apm.has_echo()

                except Exception:

                    logger.exception(
                        "WebRTC AEC failed to process near-end "
                        "stream; passing audio through unfiltered."
                    )

                    out_frames.append(frame)

            self._near_leftover = buf[n_frames * FRAME_SAMPLES:]

        if not out_frames:
           
            return np.zeros(0, dtype=np.int16)

        return np.concatenate(out_frames)


    def has_echo(self) -> bool:

        with self._lock:
            return self._last_has_echo

    def notify_playback_stopped(self) -> None:

        with self._lock:
            self._far_leftover = np.zeros(0, dtype=np.int16)
            self._last_has_echo = False
            self._playback_active = False

    @staticmethod
    def _to_int16(audio) -> np.ndarray:

        flat = np.asarray(audio).reshape(-1)

        if flat.dtype == np.int16:
            return flat

        if flat.dtype in (np.float32, np.float64):
            clipped = np.clip(flat * 32768.0, -32768, 32767)
            return clipped.astype(np.int16)

        return flat.astype(np.int16)