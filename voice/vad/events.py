from dataclasses import dataclass
from enum import Enum


@dataclass(slots=True)
class SpeechFrame:
    probability: float

class SpeechState(Enum):
    STARTED = "started"
    ENDED = "ended"


@dataclass(slots=True)
class ConversationEvent:
    state: SpeechState