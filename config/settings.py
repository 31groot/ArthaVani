from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Define the application's settings."""


    GROWW_API_KEY: str | None = None
    GROWW_API_SECRET: str | None = None
    GROWW_ACCESS_TOKEN: str | None = None
    KITE_API_KEY: str | None = None
    KITE_API_SECRET: str | None = None
    ZERODHA_MCP_URL: str = "http://127.0.0.1:8080/mcp"
    ZERODHA_KITE_SERVER_DIR: str = "third_party/kite-mcp-server"
    ZERODHA_KITE_HOST: str = "127.0.0.1"
    ZERODHA_KITE_PORT: int = 8080
    ZERODHA_KITE_PUBLIC_BASE_URL: str = "http://127.0.0.1:8080"
    
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