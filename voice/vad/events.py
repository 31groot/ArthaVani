from dataclasses import dataclass
from enum import Enum
class SpeechState(Enum):
    STARTED = "started"
    ENDED = "ended"
 # Used to duck the assistant's volume fast, without waiting out
 # the full MIN_SPEECH_DURATION_MS confirmation delay.
    POSSIBLE_STARTED = "possible_started"
    POSSIBLE_ENDED = "possible_ended"

@dataclass
class ConversationEvent:
    state: SpeechState
