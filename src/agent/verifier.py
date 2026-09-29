"""
CoreMind Backend — Agent Verifier.

Runs verification (tests, type checks) and determines if the
agent's work is correct or needs fixing.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.project.project_manager import project_manager
from src.sandbox.provider import get_sandbox_provider
from src.utils.logger import logger


@dataclass
class VerificationResult:
    """Result of a verification run."""

    success: bool
    command: str
    exit_code: int
    stdout: str
    stderr: str
    error_summary: str = ""


async def run_verification(
    project_path: str,
    agent_id: str,
) -> VerificationResult:
    """
    Run the project's test/verification command.

    Detects the test command from the project info and runs it
    through the sandbox provider.
    """
    info = project_manager.get_project(project_path)
    test_command = info.get("test_command", "") if info else ""

    if not test_command:
        logger.warn("agent.verifier.no_test_command", project=project_path)
        return VerificationResult(
            success=True,
            command="(no test command configured)",
            exit_code=0,
            stdout="No test command configured — skipping verification",
            stderr="",
        )

    logger.info("agent.verifier.running", command=test_command, agent_id=agent_id)

    provider = get_sandbox_provider()
    sandbox = await provider.create(project_path)
    sandbox_id = sandbox["sandbox_id"]

    try:
        result = await provider.execute(
            sandbox_id=sandbox_id,
            command=test_command,
            timeout_ms=120_000,
        )

        exit_code = result.get("exit_code", -1)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        success = exit_code == 0

        error_summary = ""
        if not success:
            # Extract the most useful error info
            error_output = stderr if stderr else stdout
            error_lines = error_output.strip().split("\n")
            # Keep last 30 lines (usually most relevant)
            error_summary = "\n".join(error_lines[-30:])

        logger.info(
            "agent.verifier.completed",
            success=success,
            exit_code=exit_code,
            agent_id=agent_id,
        )

        return VerificationResult(
            success=success,
            command=test_command,
            exit_code=exit_code,
            stdout=stdout[:10_000],
            stderr=stderr[:10_000],
            error_summary=error_summary,
        )

    finally:
        await provider.destroy(sandbox_id)
