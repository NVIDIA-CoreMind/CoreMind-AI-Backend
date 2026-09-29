"""
Tests for the Tool Registry.
"""

from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition, ToolRegistry


async def _dummy_executor(**kwargs: Any) -> dict[str, Any]:
    return {"result": "ok"}


class TestToolRegistry:
    """Test tool registration and lookup."""

    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}, "required": []},
            permission=PermissionLevel.READ,
            executor=_dummy_executor,
        )
        registry.register(tool)
        assert registry.get("test_tool") == tool

    def test_get_nonexistent_raises(self) -> None:
        registry = ToolRegistry()
        import pytest
        from src.utils.errors import ToolError
        with pytest.raises(ToolError):
            registry.get("nonexistent")

    def test_list_tools(self) -> None:
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}, "required": []},
            permission=PermissionLevel.READ,
            executor=_dummy_executor,
        )
        registry.register(tool)
        assert len(registry.list_tools()) == 1

    def test_to_openai_tools(self) -> None:
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="read_test",
            description="Read something",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            permission=PermissionLevel.READ,
            executor=_dummy_executor,
        )
        registry.register(tool)
        openai_tools = registry.to_openai_tools()
        assert len(openai_tools) == 1
        assert openai_tools[0]["type"] == "function"
        assert openai_tools[0]["function"]["name"] == "read_test"

    def test_get_by_permission(self) -> None:
        registry = ToolRegistry()
        for name, perm in [("r1", PermissionLevel.READ), ("w1", PermissionLevel.WRITE), ("r2", PermissionLevel.READ)]:
            registry.register(ToolDefinition(
                name=name, description="", parameters={}, permission=perm, executor=_dummy_executor,
            ))
        assert len(registry.get_by_permission(PermissionLevel.READ)) == 2
        assert len(registry.get_by_permission(PermissionLevel.WRITE)) == 1

    def test_count(self) -> None:
        registry = ToolRegistry()
        assert registry.count == 0
        registry.register(ToolDefinition(
            name="t1", description="", parameters={}, permission=PermissionLevel.READ, executor=_dummy_executor,
        ))
        assert registry.count == 1
