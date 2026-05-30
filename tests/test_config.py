"""Tests for src/config.py."""
import os
from unittest.mock import patch

import pytest

from src.config import Settings, get_settings


class TestSettings:
    """Tests for Settings configuration loading."""

    def test_default_values(self):
        """Settings should have sensible defaults when env vars are missing."""
        with patch.dict(os.environ, {"ANYTYPE_API_KEY": "test-key"}, clear=True):
            s = Settings()
            assert s.anytype_base_url == "http://anytype-cli:31012"
            assert s.anytype_api_version == "2025-11-08"
            assert s.llm_provider == "openai"
            assert s.llm_base_url is None
            assert s.llm_api_key is None
            assert s.llm_model == "gpt-4o"
            assert s.model == "gpt-4o"
            assert s.guardrail_llm_provider is None
            assert s.guardrail_llm_base_url is None
            assert s.guardrail_llm_api_key is None
            assert s.guardrail_model is None
            assert s.anytype_agent_auth_file == "/var/lib/anytype-agent/auth.json"
            assert s.codex_base_url is None
            assert s.codex_auth_issuer is None
            assert s.codex_client_id is None
            assert s.codex_refresh_skew_seconds == 300
            assert s.default_provider == "openai"
            assert s.openai_api_key is None
            assert s.guardrails_config_path == "/etc/guardrails"
            assert s.shell_protection_enabled is True
            assert s.max_input_length == 10000
            assert s.host == "0.0.0.0"
            assert s.port == 8000
            assert s.log_level == "INFO"

    def test_generic_env_override(self):
        """Generic environment variables should override defaults."""
        env = {
            "ANYTYPE_BASE_URL": "http://custom:8080",
            "ANYTYPE_API_KEY": "custom-key",
            "ANYTYPE_API_VERSION": "v2",
            "LLM_PROVIDER": "openai",
            "LLM_BASE_URL": "https://llm.example/v1",
            "LLM_API_KEY": "generic-key",
            "LLM_MODEL": "custom-model",
            "GUARDRAIL_LLM_PROVIDER": "openai",
            "GUARDRAIL_LLM_BASE_URL": "https://guard.example/v1",
            "GUARDRAIL_LLM_API_KEY": "guard-key",
            "GUARDRAIL_MODEL": "guard-model",
            "ANYTYPE_AGENT_AUTH_FILE": "/custom/anytype-agent/auth.json",
            "CODEX_BASE_URL": "https://codex.example/responses",
            "CODEX_AUTH_ISSUER": "https://auth.example",
            "CODEX_CLIENT_ID": "client-123",
            "CODEX_REFRESH_SKEW_SECONDS": "120",
            "GUARDRAILS_CONFIG_PATH": "/custom/guardrails",
            "SHELL_PROTECTION_ENABLED": "false",
            "MAX_INPUT_LENGTH": "5000",
            "HOST": "127.0.0.1",
            "PORT": "9000",
            "LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings()
            assert s.anytype_base_url == "http://custom:8080"
            assert s.anytype_api_key == "custom-key"
            assert s.anytype_api_version == "v2"
            assert s.llm_provider == "openai"
            assert s.llm_base_url == "https://llm.example/v1"
            assert s.llm_api_key == "generic-key"
            assert s.llm_model == "custom-model"
            assert s.guardrail_llm_provider == "openai"
            assert s.guardrail_llm_base_url == "https://guard.example/v1"
            assert s.guardrail_llm_api_key == "guard-key"
            assert s.guardrail_model == "guard-model"
            assert s.anytype_agent_auth_file == "/custom/anytype-agent/auth.json"
            assert s.codex_base_url == "https://codex.example/responses"
            assert s.codex_auth_issuer == "https://auth.example"
            assert s.codex_client_id == "client-123"
            assert s.codex_refresh_skew_seconds == 120
            assert s.guardrails_config_path == "/custom/guardrails"
            assert s.shell_protection_enabled is False
            assert s.max_input_length == 5000
            assert s.host == "127.0.0.1"
            assert s.port == 9000
            assert s.log_level == "DEBUG"

    def test_legacy_env_compatibility(self):
        """Legacy provider env vars should still populate compatible settings."""
        env = {
            "ANYTYPE_API_KEY": "custom-key",
            "OPENAI_API_KEY": "custom-openai",
            "MODEL": "gpt-4",
            "GUARDRAIL_MODEL": "gpt-3.5-turbo",
            "DEFAULT_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "anthro-key",
            "OLLAMA_BASE_URL": "http://ollama:11434",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings()
            assert s.llm_model == "gpt-4"
            assert s.model == "gpt-4"
            assert s.guardrail_model == "gpt-3.5-turbo"
            assert s.llm_provider == "anthropic"
            assert s.default_provider == "anthropic"
            assert s.openai_api_key == "custom-openai"
            assert s.anthropic_api_key == "anthro-key"
            assert s.ollama_base_url == "http://ollama:11434"

    def test_required_fields(self):
        """Only ANYTYPE_API_KEY is required at settings load time."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception):
                Settings()

        with patch.dict(os.environ, {"ANYTYPE_API_KEY": "k1"}, clear=True):
            s = Settings()
            assert s.openai_api_key is None

    def test_case_insensitive_env(self):
        """Env var names should be case-insensitive."""
        env = {
            "ANYTYPE_API_KEY": "k1",
            "llm_model": "gpt-4-turbo",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings()
            assert s.llm_model == "gpt-4-turbo"

    def test_generic_env_preferred_over_legacy(self):
        """Generic LLM env vars should win when legacy names are also present."""
        env = {
            "ANYTYPE_API_KEY": "k1",
            "LLM_PROVIDER": "ollama",
            "DEFAULT_PROVIDER": "anthropic",
            "LLM_MODEL": "llama3",
            "MODEL": "gpt-4",
            "LLM_API_KEY": "generic-key",
            "OPENAI_API_KEY": "legacy-openai",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings()
            assert s.llm_provider == "ollama"
            assert s.llm_model == "llama3"
            assert s.llm_api_key == "generic-key"
            assert s.openai_api_key == "legacy-openai"


class TestGetSettings:
    """Tests for get_settings cached function."""

    def test_returns_same_instance(self):
        """get_settings should return a cached instance."""
        with patch.dict(os.environ, {"ANYTYPE_API_KEY": "k1"}, clear=True):
            get_settings.cache_clear()
            s1 = get_settings()
            s2 = get_settings()
            assert s1 is s2
            get_settings.cache_clear()

    def test_cache_clear_works(self):
        """Clearing cache should yield a new instance."""
        with patch.dict(os.environ, {"ANYTYPE_API_KEY": "k1"}, clear=True):
            get_settings.cache_clear()
            s1 = get_settings()
            get_settings.cache_clear()
            s2 = get_settings()
            assert s1 is not s2
            assert s1.anytype_api_key == s2.anytype_api_key
            get_settings.cache_clear()
