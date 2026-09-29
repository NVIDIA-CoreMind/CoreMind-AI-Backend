"""
CoreMind Backend — Coding Prompt Templates.

Prompts for code generation, modification, and debugging tasks.
"""

from __future__ import annotations

CODING_CONTEXT_TEMPLATE = """## Project Context

Project: {project_name}
Language: {language}
Framework: {framework}
Package Manager: {package_manager}
Main Entry: {main_entry}
Test Command: {test_command}

## Files Changed So Far
{files_changed}
"""

ERROR_ANALYSIS_TEMPLATE = """## Error Analysis Required

The following error occurred during verification:

```
{error_output}
```

Command: `{command}`
Exit Code: {exit_code}

Analyze this error and determine the fix. Use tools to read the relevant
files, identify the root cause, and apply targeted corrections.
"""

FIX_VERIFICATION_TEMPLATE = """## Fix Verification

Your previous fix has been applied. The verification command was re-run:

Command: `{command}`
Exit Code: {exit_code}

Output:
```
{output}
```

{result_instruction}
"""


def build_coding_context(
    project_name: str,
    language: str,
    framework: str,
    package_manager: str,
    main_entry: str,
    test_command: str,
    files_changed: list[str],
) -> str:
    """Build the coding context block for Nemotron."""
    return CODING_CONTEXT_TEMPLATE.format(
        project_name=project_name,
        language=language,
        framework=framework,
        package_manager=package_manager,
        main_entry=main_entry,
        test_command=test_command,
        files_changed="\n".join(f"- {f}" for f in files_changed) if files_changed else "None yet",
    )


def build_error_analysis(error_output: str, command: str, exit_code: int) -> str:
    """Build the error analysis prompt."""
    return ERROR_ANALYSIS_TEMPLATE.format(
        error_output=error_output,
        command=command,
        exit_code=exit_code,
    )


def build_fix_verification(command: str, exit_code: int, output: str) -> str:
    """Build the fix verification prompt."""
    result_instruction = (
        "All checks passed! Summarize the changes you made."
        if exit_code == 0
        else "The issue persists. Analyze the remaining errors and apply another fix."
    )
    return FIX_VERIFICATION_TEMPLATE.format(
        command=command,
        exit_code=exit_code,
        output=output,
        result_instruction=result_instruction,
    )
