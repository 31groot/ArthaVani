from config.constants import (
    MIN_SPEECH_DURATION_MS,
    MIN_SILENCE_DURATION_MS,
    SPEECH_THRESHOLD,
    FRAME_DURATION_MS,
)

from voice.vad.events import (
    ConversationEvent,
    SpeechState,
)


class SpeechDetector:

    def __init__(
        self,
        threshold=SPEECH_THRESHOLD,
        frame_duration_ms=FRAME_DURATION_MS,
    ):
        self.threshold = threshold
        self.frame_duration_ms = frame_duration_ms

        # Track consecutive speech and silence frames
        self._speech_frames = 0
        self._silence_frames = 0

        self._speaking = False

    def update(self, probability) -> ConversationEvent | None:

        if probability >= self.threshold:
            self._speech_frames += 1

            # Speech breaks the current silence streak
            self._silence_frames = 0

        else:
            self._silence_frames += 1

            # Silence breaks the current speech streak
            self._speech_frames = 0

        if self._speaking:

            # Convert consecutive silence frames into milliseconds
            silence_ms = (
                self._silence_frames
                * self.frame_duration_ms
            )

            if silence_ms >= MIN_SILENCE_DURATION_MS:

                self._speaking = False
                self._silence_frames = 0

                return ConversationEvent(
                    state=SpeechState.ENDED,
                )

            return None

        # We are not currently speaking, so check whether speech has started
        speech_ms = (
            self._speech_frames
            * self.frame_duration_ms
        )

        if speech_ms >= MIN_SPEECH_DURATION_MS:

            self._speaking = True
            self._speech_frames = 0

            return ConversationEvent(
                state=SpeechState.STARTED,
            )

        # No speech state change yet
        return None