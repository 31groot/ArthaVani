from config.constants import (
    MIN_SPEECH_DURATION_MS,
    MIN_SILENCE_DURATION_MS,
)

from voice.vad.events import (
    ConversationEvent,
    SpeechState,
)

class SpeechDetector:

    def __init__(
        self,
        threshold = 0.5,
        frame_duration_ms = 32,
    ):
        
        self.threshold = threshold
        self.frame_duration_ms = frame_duration_ms
        self._speech_frames = 0
        self._silence_frames = 0
        self._speaking = False

    def update(self, probability,) -> ConversationEvent | None:
        if probability >= self.threshold:
            self._speech_frames += 1
            self._silence_frames = 0

        else:
            self._silence_frames += 1
            self._speech_frames = 0

        if self._speaking:
            silence_ms = (self._silence_frames * self.frame_duration_ms)

            if silence_ms >= MIN_SILENCE_DURATION_MS:

                self._speaking = False
                self._silence_frames = 0

                return ConversationEvent(
                    state=SpeechState.ENDED,
                )

            return None

        speech_ms = (
            self._speech_frames
            * self.frame_duration_ms
        )

        if speech_ms >= MIN_SPEECH_DURATION_MS:

            self._speaking = True
            self._speech_frames = 0

            return ConversationEvent(state=SpeechState.STARTED,)
        return None

    