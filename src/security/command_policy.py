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


from enum import StrEnum

class CommandClassification(StrEnum):
    SAFE = "safe"
    RISKY = "risky"
    DESTRUCTIVE = "destructive"

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

def classify_command(command: str) -> CommandClassification:
    """Classify a command into SAFE, RISKY, or DESTRUCTIVE."""
    cmd = command.strip().split()[0] if command.strip() else ""
    if not cmd:
        return CommandClassification.SAFE

    if any(pattern.search(command) for pattern in BLOCKED_COMMANDS):
        return CommandClassification.DESTRUCTIVE

    # Potentially risky commands that need approval
    risky_prefixes = ["rm", "mv", "cp", "kill", "pkill", "chmod", "chown", "apt", "apt-get", "yum", "dnf", "brew"]
    if any(cmd.startswith(prefix) for prefix in risky_prefixes):
        return CommandClassification.RISKY

    # Network-related
    network_commands = ["curl", "wget", "scp", "ssh", "ftp", "nc", "telnet"]
    if any(cmd.startswith(prefix) for prefix in network_commands):
        return CommandClassification.RISKY

    if any(cmd.startswith(prefix) for prefix in SAFE_PREFIXES):
        return CommandClassification.SAFE

    # Unknown commands are considered risky by default
    return CommandClassification.RISKY

def is_safe_command(command: str) -> bool:
    """Legacy check if a command uses a known-safe prefix."""
    return classify_command(command) == CommandClassification.SAFE
