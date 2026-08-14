import asyncio
import numpy as np
import torch
from silero_vad import load_silero_vad

from config.constants import SAMPLE_RATE
from config.logger import logger


class SileroVAD:
    def __init__(self):
        logger.info("Loading Silero VAD model...")
        torch.set_num_threads(1)
        self.model = load_silero_vad()
        logger.info("Silero VAD loaded.")

    def _infer(self, audio_bytes: bytes,) -> float:
        audio = np.frombuffer(audio_bytes, dtype=np.int16)
        audio = audio.astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio)
        speech_prob = self.model(audio_tensor, SAMPLE_RATE).item()
        return speech_prob


    async def is_speech(self, audio_bytes: bytes) -> float:
        loop = asyncio.get_running_loop()

        # Run the CPU-heavy model inference in a background thread
        # so it does not block the asyncio event loop.
        return await loop.run_in_executor(
            None,  # Use Python's default thread pool.
            self._infer,  # Function to execute in the background.
            audio_bytes,  # Audio data passed to _infer().
        )
