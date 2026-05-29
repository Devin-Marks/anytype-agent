"""FastAPI routes for the A2A protocol."""
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from .agent_card import get_anytype_agent_card
from .server import CancelTaskRequest, SendTaskRequest, get_a2a_server

router = APIRouter(tags=["A2A"])


@router.get("/.well-known/agent.json")
async def get_agent_card() -> JSONResponse:
    """Return the A2A discovery Agent Card at the standard path."""
    return JSONResponse(content=get_anytype_agent_card().to_dict())


@router.get("/a2a/.well-known/agent.json")
async def get_agent_card_compat() -> JSONResponse:
    """Return the Agent Card under the A2A prefix for clients expecting it there."""
    return await get_agent_card()


@router.post("/a2a/tasks/send")
async def send_task(request: SendTaskRequest) -> dict[str, object]:
    """Execute an A2A task and return its final state."""
    server = get_a2a_server()
    task = await server.send_task(request.session_id, request.message, request.id)
    return task.to_dict()


@router.post("/a2a/tasks/sendSubscribe")
async def send_task_subscribe(request: SendTaskRequest) -> StreamingResponse:
    """Execute an A2A task and stream task updates as SSE."""
    server = get_a2a_server()

    async def events() -> AsyncGenerator[str, None]:
        async for update in server.send_task_stream(request.session_id, request.message, request.id):
            yield f"data: {json.dumps(update, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/a2a/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, object]:
    """Return a task by id."""
    server = get_a2a_server()
    task = server.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.to_dict()


@router.post("/a2a/tasks/cancel")
async def cancel_task(request: CancelTaskRequest) -> dict[str, str]:
    """Cancel a known task."""
    server = get_a2a_server()
    if not server.cancel_task(request.id):
        raise HTTPException(status_code=404, detail=f"Task {request.id} not found")
    return {"status": "canceled"}
