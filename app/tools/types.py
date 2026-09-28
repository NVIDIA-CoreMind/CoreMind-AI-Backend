from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ReadFileArgs(BaseModel):
    path: str = Field(description="Relative path to file in workspace")
    start_line: Optional[int] = Field(default=None, description="Optional 1-indexed starting line")
    end_line: Optional[int] = Field(default=None, description="Optional 1-indexed ending line")


class WriteFileArgs(BaseModel):
    path: str = Field(description="Relative path to file in workspace")
    content: str = Field(description="UTF-8 string content to write")


class ApplyDiffArgs(BaseModel):
    path: str = Field(description="Relative path to file in workspace")
    patch: str = Field(description="Unified diff patch or <<<<<<< SEARCH / ======= / >>>>>>> block")


class RunSandboxPythonArgs(BaseModel):
    code: Optional[str] = Field(default=None, description="Python code string to execute")
    script_path: Optional[str] = Field(default=None, description="Relative path to script in workspace")
    args: Optional[List[str]] = Field(default=None, description="CLI arguments")
    timeout: Optional[int] = Field(default=None, description="Timeout in milliseconds")


class RunSandboxTestsArgs(BaseModel):
    test_command: Optional[str] = Field(default=None, description="Custom test command, e.g. 'pytest tests/'")
    test_path: Optional[str] = Field(default=None, description="Target test file or folder")
    timeout: Optional[int] = Field(default=None, description="Timeout in milliseconds")


class SandboxExecutionResult(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    traceback: Optional[str] = None
    duration_ms: int = 0
    command: str = ""


class ToolResult(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None
