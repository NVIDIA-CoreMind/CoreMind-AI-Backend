"""
CoreMind Backend — Tool: sandbox

Execute commands via the sandbox provider abstraction.
Permission: EXECUTE
"""

from __future__ import annotations

from typing import Any

from src.sandbox.provider import get_sandbox_provider
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.logger import logger


async def execute_sandbox_execute(
    project_path: str,
    command: str,
    timeout_ms: int | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Execute a command through the sandbox provider."""
    logger.info("tools.sandbox.execute", command=command[:200])

    provider = get_sandbox_provider()

    # Create a sandbox if not already active
    sandbox = await provider.create(project_path)
    sandbox_id = sandbox["sandbox_id"]

    # Execute in sandbox
    result = await provider.execute(
        sandbox_id=sandbox_id,
        command=command,
        timeout_ms=timeout_ms,
    )

    return result


sandbox_execute_tool = ToolDefinition(
    name="sandbox_execute",
    description=(
        "Execute a command in an isolated sandbox."
        " Use for running tests, builds, and generated code."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command to execute in the sandbox",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Optional timeout in milliseconds",
            },
        },
        "required": ["command"],
    },
    permission=PermissionLevel.EXECUTE,
    executor=execute_sandbox_execute,
    timeout_ms=120_000,
)
