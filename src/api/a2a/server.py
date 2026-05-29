"""A2A task server for wrapping Anytype LangGraph executions."""
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Supported A2A message roles."""

    AGENT = "agent"
    USER = "user"


class TextPart(BaseModel):
    """A text message part."""

    type: str = "text"
    text: str


class Message(BaseModel):
    """A2A message containing one or more parts."""

    role: MessageRole
    parts: list[TextPart]


class TaskStatus(str, Enum):
    """A2A task lifecycle states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class Task:
    """In-memory A2A task record."""

    id: str
    session_id: str
    status: TaskStatus = TaskStatus.SUBMITTED
    messages: list[Message] = field(default_factory=list)
    result: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable task representation."""
        return {
            "id": self.id,
            "sessionId": self.session_id,
            "status": self.status.value,
            "messages": [message.model_dump(mode="json") for message in self.messages],
            "result": self.result,
            "error": self.error,
        }


class SendTaskRequest(BaseModel):
    """Request body for A2A tasks/send and tasks/sendSubscribe."""

    id: str | None = None
    session_id: str = Field(alias="sessionId")
    message: Message
    stream: bool = True

    model_config = {"populate_by_name": True}


class CancelTaskRequest(BaseModel):
    """Request body for A2A tasks/cancel."""

    id: str


class A2AServer:
    """Minimal in-process A2A task server."""

    def __init__(self, graph: Any | None = None):
        self._tasks: dict[str, Task] = {}
        self._graph = graph

    @property
    def graph(self) -> Any:
        """Get the compiled graph lazily so tests can patch graph construction."""
        if self._graph is None:
            from ...graph.builder import get_graph

            self._graph = get_graph()
        return self._graph

    async def send_task(
        self,
        session_id: str,
        message: Message,
        task_id: str | None = None,
    ) -> Task:
        """Execute an A2A task and return the final task record."""
        task = self._create_task(session_id, message, task_id)
        task.status = TaskStatus.WORKING

        try:
            result = await self.graph.ainvoke(self._state_from_message(message))
            self._apply_graph_result(task, result)
        except Exception as exc:  # pragma: no cover - graph-specific failures vary
            task.status = TaskStatus.FAILED
            task.error = str(exc)

        return task

    async def send_task_stream(
        self,
        session_id: str,
        message: Message,
        task_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream task updates while the graph executes."""
        task = self._create_task(session_id, message, task_id)
        task.status = TaskStatus.WORKING

        yield {"type": "task", "taskId": task.id, "status": TaskStatus.SUBMITTED.value}
        yield {"type": "task", "taskId": task.id, "status": TaskStatus.WORKING.value}

        last_chunk: dict[str, Any] | None = None
        try:
            state = self._state_from_message(message)
            try:
                stream = self.graph.astream(state, stream_mode="values")
            except TypeError:
                stream = self.graph.astream(state)

            async for chunk in stream:
                if not isinstance(chunk, dict):
                    continue
                last_chunk = chunk
                async for event in self._progress_events(task.id, chunk):
                    yield event

            if last_chunk is None:
                last_chunk = await self.graph.ainvoke(state)

            self._apply_graph_result(task, last_chunk)
            if task.status == TaskStatus.COMPLETED:
                yield {
                    "type": "task",
                    "taskId": task.id,
                    "status": task.status.value,
                    "result": {"output": task.result},
                }
            else:
                yield {
                    "type": "task",
                    "taskId": task.id,
                    "status": task.status.value,
                    "error": task.error,
                }
        except Exception as exc:  # pragma: no cover - graph-specific failures vary
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            yield {"type": "task", "taskId": task.id, "status": task.status.value, "error": task.error}

    def get_task(self, task_id: str) -> Task | None:
        """Return a task by id, if known."""
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Mark a task canceled if it exists."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.CANCELED
        return True

    def _create_task(self, session_id: str, message: Message, task_id: str | None) -> Task:
        task = Task(id=task_id or str(uuid4()), session_id=session_id, messages=[message])
        self._tasks[task.id] = task
        return task

    def _state_from_message(self, message: Message) -> dict[str, Any]:
        text = "".join(part.text for part in message.parts if part.type == "text")
        return {"user_request": text, "space_id": None, "blocked": False}

    def _apply_graph_result(self, task: Task, result: dict[str, Any]) -> None:
        if result.get("blocked"):
            task.status = TaskStatus.FAILED
            task.error = result.get("block_reason") or "Request blocked by guardrail"
            return
        if result.get("is_error"):
            task.status = TaskStatus.FAILED
            task.error = result.get("error_detail") or result.get("tool_error") or "Task failed"
            return
        task.status = TaskStatus.COMPLETED
        task.result = result.get("output") or ""
        task.messages.append(
            Message(role=MessageRole.AGENT, parts=[TextPart(text=task.result)])
        )

    async def _progress_events(
        self,
        task_id: str,
        chunk: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        intent = chunk.get("intent")
        if intent:
            yield {"type": "progress", "taskId": task_id, "stage": "parsing", "intent": intent}

        tool_name = chunk.get("tool_name")
        if tool_name:
            yield {"type": "progress", "taskId": task_id, "stage": "executing", "tool": tool_name}

        if chunk.get("output"):
            yield {"type": "message", "taskId": task_id, "message": {"role": "agent", "parts": [{"type": "text", "text": chunk["output"]}]}}


_a2a_server: A2AServer | None = None


def get_a2a_server() -> A2AServer:
    """Return the process-wide A2A server."""
    global _a2a_server
    if _a2a_server is None:
        _a2a_server = A2AServer()
    return _a2a_server
