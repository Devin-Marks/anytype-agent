"""Tool routing node."""
import logging
from typing import Optional

from ..state import AgentState

logger = logging.getLogger(__name__)


def _intent_to_tool(intent: str) -> Optional[str]:
    """Map intent to tool name."""
    mapping = {
        "create_page": "create_page",
        "read_page": "read_page",
        "update_page": "update_page",
        "delete_page": "delete_page",
        "create_task": "create_task",
        "update_task": "update_task",
        "complete_task": "complete_task",
        "list_projects": "list_projects",
        "search_objects": "search",
    }
    return mapping.get(intent)


async def execute_tool(state: AgentState) -> dict:
    """Execute the appropriate tool based on intent."""
    intent = state.get("intent", "unknown")
    tool_params = state.get("tool_params", {})
    space_id = state.get("space_id")

    # Add space_id to params if present
    if space_id:
        tool_params["space_id"] = space_id

    # Map intent to tool name
    tool_name = _intent_to_tool(intent)
    if not tool_name:
        return {
            "tool_error": f"No tool found for intent: {intent}",
            "is_error": True,
        }

    # Import tool registry
    try:
        from ..tools.registry import get_tool_registry
        registry = get_tool_registry()
        
        try:
            tool = registry.get_tool(tool_name)
            result = await tool.execute(**tool_params)
            return {
                "tool_name": tool_name,
                "tool_result": result,
            }
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {
                "tool_name": tool_name,
                "tool_error": str(e),
                "is_error": True,
            }
    except ImportError:
        # Tool registry not available - return error
        return {
            "tool_error": f"Tool registry not available",
            "is_error": True,
        }