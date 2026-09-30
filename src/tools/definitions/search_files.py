"""
CoreMind Backend — Tool: search_files

Hybrid search across project files (exact string, regex, symbol, and semantic retrieval).
Permission: READ
"""

from __future__ import annotations

from typing import Any

from src.project.search import HybridCodeSearcher
from src.tools.registry import PermissionLevel, ToolDefinition


async def execute_search_files(
    project_path: str,
    pattern: str = "",
    query: str | None = None,
    file_pattern: str | None = None,
    is_regex: bool = False,
    max_results: int = 30,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Search for code or concepts across project files."""
    search_query = pattern or query or ""
    searcher = HybridCodeSearcher(project_path)
    matches = searcher.search(
        query=search_query,
        file_pattern=file_pattern,
        is_regex=is_regex,
        max_results=max_results,
    )

    return {
        "pattern": search_query,
        "matches": [m.to_dict() for m in matches],
        "total_matches": len(matches),
        "truncated": len(matches) >= max_results,
    }


search_files_tool = ToolDefinition(
    name="search_files",
    description=(
        "Hybrid search across project files. Finds exact string matches, regex patterns, "
        "code symbols (classes/methods), and conceptual/semantic matches (e.g. 'authentication logic')."
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Text, regex, symbol name, or semantic query to search for",
            },
            "file_pattern": {
                "type": "string",
                "description": "Optional glob pattern to filter files (e.g. '*.dart', '*.py')",
            },
            "is_regex": {
                "type": "boolean",
                "description": "Whether pattern should be evaluated as a regular expression",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 30)",
            },
        },
        "required": ["pattern"],
    },
    permission=PermissionLevel.READ,
    executor=execute_search_files,
    timeout_ms=30_000,
)
