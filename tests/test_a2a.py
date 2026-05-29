"""Tests for Phase 7 A2A protocol support."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.a2a.agent_card import get_anytype_agent_card
from src.api.a2a.client import A2AClient
from src.api.a2a.server import A2AServer, Message, MessageRole, TaskStatus, TextPart
from src.main import app


class FakeGraph:
    """Async graph test double for A2A tests."""

    def __init__(self, chunks=None, result=None):
        self.chunks = chunks or []
        self.result = result or {"output": "Done", "blocked": False}
        self.ainvoke_calls = []
        self.astream_calls = []

    async def ainvoke(self, state, config=None):
        self.ainvoke_calls.append({"state": state, "config": config})
        return self.result

    async def astream(self, state, config=None, stream_mode=None):
        self.astream_calls.append({"state": state, "config": config, "stream_mode": stream_mode})
        for chunk in self.chunks:
            yield chunk


@pytest.fixture
def a2a_client(mock_settings):
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


def _task_payload(message="Create a page"):
    return {
        "sessionId": "session-1",
        "message": {"role": "user", "parts": [{"type": "text", "text": message}]},
    }


class TestAgentCard:
    """Agent Card tests."""

    def test_agent_card_dict(self):
        card = get_anytype_agent_card("http://testserver").to_dict()

        assert card["name"] == "anytype-agent"
        assert card["url"] == "http://testserver"
        assert card["capabilities"]["streaming"] is True
        assert "text" in card["defaultInputModes"]
        assert {skill["name"] for skill in card["skills"]} >= {
            "anytype_pages",
            "anytype_tasks",
            "anytype_search",
        }

    def test_agent_card_endpoint_standard_path(self, a2a_client):
        response = a2a_client.get("/.well-known/agent.json")

        assert response.status_code == 200
        assert response.json()["name"] == "anytype-agent"


class TestA2AServer:
    """A2AServer unit tests."""

    @pytest.mark.asyncio
    async def test_send_task_success(self):
        graph = FakeGraph(result={"output": "Page created", "blocked": False})
        server = A2AServer(graph=graph)
        message = Message(role=MessageRole.USER, parts=[TextPart(text="Create page")])

        task = await server.send_task("session-1", message, "task-1")

        assert task.id == "task-1"
        assert task.status == TaskStatus.COMPLETED
        assert task.result == "Page created"
        assert graph.ainvoke_calls[0]["state"] == {
            "user_request": "Create page",
            "space_id": None,
            "blocked": False,
        }

    @pytest.mark.asyncio
    async def test_send_task_blocked(self):
        graph = FakeGraph(result={"blocked": True, "block_reason": "unsafe"})
        server = A2AServer(graph=graph)
        message = Message(role=MessageRole.USER, parts=[TextPart(text="bad")])

        task = await server.send_task("session-1", message)

        assert task.status == TaskStatus.FAILED
        assert task.error == "unsafe"

    @pytest.mark.asyncio
    async def test_send_task_stream(self):
        graph = FakeGraph(
            chunks=[
                {"intent": "create_page"},
                {"intent": "create_page", "tool_name": "create_page"},
                {"output": "Page created"},
            ]
        )
        server = A2AServer(graph=graph)
        message = Message(role=MessageRole.USER, parts=[TextPart(text="Create page")])

        events = [event async for event in server.send_task_stream("session-1", message, "task-1")]

        assert events[0] == {"type": "task", "taskId": "task-1", "status": "submitted"}
        assert {event.get("stage") for event in events if event["type"] == "progress"} == {
            "parsing",
            "executing",
        }
        assert events[-1] == {
            "type": "task",
            "taskId": "task-1",
            "status": "completed",
            "result": {"output": "Page created"},
        }
        assert server.get_task("task-1").status == TaskStatus.COMPLETED


class TestA2AEndpoints:
    """FastAPI endpoint tests."""

    def test_tasks_send_endpoint(self, a2a_client):
        server = A2AServer(graph=FakeGraph(result={"output": "Done", "blocked": False}))

        with patch("src.api.a2a.router.get_a2a_server", return_value=server):
            response = a2a_client.post("/a2a/tasks/send", json=_task_payload())

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"] == "Done"
        assert data["sessionId"] == "session-1"

    def test_tasks_send_subscribe_endpoint(self, a2a_client):
        server = A2AServer(graph=FakeGraph(chunks=[{"intent": "search"}, {"output": "Found"}]))

        with patch("src.api.a2a.router.get_a2a_server", return_value=server):
            response = a2a_client.post("/a2a/tasks/sendSubscribe", json=_task_payload("Search"))

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert events[0]["status"] == "submitted"
        assert events[-1]["status"] == "completed"
        assert events[-1]["result"] == {"output": "Found"}

    def test_get_and_cancel_task_endpoints(self, a2a_client):
        server = A2AServer(graph=FakeGraph())
        message = Message(role=MessageRole.USER, parts=[TextPart(text="hello")])
        server._create_task("session-1", message, "task-1")

        with patch("src.api.a2a.router.get_a2a_server", return_value=server):
            get_response = a2a_client.get("/a2a/tasks/task-1")
            cancel_response = a2a_client.post("/a2a/tasks/cancel", json={"id": "task-1"})
            get_canceled_response = a2a_client.get("/a2a/tasks/task-1")

        assert get_response.status_code == 200
        assert cancel_response.status_code == 200
        assert cancel_response.json() == {"status": "canceled"}
        assert get_canceled_response.json()["status"] == "canceled"


class TestA2AClient:
    """A2AClient tests using a mocked httpx client."""

    @pytest.mark.asyncio
    async def test_send_task(self):
        client = A2AClient("http://example.test/")
        response = MagicMock()
        response.json.return_value = {"id": "task-1", "status": "completed", "result": "Done"}
        response.raise_for_status = MagicMock()
        client.client.post = AsyncMock(return_value=response)

        result = await client.send_task("hello", session_id="session-1")
        await client.close()

        assert result.task_id == "task-1"
        assert result.status == "completed"
        assert result.result == "Done"
        client.client.post.assert_awaited_once()
