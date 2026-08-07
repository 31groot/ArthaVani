from dataclasses import dataclass

@dataclass(slot=True)
class ChatMessage:
    role: str
    content: str
