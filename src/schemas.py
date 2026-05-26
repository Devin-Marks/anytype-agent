"""Pydantic request/response schemas."""
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    """Request model for agent invocation."""
    input: str = Field(..., description="User input text")
    space_id: Optional[str] = Field(None, description="Optional space context")
    thread_id: Optional[str] = Field(None, description="Optional thread for persistence")
    prompt_name: Optional[str] = Field(None, description="Prompt template to use")


class AgentResponse(BaseModel):
    """Response model for agent invocation."""
    output: Optional[str] = None
    blocked: bool = False
    block_reason: Optional[str] = None
    is_error: bool = False
    error_detail: Optional[str] = None
    intent: Optional[str] = None
    tool_name: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None