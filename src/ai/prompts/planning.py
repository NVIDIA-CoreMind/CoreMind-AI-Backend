"""
CoreMind Backend — Planning Prompt Templates.

Prompts for task analysis and execution planning.
"""

from __future__ import annotations

PLANNING_TEMPLATE = """## Task Planning

User Task: {task}

{project_context}

## Instructions

Create a detailed step-by-step plan to complete this task.
For each step, specify:
1. What you will do
2. Which tool(s) you will use
3. What you expect to happen

Start by inspecting the relevant project files to understand the current
codebase before making any changes.

Think carefully about the order of operations and potential issues.
"""


TASK_ANALYSIS_TEMPLATE = """## Task Analysis

User Task: {task}

Before creating a plan, analyze this task:
1. What type of task is this? (create, modify, fix, refactor, test)
2. What files are likely involved?
3. What are the risks or potential issues?
4. What verification is needed?

{project_context}
"""


def build_planning_prompt(task: str, project_context: str) -> str:
    """Build the planning prompt for Nemotron."""
    return PLANNING_TEMPLATE.format(task=task, project_context=project_context)


def build_task_analysis_prompt(task: str, project_context: str) -> str:
    """Build the task analysis prompt."""
    return TASK_ANALYSIS_TEMPLATE.format(task=task, project_context=project_context)
