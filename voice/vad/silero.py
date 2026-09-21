import asyncio

import numpy as np
import torch
from silero_vad import load_silero_vad

from config.constants import SAMPLE_RATE
from config.logger import logger


class SileroVAD:

    def __init__(self):

        logger.info(
            "Loading Silero VAD model..."
        )

        # Limit PyTorch to one CPU thread for model inference.
        #
        # VAD runs frequently on small audio frames, so using a single
        # thread helps keep CPU usage predictable
        torch.set_num_threads(1)

        # Load the Silero VAD neural-network model once during startup.
        #
        # We do NOT want to reload the model for every audio frame.
        self.model = load_silero_vad()

        logger.info(
            "Silero VAD loaded."
        )

    def _infer(
        self,
        audio_bytes: bytes,
    ) -> float:

        # Convert the raw audio bytes back into int16 PCM samples.
        #
        # The microphone/audio pipeline uses int16 PCM internally.
        #

        samples = np.frombuffer(
            audio_bytes,
            dtype=np.int16,
        )

        # Convert int16 samples into float32 and normalize them
        # approximately to the range [-1.0, 1.0].
        #
        # int16 range:
        #
        #     -32768 → 32767
        #
        # After division:
        #
        #     approximately -1.0 → +1.0
        #
        # This is the format expected by the neural-network model.
        audio = (
            samples.astype(np.float32)
            / 32768.0
        )

        # Convert the NumPy array into a PyTorch tensor because
        # Silero VAD is a PyTorch model.
        audio_tensor = torch.from_numpy(
            audio
        )

        # Run the VAD model.
        #
        # The model receives:
        #
        #     1. audio samples
        #     2. sample rate
        #
        # and returns a speech probability.

        speech_prob = self.model(
            audio_tensor,
            SAMPLE_RATE,
        ).item()

        # Convert the one-value PyTorch tensor into a normal Python float.
        return speech_prob

    async def is_speech(
        self,
        audio_bytes: bytes,
    ) -> float:

        # Get the currently running asyncio event loop.
        loop = asyncio.get_running_loop()

        # Run the CPU-heavy model inference in a background thread
        # instead of directly on the asyncio event-loop thread.

        # Arguments:
        #
        #     None
        #         Use asyncio's default thread pool.
        #
        #     self._infer
        #         Function that should run in the worker thread.
        #
        #     audio_bytes
        #         Argument passed to _infer().

        return await loop.run_in_executor(
            None,
            self._infer,
            audio_bytes,
        )