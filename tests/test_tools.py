"""Tests for src/graph/tools/."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.graph.tools.base import BaseTool, ToolResult
from src.graph.tools.registry import ToolRegistry, get_tool_registry, _register_default_tools
from src.graph.tools.pages import CreatePageTool, ReadPageTool, UpdatePageTool, DeletePageTool
from src.graph.tools.tasks import CreateTaskTool, UpdateTaskTool, CompleteTaskTool
from src.graph.tools.projects import ListProjectsTool
from src.graph.tools.queries import SearchTool
from src.graph.tools.bookmarks import CreateBookmarkTool
from src.graph.tools.chats import SendMessageTool


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
        # No exception expected when no required params
        tool.validate_params()

    def test_validate_params_missing_required(self):
        """validate_params should raise when required params are missing."""
        class DummyTool(BaseTool):
            name = "dummy"
            required_params = ["title"]
            async def execute(self, **kwargs):
                return {}
        tool = DummyTool()
        with pytest.raises(ValueError, match="Missing required params"):
            tool.validate_params()

    def test_get_schema_returns_tool_info(self):
        """get_schema should include name, description, and required_params."""
        class DummyTool(BaseTool):
            name = "dummy"
            description = "A dummy tool"
            required_params = ["x"]
            async def execute(self, **kwargs):
                return {}
        tool = DummyTool()
        schema = tool.get_schema()
        assert schema["name"] == "dummy"
        assert schema["description"] == "A dummy tool"
        assert schema["required_params"] == ["x"]


class TestToolResult:
    """Tests for ToolResult."""

    def test_success_to_dict(self):
        result = ToolResult(success=True, data={"id": "123"})
        assert result.to_dict() == {"id": "123"}

    def test_failure_to_dict(self):
        result = ToolResult(success=False, error="boom")
        assert result.to_dict() == {"error": "boom"}

    def test_default_data(self):
        result = ToolResult(success=True)
        assert result.to_dict() == {}


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = CreatePageTool()
        reg.register(tool)
        assert reg.get_tool("create_page") is tool

    def test_get_missing(self):
        reg = ToolRegistry()
        assert reg.get_tool("missing") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(CreatePageTool())
        reg.register(ReadPageTool())
        assert set(reg.list_tools()) == {"create_page", "read_page"}

    def test_has_tool(self):
        reg = ToolRegistry()
        reg.register(CreatePageTool())
        assert reg.has_tool("create_page") is True
        assert reg.has_tool("y") is False

    def test_get_tool_info(self):
        reg = ToolRegistry()
        reg.register(CreatePageTool())
        info = reg.get_tool_info("create_page")
        assert info is not None
        assert info["name"] == "create_page"
        assert info["required_params"] == ["title"]

    def test_get_tool_info_missing(self):
        reg = ToolRegistry()
        assert reg.get_tool_info("missing") is None


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
        assert reg.has_tool("create_bookmark")
        assert reg.has_tool("send_message")


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
    async def test_create_page_required_params(self):
        tool = CreatePageTool()
        tool.validate_params(title="Test")
        with pytest.raises(ValueError):
            tool.validate_params()

    @pytest.mark.asyncio
    async def test_read_page(self):
        tool = ReadPageTool()
        result = await tool.execute(page_id="page_123", space_id="space_1")
        assert result["success"] is True
        assert result["page_id"] == "page_123"

    @pytest.mark.asyncio
    async def test_read_page_required_params(self):
        tool = ReadPageTool()
        tool.validate_params(page_id="123")
        with pytest.raises(ValueError):
            tool.validate_params()

    @pytest.mark.asyncio
    async def test_update_page(self):
        tool = UpdatePageTool()
        result = await tool.execute(page_id="page_123", title="New Title")
        assert result["success"] is True
        assert result["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_delete_page(self):
        tool = DeletePageTool()
        result = await tool.execute(page_id="page_123")
        assert result["success"] is True
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_execute_with_validation_success(self):
        tool = CreatePageTool()
        result = await tool.execute_with_validation(title="Test")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_validation_missing_required(self):
        tool = CreatePageTool()
        result = await tool.execute_with_validation()
        assert result["success"] is False
        assert "Missing required params" in result["error"]
        assert result["tool"] == "create_page"


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
    async def test_complete_task(self):
        tool = CompleteTaskTool()
        result = await tool.execute(task_id="task_1")
        assert result["success"] is True
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_task_required_params(self):
        create = CreateTaskTool()
        update = UpdateTaskTool()
        complete = CompleteTaskTool()
        create.validate_params(title="ok")
        update.validate_params(task_id="ok")
        complete.validate_params(task_id="ok")
        with pytest.raises(ValueError):
            create.validate_params()
        with pytest.raises(ValueError):
            update.validate_params()
        with pytest.raises(ValueError):
            complete.validate_params()


class TestProjectTool:
    """Tests for project tools."""

    @pytest.mark.asyncio
    async def test_list_projects(self):
        tool = ListProjectsTool()
        result = await tool.execute(space_id="space_1", limit=10)
        assert result["success"] is True
        assert "projects" in result
        assert result["total"] == 2

    def test_list_projects_no_required_params(self):
        tool = ListProjectsTool()
        tool.validate_params()  # should not raise


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
        assert result["success"] is True  # execute() has default empty string

    def test_search_required_params(self):
        tool = SearchTool()
        tool.validate_params(query="ok")
        with pytest.raises(ValueError):
            tool.validate_params()


class TestBookmarkTool:
    """Tests for bookmark tools."""

    @pytest.mark.asyncio
    async def test_create_bookmark(self):
        tool = CreateBookmarkTool()
        result = await tool.execute(url="https://example.com", title="Example")
        assert result["success"] is True
        assert result["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_create_bookmark_no_url(self):
        tool = CreateBookmarkTool()
        result = await tool.execute()
        # execute() directly doesn't validate, but execute_with_validation would
        assert result["bookmark_id"]  # still generates an id even without url

    def test_create_bookmark_required_params(self):
        tool = CreateBookmarkTool()
        tool.validate_params(url="https://example.com")
        with pytest.raises(ValueError):
            tool.validate_params()


class TestChatTool:
    """Tests for chat tools."""

    @pytest.mark.asyncio
    async def test_send_message(self):
        tool = SendMessageTool()
        result = await tool.execute(chat_id="chat_1", text="hello")
        assert result["success"] is True
        assert result["text"] == "hello"

    def test_send_message_required_params(self):
        tool = SendMessageTool()
        tool.validate_params(chat_id="1", text="hi")
        with pytest.raises(ValueError):
            tool.validate_params()
        with pytest.raises(ValueError):
            tool.validate_params(chat_id="1")

