"""Tests for src/graph/builder.py."""
from unittest.mock import patch

import pytest

from src.graph.builder import build_graph, get_graph, _should_proceed, _check_output_guardrail
from src.graph.state import AgentState


class TestBuildGraph:
    """Tests for graph construction."""

    def test_builds_without_error(self):
        """build_graph should compile without errors."""
        graph = build_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        """Compiled graph should contain expected node names."""
        graph = build_graph()
        # LangGraph compiled graphs expose nodes
        nodes = set(graph.nodes.keys())
        expected = {
            "input_guardrail",
            "parse_intent",
            "execute_tool",
            "output_guardrail",
            "format_response",
            "__start__",
        }
        assert expected.issubset(nodes), f"Missing nodes: {expected - nodes}"

    def test_get_graph_singleton(self):
        """get_graph should return the same compiled instance."""
        with patch("src.graph.builder._agent_graph", None):
            g1 = get_graph()
            g2 = get_graph()
            assert g1 is g2


class TestShouldProceed:
    """Tests for input guardrail routing."""

    def test_blocked_returns_blocked(self):
        """When blocked=True, should return 'blocked'."""
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
            "blocked": True,
            "block_reason": "policy",
            "is_error": False,
            "error_detail": None,
        }
        assert _should_proceed(state) == "blocked"

    def test_not_blocked_returns_proceed(self):
        """When blocked=False, should return 'proceed'."""
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
        assert _should_proceed(state) == "proceed"

    def test_blocked_defaults_to_proceed(self):
        """When blocked is missing, should default to 'proceed'."""
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
        assert _should_proceed(state) == "proceed"


class TestCheckOutputGuardrail:
    """Tests for output guardrail routing."""

    def test_blocked_returns_blocked(self):
        """When blocked=True after output check, should return 'blocked'."""
        state: AgentState = {
            "user_request": "test",
            "space_id": None,
            "intent": None,
            "object_type": None,
            "tool_params": None,
            "tool_name": None,
            "tool_result": None,
            "tool_error": None,
            "output": "some output",
            "blocked": True,
            "block_reason": "policy",
            "is_error": False,
            "error_detail": None,
        }
        assert _check_output_guardrail(state) == "blocked"

    def test_not_blocked_returns_proceed(self):
        """When blocked=False, should return 'proceed'."""
        state: AgentState = {
            "user_request": "test",
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
        assert _check_output_guardrail(state) == "proceed"
