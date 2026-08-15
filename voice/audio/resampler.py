import numpy as np
from scipy.signal import resample_poly


class AudioResampler:

    def __init__(
        self,
        input_rate: int,
        output_rate: int,
    ) -> None:

        if input_rate <= 0:
            raise ValueError(
                "input_rate must be greater than zero."
            )

        if output_rate <= 0:
            raise ValueError(
                "output_rate must be greater than zero."
            )

        self.input_rate = input_rate
        self.output_rate = output_rate

        self._up = output_rate
        self._down = input_rate

    def process(
        self,
        audio: np.ndarray,
    ) -> np.ndarray:

        if audio.size == 0:
            return np.empty(
                0,
                dtype=np.int16,
            )

        resampled = resample_poly(
            audio,
            up=self._up,
            down=self._down,
        )
        # Clip before casting to int16. resample_poly can slightly
        # overshoot the input's peak values (Gibbs-phenomenon ripple
        # at transitions). Without clipping, any overshoot past the
        # int16 range wraps around instead of saturating, turning a
        # small overshoot into a violent, full-scale discontinuity.

        clipped = np.clip(np.round(resampled), -32768, 32767)


        return np.asarray(clipped, dtype=np.int16)