"""LLM-based intent parsing node."""
import json
import logging

from ...llm import get_router
from ..state import AgentState

logger = logging.getLogger(__name__)

# Intent patterns for Anytype operations
INTENT_PATTERNS = {
    "create_page": ["create page", "new page", "add page"],
    "read_page": ["read page", "view page", "get page", "show page"],
    "update_page": ["update page", "edit page", "modify page"],
    "delete_page": ["delete page", "remove page"],
    "create_task": ["create task", "new task", "add task"],
    "update_task": ["update task", "edit task", "complete task"],
    "list_projects": ["list projects", "show projects", "show me my projects", "get projects"],
    "search_objects": ["search", "find", "query"],
}


async def parse_intent(state: AgentState) -> dict:
    """Parse user request to determine intent and parameters."""
    user_request = state["user_request"]

    try:
        router = get_router()
        provider = router.get_route("intent")
        messages = [
            {
                "role": "system",
                "content": """You are an intent parser for Anytype API.
                Extract the intent and parameters from user requests.
                Return JSON with: intent, object_type, params.
                Intents: create_page, read_page, update_page, delete_page,
                create_task, update_task, complete_task, list_projects,
                search_objects, unknown""",
            },
            {"role": "user", "content": user_request},
        ]

        response = await provider.complete(messages)
        content = response.content

        # Parse JSON response
        try:
            parsed = json.loads(content)
            return {
                "intent": parsed.get("intent", "unknown"),
                "object_type": parsed.get("object_type"),
                "tool_params": parsed.get("params", {}),
            }
        except json.JSONDecodeError:
            # Fallback: simple keyword matching
            return _fallback_intent_parse(user_request)

    except Exception as e:
        logger.error(f"Intent parsing failed: {e}")
        return {
            "intent": "unknown",
            "tool_error": str(e),
            "is_error": True,
        }


def _fallback_intent_parse(text: str) -> dict:
    """Fallback intent parsing using keyword matching."""
    text_lower = text.lower()

    for intent, keywords in INTENT_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            return {
                "intent": intent,
                "object_type": intent.split("_")[1] if "_" in intent else None,
            }

    return {"intent": "unknown"}