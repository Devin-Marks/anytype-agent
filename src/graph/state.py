"""Agent state schema for LangGraph."""
from typing import Annotated, Optional, Literal
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """State schema for the Anytype agent."""

    # User input
    user_request: str
    space_id: Optional[str]  # Optional space context

    # Intent parsing
    intent: Optional[str]  # e.g., "create_page", "read_task", "list_projects"
    object_type: Optional[str]  # e.g., "page", "task", "project"
    tool_params: Optional[dict]  # Resolved tool parameters

    # Execution
    tool_name: Optional[str]
    tool_result: Optional[dict]  # Raw tool result
    tool_error: Optional[str]  # Error from tool execution

    # Output
    output: Optional[str]  # Formatted response to user
    blocked: bool  # Guardrail triggered
    block_reason: Optional[str]  # Reason for block
    is_error: bool  # Non-blocking error occurred
    error_detail: Optional[str]  # Full error details for API responses


class BlockedState(TypedDict):
    """Minimal state when request is blocked by guardrail."""
    user_request: str
    blocked: bool
    block_reason: Optional[str]