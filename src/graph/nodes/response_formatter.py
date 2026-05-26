"""Response formatting node."""
import logging
from typing import Optional

from openai import AsyncOpenAI

from ..config import get_settings
from ..state import AgentState

logger = logging.getLogger(__name__)


async def format_response(state: AgentState) -> dict:
    """Format tool result into user-friendly output."""
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    tool_result = state.get("tool_result")
    tool_error = state.get("tool_error")
    is_error = state.get("is_error", False)

    if is_error and tool_error:
        return {"output": f"Error: {tool_error}"}

    if not tool_result:
        return {"output": "No result available"}

    try:
        response = await client.chat.completions.create(
            model=settings.model,
            messages=[
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
            ],
            temperature=0.3,
            max_tokens=500,
        )

        return {"output": response.choices[0].message.content}

    except Exception as e:
        # Fallback to simple formatting
        logger.warning(f"Response formatting LLM call failed: {e}")
        return {"output": str(tool_result)}