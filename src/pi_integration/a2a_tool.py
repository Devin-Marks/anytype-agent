"""A2A helper tool for pi agent integrations."""
from typing import Any

from src.api.a2a.client import A2AClient


class A2AAnytypeTool:
    """Thin wrapper around A2AClient for pi tool-style execution."""

    name = "anytype_a2a"
    description = "Interact with Anytype via the A2A protocol"

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.client = A2AClient(base_url)

    async def execute(self, query: str, stream: bool = True) -> dict[str, Any]:
        """Execute a query through A2A, optionally collecting stream events."""
        if stream:
            events = [event async for event in self.client.send_task_stream(query)]
            return {"events": events}

        result = await self.client.send_task(query)
        return {"task_id": result.task_id, "status": result.status, "result": result.result}

    async def close(self) -> None:
        """Close the underlying A2A client."""
        await self.client.close()


async def anytype_a2a(query: str) -> dict[str, Any]:
    """Convenience coroutine for pi to call Anytype through A2A."""
    tool = A2AAnytypeTool()
    try:
        return await tool.execute(query)
    finally:
        await tool.close()
