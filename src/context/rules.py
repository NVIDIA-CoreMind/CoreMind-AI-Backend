"""
CoreMind Backend — Project Rules Loader.

Loads project-specific instructions from `.coremindrules`, `AGENTS.md`,
or `.cursorrules` to guide agent decision making and coding standards.
"""

from __future__ import annotations

from pathlib import Path
from src.utils.logger import logger

RULE_FILENAMES = [
    ".coremindrules",
    "AGENTS.md",
    ".cursorrules",
]

MAX_RULE_CHARS = 12_000


def load_project_rules(project_path: str) -> str:
    """
    Search for and load project rule files from the project root.
    Returns combined instructions formatted for the system prompt.
    """
    root = Path(project_path)
    if not root.exists() or not root.is_dir():
        return ""

    loaded_sections: list[str] = []

    for fname in RULE_FILENAMES:
        rule_file = root / fname
        if rule_file.is_file():
            try:
                content = rule_file.read_text(encoding="utf-8", errors="ignore").strip()
                if content:
                    logger.info("context.rules.loaded", file=fname, length=len(content))
                    loaded_sections.append(
                        f"### Instructions from {fname}:\n{content[:MAX_RULE_CHARS]}"
                    )
            except Exception as e:
                logger.warn("context.rules.read_failed", file=fname, error=str(e))

    if not loaded_sections:
        return ""

    return (
        "## Project-Specific Rules & Guidelines\n"
        "Strictly adhere to the following project instructions:\n\n"
        + "\n\n".join(loaded_sections)
    )
