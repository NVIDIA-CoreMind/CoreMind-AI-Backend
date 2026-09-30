"""
Tests for Phase 1 upgrades: TaskGraph, ReadFile, EditFile, Diff/Patch, Verifier.
"""

from pathlib import Path
import pytest

from src.agent.task_graph import TaskGraph, TaskNodeStatus
from src.agent.verifier import validate_syntax
from src.changes.diff import create_file_diff, generate_diff
from src.changes.patch import apply_patch, rollback_patch, validate_patch
from src.tools.definitions.edit_file import execute_edit_file
from src.tools.definitions.read_file import execute_read_file
from src.utils.errors import ToolError


class TestTaskGraph:
    """Test dynamic task graph capabilities."""

    def test_create_and_runnable_tasks(self) -> None:
        graph = TaskGraph(goal="Add authentication")
        t1 = graph.create_task("Inspect auth", task_id="task_1", priority=1)
        t2 = graph.create_task("Create service", task_id="task_2", dependencies=["task_1"], priority=2)

        # Initially, only t1 is runnable because t2 depends on t1
        runnable = graph.get_runnable_tasks()
        assert len(runnable) == 1
        assert runnable[0].id == "task_1"

        # Complete t1
        graph.complete_task("task_1", result="Found legacy auth")
        assert t1.status == TaskNodeStatus.COMPLETED

        # Now t2 is runnable
        runnable2 = graph.get_runnable_tasks()
        assert len(runnable2) == 1
        assert runnable2[0].id == "task_2"

        # Complete t2
        graph.complete_task("task_2")
        assert graph.is_completed()
        assert not graph.has_failures()

    def test_serialization(self) -> None:
        graph = TaskGraph(goal="Test goal")
        graph.create_task("T1", task_id="task_1")
        data = graph.to_dict()
        assert data["goal"] == "Test goal"
        assert len(data["tasks"]) == 1

        restored = TaskGraph.from_dict(data)
        assert restored.goal == "Test goal"
        assert restored.get_task("task_1") is not None


class TestReadFile:
    """Test upgraded read_file with line numbers and windowing."""

    @pytest.mark.asyncio
    async def test_read_file_line_numbers(self, tmp_path: Path) -> None:
        file = tmp_path / "sample.py"
        file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")

        res = await execute_read_file(
            project_path=str(tmp_path),
            path="sample.py",
            start_line=2,
            end_line=4,
        )

        assert res["total_lines"] == 5
        assert res["lines_shown"] == 3
        assert "2 | line 2" in res["numbered_content"]
        assert "4 | line 4" in res["numbered_content"]

    @pytest.mark.asyncio
    async def test_read_file_invalid_range_raises(self, tmp_path: Path) -> None:
        file = tmp_path / "sample.py"
        file.write_text("line 1\nline 2\n")

        with pytest.raises(ToolError):
            await execute_read_file(
                project_path=str(tmp_path),
                path="sample.py",
                start_line=10,
                end_line=2,
            )


class TestDiffAndPatch:
    """Test unified diff and patch application / rollback."""

    def test_diff_generation_and_patching(self) -> None:
        old = "def hello():\n    print('hello')\n"
        new = "def hello():\n    print('hello world')\n"

        diff = generate_diff(old, new, "test.py")
        assert "-    print('hello')" in diff
        assert "+    print('hello world')" in diff

        assert validate_patch(old, diff)
        patched = apply_patch(old, diff)
        assert patched == new

        # Rollback
        restored = rollback_patch(patched, diff)
        assert restored == old

    def test_file_diff_metadata(self) -> None:
        old = "line 1\nline 2\n"
        new = "line 1\nline 2 modified\nline 3\n"
        fd = create_file_diff(old, new, "file.txt")
        assert fd.path == "file.txt"
        assert fd.status == "modified"
        assert fd.additions > 0


class TestEditFileMultiStrategy:
    """Test multi-strategy safe editing."""

    @pytest.mark.asyncio
    async def test_exact_replacement(self, tmp_path: Path) -> None:
        f = tmp_path / "app.py"
        f.write_text("a = 1\nb = 2\n")

        res = await execute_edit_file(
            project_path=str(tmp_path),
            path="app.py",
            old_content="b = 2",
            new_content="b = 42",
        )
        assert res["strategy"] == "exact"
        assert f.read_text() == "a = 1\nb = 42\n"

    @pytest.mark.asyncio
    async def test_line_range_editing(self, tmp_path: Path) -> None:
        f = tmp_path / "app.py"
        f.write_text("x = 10\ny = 20\nz = 30\n")

        res = await execute_edit_file(
            project_path=str(tmp_path),
            path="app.py",
            start_line=2,
            end_line=2,
            new_content="y = 999",
        )
        assert res["strategy"] == "line_range"
        assert "y = 999" in f.read_text()

    @pytest.mark.asyncio
    async def test_multi_chunk_replacement(self, tmp_path: Path) -> None:
        f = tmp_path / "app.py"
        f.write_text("x = 1\ny = 2\nz = 3\n")

        res = await execute_edit_file(
            project_path=str(tmp_path),
            path="app.py",
            chunks=[
                {"old_content": "x = 1", "new_content": "x = 100"},
                {"old_content": "z = 3", "new_content": "z = 300"},
            ],
        )
        assert res["strategy"] == "multi_chunk"
        assert f.read_text() == "x = 100\ny = 2\nz = 300\n"

    @pytest.mark.asyncio
    async def test_fuzzy_fallback(self, tmp_path: Path) -> None:
        f = tmp_path / "app.py"
        f.write_text("def test():   \n    val = 10  \n    return val\n")

        # Notice differences in trailing whitespace
        res = await execute_edit_file(
            project_path=str(tmp_path),
            path="app.py",
            old_content="def test():\n    val = 10\n    return val",
            new_content="def test():\n    return 42",
        )
        assert res["strategy"] == "fuzzy_fallback"
        assert "return 42" in f.read_text()

    @pytest.mark.asyncio
    async def test_syntax_validation_prevents_broken_file(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("x = 1\n")

        with pytest.raises(ToolError) as exc_info:
            await execute_edit_file(
                project_path=str(tmp_path),
                path="bad.py",
                old_content="x = 1",
                new_content="def broken_syntax(:",
            )
        assert "Syntax validation" in str(exc_info.value) or "syntax error" in str(exc_info.value).lower()
        # Original file must remain untouched!
        assert f.read_text() == "x = 1\n"


class TestSyntaxValidator:
    """Test syntax validation for multiple languages."""

    def test_python_valid_and_invalid(self) -> None:
        ok, _ = validate_syntax("file.py", "x = [1, 2, 3]\n")
        assert ok

        ok2, err2 = validate_syntax("file.py", "def func(:\n")
        assert not ok2
        assert "SyntaxError" in err2

    def test_json_valid_and_invalid(self) -> None:
        ok, _ = validate_syntax("config.json", '{"key": "value"}')
        assert ok

        ok2, err2 = validate_syntax("config.json", '{"key": value}')
        assert not ok2
        assert "JSONDecodeError" in err2

    def test_javascript_with_regex_delimiters(self) -> None:
        ok, _ = validate_syntax("app.js", "const regex = /\\{/g;\nconst r2 = /\\}/i;\nfunction test() { return 1; }\n")
        assert ok

    @pytest.mark.asyncio
    async def test_tool_parameter_aliases(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from src.tools.definitions.write_file import execute_write_file

        project = str(tmp_path)
        # write_file with file_path alias
        w_res = await execute_write_file(project_path=project, file_path="hello.txt", content="hello world")
        assert w_res["path"] == "hello.txt"
        assert (tmp_path / "hello.txt").read_text() == "hello world"

        # read_file with file_path alias
        r_res = await execute_read_file(project_path=project, file_path="hello.txt")
        assert r_res["content"] == "hello world"

        # edit_file with target_content and replacement_content
        e_res = await execute_edit_file(
            project_path=project,
            file_path="hello.txt",
            target_content="hello world",
            replacement_content="hello universe",
        )
        assert e_res["action"] == "edited"
        assert (tmp_path / "hello.txt").read_text() == "hello universe"
