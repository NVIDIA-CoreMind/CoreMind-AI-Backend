"""
CoreMind Backend — Tool: flutter_check_env

Detects installed tools such as Flutter, Dart, Git, and VS Code.
Permission: READ
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.logger import logger

async def execute_flutter_check_env(
    project_path: str,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Check for Flutter and related tools."""
    logger.info("tools.flutter_check_env.execute", cwd=project_path)
    
    tools_to_check = {
        "flutter": "flutter --version",
        "dart": "dart --version",
        "git": "git --version",
        "code": "code --version",
    }
    
    results: dict[str, Any] = {}
    
    for tool, cmd in tools_to_check.items():
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)
            stdout = stdout_bytes.decode("utf-8", errors="ignore").strip()
            if process.returncode == 0 and stdout:
                results[tool] = {"installed": True, "version": stdout.split("\n")[0][:100]}
            else:
                results[tool] = {"installed": False, "version": None}
        except Exception:
            results[tool] = {"installed": False, "version": None}
            
    return {
        "tools": results,
        "success": True,
    }

flutter_check_env_tool = ToolDefinition(
    name="flutter_check_env",
    description=(
        "Detect if Flutter, Dart, Git, and VS Code are installed on the system "
        "and retrieve their versions. Use this to verify the environment before "
        "running Flutter commands or setting up a project."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    permission=PermissionLevel.READ,
    executor=execute_flutter_check_env,
)


async def execute_flutter_create_project(
    project_path: str,
    project_name: str,
    organization: str | None = None,
    org: str | None = None,
    platforms: Any = None,
    description: str | None = None,
    project_type: str | None = None,
    template: str | None = None,
    overwrite: bool = True,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Scaffold a new Flutter project cleanly."""
    import json
    from pathlib import Path

    logger.info("tools.flutter_create_project.execute", project=project_name, cwd=project_path)

    cmd_parts = ["flutter", "create", project_name]

    # Organization
    clean_org = org or organization or "com.example"
    cmd_parts.extend(["--org", clean_org])

    # Template
    tmpl = template or project_type
    if tmpl:
        tmpl_clean = tmpl.lower()
        if tmpl_clean in ("application", "app"):
            cmd_parts.extend(["--template", "app"])
        elif tmpl_clean in ("package", "plugin", "module"):
            cmd_parts.extend(["--template", tmpl_clean])

    # Platforms
    if platforms:
        if isinstance(platforms, str):
            try:
                parsed = json.loads(platforms)
                if isinstance(parsed, list):
                    cmd_parts.extend(["--platforms", ",".join(str(p).strip() for p in parsed)])
                else:
                    cmd_parts.extend(["--platforms", platforms.strip("[]\"' ")])
            except Exception:
                cmd_parts.extend(["--platforms", platforms.strip("[]\"' ")])
        elif isinstance(platforms, (list, tuple)):
            cmd_parts.extend(["--platforms", ",".join(str(p).strip() for p in platforms)])

    if description:
        cmd_parts.extend(["--description", description[:120]])

    if overwrite:
        cmd_parts.append("--overwrite")

    command_str = " ".join(cmd_parts)

    try:
        # Argument list, not a shell string: user-supplied names and descriptions are never parsed by a shell (SEC-02)
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=120.0)
        stdout = stdout_bytes.decode("utf-8", errors="ignore").strip()
        stderr = stderr_bytes.decode("utf-8", errors="ignore").strip()

        success = process.returncode == 0
        project_dir = Path(project_path) / project_name
        verified = project_dir.exists() and (project_dir / "pubspec.yaml").exists()

        return {
            "success": success,
            "exit_code": process.returncode,
            "command": command_str,
            "project_name": project_name,
            "project_dir": str(project_dir),
            "main_entrypoint": f"{project_name}/lib/main.dart",
            "instructions": (
                f"Scaffolded Flutter project '{project_name}'. IMPORTANT: The template creates a default counter "
                f"app at '{project_name}/lib/main.dart'. You MUST overwrite/write '{project_name}/lib/main.dart' "
                f"with the user's requested application logic and UI using write_file. Do not stop until "
                f"'{project_name}/lib/main.dart' has been updated with the actual implementation."
            ),
            "stdout": stdout,
            "stderr": stderr,
            "verified_on_disk": verified,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "command": command_str,
        }


flutter_create_project_tool = ToolDefinition(
    name="flutter_create_project",
    description=(
        "Scaffold a new Flutter project structure with complete standard directories "
        "(lib/, android/, ios/, web/, test/, pubspec.yaml). Use this to initialize new Flutter apps."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "Name of the Flutter project to create (must be valid dart package name, e.g. todo_app)",
            },
            "organization": {
                "type": "string",
                "description": "Organization in reverse domain notation (default: com.example)",
            },
            "description": {
                "type": "string",
                "description": "Short description for the project pubspec.yaml",
            },
            "platforms": {
                "type": "string",
                "description": "Target platforms (e.g. 'android,ios,web,macos,windows,linux')",
            },
            "template": {
                "type": "string",
                "description": "Project template type: app (default), package, plugin, module",
            },
        },
        "required": ["project_name"],
    },
    permission=PermissionLevel.EXECUTE,
    executor=execute_flutter_create_project,
    timeout_ms=120_000,
)

