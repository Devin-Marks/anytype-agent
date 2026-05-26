"""Tool registry for the Anytype agent."""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self._tools: Dict[str, "BaseTool"] = {}

    def register(self, tool: "BaseTool") -> None:
        """Register a tool with the registry.

        Args:
            tool: Tool instance to register
        """
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional["BaseTool"]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tool information."""
        tool = self.get_tool(name)
        if tool:
            return {
                "name": tool.name,
                "description": tool.description,
                "required_params": tool.required_params,
            }
        return None


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools()
    return _registry


def _register_default_tools() -> None:
    """Register default tools."""
    try:
        from .pages import CreatePageTool, ReadPageTool, UpdatePageTool, DeletePageTool
        from .tasks import CreateTaskTool, UpdateTaskTool, CompleteTaskTool
        from .projects import ListProjectsTool
        from .queries import SearchTool
        from .bookmarks import CreateBookmarkTool
        from .chats import SendMessageTool

        registry = get_tool_registry()

        # Register page tools
        registry.register(CreatePageTool())
        registry.register(ReadPageTool())
        registry.register(UpdatePageTool())
        registry.register(DeletePageTool())

        # Register task tools
        registry.register(CreateTaskTool())
        registry.register(UpdateTaskTool())
        registry.register(CompleteTaskTool())

        # Register project tools
        registry.register(ListProjectsTool())

        # Register search tool
        registry.register(SearchTool())

        # Register bookmark tool
        registry.register(CreateBookmarkTool())

        # Register chat tool
        registry.register(SendMessageTool())

        logger.info(f"Registered {len(registry.list_tools())} tools")
    except ImportError as e:
        logger.warning(f"Could not register default tools: {e}")


# Import BaseTool for type hints
from .base import BaseTool
