"""Response formatting node."""
import logging
from typing import Optional

from ...llm import get_router
from ..state import AgentState

logger = logging.getLogger(__name__)


async def format_response(state: AgentState) -> dict:
    """Format tool result into user-friendly output."""
    router = get_router()
    provider = router.get_route("response")

    tool_result = state.get("tool_result")
    tool_error = state.get("tool_error")
    is_error = state.get("is_error", False)

    if is_error and tool_error:
        return {"output": f"Error: {tool_error}"}

    if not tool_result:
        return {"output": "No result available"}

    try:
        messages = [
            {
                "role": "system",
                "content": """You are a response formatter.
                Format tool results into user-friendly responses.
                Keep responses concise and clear.""",
            },
            {
                "role": "user",
                "content": f"Format this result for the user:\n{tool_result}",
            },
        ]

        response = await provider.complete(messages)
        return {"output": response.content}

    except Exception as e:
        # Fallback to simple formatting
        logger.warning(f"Response formatting LLM call failed: {e}")
        return {"output": str(tool_result)}