"""Tests for src/graph/nodes/tool_router.py."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.graph.state import AgentState
from src.graph.nodes.tool_router import execute_tool, _intent_to_tool


class TestIntentToTool:
    """Tests for _intent_to_tool mapping."""

    def test_create_page(self):
        assert _intent_to_tool("create_page") == "create_page"

    def test_read_page(self):
        assert _intent_to_tool("read_page") == "read_page"

    def test_delete_page(self):
        assert _intent_to_tool("delete_page") == "delete_page"

    def test_create_task(self):
        assert _intent_to_tool("create_task") == "create_task"

    def test_complete_task(self):
        assert _intent_to_tool("complete_task") == "complete_task"

    def test_list_projects(self):
        assert _intent_to_tool("list_projects") == "list_projects"

    def test_search_objects(self):
        assert _intent_to_tool("search_objects") == "search"

    def test_unknown(self):
        assert _intent_to_tool("unknown") is None

    def test_none(self):
        assert _intent_to_tool("nonexistent_intent") is None


class TestExecuteTool:
    """Tests for execute_tool node."""

    @pytest.mark.asyncio
    async def test_unknown_intent(self):
        state: AgentState = {
            "user_request": "hello",
            "space_id": None,
            "intent": "unknown",
            "object_type": None,
            "tool_params": {},
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }
        result = await execute_tool(state)
        assert result.get("is_error") is True
        assert "No tool found" in result.get("tool_error", "")

    @pytest.mark.asyncio
    async def test_tool_execution(self):
        mock_tool = AsyncMock()
        mock_tool.execute_with_validation = AsyncMock(return_value={"success": True, "id": "123"})
        mock_registry = MagicMock()
        mock_registry.get_tool = MagicMock(return_value=mock_tool)

        state: AgentState = {
            "user_request": "create a page",
            "space_id": "space_1",
            "intent": "create_page",
            "object_type": None,
            "tool_params": {"title": "Test Page"},
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }

        with patch("src.graph.nodes.tool_router.get_tool_registry", return_value=mock_registry):
            result = await execute_tool(state)

        assert result["tool_name"] == "create_page"
        assert result["tool_result"]["success"] is True
        mock_tool.execute_with_validation.assert_awaited_once_with(title="Test Page", space_id="space_1")

    @pytest.mark.asyncio
    async def test_tool_execution_failure(self):
        mock_tool = AsyncMock()
        mock_tool.execute_with_validation = AsyncMock(side_effect=Exception("API error"))
        mock_registry = MagicMock()
        mock_registry.get_tool = MagicMock(return_value=mock_tool)

        state: AgentState = {
            "user_request": "create a page",
            "space_id": None,
            "intent": "create_page",
            "object_type": None,
            "tool_params": {},
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": None,
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
        }

        with patch("src.graph.nodes.tool_router.get_tool_registry", return_value=mock_registry):
            result = await execute_tool(state)

        assert result.get("is_error") is True
        assert "API error" in result.get("tool_error", "")

    @pytest.mark.asyncio
    async def test_tool_registry_unavailable(self):
        with patch("src.graph.nodes.tool_router.get_tool_registry", side_effect=ImportError):
            state: AgentState = {
                "user_request": "create a page",
                "space_id": None,
                "intent": "create_page",
                "object_type": None,
                "tool_params": {},
                "tool_name": None,
                "tool_result": None,
                "tool_error": None,
                "output": None,
                "blocked": False,
                "block_reason": None,
                "is_error": False,
                "error_detail": None,
            }
            result = await execute_tool(state)
            assert result.get("is_error") is True
            assert "not available" in result.get("tool_error", "").lower()
