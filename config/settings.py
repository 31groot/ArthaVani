from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Define the application's settings."""
    
    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str =""
    GROQ_MODEL: str =""


    DEEPGRAM_API_KEY: str
    DEEPGRAM_MODEL: str = "nova-3"

    DISABLE_AEC: bool = False

    EDGE_TTS_VOICE: str = "en-GB-SoniaNeural"

    LOG_LEVEL: str ="info"

    """Configure how settings are loaded."""
    model_config = SettingsConfigDict(
        env_file=".env",
    )

@lru_cache
def get_settings() -> Settings:
    """Create and cache the settings object."""
    return Settings()


settings = get_settings()