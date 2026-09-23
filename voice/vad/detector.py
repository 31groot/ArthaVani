from config.constants import (
    MIN_SILENCE_DURATION_MS,
    BARGE_IN_CONFIRMATION_DURATION_MS,
    POSSIBLE_SPEECH_DURATION_MS,
    POSSIBLE_SILENCE_DURATION_MS,
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

        self._speech_frames = 0
        self._silence_frames = 0

        # Confirmed user speech turn.
        self._speaking = False

        # Early speech candidate used for fast ducking.
        self._possible_active = False

    def update(
        self,
        probability,
    ) -> ConversationEvent | None:

        if probability >= self.threshold:

            self._speech_frames += 1
            self._silence_frames = 0

            # Already inside a confirmed speech turn.
            if self._speaking:
                return None

            speech_ms = (
                self._speech_frames
                * self.frame_duration_ms
            )

            # Early signal: duck the speaker quickly.
            if (
                not self._possible_active
                and speech_ms >= POSSIBLE_SPEECH_DURATION_MS
            ):
                self._possible_active = True

                return ConversationEvent(
                    state=SpeechState.POSSIBLE_STARTED,
                )

            # Full confirmation: now perform real barge-in.
            if (
                self._possible_active
                and speech_ms >= BARGE_IN_CONFIRMATION_DURATION_MS
            ):
                self._speaking = True
                self._possible_active = False
                self._speech_frames = 0
                self._silence_frames = 0

                return ConversationEvent(
                    state=SpeechState.STARTED,
                )

            return None

        # Silence.

        self._silence_frames += 1

        # Confirmed speech turn.
        if self._speaking:

            silence_ms = (
                self._silence_frames
                * self.frame_duration_ms
            )

            if silence_ms >= MIN_SILENCE_DURATION_MS:

                self._speaking = False
                self._speech_frames = 0
                self._silence_frames = 0
                self._possible_active = False

                return ConversationEvent(
                    state=SpeechState.ENDED,
                )

            return None

        # Early possible-speech phase.
        if self._possible_active:

            possible_silence_ms = (
                self._silence_frames
                * self.frame_duration_ms
            )

            if (
                possible_silence_ms
                >= POSSIBLE_SILENCE_DURATION_MS
            ):
                self._possible_active = False
                self._speech_frames = 0
                self._silence_frames = 0

                return ConversationEvent(
                    state=SpeechState.POSSIBLE_ENDED,
                )

            return None

        # No speech candidate.
        self._speech_frames = 0

        return None
