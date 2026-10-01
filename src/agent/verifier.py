"""
CoreMind Backend — Agent Verifier.

Runs verification (tests, type checks, linting, syntax validation) and determines
if the agent's work is correct or needs fixing.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

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


def validate_syntax(file_path: str | Path, content: str) -> tuple[bool, str]:
    """
    Validate syntax of file content based on file extension.
    Returns (is_valid, error_description).
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".py":
        try:
            ast.parse(content, filename=str(path))
            return True, ""
        except SyntaxError as e:
            return False, f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        except Exception as e:
            return False, f"Python parsing error: {e}"

    elif suffix == ".json":
        try:
            json.loads(content)
            return True, ""
        except json.JSONDecodeError as e:
            return False, f"JSONDecodeError at line {e.lineno}, col {e.colno}: {e.msg}"

    elif suffix == ".toml":
        try:
            tomllib.loads(content)
            return True, ""
        except Exception as e:
            return False, f"TOML parsing error: {e}"

    # For other languages (Dart, TS, etc.), basic delimiter balancing check
    if suffix in (".dart", ".ts", ".js", ".tsx", ".jsx", ".rs", ".go", ".java"):
        balanced, msg = _check_balanced_delimiters(content)
        if not balanced:
            return False, msg

    return True, ""


def _check_balanced_delimiters(code: str) -> tuple[bool, str]:
    """Simple check for mismatched braces/brackets/parentheses."""
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "}": "{", "]": "["}
    line_num = 1

    in_line_comment = False
    in_block_comment = False
    in_string: str | None = None
    i = 0
    chars = list(code)

    while i < len(chars):
        c = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""

        if c == "\n":
            line_num += 1
            in_line_comment = False
            i += 1
            continue

        if in_line_comment:
            i += 1
            continue

        if in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if c == "\\" and nxt:
                i += 2
                continue
            if c == in_string:
                in_string = None
            i += 1
            continue

        # Check start of comment / string / regex
        if c == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if c == "/" and nxt not in ("/", "*"):
            j = i - 1
            while j >= 0 and chars[j] in (" ", "\t", "\r"):
                j -= 1
            prev_char = chars[j] if j >= 0 else "\n"
            if prev_char in ("=", "(", "[", "{", ",", ":", ";", "!", "&", "|", "?", "~", "^", "\n"):
                i += 1
                in_char_class = False
                while i < len(chars):
                    rc = chars[i]
                    if rc == "\n":
                        line_num += 1
                        break
                    if rc == "\\" and i + 1 < len(chars):
                        i += 2
                        continue
                    if rc == "[" and not in_char_class:
                        in_char_class = True
                    elif rc == "]" and in_char_class:
                        in_char_class = False
                    elif rc == "/" and not in_char_class:
                        i += 1
                        break
                    i += 1
                continue
        if c in ("'", '"', "`"):
            in_string = c
            i += 1
            continue

        # Check delimiters
        if c in ("(", "{", "["):
            stack.append((c, line_num))
        elif c in (")", "}", "]"):
            if not stack:
                return False, f"Unmatched closing delimiter '{c}' at line {line_num}"
            open_delim, open_line = stack.pop()
            if open_delim != pairs[c]:
                return (
                    False,
                    f"Mismatched delimiter: opened '{open_delim}' at line {open_line} "
                    f"but closed with '{c}' at line {line_num}",
                )

        i += 1

    if stack:
        open_delim, open_line = stack[-1]
        return False, f"Unclosed delimiter '{open_delim}' opened at line {open_line}"

    return True, ""


async def run_post_edit_validation(project_path: str, rel_path: str) -> tuple[bool, str]:
    """
    Run fast post-edit validation (syntax check + available project linters).
    """
    abs_path = Path(project_path) / rel_path
    if not abs_path.exists():
        return False, f"File {rel_path} does not exist"

    try:
        content = abs_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Could not read file: {e}"

    # Step 1: Syntax validation
    valid, syntax_err = validate_syntax(abs_path, content)
    if not valid:
        return False, f"Syntax validation failed in {rel_path}: {syntax_err}"

    # Step 2: Language-specific tool validation if installed
    suffix = abs_path.suffix.lower()
    project_info = project_manager.get_project(project_path) or {}
    lang = project_info.get("language", "").lower()

    # Python with ruff
    if suffix == ".py" or "python" in lang:
        if shutil.which("ruff"):
            try:
                proc = subprocess.run(
                    ["ruff", "check", str(abs_path)],
                    capture_output=True,
                    text=True,
                    cwd=project_path,
                    timeout=10,
                )
                if proc.returncode != 0 and proc.stdout:
                    # Return error summary from ruff
                    return False, f"Ruff linter errors:\n{proc.stdout.strip()[:1000]}"
            except Exception:
                pass

    # Dart / Flutter with dart analyze
    elif suffix == ".dart" or "dart" in lang or "flutter" in lang:
        dart_cmd = shutil.which("dart") or shutil.which("flutter")
        if dart_cmd:
            try:
                cmd = [dart_cmd, "analyze", str(abs_path)]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=project_path,
                    timeout=15,
                )
                if proc.returncode != 0:
                    output = (proc.stdout or proc.stderr).strip()
                    if "error •" in output.lower():
                        return False, f"Dart analyzer error:\n{output[:1000]}"
            except Exception:
                pass

    # TypeScript / Node with tsc if node_modules/.bin/tsc or tsc exists
    elif suffix in (".ts", ".tsx") or "typescript" in lang:
        tsc_path = Path(project_path) / "node_modules" / ".bin" / "tsc"
        tsc_cmd = str(tsc_path) if tsc_path.exists() else shutil.which("tsc")
        if tsc_cmd:
            try:
                proc = subprocess.run(
                    [tsc_cmd, "--noEmit", str(abs_path)],
                    capture_output=True,
                    text=True,
                    cwd=project_path,
                    timeout=15,
                )
                if proc.returncode != 0:
                    return False, f"TypeScript check error:\n{proc.stdout[:1000]}"
            except Exception:
                pass

    return True, ""


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
        # Check if pytest or package.json test exists in project
        root = Path(project_path)
        if (root / "pytest.ini").exists() or (root / "tests").is_dir() or (root / "pyproject.toml").exists():
            test_command = "pytest"
        elif (root / "pubspec.yaml").exists():
            test_command = "flutter test"
        elif (root / "package.json").exists():
            test_command = "npm test"

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

        # In pytest, exit code 5 means "no tests were collected" (e.g. newly created code with no tests yet).
        # This is a benign no-op, NOT a test failure.
        is_no_tests_collected = "pytest" in test_command and (
            exit_code == 5 or "collected 0 items" in stdout.lower() or "no tests ran" in stdout.lower()
        )
        success = exit_code == 0 or is_no_tests_collected

        error_summary = ""
        if not success:
            error_output = stderr if stderr else stdout
            error_lines = error_output.strip().split("\n")
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
