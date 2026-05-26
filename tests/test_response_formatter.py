"""Tests for src/graph/nodes/response_formatter.py."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.graph.state import AgentState
from src.graph.nodes.response_formatter import format_response


class TestFormatResponse:
    """Tests for format_response node."""

    @pytest.mark.asyncio
    async def test_error_state(self):
        state: AgentState = {
            "user_request": "test",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": "Something went wrong",
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": True,
            "error_detail": None,
        }
        result = await format_response(state)
        assert result["output"] == "Error: Something went wrong"

    @pytest.mark.asyncio
    async def test_no_result(self):
        state: AgentState = {
            "user_request": "test",
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
        result = await format_response(state)
        assert result["output"] == "No result available"

    @pytest.mark.asyncio
    async def test_successful_llm_format(self):
        mock_router = MagicMock()
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(content="Your page was created successfully!")
        )
        mock_router.get_route = MagicMock(return_value=mock_provider)

        state: AgentState = {
            "user_request": "create a page",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": {"success": True, "title": "My Page"},
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }

        with patch("src.graph.nodes.response_formatter.get_router", return_value=mock_router):
            result = await format_response(state)

        assert result["output"] == "Your page was created successfully!"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        mock_router = MagicMock()
        mock_router.get_route = MagicMock(side_effect=Exception("LLM error"))

        state: AgentState = {
            "user_request": "create a page",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": {"success": True, "title": "My Page"},
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }

        with patch("src.graph.nodes.response_formatter.get_router", return_value=mock_router):
            result = await format_response(state)

        # Should fallback to string representation of tool_result
        assert "success" in result["output"]

    @pytest.mark.asyncio
    async def test_tool_error_without_is_error(self):
        state: AgentState = {
            "user_request": "test",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": "Missing param",
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        # Only when is_error=True does it return Error: ...
        result = await format_response(state)
        # No result => "No result available" since is_error is False
        assert result["output"] == "No result available"
