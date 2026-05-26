"""Tests for src/main.py FastAPI endpoints."""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client(mock_settings):
    """Return a FastAPI TestClient with patched settings."""
    with patch("src.main.get_settings", return_value=mock_settings):
        with patch("src.main.get_sandbox_manager") as mock_mgr:
            mock_instance = MagicMock()
            mock_instance.is_available = False
            mock_instance.state = MagicMock(value="stopped")
            mock_instance.sandbox_name = None
            mock_mgr.return_value = mock_instance
            with TestClient(app) as test_client:
                yield test_client


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_readiness(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"ready": True}

    def test_sandbox_health(self, client):
        with patch("src.main.get_sandbox_manager") as mock_mgr:
            mock_instance = MagicMock()
            mock_instance.is_available = False
            mock_instance.state = MagicMock(value="stopped")
            mock_instance.sandbox_name = None
            mock_mgr.return_value = mock_instance

            response = client.get("/health/sandbox")
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["openshell_available"] is False
            assert data["isolated"] is False


class TestInvokeEndpoint:
    """Tests for /invoke endpoint."""

    def test_invoke_success(self, client):
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "output": "Page created successfully",
            "blocked": False,
            "block_reason": None,
            "is_error": False,
            "error_detail": None,
            "intent": "create_page",
            "tool_name": "create_page",
        })

        with patch("src.graph.builder.get_graph", return_value=mock_graph):
            response = client.post("/invoke", json={
                "input": "Create a page called Test",
                "space_id": "space_1",
                "thread_id": "thread_1",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["output"] == "Page created successfully"
        assert data["blocked"] is False
        assert data["intent"] == "create_page"
        assert data["tool_name"] == "create_page"

    def test_invoke_minimal(self, client):
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "output": "Done",
            "blocked": False,
        })

        with patch("src.graph.builder.get_graph", return_value=mock_graph):
            response = client.post("/invoke", json={"input": "hello"})

        assert response.status_code == 200
        data = response.json()
        assert data["output"] == "Done"
        assert data["blocked"] is False

    def test_invoke_blocked(self, client):
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "output": "I cannot help with that.",
            "blocked": True,
            "block_reason": "content policy violation",
        })

        with patch("src.graph.builder.get_graph", return_value=mock_graph):
            response = client.post("/invoke", json={"input": "bad request"})

        assert response.status_code == 200
        data = response.json()
        assert data["blocked"] is True
        assert data["block_reason"] == "content policy violation"

    def test_invoke_error(self, client):
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "output": None,
            "blocked": False,
            "is_error": True,
            "error_detail": "Tool failed",
        })

        with patch("src.graph.builder.get_graph", return_value=mock_graph):
            response = client.post("/invoke", json={"input": "test"})

        assert response.status_code == 200
        data = response.json()
        assert data["is_error"] is True
        assert data["error_detail"] == "Tool failed"

    def test_invoke_invalid_request(self, client):
        """Missing required 'input' field should fail validation."""
        response = client.post("/invoke", json={})
        assert response.status_code == 422

    def test_invoke_with_thread_id(self, client):
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"output": "ok"})

        with patch("src.graph.builder.get_graph", return_value=mock_graph):
            response = client.post("/invoke", json={
                "input": "hello",
                "thread_id": "abc-123",
            })

        assert response.status_code == 200
        # Verify thread_id was passed to graph config
        call_args = mock_graph.ainvoke.call_args
        config = call_args[1].get("config", {})
        assert config.get("configurable", {}).get("thread_id") == "abc-123"
