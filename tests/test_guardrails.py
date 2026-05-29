"""Tests for src/graph/nodes/guardrails.py."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.graph.state import AgentState
from src.graph.nodes import guardrails as guardrails_module
from src.graph.nodes.guardrails import (
    input_guardrail,
    output_guardrail,
    llm_input_guardrail,
    llm_output_guardrail,
    _is_refusal,
)


class TestIsRefusal:
    """Tests for _is_refusal helper."""

    def test_detects_i_cannot(self):
        assert _is_refusal({"content": "I cannot help with that"}) is True

    def test_detects_i_cannot_mixed_case(self):
        assert _is_refusal({"content": "I Cannot Do This"}) is True

    def test_detects_im_not_able(self):
        assert _is_refusal({"content": "I'm not able to assist"}) is True

    def test_detects_refuse(self):
        assert _is_refusal({"content": "I refuse this request"}) is True

    def test_non_refusal(self):
        assert _is_refusal({"content": "Here is the answer"}) is False

    def test_empty(self):
        assert _is_refusal({"content": ""}) is False


class TestGetRails:
    """Tests for NeMo rails initialization."""

    def test_uses_top_level_settings_import(self, mock_settings):
        mock_settings.guardrails_config_path = "/custom/guardrails"
        mock_rails = MagicMock()
        mock_config = MagicMock()

        with patch("src.graph.nodes.guardrails.NEMO_AVAILABLE", True):
            with patch("src.graph.nodes.guardrails.RailsConfig") as rails_config:
                with patch("src.graph.nodes.guardrails.LLMRails", return_value=mock_rails) as llm_rails:
                    with patch("src.config.get_settings", return_value=mock_settings):
                        guardrails_module._rails = None
                        rails_config.from_path.return_value = mock_config
                        assert guardrails_module.get_rails() is mock_rails

        rails_config.from_path.assert_called_once_with("/custom/guardrails")
        llm_rails.assert_called_once_with(mock_config)
        guardrails_module._rails = None


class TestInputGuardrail:
    """Tests for input_guardrail node."""

    @pytest.mark.asyncio
    async def test_nemo_unavailable_returns_not_blocked(self):
        """When NeMo is unavailable, should return blocked=False."""
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        result = await input_guardrail(state)
        assert result.get("blocked") is False

    @pytest.mark.asyncio
    async def test_nemo_blocks_refusal(self):
        """When NeMo returns refusal, should block."""
        mock_rails = AsyncMock()
        mock_rails.generate_async = AsyncMock(
            return_value={"content": "I cannot help with that"}
        )
        state: AgentState = {
            "user_request": "harmful request",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        with patch("src.graph.nodes.guardrails.get_rails", return_value=mock_rails):
            with patch("src.graph.nodes.guardrails.NEMO_AVAILABLE", True):
                result = await input_guardrail(state)
        assert result.get("blocked") is True
        assert "guardrail" in result.get("block_reason", "")

    @pytest.mark.asyncio
    async def test_nemo_error_fails_open(self):
        """When NeMo raises exception, should fail open (not block)."""
        mock_rails = AsyncMock()
        mock_rails.generate_async = AsyncMock(side_effect=Exception("API down"))
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        with patch("src.graph.nodes.guardrails.get_rails", return_value=mock_rails):
            with patch("src.graph.nodes.guardrails.NEMO_AVAILABLE", True):
                result = await input_guardrail(state)
        assert result.get("blocked") is False


class TestOutputGuardrail:
    """Tests for output_guardrail node."""

    @pytest.mark.asyncio
    async def test_nemo_unavailable_returns_not_blocked(self):
        """When NeMo is unavailable, should return blocked=False."""
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": "some output",
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        result = await output_guardrail(state)
        assert result.get("blocked") is False

    @pytest.mark.asyncio
    async def test_empty_output_not_blocked(self):
        """When output is empty, should not make LLM call."""
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": "",
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        result = await output_guardrail(state)
        assert result.get("blocked") is False

    @pytest.mark.asyncio
    async def test_nemo_error_fails_closed(self):
        """When NeMo raises exception, should fail closed (block)."""
        mock_rails = AsyncMock()
        mock_rails.generate_async = AsyncMock(side_effect=Exception("API down"))
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": "some output",
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        with patch("src.graph.nodes.guardrails.get_rails", return_value=mock_rails):
            with patch("src.graph.nodes.guardrails.NEMO_AVAILABLE", True):
                result = await output_guardrail(state)
        assert result.get("blocked") is True
        assert result.get("output") == "I cannot help with that."


class TestLLMInputGuardrail:
    """Tests for llm_input_guardrail (non-NeMo fallback)."""

    @pytest.mark.asyncio
    async def test_safe_input(self):
        mock_router = MagicMock()
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(content="safe")
        )
        mock_router.get_route = MagicMock(return_value=mock_provider)
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        with patch("src.graph.nodes.guardrails.get_router", return_value=mock_router):
            result = await llm_input_guardrail(state)
        assert result.get("blocked") is False

    @pytest.mark.asyncio
    async def test_unsafe_input(self):
        mock_router = MagicMock()
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(content="unsafe: harmful content detected")
        )
        mock_router.get_route = MagicMock(return_value=mock_provider)
        state: AgentState = {
            "user_request": "bad stuff",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        with patch("src.graph.nodes.guardrails.get_router", return_value=mock_router):
            result = await llm_input_guardrail(state)
        assert result.get("blocked") is True
        assert "unsafe" in result.get("block_reason", "")

    @pytest.mark.asyncio
    async def test_llm_error_fails_open(self):
        mock_router = MagicMock()
        mock_router.get_route = MagicMock(side_effect=Exception("LLM down"))
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        with patch("src.graph.nodes.guardrails.get_router", return_value=mock_router):
            result = await llm_input_guardrail(state)
        assert result.get("blocked") is False


class TestLLMOutputGuardrail:
    """Tests for llm_output_guardrail (non-NeMo fallback)."""

    @pytest.mark.asyncio
    async def test_empty_output_short_circuits(self):
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": "",
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        result = await llm_output_guardrail(state)
        assert result.get("blocked") is False

    @pytest.mark.asyncio
    async def test_llm_error_fails_closed(self):
        mock_router = MagicMock()
        mock_router.get_route = MagicMock(side_effect=Exception("LLM down"))
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": "some output",
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        with patch("src.graph.nodes.guardrails.get_router", return_value=mock_router):
            result = await llm_output_guardrail(state)
        assert result.get("blocked") is True
        assert result.get("output") == "I cannot help with that."
