from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):


    azure_openai_endpoint: str = Field(
        validation_alias="AZURE_OPENAI_ENDPOINT"
    )

    azure_openai_api_key: str = Field(
        validation_alias="AZURE_OPENAI_API_KEY"
    )

    azure_openai_api_version: str = Field(
        default="2025-04-01-preview",
        validation_alias="AZURE_OPENAI_API_VERSION"
    )

    azure_openai_deployment: str = Field(
        validation_alias="AZURE_OPENAI_DEPLOYMENT"
    )


    deepgram_api_key: str = Field(
        validation_alias="DEEPGRAM_API_KEY"
    )

    deepgram_model: str = Field(
        default="nova-3",
        validation_alias="DEEPGRAM_MODEL"
    )

    elevenlabs_api_key: str = Field(
        validation_alias="ELEVENLABS_API_KEY"
    )

    elevenlabs_voice_id: str = Field(
        validation_alias="ELEVENLABS_VOICE_ID"
    )

    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:

    return Settings()


settings = get_settings()