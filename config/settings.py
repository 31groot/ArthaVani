
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration for the native LangGraph tool layer."""

    GROWW_API_KEY: str | None = None
    GROWW_API_SECRET: str | None = None
    GROWW_ACCESS_TOKEN: str | None = None

    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = ""

    DEEPGRAM_API_KEY: str
    DEEPGRAM_MODEL: str = "nova-3"

    DISABLE_AEC: bool = False
    EDGE_TTS_VOICE: str = "en-GB-SoniaNeural"
    LOG_LEVEL: str = "info"

    WATCHLIST_DB_PATH: str = "data/watchlist.db"

    model_config = SettingsConfigDict(
        env_file=".env",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
