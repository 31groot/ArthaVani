from dataclasses import dataclass
from enum import Enum
class SpeechState(Enum):
    STARTED = "started"
    ENDED = "ended"

@dataclass
class ConversationEvent:
    state: SpeechState
