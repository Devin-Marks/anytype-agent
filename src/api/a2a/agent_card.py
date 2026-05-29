"""A2A Agent Card metadata for anytype-agent."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentSkill:
    """A skill advertised by the A2A Agent Card."""

    name: str
    description: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentCapabilities:
    """Capabilities supported by this A2A server."""

    streaming: bool = True
    push_notifications: bool = False
    state_transitions: bool = False

    def to_dict(self) -> dict[str, bool]:
        """Return protocol-compatible capability keys."""
        return {
            "streaming": self.streaming,
            "pushNotifications": self.push_notifications,
            "stateTransitions": self.state_transitions,
        }


@dataclass(frozen=True)
class AgentCard:
    """A2A discovery document for anytype-agent."""

    name: str = "anytype-agent"
    description: str = "LangGraph agent for Anytype API interactions"
    version: str = "1.0.0"
    url: str = "http://localhost:8000"
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)
    skills: list[AgentSkill] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the card to a JSON-serializable mapping."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "capabilities": self.capabilities.to_dict(),
            "skills": [
                {"name": skill.name, "description": skill.description, "tags": skill.tags}
                for skill in self.skills
            ],
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
        }


def get_anytype_agent_card(url: str = "http://localhost:8000") -> AgentCard:
    """Return the Anytype Agent Card advertised for A2A discovery."""
    return AgentCard(
        name="anytype-agent",
        description="Interact with an Anytype workspace through a LangGraph agent",
        url=url,
        skills=[
            AgentSkill(name="anytype_pages", description="Create, read, update, and delete pages", tags=["pages", "crud"]),
            AgentSkill(name="anytype_tasks", description="Create, update, and complete tasks", tags=["tasks"]),
            AgentSkill(name="anytype_search", description="Search Anytype objects", tags=["search"]),
            AgentSkill(name="anytype_projects", description="List and inspect projects", tags=["projects"]),
        ],
    )
