"""Tests for src/schemas.py."""
import pytest
from pydantic import ValidationError

from src.schemas import AgentRequest, AgentResponse, ErrorResponse


class TestAgentRequest:
    """Tests for AgentRequest schema."""

    def test_minimal_valid(self):
        """Request with just input should be valid."""
        req = AgentRequest(input="hello")
        assert req.input == "hello"
        assert req.space_id is None
        assert req.thread_id is None
        assert req.prompt_name is None

    def test_full_valid(self):
        """Request with all fields should be valid."""
        req = AgentRequest(
            input="create a page",
            space_id="space_123",
            thread_id="thread_456",
            prompt_name="default",
        )
        assert req.input == "create a page"
        assert req.space_id == "space_123"
        assert req.thread_id == "thread_456"
        assert req.prompt_name == "default"

    def test_input_required(self):
        """Request without input should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            AgentRequest()
        assert "input" in str(exc_info.value)

    def test_input_empty_string_allowed(self):
        """Empty string input is technically allowed by schema."""
        req = AgentRequest(input="")
        assert req.input == ""


class TestAgentResponse:
    """Tests for AgentResponse schema."""

    def test_minimal_valid(self):
        """Response with no fields should use defaults."""
        resp = AgentResponse()
        assert resp.output is None
        assert resp.blocked is False
        assert resp.block_reason is None
        assert resp.is_error is False
        assert resp.error_detail is None
        assert resp.intent is None
        assert resp.tool_name is None

    def test_full_valid(self):
        """Response with all fields should be valid."""
        resp = AgentResponse(
            output="Page created",
            blocked=False,
            block_reason=None,
            is_error=False,
            error_detail=None,
            intent="create_page",
            tool_name="create_page",
        )
        assert resp.output == "Page created"
        assert resp.intent == "create_page"

    def test_blocked_response(self):
        """Blocked response should be valid."""
        resp = AgentResponse(
            output="I cannot help with that.",
            blocked=True,
            block_reason="content policy violation",
        )
        assert resp.blocked is True
        assert resp.block_reason == "content policy violation"

    def test_error_response(self):
        """Error response should be valid."""
        resp = AgentResponse(
            output=None,
            is_error=True,
            error_detail="Tool execution failed: timeout",
        )
        assert resp.is_error is True
        assert resp.error_detail == "Tool execution failed: timeout"


class TestErrorResponse:
    """Tests for ErrorResponse schema."""

    def test_valid(self):
        """ErrorResponse with required fields should be valid."""
        err = ErrorResponse(error="Something went wrong")
        assert err.error == "Something went wrong"
        assert err.detail is None
        assert err.request_id is None

    def test_full(self):
        """ErrorResponse with all fields should be valid."""
        err = ErrorResponse(
            error="Internal Server Error",
            detail="Database connection failed",
            request_id="req-abc-123",
        )
        assert err.error == "Internal Server Error"
        assert err.detail == "Database connection failed"
        assert err.request_id == "req-abc-123"

    def test_error_required(self):
        """ErrorResponse without error field should fail."""
        with pytest.raises(ValidationError):
            ErrorResponse()
