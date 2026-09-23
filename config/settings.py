
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

    # Postgres connection string used by AsyncPostgresSaver to persist
    # LangGraph conversation state (checkpoints), keyed by thread_id.
    #
    # Example: postgresql://user:password@localhost:5432/arthavani
    #
    # Optional and defaults to None: when unset, FinanceAgentRunner falls
    # back to its original stateless behavior (no checkpointer attached).
    # This keeps unit tests -- which construct FinanceAgentRunner directly
    # without a database -- working without requiring Postgres.
    DATABASE_URL: str | None = None

    # Stable LangGraph thread identifier used for the default voice
    # conversation. Override this per user/session in the environment.
    CONVERSATION_THREAD_ID: str = "default-user"

    model_config = SettingsConfigDict(
        env_file=".env",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
