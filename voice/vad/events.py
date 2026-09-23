from typing import ClassVar
from pydantic import BaseModel


class SpeechState(BaseModel):
    POSSIBLE_STARTED: ClassVar[str] = "possible_started"
    POSSIBLE_ENDED: ClassVar[str] = "possible_ended"

    STARTED: ClassVar[str] = "started"
    ENDED: ClassVar[str] = "ended"

#   POSSIBLE_STARTED: ClassVar[str] = "possible_started"
#   POSSIBLE_ENDED: ClassVar[str] = "possible_ended" 


class ConversationEvent(BaseModel):
    state: str