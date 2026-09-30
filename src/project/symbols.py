"""
CoreMind Backend — Code Symbol Extraction.

Extracts symbols (classes, functions, methods, imports, docstrings) across
languages (Python, Dart/Flutter, TypeScript/JavaScript, Go, Rust, Java)
to build compact repository maps and power symbol search.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SymbolInfo:
    """Represents a code symbol extracted from source."""

    name: str
    kind: str  # "class", "function", "method", "interface", "import"
    file_path: str
    line_number: int
    signature: str = ""
    docstring: str = ""
    parent: str | None = None
    children: list[SymbolInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "signature": self.signature,
            "docstring": self.docstring,
            "parent": self.parent,
            "children": [c.to_dict() for c in self.children],
        }


def extract_python_symbols(source_code: str, file_path: str = "") -> list[SymbolInfo]:
    """Extract classes, functions, methods, and docstrings from Python source using ast."""
    symbols: list[SymbolInfo] = []
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError:
        return symbols

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node) or ""
            class_sym = SymbolInfo(
                name=node.name,
                kind="class",
                file_path=file_path,
                line_number=node.lineno,
                signature=f"class {node.name}",
                docstring=class_doc[:150],
            )
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_doc = ast.get_docstring(item) or ""
                    args_list = [a.arg for a in item.args.args if a.arg != "self"]
                    method_sig = f"{item.name}({', '.join(args_list)})"
                    class_sym.children.append(
                        SymbolInfo(
                            name=item.name,
                            kind="method",
                            file_path=file_path,
                            line_number=item.lineno,
                            signature=method_sig,
                            docstring=method_doc[:100],
                            parent=node.name,
                        )
                    )
            symbols.append(class_sym)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_doc = ast.get_docstring(node) or ""
            args_list = [a.arg for a in node.args.args]
            func_sig = f"{node.name}({', '.join(args_list)})"
            symbols.append(
                SymbolInfo(
                    name=node.name,
                    kind="function",
                    file_path=file_path,
                    line_number=node.lineno,
                    signature=func_sig,
                    docstring=func_doc[:150],
                )
            )

    return symbols


# Regex patterns for Dart, TypeScript, JavaScript
DART_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z0-9_]+)(?:\s+extends\s+[A-Za-z0-9_]+)?(?:\s+with\s+[A-Za-z0-9_,\s]+)?(?:\s+implements\s+[A-Za-z0-9_,\s]+)?\s*\{", re.MULTILINE)
DART_METHOD_RE = re.compile(r"^\s*(?:@override\s+)?(?:[A-Za-z0-9_<>,?\s]+\s+)?([A-Za-z0-9_]+)\s*\((.*?)\)\s*(?:async\s*)?\{", re.MULTILINE)

TS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z0-9_]+)", re.MULTILINE)
TS_INTERFACE_RE = re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z0-9_]+)", re.MULTILINE)
TS_FUNC_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\((.*?)\)", re.MULTILINE)
TS_CONST_FUNC_RE = re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>", re.MULTILINE)


def extract_dart_symbols(source_code: str, file_path: str = "") -> list[SymbolInfo]:
    """Extract classes, widgets, and methods from Dart/Flutter source."""
    symbols: list[SymbolInfo] = []
    lines = source_code.splitlines()

    current_class: SymbolInfo | None = None

    for i, line in enumerate(lines, start=1):
        class_match = DART_CLASS_RE.search(line)
        if class_match:
            class_name = class_match.group(1)
            current_class = SymbolInfo(
                name=class_name,
                kind="class",
                file_path=file_path,
                line_number=i,
                signature=line.strip().rstrip("{").strip(),
            )
            symbols.append(current_class)
            continue

        method_match = DART_METHOD_RE.search(line)
        if method_match:
            name = method_match.group(1)
            if name not in ("if", "for", "while", "switch", "catch", "return"):
                args = method_match.group(2).strip()
                method_sym = SymbolInfo(
                    name=name,
                    kind="method" if current_class else "function",
                    file_path=file_path,
                    line_number=i,
                    signature=f"{name}({args[:40]})",
                    parent=current_class.name if current_class else None,
                )
                if current_class:
                    current_class.children.append(method_sym)
                else:
                    symbols.append(method_sym)

    return symbols


def extract_ts_symbols(source_code: str, file_path: str = "") -> list[SymbolInfo]:
    """Extract classes, interfaces, and functions from TypeScript/JavaScript source."""
    symbols: list[SymbolInfo] = []
    lines = source_code.splitlines()

    for i, line in enumerate(lines, start=1):
        # Class
        m_cls = TS_CLASS_RE.search(line)
        if m_cls:
            symbols.append(
                SymbolInfo(
                    name=m_cls.group(1),
                    kind="class",
                    file_path=file_path,
                    line_number=i,
                    signature=line.strip().rstrip("{").strip(),
                )
            )
            continue

        # Interface
        m_iface = TS_INTERFACE_RE.search(line)
        if m_iface:
            symbols.append(
                SymbolInfo(
                    name=m_iface.group(1),
                    kind="interface",
                    file_path=file_path,
                    line_number=i,
                    signature=line.strip().rstrip("{").strip(),
                )
            )
            continue

        # Function
        m_fn = TS_FUNC_RE.search(line)
        if m_fn:
            symbols.append(
                SymbolInfo(
                    name=m_fn.group(1),
                    kind="function",
                    file_path=file_path,
                    line_number=i,
                    signature=f"{m_fn.group(1)}({m_fn.group(2)[:40]})",
                )
            )
            continue

        # Const arrow function
        m_arrow = TS_CONST_FUNC_RE.search(line)
        if m_arrow:
            symbols.append(
                SymbolInfo(
                    name=m_arrow.group(1),
                    kind="function",
                    file_path=file_path,
                    line_number=i,
                    signature=f"{m_arrow.group(1)}({m_arrow.group(2)[:40]})",
                )
            )

    return symbols


def extract_symbols_from_file(file_path: Path, rel_path: str = "") -> list[SymbolInfo]:
    """Extract code symbols based on file extension."""
    suffix = file_path.suffix.lower()
    rel = rel_path or str(file_path)

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    if suffix == ".py":
        return extract_python_symbols(content, rel)
    elif suffix == ".dart":
        return extract_dart_symbols(content, rel)
    elif suffix in (".ts", ".tsx", ".js", ".jsx"):
        return extract_ts_symbols(content, rel)
    return []
