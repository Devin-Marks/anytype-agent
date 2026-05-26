"""Configuration loading from environment variables."""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Anytype API
    anytype_base_url: str = Field(
        default="http://anytype-cli:31012",
        description="Base URL for Anytype API",
    )
    anytype_api_key: str = Field(
        description="API key for Anytype",
    )
    anytype_api_version: str = Field(
        default="2025-11-08",
        description="Anytype API version",
    )

    # LLM Configuration
    openai_api_key: str = Field(
        description="OpenAI API key",
    )
    model: str = Field(
        default="gpt-4o",
        description="LLM model for agent",
    )
    guardrail_model: str = Field(
        default="gpt-4o-mini",
        description="LLM model for guardrail checks",
    )
    default_provider: str = Field(
        default="openai",
        description="Default LLM provider (openai, anthropic, ollama)",
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude",
    )
    ollama_base_url: Optional[str] = Field(
        default=None,
        description="Base URL for Ollama (e.g., http://localhost:11434)",
    )

    # Guardrails
    guardrails_config_path: str = Field(
        default="/etc/guardrails",
        description="Path to NeMo Guardrails configuration",
    )

    # Safety
    shell_protection_enabled: bool = Field(
        default=True,
        description="Enable openshell protection",
    )
    max_input_length: int = Field(
        default=10000,
        description="Maximum input length in characters",
    )

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()