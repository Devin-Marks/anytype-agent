"""A2A protocol support."""
from .agent_card import AgentCard, AgentCapabilities, AgentSkill, get_anytype_agent_card
from .client import A2AClient, A2ATaskResult
from .router import router as a2a_router
from .server import A2AServer, Message, MessageRole, Task, TaskStatus, TextPart, get_a2a_server

__all__ = [
    "A2AClient",
    "A2AServer",
    "A2ATaskResult",
    "AgentCapabilities",
    "AgentCard",
    "AgentSkill",
    "Message",
    "MessageRole",
    "Task",
    "TaskStatus",
    "TextPart",
    "a2a_router",
    "get_a2a_server",
    "get_anytype_agent_card",
]
