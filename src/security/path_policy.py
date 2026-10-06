"""
CoreMind Backend — Path Policy.

Restricts all file operations to the active project directory.
Prevents directory traversal and access outside the project root.
"""

from __future__ import annotations

from pathlib import Path

from src.utils.errors import ErrorCode, ToolError
from src.utils.logger import logger

# Paths that are NEVER accessible regardless of project root
BLOCKED_PATHS = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".git/config",
    "credentials",
    "secrets.json",
    ".aws/credentials",
    ".aws/config",
    ".ssh/id_rsa",
    ".ssh/id_ed25519",
}

BLOCKED_EXTENSIONS = {
    ".pem", ".key", ".p12", ".pfx", ".jks",
    ".cer", ".crt", ".keystore",
}



SYSTEM_ABSOLUTE_ROOTS = (
    "/etc", "/var", "/tmp", "/usr", "/bin", "/opt", "/dev",
    "/proc", "/sys", "/System", "/Library", "/Applications",
    "/Windows", "/Program Files", "/Users",
)


def normalize_project_path(file_path: str, project_path: str) -> str:
    """
    Normalize simulated absolute paths or leading slashes from LLMs
    (e.g., '/main.py', '/home/user/project/main.py', '/workspace/main.py')
    into safe relative project paths when possible.
    """
    import re
    project_root = Path(project_path).resolve()
    raw = Path(file_path)

    # 1. If it is already an absolute path that lives within project_root
    try:
        if raw.is_absolute() and raw.resolve().is_relative_to(project_root):
            return str(raw.resolve().relative_to(project_root))
    except (ValueError, RuntimeError):
        pass

    s = file_path.strip().replace("\\", "/")

    # 2. Match common simulated container/sandbox prefixes:
    # /home/<user>/<project>/... or /workspace/<project>/... or /app/<project>/...
    m = re.match(r"^(?:/(?:home/[^/]+|workspace|app|root)/[^/]+)/(.*)$", s)
    if m and m.group(1):
        candidate = m.group(1)
        if not candidate.startswith("/") and not candidate.startswith(".."):
            target = (project_root / candidate).resolve()
            if target.is_relative_to(project_root):
                return candidate

    # 3. Match project folder name as leading segment: e.g. /<project_root.name>/...
    proj_name = project_root.name
    if proj_name and s.startswith(f"/{proj_name}/"):
        candidate = s[len(f"/{proj_name}/"):]
        target = (project_root / candidate).resolve()
        if target.is_relative_to(project_root):
            return candidate

    # Never strip actual system roots if not within project_root
    for sys_root in SYSTEM_ABSOLUTE_ROOTS:
        if s == sys_root or s.startswith(sys_root + "/"):
            return file_path

    # 4. Leading slash strip: /src/app.py -> src/app.py, /main.py -> main.py
    clean = s.lstrip("/")
    target = (project_root / clean).resolve()
    if target.is_relative_to(project_root):
        return clean

    return file_path


def validate_path(file_path: str, project_path: str) -> str:
    """
    Validate that a file path is within the project root.
    Returns the cleaned relative path if valid.

    Raises ToolError if the path escapes the project directory.
    """
    try:
        norm_path = normalize_project_path(file_path, project_path)
        project_root = Path(project_path).resolve()
        target = (project_root / norm_path).resolve()

        # Check directory traversal
        if not target.is_relative_to(project_root):
            logger.error(
                "security.path.traversal_blocked",
                path=file_path,
                project=project_path,
            )
            raise ToolError(
                ErrorCode.TOOL_INVALID_PATH,
                f"Path escapes project directory: {file_path}",
            )

        # Check blocked paths
        rel_path = str(target.relative_to(project_root))
        if rel_path in BLOCKED_PATHS:
            logger.error("security.path.blocked", path=rel_path)
            raise ToolError(
                ErrorCode.TOOL_PERMISSION_DENIED,
                f"Access to '{rel_path}' is blocked for security reasons",
            )

        # Check blocked extensions
        if target.suffix.lower() in BLOCKED_EXTENSIONS:
            logger.error("security.path.blocked_extension", path=rel_path, ext=target.suffix)
            raise ToolError(
                ErrorCode.TOOL_PERMISSION_DENIED,
                f"Access to files with extension '{target.suffix}' is blocked",
            )

        return norm_path

    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            ErrorCode.TOOL_INVALID_PATH,
            f"Invalid path: {file_path} — {exc}",
        )
