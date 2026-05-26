# test_tools.py — Tool Registry + Tool Execution 单元测试
"""对标 Hermes tools 测试：注册、dispatch、权限、边界。"""

import pytest, json, os
from tools import ToolRegistry, Tool, tool as tool_decorator


class TestToolRegistry:
    """ToolRegistry 核心功能测试。"""

    def test_register_and_dispatch(self):
        """注册工具后应能正确 dispatch。"""
        reg = ToolRegistry()

        def my_tool(name: str) -> dict:
            return {"greeting": f"Hello {name}"}

        schema = {
            "type": "function",
            "function": {
                "name": "my_tool",
                "description": "A test tool",
                "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
            }
        }
        reg.register(Tool(name="my_tool", fn=my_tool, schema=schema, permission="ALLOW"))

        result = reg.dispatch("my_tool", {"name": "World"})
        assert result["greeting"] == "Hello World"

    def test_unknown_tool(self):
        """dispatch 未知工具应返回 error。"""
        reg = ToolRegistry()
        result = reg.dispatch("nonexistent", {})
        assert "error" in result

    def test_tool_error_handling(self):
        """工具执行出错应返回 error，不崩溃。"""
        reg = ToolRegistry()

        def failing_tool() -> dict:
            raise ValueError("bang")

        schema = {"type": "function", "function": {"name": "fail", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}}}
        reg.register(Tool(name="fail", fn=failing_tool, schema=schema, permission="ALLOW"))

        result = reg.dispatch("fail", {})
        assert "error" in result
        assert "ValueError" in str(result["error"])

    def test_get_schemas(self):
        """get_schemas 应返回 OpenAI tool-calling 格式。"""
        reg = ToolRegistry()

        def tool_a():
            return {}
        def tool_b():
            return {}

        schema = {"type": "function", "function": {"name": "a", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}}}
        reg.register(Tool(name="a", fn=tool_a, schema=schema, permission="ALLOW"))
        reg.register(Tool(name="b", fn=tool_b, schema=schema, permission="ALLOW"))

        schemas = reg.get_schemas()
        assert len(schemas) == 2
        for s in schemas:
            assert s["type"] == "function"

    def test_list_tools(self):
        """list() 应返回所有注册工具。"""
        reg = ToolRegistry()

        def t1(): return {}
        schema = {"type": "function", "function": {"name": "t1", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}}}
        reg.register(Tool(name="t1", fn=t1, schema=schema, permission="ALLOW"))

        tools = reg.list()
        assert len(tools) == 1
        assert tools[0].name == "t1"


class TestBuiltinTools:
    """内置工具执行测试。"""

    def test_do_read(self, tmp_path):
        from tools import do_read, set_tool_workspace
        set_tool_workspace(str(tmp_path))
        path = "test.txt"  # relative path within workspace
        full_path = str(tmp_path / path)
        with open(full_path, "w") as f:
            f.write("line1\nline2\nline3\n")

        result = do_read(path=path)
        assert "content" in result
        assert "line1" in result["content"]

    def test_do_read_not_found(self):
        from tools import do_read
        # 相对路径的非存在文件
        result = do_read(path="nonexistent/file.txt")
        assert "error" in result

    def test_do_write_and_read(self, tmp_path):
        from tools import do_write, do_read, set_tool_workspace
        set_tool_workspace(str(tmp_path))

        write_result = do_write(path="writing.txt", content="hello world")
        assert write_result["wrote"] > 0

        read_result = do_read(path="writing.txt")
        assert "hello world" in read_result["content"]

    def test_do_search_files(self, tmp_path):
        from tools import do_search, set_tool_workspace
        set_tool_workspace(str(tmp_path))
        os.makedirs(str(tmp_path / "sub"), exist_ok=True)

        result = do_search(query="*.py", path=".", mode="files", file_glob="*.py")
        assert result["mode"] == "files"

    def test_do_search_content(self, tmp_path):
        from tools import do_search, set_tool_workspace
        set_tool_workspace(str(tmp_path))
        path = str(tmp_path / "search_test.txt")
        with open(path, "w") as f:
            f.write("needle in the haystack")

        result = do_search(query="needle", path=".", mode="content")
        assert result["count"] >= 1

    def test_do_memory_add(self, tmp_path):
        from tools import do_memory, set_memory_workspace
        ws = str(tmp_path)
        set_memory_workspace(ws)
        from memory_tool import ensure_memory_files
        ensure_memory_files(ws)

        result = do_memory(action="add", target="memory", content="测试记忆条目")
        assert result["ok"] is True


class TestToolDecorator:
    """@tool 装饰器测试。"""

    def test_decorator_generates_meta(self):
        from tools import tool as tool_dec

        @tool_dec(permission="ALLOW")
        def sample_tool(param1: str, param2: int = 0) -> dict:
            """Sample tool for testing."""
            return {"ok": True}

        assert hasattr(sample_tool, '_tool_meta')
        meta = sample_tool._tool_meta
        assert meta["name"] == "sample_tool"
        assert meta["permission"] == "ALLOW"
        assert meta["schema"]["type"] == "function"
