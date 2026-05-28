"""Tests for SSE streaming support."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.streaming import StreamingHandler, StreamEvent, StreamEventType
from src.main import app
from src.schemas import StreamEventSchema, StreamResponse


class FakeGraph:
    """Small async streaming graph test double."""

    def __init__(self, chunks=None, error: Exception | None = None):
        self.chunks = chunks or []
        self.error = error
        self.calls = []

    async def astream(self, state, config=None, stream_mode=None):
        self.calls.append({"state": state, "config": config, "stream_mode": stream_mode})
        if self.error:
            raise self.error
        for chunk in self.chunks:
            yield chunk


def _event_lines(response_text: str) -> list[str]:
    """Return non-empty SSE lines from a response body."""
    return [line.strip() for line in response_text.splitlines() if line.strip()]


@pytest.fixture
def streaming_client(mock_settings):
    """Return a FastAPI TestClient with startup dependencies patched."""
    with patch("src.main.get_settings", return_value=mock_settings):
        with patch("src.main.get_sandbox_manager") as mock_mgr:
            mock_instance = MagicMock()
            mock_instance.is_available = False
            mock_instance.state = MagicMock(value="stopped")
            mock_instance.sandbox_name = None
            mock_instance.stop_sandbox = AsyncMock()
            mock_mgr.return_value = mock_instance
            with TestClient(app) as client:
                yield client


class TestStreamEvent:
    """Tests for stream event conversion."""

    def test_to_sse(self):
        event = StreamEvent(StreamEventType.OUTPUT, {"output": "Done"})

        assert event.to_sse() == {
            "event": "output",
            "data": json.dumps({"output": "Done"}),
        }

    def test_to_sse_with_comment(self):
        event = StreamEvent(StreamEventType.THINKING, {"stage": "x"}, comment="keepalive")

        assert event.to_sse()["comment"] == "keepalive"


class TestStreamingHandler:
    """Tests for StreamingHandler."""

    @pytest.mark.asyncio
    async def test_stream_response_event_ordering(self):
        graph = FakeGraph([
            {"intent": "create_page"},
            {"intent": "create_page", "tool_name": "create_page", "tool_params": {"title": "T"}},
            {
                "intent": "create_page",
                "tool_name": "create_page",
                "tool_result": {"id": "page-1"},
            },
            {"output": "Page created"},
        ])
        handler = StreamingHandler(graph)

        events = [event async for event in handler.stream_response({"user_request": "create T"})]

        assert [event.event_type for event in events] == [
            StreamEventType.THINKING,
            StreamEventType.TOOL_CALL,
            StreamEventType.TOOL_RESULT,
            StreamEventType.OUTPUT,
            StreamEventType.DONE,
        ]
        assert events[0].data == {"stage": "parsing_intent", "intent": "create_page"}
        assert events[1].data == {"tool": "create_page", "params": {"title": "T"}}
        assert events[-1].data == {"completed": True}
        assert graph.calls[0]["stream_mode"] == "values"
        assert graph.calls[0]["config"]["stream_mode"] == "values"

    @pytest.mark.asyncio
    async def test_stream_response_deduplicates_values_mode_chunks(self):
        graph = FakeGraph([
            {"intent": "create_page"},
            {"intent": "create_page"},
            {"intent": "create_page", "output": "Done"},
            {"intent": "create_page", "output": "Done"},
        ])
        handler = StreamingHandler(graph)

        events = [event async for event in handler.stream_response({})]

        assert [event.event_type for event in events] == [
            StreamEventType.THINKING,
            StreamEventType.OUTPUT,
            StreamEventType.DONE,
        ]

    @pytest.mark.asyncio
    async def test_stream_response_error_event(self):
        graph = FakeGraph(error=RuntimeError("boom"))
        handler = StreamingHandler(graph)

        events = [event async for event in handler.stream_response({})]

        assert len(events) == 1
        assert events[0].event_type == StreamEventType.ERROR
        assert events[0].data == {"error": "boom"}


class TestStreamingSchemas:
    """Tests for streaming schemas."""

    def test_stream_response_schema(self):
        response = StreamResponse(
            events=[StreamEventSchema(event="output", data={"output": "Done"})],
            output="Done",
        )

        assert response.events[0].event == "output"
        assert response.output == "Done"
        assert response.blocked is False


class TestStreamingEndpoints:
    """Tests for streaming FastAPI endpoints."""

    def test_stream_invoke(self, streaming_client):
        graph = FakeGraph([{"intent": "create_page"}, {"output": "Done"}])

        with patch("src.graph.builder.get_graph", return_value=graph):
            response = streaming_client.post(
                "/stream/invoke",
                json={"input": "Create page", "space_id": "space-1", "thread_id": "thread-1"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = _event_lines(response.text)
        assert "event: thinking" in lines
        assert f"data: {json.dumps({'stage': 'parsing_intent', 'intent': 'create_page'})}" in lines
        assert "event: output" in lines
        assert f"data: {json.dumps({'output': 'Done'})}" in lines
        assert "event: done" in lines
        assert graph.calls[0]["state"] == {
            "user_request": "Create page",
            "space_id": "space-1",
            "blocked": False,
        }
        assert graph.calls[0]["config"] == {
            "configurable": {"thread_id": "thread-1"},
            "stream_mode": "values",
        }

    def test_stream_events_query_params(self, streaming_client):
        graph = FakeGraph([{"output": "Done"}])

        with patch("src.graph.builder.get_graph", return_value=graph):
            response = streaming_client.get(
                "/stream/events?input=hello&space_id=space-1&thread_id=thread-1"
            )

        assert response.status_code == 200
        assert "event: output" in _event_lines(response.text)
        assert graph.calls[0]["state"] == {
            "user_request": "hello",
            "space_id": "space-1",
            "blocked": False,
        }
        assert graph.calls[0]["config"] == {
            "configurable": {"thread_id": "thread-1"},
            "stream_mode": "values",
        }
