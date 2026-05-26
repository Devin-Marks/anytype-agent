"""Tests for src/graph/state.py."""
from typing import get_type_hints

from src.graph.state import AgentState, BlockedState


class TestAgentState:
    """Tests for AgentState TypedDict."""

    def test_has_required_fields(self):
        """AgentState should define all expected keys."""
        keys = get_type_hints(AgentState).keys()
        expected = {
            "user_request",
            "space_id",
            "intent",
            "object_type",
            "tool_params",
            "tool_name",
            "tool_result",
            "tool_error",
            "output",
            "blocked",
            "block_reason",
            "is_error",
            "error_detail",
        }
        assert expected.issubset(keys)

    def test_user_request_required(self):
        """user_request should be required (not Optional)."""
        hints = get_type_hints(AgentState)
        # str means required, not Optional[str]
        assert "Optional" not in str(hints["user_request"])

    def test_blocked_required(self):
        """blocked should be a required bool field."""
        hints = get_type_hints(AgentState)
        assert "bool" in str(hints["blocked"])

    def test_space_id_optional(self):
        """space_id should be Optional."""
        hints = get_type_hints(AgentState)
        assert "Optional" in str(hints["space_id"])


class TestBlockedState:
    """Tests for BlockedState TypedDict."""

    def test_minimal_fields(self):
        """BlockedState should have minimal fields for blocked responses."""
        keys = get_type_hints(BlockedState).keys()
        assert keys == {"user_request", "blocked", "block_reason"}
