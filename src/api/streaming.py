"""SSE streaming support for the Anytype agent.

Provides real-time streaming of agent responses using Server-Sent Events.
Integrates with LangGraph for streaming intermediate steps.
"""
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sse_starlette.sse import EventStreamResponse


class StreamEventType(Enum):
    """Types of events in the stream."""

    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    OUTPUT = "output"
    ERROR = "error"
    DONE = "done"


@dataclass(frozen=True)
class StreamEvent:
    """SSE event structure."""

    event_type: StreamEventType
    data: dict[str, Any]
    comment: str | None = None

    def to_sse(self) -> dict[str, str]:
        """Convert to SSE response format."""
        event = {
            "event": self.event_type.value,
            "data": json.dumps(self.data, default=str),
        }
        if self.comment is not None:
            event["comment"] = self.comment
        return event


class StreamingHandler:
    """Handles SSE streaming for agent responses."""

    def __init__(self, graph: Any):
        """Initialize streaming handler.

        Args:
            graph: Compiled LangGraph for streaming.
        """
        self.graph = graph

    async def stream_response(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream agent response with typed events.

        Args:
            state: Initial agent state.
            config: LangGraph configuration.

        Yields:
            StreamEvent objects for each graph step.
        """
        config = dict(config or {})
        config.setdefault("stream_mode", "values")
        emitted_values: dict[str, Any] = {}

        try:
            try:
                stream = self.graph.astream(state, config=config, stream_mode="values")
            except TypeError:
                stream = self.graph.astream(state, config=config)

            async for chunk in stream:
                if not isinstance(chunk, dict):
                    continue

                async for event in self._events_for_chunk(chunk, emitted_values):
                    yield event

            yield StreamEvent(
                event_type=StreamEventType.DONE,
                data={"completed": True},
            )
        except Exception as exc:  # pragma: no cover - exact exceptions depend on graph internals
            yield StreamEvent(
                event_type=StreamEventType.ERROR,
                data={"error": str(exc)},
            )

    async def _events_for_chunk(
        self,
        chunk: dict[str, Any],
        emitted_values: dict[str, Any],
    ) -> AsyncGenerator[StreamEvent, None]:
        """Map a LangGraph stream chunk to zero or more SSE events."""
        intent = chunk.get("intent")
        if intent and emitted_values.get("intent") != intent:
            emitted_values["intent"] = intent
            yield StreamEvent(
                event_type=StreamEventType.THINKING,
                data={"stage": "parsing_intent", "intent": intent},
            )

        tool_name = chunk.get("tool_name")
        if tool_name and emitted_values.get("tool_name") != tool_name:
            emitted_values["tool_name"] = tool_name
            yield StreamEvent(
                event_type=StreamEventType.TOOL_CALL,
                data={"tool": tool_name, "params": chunk.get("tool_params", {})},
            )

        tool_result = chunk.get("tool_result")
        if tool_result and emitted_values.get("tool_result") != tool_result:
            emitted_values["tool_result"] = tool_result
            yield StreamEvent(
                event_type=StreamEventType.TOOL_RESULT,
                data={"result": tool_result},
            )

        error_detail = chunk.get("tool_error") or chunk.get("error_detail")
        if chunk.get("is_error") and error_detail and emitted_values.get("error") != error_detail:
            emitted_values["error"] = error_detail
            yield StreamEvent(
                event_type=StreamEventType.ERROR,
                data={"error": error_detail},
            )

        output = chunk.get("output")
        if output and emitted_values.get("output") != output:
            emitted_values["output"] = output
            yield StreamEvent(
                event_type=StreamEventType.OUTPUT,
                data={"output": output},
            )

    async def stream_to_sse(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> EventStreamResponse:
        """Convert the graph event stream to an SSE response.

        Args:
            state: Initial agent state.
            config: LangGraph configuration.

        Returns:
            SSE EventStreamResponse.
        """

        async def event_generator() -> AsyncGenerator[dict[str, str], None]:
            async for event in self.stream_response(state, config):
                yield event.to_sse()

        return EventStreamResponse(
            event_generator(),
            media_type="text/event-stream",
        )
