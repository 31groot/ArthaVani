import threading

import numpy as np

import webrtc_audio_processing as wap

from config.constants import (
    SAMPLE_RATE,
    CHANNELS,
    REFERENCE_BUFFER_SECONDS,
    FRAME_SAMPLES,
    AEC_TYPE_DESKTOP,
    INITIAL_SYSTEM_DELAY_MS,
)
from config.logger import logger


class EchoCanceller:

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        stream_delay_ms: int = INITIAL_SYSTEM_DELAY_MS,
    ) -> None:

        # The current WebRTC AEC implementation is configured
        # to work with mono audio only.
        if channels != 1:
            raise ValueError(
                "webrtc_aec currently only supports mono audio."
            )

        # Store the audio format used by the microphone/speaker.
        self.sample_rate = sample_rate
        self.channels = channels

        # Protect shared AEC state when microphone and speaker
        # operations happen from different threads/tasks.
        self._lock = threading.Lock()

        # Create the WebRTC Audio Processing Module.
        #
        # This module performs the actual audio processing.
        #
        # aec_type:
        #     Selects the WebRTC echo cancellation mode.
        #
        # enable_ns=True:
        #     Enables noise suppression.
        #
        # agc_type=0:
        #     Automatic gain control is disabled.
        #
        # enable_vad=False:
        #     Voice activity detection is disabled.
        self._apm = wap.AudioProcessingModule(
            aec_type=AEC_TYPE_DESKTOP,
            enable_ns=True,
            agc_type=0,
            enable_vad=False,
        )

        # Tell WebRTC the format of the microphone/near-end stream.
        self._apm.set_stream_format(
            sample_rate,
            channels,
        )

        # Tell WebRTC the format of the speaker/far-end
        # (reverse/reference) stream.
        self._apm.set_reverse_stream_format(
            sample_rate,
            channels,
        )

        # Tell WebRTC approximately how much delay exists between
        # speaker playback and the microphone receiving that sound.
        #
        # AEC needs this information to align the reference signal
        # with the echo appearing in the microphone signal.
        self._apm.set_system_delay(
            stream_delay_ms
        )

        # WebRTC expects fixed-size frames, typically 10 ms.
        #
        # The microphone/speaker callbacks may not always provide
        # exactly one complete WebRTC frame, so we keep incomplete
        # samples here until the next call.
        #
        # Near end  = microphone audio
        # Far end   = speaker/reference audio
        self._near_leftover = np.zeros(
            0,
            dtype=np.int16,
        )

        self._far_leftover = np.zeros(
            0,
            dtype=np.int16,
        )

        # Remember the most recent echo detection result.
        self._last_has_echo = False

        logger.info(
            "WebRTC AEC initialized."
        )


        # Tracks whether the speaker is currently producing
        # real audio.
        self._playback_active = False

    def set_playback_active(
        self,
        active: bool,
    ) -> None:

        # Called by Speaker to tell the AEC whether audio is
        # currently being rendered through the speakers.
        with self._lock:
            self._playback_active = bool(active)

    def is_playback_active(self) -> bool:

        # Used by Microphone to determine whether AEC processing
        # is necessary.
        with self._lock:
            return self._playback_active

    def push_reference(
        self,
        audio,
    ) -> None:

        # Convert the speaker/reference audio into int16 PCM.
        samples = self._to_int16(audio)

        # Nothing to process.
        if samples.size == 0:
            return

        with self._lock:

            # If the speaker isn't actually playing audio,
            # there is no reference signal to send to WebRTC.
            if not self._playback_active:
                return

            # Combine any incomplete frame left from the previous call
            # with the new speaker samples.
            buf = np.concatenate(
                (
                    self._far_leftover,
                    samples,
                )
            )

            # Calculate how many complete WebRTC frames exist.
            #
            # For example:
            #
            # 350 samples / 160 samples per frame
            # = 2 complete frames
            n_frames = (
                buf.size // FRAME_SAMPLES
            )

            for i in range(n_frames):

                # Extract exactly one complete WebRTC frame.
                frame = buf[
                    i * FRAME_SAMPLES:
                    (i + 1) * FRAME_SAMPLES
                ]

                try:

                    # Send the speaker audio to WebRTC as the
                    # reverse/far-end reference signal.
                    #
                    # WebRTC uses this signal to estimate what
                    # audio is likely to appear as echo in the
                    # microphone recording.
                    self._apm.process_reverse_stream(
                        frame.tobytes()
                    )

                except Exception:

                    # Do not let an AEC error crash the speaker pipeline.
                    logger.exception(
                        "WebRTC AEC failed to process reverse "
                        "(reference) stream."
                    )

            # Save any incomplete samples for the next call.
            #
            # Example:
            #
            # 350 samples total
            # 320 processed
            # 30 leftover
            #
            # Those 30 samples are kept here.
            self._far_leftover = buf[
                n_frames * FRAME_SAMPLES:
            ]

    def process(
        self,
        audio,
    ):

        # Convert microphone/near-end audio into int16 PCM.
        near = self._to_int16(audio)

        # If there is no microphone data, return immediately.
        if near.size == 0:
            return near

        with self._lock:

            # If the speaker is silent, there is no speaker echo
            # that needs to be removed.
            #
            # Return the microphone audio unchanged.
            if not self._playback_active:
                return near

            # Add any incomplete frame from the previous call
            # to the new microphone samples.
            buf = np.concatenate(
                (
                    self._near_leftover,
                    near,
                )
            )

            # Count the number of complete WebRTC frames available.
            n_frames = (
                buf.size // FRAME_SAMPLES
            )

            # Store processed frames here.
            out_frames = []

            for i in range(n_frames):

                # Extract one exact-size WebRTC frame.
                frame = buf[
                    i * FRAME_SAMPLES:
                    (i + 1) * FRAME_SAMPLES
                ]

                try:

                    # Send the microphone/near-end frame to WebRTC.
                    #
                    # WebRTC has already received the speaker audio
                    # through process_reverse_stream(), so it can
                    # compare the two and attempt to remove the echo.
                    processed = self._apm.process_stream(
                        frame.tobytes()
                    )

                    # Convert WebRTC's output bytes back into
                    # an int16 NumPy array.
                    processed_array = np.frombuffer(
                        processed,
                        dtype=np.int16,
                    )

                    # Store the processed frame.
                    out_frames.append(
                        processed_array
                    )

                    # Remember whether WebRTC detected echo
                    # for this frame.
                    self._last_has_echo = (
                        self._apm.has_echo()
                    )

                except Exception:

                    # If AEC fails, don't destroy the microphone stream.
                    #
                    # Use the original frame as a safe fallback.
                    logger.exception(
                        "WebRTC AEC failed to process near-end "
                        "stream; passing audio through unfiltered."
                    )

                    out_frames.append(
                        frame
                    )

            # Save any incomplete samples for the next microphone call.
            self._near_leftover = buf[
                n_frames * FRAME_SAMPLES:
            ]

        # No complete frame was available yet.
        #
        # The incomplete samples have been saved in
        # _near_leftover and will be combined with the next call.
        if not out_frames:

            return np.zeros(
                0,
                dtype=np.int16,
            )

        # Join all processed frames back into one continuous
        # microphone audio array.
        return np.concatenate(
            out_frames
        )

    def has_echo(
        self,
    ) -> bool:

        # Return the most recently reported echo-detection state.
        with self._lock:
            return self._last_has_echo

    def notify_playback_stopped(
        self,
    ) -> None:

        # Reset state when the assistant stops speaking.
        #
        # Old speaker-reference leftovers should not be reused
        # for a future playback session.
        with self._lock:

            self._far_leftover = np.zeros(
                0,
                dtype=np.int16,
            )

            # Clear the last echo-detection result.
            self._last_has_echo = False

            # Mark speaker playback as inactive.
            self._playback_active = False

    @staticmethod
    def _to_int16(
        audio,
    ) -> np.ndarray:

        # Convert whatever was supplied into a NumPy array
        # and flatten it to one dimension.
        flat = np.asarray(
            audio
        ).reshape(-1)

        # If it is already int16, no conversion is necessary.
        if flat.dtype == np.int16:
            return flat

        # If the audio is normalized floating-point audio,
        # convert it from approximately [-1.0, 1.0] into
        # the int16 PCM range [-32768, 32767].
        if flat.dtype in (
            np.float32,
            np.float64,
        ):

            # Multiply normalized floating-point samples
            # by the int16 scale factor.
            #
            # Then clip to prevent values outside the valid
            # int16 range.
            clipped = np.clip(
                flat * 32768.0,
                -32768,
                32767,
            )

            return clipped.astype(
                np.int16
            )

        # For any other numeric dtype, simply convert to int16.
        return flat.astype(
            np.int16
        )