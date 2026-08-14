from dataclasses import dataclass

@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass
class TokenEvent:
    text: str