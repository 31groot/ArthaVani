import numpy as np
import torch
from silero_vad import load_silero_vad

from config.constants import SAMPLE_RATE
from config.logger import logger


class SileroVAD:
    def __init__(self):
        logger.info("Loading Silero VAD model...")
        self.model = load_silero_vad()
        logger.info("Silero VAD loaded.")

    def is_speech(
        self,
        audio_bytes: bytes,
        threshold: float = 0.5,
    ) -> bool:



        audio = np.frombuffer(audio_bytes, dtype=np.int16)
        audio = audio.astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio)

        speech_prob = self.model(audio_tensor, SAMPLE_RATE).item()

        return speech_prob > threshold