"""
CoreMind Backend — Tool: get_diagnostics

Retrieves compiler, analyzer, linter, or syntax diagnostics for project files.
Permission: READ
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.security.path_policy import validate_path
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger


async def execute_get_diagnostics(
    project_path: str,
    path: str | None = None,
    file_path: str | None = None,
    severity: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Retrieve diagnostics for a file or the whole workspace."""
    target_rel = path or file_path
    if target_rel:
        target_rel = validate_path(target_rel, project_path)

    diagnostics: list[dict[str, Any]] = []
    root = Path(project_path)

    # 1. Target specific file if provided
    files_to_check: list[Path] = []
    if target_rel:
        p = root / target_rel
        if p.exists() and p.is_file():
            files_to_check.append(p)
        else:
            raise ToolError(ErrorCode.TOOL_FILE_NOT_FOUND, f"File not found: {target_rel}")
    else:
        # Check python/ts/js/dart source files up to 20 files
        for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.dart"):
            for f in root.glob(f"src/**/{ext}"):
                if f.is_file() and not any(part.startswith(".") for part in f.parts):
                    files_to_check.append(f)
                    if len(files_to_check) >= 20:
                        break
            if len(files_to_check) >= 20:
                break

    # Run Python AST syntax checks
    for f in files_to_check:
        rel = str(f.relative_to(root))
        if f.suffix == ".py":
            try:
                content = f.read_text(encoding="utf-8")
                ast.parse(content, filename=str(f))
            except SyntaxError as e:
                diagnostics.append({
                    "file": rel,
                    "line": e.lineno or 1,
                    "column": e.offset or 1,
                    "severity": "error",
                    "message": f"SyntaxError: {e.msg}",
                    "source": "python-ast",
                })
            except Exception as e:
                diagnostics.append({
                    "file": rel,
                    "line": 1,
                    "column": 1,
                    "severity": "error",
                    "message": f"ParseError: {e}",
                    "source": "python-ast",
                })

    # Run linter tool if available (ruff / dart analyze / tsc)
    if (root / "pyproject.toml").exists() or any(f.suffix == ".py" for f in files_to_check):
        if shutil.which("ruff"):
            try:
                cmd = ["ruff", "check"]
                if target_rel:
                    cmd.append(target_rel)
                else:
                    cmd.append(".")
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path, timeout=10)
                for line in proc.stdout.splitlines():
                    if ":" in line:
                        parts = line.split(":", 3)
                        if len(parts) >= 3:
                            file_p = parts[0].strip()
                            line_n = int(parts[1].strip()) if parts[1].strip().isdigit() else 1
                            col_n = int(parts[2].strip()) if len(parts) > 3 and parts[2].strip().isdigit() else 1
                            msg = parts[-1].strip()
                            diagnostics.append({
                                "file": file_p,
                                "line": line_n,
                                "column": col_n,
                                "severity": "warning",
                                "message": msg,
                                "source": "ruff",
                            })
            except Exception:
                pass

    if (root / "pubspec.yaml").exists() or any(f.suffix == ".dart" for f in files_to_check):
        dart_cmd = shutil.which("dart") or shutil.which("flutter")
        if dart_cmd:
            try:
                cmd = [dart_cmd, "analyze"]
                if target_rel:
                    cmd.append(target_rel)
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path, timeout=15)
                output = proc.stdout or proc.stderr
                for line in output.splitlines():
                    if " • " in line:
                        diagnostics.append({
                            "file": target_rel or "project",
                            "line": 1,
                            "column": 1,
                            "severity": "error" if "error" in line.lower() else "warning",
                            "message": line.strip(),
                            "source": "dart-analyzer",
                        })
            except Exception:
                pass

    # Filter severity if requested
    if severity:
        sev_lower = severity.lower()
        diagnostics = [d for d in diagnostics if d["severity"].lower() == sev_lower]

    total_errors = sum(1 for d in diagnostics if d["severity"] == "error")
    total_warnings = sum(1 for d in diagnostics if d["severity"] == "warning")

    logger.info("tools.get_diagnostics", file=target_rel or "all", errors=total_errors, warnings=total_warnings)

    return {
        "target": target_rel or "workspace",
        "diagnostics": diagnostics[:100],
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "clean": len(diagnostics) == 0,
    }


get_diagnostics_tool = ToolDefinition(
    name="get_diagnostics",
    description="Retrieve compiler, analyzer, linter, or syntax diagnostics for a file or workspace.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Optional relative path to a specific file to check",
            },
            "severity": {
                "type": "string",
                "enum": ["error", "warning"],
                "description": "Optional filter for diagnostic severity",
            },
        },
    },
    permission=PermissionLevel.READ,
    executor=execute_get_diagnostics,
    timeout_ms=30_000,
)
