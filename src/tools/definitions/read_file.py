"""
CoreMind Backend — Tool: read_file

Reads the contents of a file from the project with line numbers,
windowing, and guardrails for binary and large files.
Permission: READ
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError

MAX_FILE_SIZE = 2_000_000  # 2 MB
DEFAULT_MAX_LINES = 500


def _is_binary_file(file_path: Path) -> bool:
    """Check if file appears to be binary by inspecting first 8KB."""
    try:
        with file_path.open("rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
            return False
    except OSError:
        return False


async def execute_read_file(
    project_path: str,
    path: str = "",
    file_path: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    max_lines: int | None = DEFAULT_MAX_LINES,
    **_kwargs: Any,
) -> dict[str, Any]:
    """
    Read file contents, supporting line numbering, range selection,
    and safeguards against large/binary files.
    """
    from src.security.path_policy import validate_path

    target_rel_path = path or file_path
    if not target_rel_path:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, "Missing required argument 'path' or 'file_path'")

    valid_rel_path = validate_path(target_rel_path, project_path)
    file_obj = Path(project_path) / valid_rel_path

    if not file_obj.exists():
        raise ToolError(ErrorCode.TOOL_FILE_NOT_FOUND, f"File not found: {valid_rel_path}")

    if not file_obj.is_file():
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Not a file: {valid_rel_path}")

    stat = file_obj.stat()
    if stat.st_size > MAX_FILE_SIZE:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"File too large ({stat.st_size} bytes). Max limit is {MAX_FILE_SIZE} bytes. "
            "Please read a targeted line range using start_line and end_line.",
        )

    if _is_binary_file(file_obj):
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Cannot read binary file: {target_rel_path}")

    try:
        raw_text = file_obj.read_text(encoding="utf-8")
    except UnicodeDecodeError as err:
        raise ToolError(ErrorCode.TOOL_INVALID_ARGS, f"Cannot read binary or non-UTF8 file: {target_rel_path}") from err

    all_lines = raw_text.splitlines()
    total_lines = len(all_lines)

    # Empty file
    if total_lines == 0:
        return {
            "path": target_rel_path,
            "content": "",
            "numbered_content": "",
            "start_line": 1,
            "end_line": 0,
            "total_lines": 0,
            "lines_shown": 0,
            "truncated": False,
        }

    # Range normalization and validation
    s_line = start_line if start_line is not None else 1
    if s_line < 1:
        s_line = 1
    if s_line > total_lines:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"start_line ({s_line}) exceeds total lines in file ({total_lines}).",
        )

    e_line = end_line if end_line is not None else total_lines
    if e_line < s_line:
        raise ToolError(
            ErrorCode.TOOL_INVALID_ARGS,
            f"end_line ({e_line}) cannot be less than start_line ({s_line}).",
        )

    # Apply max_lines cap if needed
    line_limit = max_lines if (max_lines is not None and max_lines > 0) else DEFAULT_MAX_LINES
    truncated = False
    if (e_line - s_line + 1) > line_limit:
        e_line = s_line + line_limit - 1
        truncated = True

    e_line = min(e_line, total_lines)

    selected_lines = all_lines[s_line - 1 : e_line]
    raw_content = "\n".join(selected_lines)

    # Compute formatted line numbers with consistent width padding
    width = len(str(e_line))
    numbered_lines = [
        f"{idx:>{width}} | {line}"
        for idx, line in enumerate(selected_lines, start=s_line)
    ]
    numbered_content = "\n".join(numbered_lines)

    return {
        "path": target_rel_path,
        "content": raw_content,
        "numbered_content": numbered_content,
        "start_line": s_line,
        "end_line": e_line,
        "total_lines": total_lines,
        "lines_shown": len(selected_lines),
        "truncated": truncated,
    }


read_file_tool = ToolDefinition(
    name="read_file",
    description=(
        "Read file contents with line-numbered output. Supports line range selection "
        "(start_line, end_line) and max_lines to inspect relevant code sections efficiently."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file from project root",
            },
            "start_line": {
                "type": "integer",
                "description": "Optional start line (1-indexed, inclusive)",
            },
            "end_line": {
                "type": "integer",
                "description": "Optional end line (1-indexed, inclusive)",
            },
            "max_lines": {
                "type": "integer",
                "description": "Optional maximum number of lines to return (default: 500)",
            },
        },
        "required": ["path"],
    },
    permission=PermissionLevel.READ,
    executor=execute_read_file,
    timeout_ms=10_000,
)
