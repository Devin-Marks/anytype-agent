"""Shared test fixtures and mocks."""
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Generator
import pytest


# ── Config fixture ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_settings():
    """Return a fully-configured Settings mock for tests."""
    from src.config import Settings

    settings = Settings(
        anytype_base_url="http://anytype-cli:31012",
        anytype_api_key="test-anytype-key",
        anytype_api_version="2025-11-08",
        openai_api_key="test-openai-key",
        model="gpt-4o",
        guardrail_model="gpt-4o-mini",
        default_provider="openai",
        anthropic_api_key=None,
        ollama_base_url=None,
        guardrails_config_path="/etc/guardrails",
        shell_protection_enabled=True,
        max_input_length=10000,
        host="0.0.0.0",
        port=8000,
        log_level="INFO",
    )
    return settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear settings lru_cache between tests."""
    from src.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── LLM Provider fixtures ───────────────────────────────────────────────────

@pytest.fixture
def mock_llm_provider():
    """Return a mock BaseLLMProvider."""
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=MagicMock(
            content='{"intent": "create_page", "object_type": "page", "params": {"title": "Test"}}',
            model="gpt-4o",
            provider="openai",
            usage={},
            raw_response=None,
            finish_reason="stop",
        )
    )
    provider.stream = AsyncMock(return_value="mock chunk")
    provider.health_check = AsyncMock(return_value=True)
    return provider


@pytest.fixture
def mock_llm_router(mock_llm_provider):
    """Return a mock LLMRouter with a configured provider."""
    router = MagicMock()
    router.get_route = MagicMock(return_value=mock_llm_provider)
    router.register_route = MagicMock()
    router.set_default = MagicMock()
    return router


@pytest.fixture
def patch_llm_router(mock_llm_router):
    """Patch get_router globally for tests."""
    with patch("src.llm.router.get_router", return_value=mock_llm_router):
        yield mock_llm_router


# ── Guardrail fixtures ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_nemo_guardrails():
    """Ensure NeMo Guardrails is treated as unavailable in tests."""
    with patch("src.graph.nodes.guardrails.NEMO_AVAILABLE", False):
        yield


# ── Sandbox fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def patch_openshell_unavailable():
    """Ensure OpenShell is treated as unavailable in tests."""
    with patch("src.safety.sandbox_manager._check_openshell_available", return_value=False):
        yield


# ── Tool registry fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tool_registry():
    """Return a fresh tool registry."""
    from src.graph.tools.registry import ToolRegistry
    return ToolRegistry()


@pytest.fixture
def registered_registry():
    """Return a tool registry with default tools registered."""
    from src.graph.tools.registry import ToolRegistry
    from src.graph.tools.pages import (
        CreatePageTool, ReadPageTool, UpdatePageTool, DeletePageTool,
    )
    from src.graph.tools.tasks import CreateTaskTool, UpdateTaskTool, CompleteTaskTool
    from src.graph.tools.projects import ListProjectsTool
    from src.graph.tools.queries import SearchTool

    reg = ToolRegistry()
    reg.register(CreatePageTool())
    reg.register(ReadPageTool())
    reg.register(UpdatePageTool())
    reg.register(DeletePageTool())
    reg.register(CreateTaskTool())
    reg.register(UpdateTaskTool())
    reg.register(CompleteTaskTool())
    reg.register(ListProjectsTool())
    reg.register(SearchTool())
    return reg


# ── FastAPI client fixture ─────────────────────────────────────────────────

@pytest.fixture
def test_client(mock_settings):
    """Return a FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from src.main import app

    with patch("src.config.get_settings", return_value=mock_settings):
        with TestClient(app) as client:
            yield client
