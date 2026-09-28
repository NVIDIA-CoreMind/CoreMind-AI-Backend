import json
from pathlib import Path
from typing import Any, Dict, List, Union
from app.sandbox.python_runner import PythonRunner, default_python_runner
from app.tools.file_tools import execute_read_file, execute_write_file, execute_apply_diff
from app.tools.sandbox_tools import execute_run_sandbox_python, execute_run_sandbox_tests
from app.tools.types import (
    ReadFileArgs,
    WriteFileArgs,
    ApplyDiffArgs,
    RunSandboxPythonArgs,
    RunSandboxTestsArgs,
    ToolResult,
)

CORE_MIND_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file within the workspace. Supports viewing specific line spans.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file within the active workspace.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional 1-indexed starting line number.",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional 1-indexed ending line number.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely overwrite an existing file with provided content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path where the file will be saved.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The raw UTF-8 string content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_diff",
            "description": "Apply surgical diff modifications to an existing file using search/replace blocks: <<<<<<< SEARCH ... ======= ... >>>>>>>",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path of the target file to patch.",
                    },
                    "patch": {
                        "type": "string",
                        "description": "<<<<<<< SEARCH / ======= / >>>>>>> block patch string.",
                    },
                },
                "required": ["path", "patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sandbox_python",
            "description": "Execute Python code or a Python script inside the isolated execution sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code snippet to execute directly.",
                    },
                    "script_path": {
                        "type": "string",
                        "description": "Relative path to an existing Python file in workspace to execute.",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional CLI arguments to pass to the script.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Optional timeout in milliseconds.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sandbox_tests",
            "description": "Execute pytest or unittest test suites inside the isolated sandbox and capture complete test outcomes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_command": {
                        "type": "string",
                        "description": 'Optional custom test command, e.g. "pytest tests/ -v".',
                    },
                    "test_path": {
                        "type": "string",
                        "description": "Optional relative path to a specific test file or directory.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Optional timeout in milliseconds.",
                    },
                },
            },
        },
    },
]


class ToolRegistry:
    def __init__(self, runner: PythonRunner = default_python_runner):
        self.runner = runner

    def get_tools(self) -> List[Dict[str, Any]]:
        return CORE_MIND_TOOLS

    async def execute_tool(
        self,
        tool_name: str,
        raw_args: Union[str, Dict[str, Any]],
        workspace_root: Union[str, Path],
    ) -> ToolResult:
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args)
            except Exception as err:
                return ToolResult(
                    success=False,
                    error=f'Malformed JSON arguments for tool "{tool_name}": {err}',
                )
        else:
            parsed_args = raw_args

        try:
            if tool_name == "read_file":
                args = ReadFileArgs(**parsed_args)
                return await execute_read_file(
                    workspace_root,
                    args.path,
                    args.start_line,
                    args.end_line,
                )
            elif tool_name == "write_file":
                args = WriteFileArgs(**parsed_args)
                return await execute_write_file(workspace_root, args.path, args.content)
            elif tool_name == "apply_diff":
                args = ApplyDiffArgs(**parsed_args)
                return await execute_apply_diff(workspace_root, args.path, args.patch)
            elif tool_name == "run_sandbox_python":
                args = RunSandboxPythonArgs(**parsed_args)
                return await execute_run_sandbox_python(self.runner, args, workspace_root)
            elif tool_name == "run_sandbox_tests":
                args = RunSandboxTestsArgs(**parsed_args)
                return await execute_run_sandbox_tests(self.runner, args, workspace_root)
            else:
                return ToolResult(
                    success=False,
                    error=f'Unsupported tool: "{tool_name}". Available tools: read_file, write_file, apply_diff, run_sandbox_python, run_sandbox_tests.',
                )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f'Unexpected error executing tool "{tool_name}": {exc}',
            )


default_tool_registry = ToolRegistry()
