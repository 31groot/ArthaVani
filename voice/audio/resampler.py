import numpy as np
from scipy.signal import resample_poly

class AudioResampler:

    def __init__(
        self,
        input_rate: int,
        output_rate: int,
    ) -> None:

        # The input sample rate is the number of audio samples
        # received from the microphone per second.
        #

        if input_rate <= 0:
            raise ValueError(
                "input_rate must be greater than zero."
            )

        # The output sample rate is the number of samples per second
        # that we want after resampling.
        
        if output_rate <= 0:
            raise ValueError(
                "output_rate must be greater than zero."
            )

        # resample_poly() performs resampling using an up/down ratio.
        
        self._up = output_rate
        self._down = input_rate

    def process(
        self,
        audio: np.ndarray,
    ) -> np.ndarray:

        # If there is no audio data, return an empty int16 array.
        #
        # This avoids sending an empty signal resampler
        # and keeps the output type consistent with our PCM audio.
        if audio.size == 0:
            return np.empty(
                0,
                dtype=np.int16,
            )

        # Resample the audio from input_rate to output_rate.
        #
        # resample_poly() performs the necessary interpolation,
        # filtering, and decimation to produce a new signal
        # at the desired sample rate.
        resampled = resample_poly(
            audio,
            up=self._up,
            down=self._down,
        )

        # resample_poly() can produce floating-point values and may
        # slightly overshoot the original audio's peak values because
        # of the filtering used during resampling.
        #
        # int16 can only represent values from:
        #
        #     -32768 to 32767
        #
        # So we first round the values and then clip anything outside
        # the valid int16 range.
        #
        # Without clipping, an out-of-range value could produce
        # undesirable results when converted to int16.
        clipped = np.clip(
            np.round(resampled),
            -32768,
            32767,
        )

        # Convert the final audio back into 16-bit signed PCM values.
        #
        # This gives us the same int16 format used by the microphone
        # input and the rest of the audio pipeline.
        return np.asarray(
            clipped,
            dtype=np.int16,
        )
