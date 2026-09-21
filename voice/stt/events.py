from pydantic import BaseModel 
class TranscriptEvent(BaseModel):
    text : str 
    confidence: float
    is_final: bool
