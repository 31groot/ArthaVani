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
        # Probability above which a frame is considered speech.
        #
        # Example:
        #   threshold = 0.5
        #
        #   probability >= 0.5 → speech
        #   probability <  0.5 → silence
        self.threshold = threshold

        # Duration represented by one VAD frame.

        # This is used to convert frame counts into milliseconds.
        self.frame_duration_ms = frame_duration_ms

        # Number of consecutive frames currently detected as speech.
        #
        # This is a streak counter, not the total amount of speech
        # during the entire conversation.
        self._speech_frames = 0

        # Number of consecutive frames currently detected as silence.
        #
        # This is also a streak counter.
        self._silence_frames = 0

        # Tracks the current high-level speech state.
        #
        # False → user is not currently considered to be speaking
        # True  → user is currently considered to be speaking
        self._speaking = False

        
        # self._possible_active = False

    def update(
        self,
        probability,
    ) -> ConversationEvent | None:

        # Decide whether this frame is speech or silence.

        if probability >= self.threshold:

            # Current frame is considered speech.
            self._speech_frames += 1

            # Speech breaks any existing silence streak.
            
            self._silence_frames = 0

            #
            # if not self._speaking and not self._possible_active:
            #
            #     self._possible_active = True
            #
            #     return ConversationEvent(
            #         state=SpeechState.POSSIBLE_STARTED,
            #     )

        else:

            # Current frame is considered silence.
            self._silence_frames += 1

            # Silence breaks any existing speech streak.
            #

            # After silence:
            self._speech_frames = 0

            
            # if not self._speaking and self._possible_active:
            #
            #     self._possible_active = False
            #
            #     return ConversationEvent(
            #         state=SpeechState.POSSIBLE_ENDED,
            #     )

        #  If we are already speaking, look for enough
        #  consecutive silence to end the speech.

        if self._speaking:

            # Convert the number of consecutive silent frames
            # into milliseconds.
            
            # Example:
            
            #   6 silent frames × 32 ms = 192 ms
            silence_ms = (
                self._silence_frames
                * self.frame_duration_ms
            )

            # Only end speech after silence has lasted long enough.
            #
            # This prevents a tiny pause between words from being
            # interpreted as the user completely stopping.
            if silence_ms >= MIN_SILENCE_DURATION_MS:

                # User is no longer considered to be speaking.
                self._speaking = False

                # Reset the silence streak after detecting the
                # transition to ENDED.
                self._silence_frames = 0

                # self._possible_active = False

                return ConversationEvent(
                    state=SpeechState.ENDED,
                )

            # We are still inside the same speech turn.
            # No state change needs to be reported.
            return

        # We are NOT currently speaking.
        # Check whether enough consecutive speech has
        # accumulated to start a speech turn.

        # Convert consecutive speech frames into milliseconds.
        speech_ms = (
            self._speech_frames
            * self.frame_duration_ms
        )

        # Only start speech after the user has been detected
        # speaking for long enough.
        #
        # This prevents a single noisy VAD frame from creating
        # a false "speech started" event.
        if speech_ms >= MIN_SPEECH_DURATION_MS:

            # The user is now officially considered to be speaking.
            self._speaking = True

            # Reset the speech streak because it has already caused
            # the STARTED state transition.
            self._speech_frames = 0

            # self._possible_active = False

            return ConversationEvent(
                state=SpeechState.STARTED,
            )

        # No state transition has happened yet.
        # Keep accumulating speech/silence frames.
        return