"""
CoreMind Backend — Command Policy.

Validates and classifies shell commands before execution.

- validate_command() is a hard block for patterns that are never allowed.
- classify_command() decides whether a command runs without approval:
  SAFE runs directly, RISKY needs approval, DESTRUCTIVE is refused.
  SAFE is an allowlist of read-only commands. Interpreters, test runners, package managers,
  shell chaining, and paths outside the workspace are all RISKY.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

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

# Tools whose arguments carry a shell command
SHELL_TOOLS = frozenset({"terminal", "run_terminal", "sandbox_execute", "run_tests", "run_build"})

# Argument names that can carry a command. Tools read different ones, so all of them are checked.
COMMAND_ARG_KEYS = ("command", "cmd", "test_command", "build_command")

# Read-only programs that may run without approval
SAFE_COMMANDS = frozenset({"cat", "head", "tail", "wc", "grep", "ls", "dir", "pwd", "echo", "which", "tree"})
# Read-only git subcommands
SAFE_GIT_SUBCOMMANDS = frozenset({"status", "diff", "log", "show"})
# find options that run programs or delete files
UNSAFE_FIND_ARGS = frozenset({"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fls"})
# Shell syntax that chains commands, substitutes output, or redirects
SHELL_OPERATORS = re.compile(r"[;&|`<>\n\r]|\$\(|\$\{")
# Files that usually hold credentials
SECRET_FILE_PATTERN = re.compile(
    r"(^|/)(\.env(\..*)?|id_rsa.*|id_ed25519.*|.*\.(pem|key|p12|pfx)|credentials|secrets\.json)$"
)


class CommandClassification(StrEnum):
    SAFE = "safe"
    RISKY = "risky"
    DESTRUCTIVE = "destructive"


_SEVERITY = {
    CommandClassification.SAFE: 0,
    CommandClassification.RISKY: 1,
    CommandClassification.DESTRUCTIVE: 2,
}


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


def _touches_outside_workspace_or_secrets(args: list[str]) -> bool:
    for arg in args:
        if arg.startswith(("/", "~")) or ".." in arg.split("/"):
            return True
        if SECRET_FILE_PATTERN.search(arg):
            return True
    return False


def classify_command(command: str) -> CommandClassification:
    """Classify a command as SAFE (runs without approval), RISKY (needs approval), or DESTRUCTIVE (refused)."""
    raw = command.strip()
    if not raw:
        return CommandClassification.SAFE

    if any(pattern.search(command) for pattern in BLOCKED_COMMANDS):
        return CommandClassification.DESTRUCTIVE

    if SHELL_OPERATORS.search(raw):
        # Chaining, substitution, and redirection can hide a second command.
        return CommandClassification.RISKY

    try:
        tokens = shlex.split(raw)
    except ValueError:
        return CommandClassification.RISKY
    if not tokens:
        return CommandClassification.SAFE

    program, args = tokens[0], tokens[1:]
    if "/" in program:
        # A path to a program could be any binary, even one named like a safe command.
        return CommandClassification.RISKY
    if _touches_outside_workspace_or_secrets(args):
        return CommandClassification.RISKY

    if program in SAFE_COMMANDS:
        return CommandClassification.SAFE
    if program == "find" and not UNSAFE_FIND_ARGS.intersection(args):
        return CommandClassification.SAFE
    if program == "git" and args and args[0] in SAFE_GIT_SUBCOMMANDS:
        return CommandClassification.SAFE
    return CommandClassification.RISKY


def is_safe_command(command: str) -> bool:
    """Check if a command is classified as safe."""
    return classify_command(command) == CommandClassification.SAFE


def extract_commands(args: Mapping[str, Any]) -> list[str]:
    """Every command-like value in a tool call, whichever argument name carried it."""
    found: list[str] = []
    for key in COMMAND_ARG_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            found.append(value)
    return found


def worst_classification(commands: Iterable[str]) -> CommandClassification:
    """The most severe classification among several commands. An empty list is SAFE."""
    worst = CommandClassification.SAFE
    for command in commands:
        current = classify_command(command)
        if _SEVERITY[current] > _SEVERITY[worst]:
            worst = current
    return worst
