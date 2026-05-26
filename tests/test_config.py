"""Tests for src/config.py."""
import os
from unittest.mock import patch

import pytest

from src.config import Settings, get_settings


class TestSettings:
    """Tests for Settings configuration loading."""

    def test_default_values(self):
        """Settings should have sensible defaults when env vars are missing."""
        with patch.dict(os.environ, {
            "ANYTYPE_API_KEY": "test-key",
            "OPENAI_API_KEY": "openai-key",
        }, clear=True):
            s = Settings()
            assert s.anytype_base_url == "http://anytype-cli:31012"
            assert s.anytype_api_version == "2025-11-08"
            assert s.model == "gpt-4o"
            assert s.guardrail_model == "gpt-4o-mini"
            assert s.default_provider == "openai"
            assert s.guardrails_config_path == "/etc/guardrails"
            assert s.shell_protection_enabled is True
            assert s.max_input_length == 10000
            assert s.host == "0.0.0.0"
            assert s.port == 8000
            assert s.log_level == "INFO"

    def test_env_override(self):
        """Environment variables should override defaults."""
        env = {
            "ANYTYPE_BASE_URL": "http://custom:8080",
            "ANYTYPE_API_KEY": "custom-key",
            "ANYTYPE_API_VERSION": "v2",
            "OPENAI_API_KEY": "custom-openai",
            "MODEL": "gpt-4",
            "GUARDRAIL_MODEL": "gpt-3.5-turbo",
            "DEFAULT_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "anthro-key",
            "OLLAMA_BASE_URL": "http://ollama:11434",
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
            assert s.model == "gpt-4"
            assert s.guardrail_model == "gpt-3.5-turbo"
            assert s.default_provider == "anthropic"
            assert s.anthropic_api_key == "anthro-key"
            assert s.ollama_base_url == "http://ollama:11434"
            assert s.guardrails_config_path == "/custom/guardrails"
            assert s.shell_protection_enabled is False
            assert s.max_input_length == 5000
            assert s.host == "127.0.0.1"
            assert s.port == 9000
            assert s.log_level == "DEBUG"

    def test_required_fields(self):
        """ANYTYPE_API_KEY and OPENAI_API_KEY are required."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception):
                Settings()

    def test_case_insensitive_env(self):
        """Env var names should be case-insensitive."""
        # model_config has case_sensitive=False
        with patch.dict(os.environ, {"model": "gpt-4-turbo"}, clear=True):
            # Need required keys too
            env = {
                "ANYTYPE_API_KEY": "k1",
                "OPENAI_API_KEY": "k2",
                "model": "gpt-4-turbo",
            }
            with patch.dict(os.environ, env, clear=True):
                s = Settings()
                assert s.model == "gpt-4-turbo"


class TestGetSettings:
    """Tests for get_settings cached function."""

    def test_returns_same_instance(self):
        """get_settings should return a cached instance."""
        with patch.dict(os.environ, {
            "ANYTYPE_API_KEY": "k1",
            "OPENAI_API_KEY": "k2",
        }, clear=True):
            get_settings.cache_clear()
            s1 = get_settings()
            s2 = get_settings()
            assert s1 is s2
            get_settings.cache_clear()

    def test_cache_clear_works(self):
        """Clearing cache should yield a new instance."""
        with patch.dict(os.environ, {
            "ANYTYPE_API_KEY": "k1",
            "OPENAI_API_KEY": "k2",
        }, clear=True):
            get_settings.cache_clear()
            s1 = get_settings()
            get_settings.cache_clear()
            s2 = get_settings()
            # Same values, different objects
            assert s1 is not s2
            assert s1.anytype_api_key == s2.anytype_api_key
            get_settings.cache_clear()
