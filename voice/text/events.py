from dataclasses import dataclass


@dataclass(slots=True)
class SentenceEvent:

    text: str