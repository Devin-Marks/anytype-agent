"""Async A2A client for calling anytype-agent."""
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class A2ATaskResult:
    """Result returned by the A2A tasks/send endpoint."""

    task_id: str
    status: str
    result: str | None = None
    error: str | None = None


class A2AClient:
    """Small HTTP client for anytype-agent's A2A endpoints."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=120.0)

    async def get_agent_card(self) -> dict[str, Any]:
        """Discover and return the remote Agent Card."""
        response = await self.client.get(f"{self.base_url}/.well-known/agent.json")
        response.raise_for_status()
        return response.json()

    async def send_task(self, message: str, session_id: str | None = None) -> A2ATaskResult:
        """Send a non-streaming task."""
        response = await self.client.post(
            f"{self.base_url}/a2a/tasks/send",
            json=self._payload(message, session_id),
        )
        response.raise_for_status()
        data = response.json()
        return A2ATaskResult(
            task_id=data["id"],
            status=data["status"],
            result=data.get("result"),
            error=data.get("error"),
        )

    async def send_task_stream(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Send a streaming task and yield decoded SSE data events."""
        async with self.client.stream(
            "POST",
            f"{self.base_url}/a2a/tasks/sendSubscribe",
            json=self._payload(message, session_id),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield json.loads(line.removeprefix("data: "))

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self.client.aclose()

    def _payload(self, message: str, session_id: str | None) -> dict[str, Any]:
        return {
            "sessionId": session_id or "default",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
            },
        }
