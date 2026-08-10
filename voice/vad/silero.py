import numpy as np
import torch
from silero_vad import load_silero_vad

from config.constants import SAMPLE_RATE, SPEECH_THRESHOLD
from config.logger import logger


class SileroVAD:

    def __init__(self):
        logger.info("Loading Silero VAD model...")
        self.model = load_silero_vad()
        logger.info("Silero VAD loaded.")

    def is_speech(
        self,
        audio_bytes: bytes,
        threshold: float = SPEECH_THRESHOLD,
    ) -> bool:

        # Convert raw audio bytes into int16 audio samples
        audio = np.frombuffer(audio_bytes, dtype=np.int16)

        # Normalize int16 audio
        audio = audio.astype(np.float32) / 32768.0

        # Convert the NumPy array into a PyTorch tensor for Silero
        audio_tensor = torch.from_numpy(audio)

        # Run the VAD model and get the speech probability
        speech_prob = self.model(audio_tensor, SAMPLE_RATE).item()

        # Return True if the probability is above the speech threshold
        return speech_prob > threshold
