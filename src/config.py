"""Configuration loading from environment variables."""
from functools import lru_cache
import os
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_app_state_dir() -> str:
    configured = os.getenv("ANYTYPE_AGENT_STATE_DIR")
    if configured:
        return configured
    if os.getenv("KUBERNETES_SERVICE_HOST") or Path("/.dockerenv").exists():
        return "/var/lib/anytype-agent"
    xdg_state = os.getenv("XDG_STATE_HOME")
    if xdg_state:
        return str(Path(xdg_state) / "anytype-agent")
    return str(Path.home() / ".local" / "state" / "anytype-agent")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
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

    # Generic LLM configuration. Prefer these names for new deployments.
    llm_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("LLM_PROVIDER", "DEFAULT_PROVIDER", "llm_provider", "default_provider"),
        description="Default LLM provider (openai, openai-codex, anthropic, ollama)",
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("LLM_BASE_URL", "llm_base_url"),
        description="OpenAI-compatible or provider endpoint URL",
    )
    llm_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "llm_api_key"),
        description="API key for the configured LLM endpoint, if required",
    )
    llm_model: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("LLM_MODEL", "MODEL", "llm_model", "model"),
        description="LLM model for agent",
    )

    # Guardrail LLM configuration. Unset values inherit the main LLM settings.
    guardrail_llm_provider: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GUARDRAIL_LLM_PROVIDER", "guardrail_llm_provider"),
        description="Provider for guardrail checks; defaults to LLM_PROVIDER",
    )
    guardrail_llm_base_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GUARDRAIL_LLM_BASE_URL", "guardrail_llm_base_url"),
        description="Endpoint URL for guardrail checks; defaults to LLM_BASE_URL",
    )
    guardrail_llm_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GUARDRAIL_LLM_API_KEY", "guardrail_llm_api_key"),
        description="API key for guardrail checks; defaults to LLM_API_KEY",
    )
    guardrail_model: Optional[str] = Field(
        default=None,
        description="LLM model for guardrail checks; defaults to LLM_MODEL",
    )

    # OpenAI Codex/ChatGPT subscription auth. Only used with LLM_PROVIDER=openai-codex.
    # Credentials are always read from <Anytype-Agent state root>/auth.json.
    codex_base_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("CODEX_BASE_URL", "codex_base_url"),
        description="Override Codex backend endpoint; defaults to the known Codex responses endpoint",
    )
    codex_auth_issuer: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("CODEX_AUTH_ISSUER", "codex_auth_issuer"),
        description="Override Codex OAuth issuer; defaults to https://auth.openai.com",
    )
    codex_client_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("CODEX_CLIENT_ID", "codex_client_id"),
        description="Override Codex OAuth client id; defaults to Anytype-Agent's Codex OAuth client id",
    )
    codex_refresh_skew_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("CODEX_REFRESH_SKEW_SECONDS", "codex_refresh_skew_seconds"),
        description="Refresh Codex access tokens this many seconds before expiry",
    )

    # Legacy/provider-specific settings. Kept for backward compatibility.
    openai_api_key: Optional[str] = Field(
        default=None,
        description="Legacy OpenAI API key; prefer LLM_API_KEY",
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Legacy Anthropic API key; prefer LLM_API_KEY with LLM_PROVIDER=anthropic",
    )
    ollama_base_url: Optional[str] = Field(
        default=None,
        description="Legacy Ollama base URL; prefer LLM_BASE_URL with LLM_PROVIDER=ollama",
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

    @property
    def model(self) -> str:
        """Backward-compatible alias for llm_model."""
        return self.llm_model

    @property
    def default_provider(self) -> str:
        """Backward-compatible alias for llm_provider."""
        return self.llm_provider


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
