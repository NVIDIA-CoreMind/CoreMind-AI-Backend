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
