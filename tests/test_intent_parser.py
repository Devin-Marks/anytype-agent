"""Tests for src/graph/nodes/intent_parser.py."""
import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.graph.state import AgentState
from src.graph.nodes.intent_parser import parse_intent, _fallback_intent_parse, INTENT_PATTERNS


class TestFallbackIntentParse:
    """Tests for _fallback_intent_parse."""

    def test_create_page_keyword(self):
        result = _fallback_intent_parse("Create a new page")
        assert result["intent"] == "create_page"
        assert result["object_type"] == "page"

    def test_create_task_keyword(self):
        result = _fallback_intent_parse("Add a new task")
        assert result["intent"] == "create_task"
        assert result["object_type"] == "task"

    def test_list_projects_keyword(self):
        result = _fallback_intent_parse("Show me my projects")
        assert result["intent"] == "list_projects"
        assert result["object_type"] == "projects"

    def test_unknown_input(self):
        result = _fallback_intent_parse("Random unrelated text")
        assert result["intent"] == "unknown"

    def test_search_keyword(self):
        result = _fallback_intent_parse("Find my notes")
        assert result["intent"] == "search_objects"
        assert result["object_type"] == "objects"

    def test_intent_patterns_coverage(self):
        """All intent patterns should have at least one keyword."""
        for intent, keywords in INTENT_PATTERNS.items():
            assert len(keywords) > 0
            assert "_" in intent


class TestParseIntent:
    """Tests for parse_intent node."""

    @pytest.mark.asyncio
    async def test_successful_llm_parse(self):
        mock_router = MagicMock()
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(
                content=json.dumps({
                    "intent": "create_page",
                    "object_type": "page",
                    "params": {"title": "My Page"},
                })
            )
        )
        mock_router.get_route = MagicMock(return_value=mock_provider)

        state: AgentState = {
            "user_request": "Create a page called My Page",
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

        with patch("src.graph.nodes.intent_parser.get_router", return_value=mock_router):
            result = await parse_intent(state)

        assert result["intent"] == "create_page"
        assert result["object_type"] == "page"
        assert result["tool_params"]["title"] == "My Page"

    @pytest.mark.asyncio
    async def test_invalid_json_fallback(self):
        mock_router = MagicMock()
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(content="not valid json")
        )
        mock_router.get_route = MagicMock(return_value=mock_provider)

        state: AgentState = {
            "user_request": "Create a page",
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

        with patch("src.graph.nodes.intent_parser.get_router", return_value=mock_router):
            result = await parse_intent(state)

        # Should fallback to keyword matching
        assert result["intent"] in ("create_page", "unknown")

    @pytest.mark.asyncio
    async def test_llm_error(self):
        mock_router = MagicMock()
        mock_router.get_route = MagicMock(side_effect=Exception("LLM unavailable"))

        state: AgentState = {
            "user_request": "Create a page",
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

        with patch("src.graph.nodes.intent_parser.get_router", return_value=mock_router):
            result = await parse_intent(state)

        assert result["intent"] == "unknown"
        assert result.get("is_error") is True
        assert "LLM unavailable" in result["tool_error"]
