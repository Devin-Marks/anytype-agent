"""Tests for src/graph/tools/."""
import pytest
from unittest.mock import AsyncMock, patch

from src.graph.tools.base import BaseTool
from src.graph.tools.registry import ToolRegistry, get_tool_registry, _register_default_tools
from src.graph.tools.pages import CreatePageTool, ReadPageTool, UpdatePageTool, DeletePageTool
from src.graph.tools.tasks import CreateTaskTool, UpdateTaskTool, CompleteTaskTool
from src.graph.tools.projects import ListProjectsTool
from src.graph.tools.queries import SearchTool


class TestBaseTool:
    """Tests for BaseTool abstract class."""

    def test_cannot_instantiate_directly(self):
        """BaseTool is abstract and should not be instantiable."""
        with pytest.raises(TypeError):
            BaseTool()

    def test_validate_params_no_required(self):
        """validate_params with no required_params should always pass."""
        class DummyTool(BaseTool):
            name = "dummy"
            async def execute(self, **kwargs):
                return {}
        tool = DummyTool()
        valid, error = tool.validate_params()
        assert valid is True
        assert error is None


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = CreatePageTool()
        reg.register("create_page", tool)
        assert reg.get_tool("create_page") is tool

    def test_get_missing(self):
        reg = ToolRegistry()
        assert reg.get_tool("missing") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register("a", CreatePageTool())
        reg.register("b", ReadPageTool())
        assert set(reg.list_tools()) == {"a", "b"}

    def test_has_tool(self):
        reg = ToolRegistry()
        reg.register("x", CreatePageTool())
        assert reg.has_tool("x") is True
        assert reg.has_tool("y") is False


class TestDefaultToolRegistration:
    """Tests for default tool registration."""

    def test_get_tool_registry_populated(self):
        """get_tool_registry should come pre-populated."""
        reg = get_tool_registry()
        assert reg.has_tool("create_page")
        assert reg.has_tool("read_page")
        assert reg.has_tool("update_page")
        assert reg.has_tool("delete_page")
        assert reg.has_tool("create_task")
        assert reg.has_tool("update_task")
        assert reg.has_tool("complete_task")
        assert reg.has_tool("list_projects")
        assert reg.has_tool("search")


class TestPageTools:
    """Tests for page CRUD tools."""

    @pytest.mark.asyncio
    async def test_create_page(self):
        tool = CreatePageTool()
        result = await tool.execute(title="Test Page", space_id="space_1")
        assert result["success"] is True
        assert result["title"] == "Test Page"
        assert "object_id" in result

    @pytest.mark.asyncio
    async def test_create_page_default_title(self):
        tool = CreatePageTool()
        result = await tool.execute()
        assert result["title"] == "Untitled"

    @pytest.mark.asyncio
    async def test_read_page(self):
        tool = ReadPageTool()
        result = await tool.execute(page_id="page_123", space_id="space_1")
        assert result["success"] is True
        assert result["page_id"] == "page_123"

    @pytest.mark.asyncio
    async def test_read_page_missing_id(self):
        tool = ReadPageTool()
        result = await tool.execute()
        assert result["success"] is False
        assert "page_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_update_page(self):
        tool = UpdatePageTool()
        result = await tool.execute(page_id="page_123", title="New Title")
        assert result["success"] is True
        assert result["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_update_page_missing_id(self):
        tool = UpdatePageTool()
        result = await tool.execute()
        assert result["success"] is False
        assert "page_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_delete_page(self):
        tool = DeletePageTool()
        result = await tool.execute(page_id="page_123")
        assert result["success"] is True
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_page_missing_id(self):
        tool = DeletePageTool()
        result = await tool.execute()
        assert result["success"] is False
        assert "page_id is required" in result["error"]


class TestTaskTools:
    """Tests for task CRUD tools."""

    @pytest.mark.asyncio
    async def test_create_task(self):
        tool = CreateTaskTool()
        result = await tool.execute(title="My Task", due_date="2024-12-01")
        assert result["success"] is True
        assert result["title"] == "My Task"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_task_default_title(self):
        tool = CreateTaskTool()
        result = await tool.execute()
        assert result["title"] == "Untitled Task"

    @pytest.mark.asyncio
    async def test_update_task(self):
        tool = UpdateTaskTool()
        result = await tool.execute(task_id="task_1", status="in_progress")
        assert result["success"] is True
        assert result["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_update_task_missing_id(self):
        tool = UpdateTaskTool()
        result = await tool.execute()
        assert result["success"] is False
        assert "task_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_complete_task(self):
        tool = CompleteTaskTool()
        result = await tool.execute(task_id="task_1")
        assert result["success"] is True
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_complete_task_missing_id(self):
        tool = CompleteTaskTool()
        result = await tool.execute()
        assert result["success"] is False
        assert "task_id is required" in result["error"]


class TestProjectTool:
    """Tests for project tools."""

    @pytest.mark.asyncio
    async def test_list_projects(self):
        tool = ListProjectsTool()
        result = await tool.execute(space_id="space_1", limit=10)
        assert result["success"] is True
        assert "projects" in result
        assert result["total"] == 2


class TestSearchTool:
    """Tests for search tool."""

    @pytest.mark.asyncio
    async def test_search(self):
        tool = SearchTool()
        result = await tool.execute(query="test", space_id="space_1")
        assert result["success"] is True
        assert result["query"] == "test"
        assert "results" in result

    @pytest.mark.asyncio
    async def test_search_missing_query(self):
        tool = SearchTool()
        result = await tool.execute()
        assert result["success"] is False
        assert "query is required" in result["error"]
