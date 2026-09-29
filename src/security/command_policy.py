"""
CoreMind Backend — Command Policy.

Validates and filters shell commands before execution.
Blocks dangerous commands that could harm the host system.
"""

from __future__ import annotations

import re

from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger

# Commands that are NEVER allowed
BLOCKED_COMMANDS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-rf\s+/", re.IGNORECASE),     # rm -rf /
    re.compile(r"\brm\s+-rf\s+~", re.IGNORECASE),     # rm -rf ~
    re.compile(r"\bmkfs\b", re.IGNORECASE),             # format disk
    re.compile(r"\bdd\s+if=", re.IGNORECASE),           # disk destroy
    re.compile(r"\b:\(\)\{", re.IGNORECASE),             # fork bomb
    re.compile(r"\bcurl\b.*\|\s*(ba)?sh", re.IGNORECASE),  # curl | sh
    re.compile(r"\bwget\b.*\|\s*(ba)?sh", re.IGNORECASE),  # wget | sh
    re.compile(r"\bchmod\s+777\s+/", re.IGNORECASE),   # open perms on root
    re.compile(r"\bsudo\b", re.IGNORECASE),              # sudo anything
    re.compile(r"\bsu\s+-", re.IGNORECASE),              # switch user
    re.compile(r"\bshutdown\b", re.IGNORECASE),          # shutdown
    re.compile(r"\breboot\b", re.IGNORECASE),            # reboot
    re.compile(r"\bsystemctl\b", re.IGNORECASE),         # systemd
    re.compile(r"\blaunchctl\b", re.IGNORECASE),         # macOS services
    re.compile(r"\beval\s+\$\(", re.IGNORECASE),         # eval $(...)
    re.compile(r">>\s*/etc/", re.IGNORECASE),            # append to system files
    re.compile(r">\s*/etc/", re.IGNORECASE),             # overwrite system files
]

# Allowed command prefixes (safe by default)
SAFE_PREFIXES = [
    "python", "python3", "pip", "pip3",
    "node", "npm", "npx", "yarn", "pnpm",
    "dart", "flutter", "pub",
    "cargo", "rustc",
    "go", "go test", "go build",
    "mvn", "gradle",
    "git",
    "cat", "head", "tail", "wc", "grep", "find", "ls", "echo",
    "pytest", "ruff", "mypy", "black", "isort",
    "jest", "vitest", "eslint", "tsc",
    "make", "cmake",
]


def validate_command(command: str) -> None:
    """
    Validate a shell command before execution.

    Raises ToolError if the command matches a blocked pattern.
    """
    # Check blocked patterns
    for pattern in BLOCKED_COMMANDS:
        if pattern.search(command):
            logger.error("security.command.blocked", command=command[:200])
            raise ToolError(
                ErrorCode.TOOL_PERMISSION_DENIED,
                f"Command blocked by security policy: {command[:100]}",
            )

    logger.debug("security.command.allowed", command=command[:100])


def is_safe_command(command: str) -> bool:
    """Check if a command uses a known-safe prefix."""
    cmd = command.strip().split()[0] if command.strip() else ""
    return any(cmd.startswith(prefix) for prefix in SAFE_PREFIXES)
