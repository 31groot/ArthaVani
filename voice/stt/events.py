from dataclasses import dataclass

@dataclass(slots=True)
class TranscriptEvent:
    text: str
    confidence: float
    is_final: bool