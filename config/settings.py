from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Define the application's settings."""

    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_API_VERSION: str
    AZURE_OPENAI_DEPLOYMENT: str

    DEEPGRAM_API_KEY: str
    DEEPGRAM_MODEL: str = "flux-general-en"

    ELEVENLABS_API_KEY: str
    ELEVENLABS_VOICE_ID: str

    LOG_LEVEL: str = "INFO"

    """Configure how settings are loaded."""
    model_config = SettingsConfigDict(
        env_file=".env",
    )

@lru_cache
def get_settings() -> Settings:
    """Create and cache the settings object."""
    return Settings()


settings = get_settings()