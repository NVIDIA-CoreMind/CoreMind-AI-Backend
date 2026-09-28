import re
from pathlib import Path
from typing import Optional
from app.tools.types import ToolResult


def resolve_safe_path(workspace_root: str | Path, target_path: str) -> Path:
    """Resolve target path ensuring it strictly resides within workspace root."""
    root = Path(workspace_root).resolve()
    target = Path(target_path)
    resolved = (root / target).resolve() if not target.is_absolute() else target.resolve()

    try:
        resolved.relative_to(root)
    except ValueError:
        raise PermissionError(
            f'Access denied: Path "{target_path}" resolves outside of workspace root "{root}"'
        )

    return resolved


async def execute_read_file(
    workspace_root: str | Path,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> ToolResult:
    try:
        safe_path = resolve_safe_path(workspace_root, file_path)
        if not safe_path.exists():
            return ToolResult(success=False, error=f'File "{file_path}" does not exist.')

        content = safe_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        total_lines = len(lines)

        if start_line is not None or end_line is not None:
            start = max(1, start_line if start_line is not None else 1)
            end = min(total_lines, end_line if end_line is not None else total_lines)
            selected = lines[start - 1 : end]
            numbered = "\n".join(f"{start + i}: {line}" for i, line in enumerate(selected))

            return ToolResult(
                success=True,
                data={
                    "content": numbered,
                    "total_lines": total_lines,
                    "range": [start, end],
                },
            )

        return ToolResult(
            success=True,
            data={"content": content, "total_lines": total_lines},
        )
    except Exception as exc:
        return ToolResult(success=False, error=f'Failed to read file "{file_path}": {exc}')


async def execute_write_file(
    workspace_root: str | Path,
    file_path: str,
    content: str,
) -> ToolResult:
    try:
        safe_path = resolve_safe_path(workspace_root, file_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")
        bytes_written = len(content.encode("utf-8"))

        return ToolResult(
            success=True,
            data={"path": file_path, "bytes_written": bytes_written},
            message=f"Successfully wrote {bytes_written} bytes to {file_path}",
        )
    except Exception as exc:
        return ToolResult(success=False, error=f'Failed to write file "{file_path}": {exc}')


def apply_search_replace_patch(source: str, patch: str) -> Optional[str]:
    """Parse and apply <<<<<<< SEARCH ... ======= ... >>>>>>> blocks."""
    block_pattern = re.compile(r"<<<<<<< SEARCH\r?\n([\s\S]*?)\r?\n=======\r?\n([\s\S]*?)\r?\n>>>>>>>")
    matches = list(block_pattern.finditer(patch))
    if not matches:
        return None

    result = source
    for match in matches:
        search_block = match.group(1)
        replace_block = match.group(2)

        if search_block in result:
            result = result.replace(search_block, replace_block, 1)
        else:
            # Normalize newlines and retry
            norm_res = result.replace("\r\n", "\n")
            norm_search = search_block.replace("\r\n", "\n")
            if norm_search in norm_res:
                norm_replace = replace_block.replace("\r\n", "\n")
                result = norm_res.replace(norm_search, norm_replace, 1)
            else:
                return None
    return result


async def execute_apply_diff(
    workspace_root: str | Path,
    file_path: str,
    patch: str,
) -> ToolResult:
    try:
        safe_path = resolve_safe_path(workspace_root, file_path)
        if not safe_path.exists():
            return ToolResult(
                success=False,
                error=f'Cannot apply diff: Target file "{file_path}" does not exist.',
            )

        original_content = safe_path.read_text(encoding="utf-8")
        patched_content = apply_search_replace_patch(original_content, patch)

        if patched_content is None:
            return ToolResult(
                success=False,
                error=f'Failed to apply patch to "{file_path}". Target search block not found.',
            )

        safe_path.write_text(patched_content, encoding="utf-8")
        return ToolResult(
            success=True,
            data={"path": file_path, "applied": True},
            message=f"Successfully applied diff to {file_path}",
        )
    except Exception as exc:
        return ToolResult(success=False, error=f'Error applying diff to "{file_path}": {exc}')
