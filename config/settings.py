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

    DISABLE_AEC: bool = False

    EDGE_TTS_VOICE: str = "en-GB-SoniaNeural"

    MIC_INPUT_GAIN: float = 0.5

    LOG_LEVEL: str

    """Configure how settings are loaded."""
    model_config = SettingsConfigDict(
        env_file=".env",
    )

@lru_cache
def get_settings() -> Settings:
    """Create and cache the settings object."""
    return Settings()


settings = get_settings()