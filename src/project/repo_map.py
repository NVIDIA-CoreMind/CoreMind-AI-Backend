"""
CoreMind Backend — Repository Map Generator.

Builds a compact structural and symbol-aware representation of the project
that fits efficiently in LLM context windows without loading full files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.project.symbols import SymbolInfo, extract_symbols_from_file

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "coverage", ".dart_tool",
    ".pytest_cache", ".ruff_cache",
}

INTERESTING_EXTS = {".py", ".dart", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}


class RepoMap:
    """Generates compact project summaries with structural hierarchy and key symbols."""

    def __init__(self, project_path: str) -> None:
        self.project_path = Path(project_path)
        self._symbols_cache: dict[str, list[SymbolInfo]] = {}

    def scan_symbols(self, max_files: int = 80) -> dict[str, list[SymbolInfo]]:
        """Scan key code files and extract symbol metadata."""
        if not self.project_path.exists():
            return {}

        results: dict[str, list[SymbolInfo]] = {}
        count = 0

        for dirpath, dirnames, filenames in os.walk(self.project_path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

            for fname in sorted(filenames):
                p = Path(dirpath) / fname
                if p.suffix.lower() in INTERESTING_EXTS:
                    rel = str(p.relative_to(self.project_path))
                    syms = extract_symbols_from_file(p, rel)
                    if syms:
                        results[rel] = syms
                        count += 1
                        if count >= max_files:
                            break
            if count >= max_files:
                break

        self._symbols_cache = results
        return results

    def build_compact_summary(self, max_chars: int = 4000) -> str:
        """
        Build a compact, human-readable summary of the codebase.
        Format:
        path/file.py
          class MyClass
            method1()
            method2()
          func1()
        """
        if not self._symbols_cache:
            self.scan_symbols()

        lines: list[str] = ["## Repository Map & Key Symbols"]
        current_len = len(lines[0])

        for rel_path, syms in self._symbols_cache.items():
            file_header = f"\n{rel_path}"
            file_lines = [file_header]

            for sym in syms:
                if sym.kind == "class":
                    file_lines.append(f"  class {sym.name}")
                    for child in sym.children[:6]:  # Limit child methods
                        file_lines.append(f"    {child.signature or child.name + '()'}")
                elif sym.kind in ("function", "interface"):
                    file_lines.append(f"  {sym.signature or sym.name + '()'}")

            block = "\n".join(file_lines)
            if current_len + len(block) > max_chars:
                lines.append("\n  ... [more files indexed]")
                break

            lines.append(block)
            current_len += len(block)

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        if not self._symbols_cache:
            self.scan_symbols()

        return {
            "project_path": str(self.project_path),
            "files_indexed": len(self._symbols_cache),
            "symbols": {
                f: [s.to_dict() for s in syms]
                for f, syms in self._symbols_cache.items()
            },
        }
