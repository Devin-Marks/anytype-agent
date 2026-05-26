"""Tool registry for the Anytype agent."""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self._tools: Dict[str, "BaseTool"] = {}

    def register(self, name: str, tool: "BaseTool") -> None:
        """Register a tool with the registry."""
        self._tools[name] = tool
        logger.debug(f"Registered tool: {name}")

    def get_tool(self, name: str) -> Optional["BaseTool"]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools


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
    # Import tools to register them
    try:
        from .pages import CreatePageTool, ReadPageTool, UpdatePageTool, DeletePageTool
        from .tasks import CreateTaskTool, UpdateTaskTool, CompleteTaskTool
        from .projects import ListProjectsTool
        from .queries import SearchTool
        
        registry = get_tool_registry()
        
        # Register page tools
        registry.register("create_page", CreatePageTool())
        registry.register("read_page", ReadPageTool())
        registry.register("update_page", UpdatePageTool())
        registry.register("delete_page", DeletePageTool())
        
        # Register task tools
        registry.register("create_task", CreateTaskTool())
        registry.register("update_task", UpdateTaskTool())
        registry.register("complete_task", CompleteTaskTool())
        
        # Register project tools
        registry.register("list_projects", ListProjectsTool())
        
        # Register search tool
        registry.register("search", SearchTool())
        
        logger.info(f"Registered {len(registry.list_tools())} tools")
    except ImportError as e:
        logger.warning(f"Could not register default tools: {e}")


# Import BaseTool for type hints
from .base import BaseTool