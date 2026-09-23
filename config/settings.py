from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration for ArthaVani."""

    GROWW_API_KEY: str | None = None
    GROWW_API_SECRET: str | None = None

    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = ""

    DEEPGRAM_API_KEY: str
    DEEPGRAM_MODEL: str = "nova-3"

    DISABLE_AEC: bool = False
    EDGE_TTS_VOICE: str = "en-GB-SoniaNeural"
    LOG_LEVEL: str = "info"

    WATCHLIST_DB_PATH: str = "data/watchlist.db"

    DATABASE_URL: str | None = None

    CONVERSATION_USER_ID: str = "default-user"
    CONVERSATION_ID: str = "default"

    # FastAPI authentication
    API_JWT_SECRET_KEY: str = ""
    API_JWT_ALGORITHM: str = "HS256"
    API_JWT_EXPIRE_MINUTES: int = 60
    API_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # Encrypt stored Groww credentials at rest.
    GROWW_CREDENTIALS_ENCRYPTION_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
