"""
CoreMind Backend — Agent Planner.

Analyzes tasks and creates structured execution task graphs with dependencies.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.agent.task_graph import TaskGraph
from src.ai.prompts.planning import build_task_analysis_prompt
from src.ai.provider import AIResponse, get_ai_provider
from src.utils.logger import logger


STRUCTURED_PLAN_PROMPT = """Analyze the following coding task and generate a structured JSON execution plan.

Task: {task}
Project Context:
{project_context}

Return ONLY valid JSON in this exact structure:
{{
  "goal": "{task}",
  "tasks": [
    {{
      "id": "task_1",
      "title": "Inspect codebase and relevant files",
      "description": "Read and locate files related to the task",
      "dependencies": []
    }},
    {{
      "id": "task_2",
      "title": "Make code edits",
      "description": "Apply required changes cleanly",
      "dependencies": ["task_1"]
    }},
    {{
      "id": "task_3",
      "title": "Verify changes and fix errors",
      "description": "Run tests or linting to verify the implementation",
      "dependencies": ["task_2"]
    }}
  ]
}}
"""


async def analyze_task(task: str, project_context: str) -> AIResponse:
    """Ask AI provider to analyze a task before planning."""
    provider = get_ai_provider()
    prompt = build_task_analysis_prompt(task, project_context)

    logger.info("agent.planner.analyzing", task=task[:100])

    response = await provider.chat(
        messages=[
            {
                "role": "system",
                "content": "You are an expert software engineer. Analyze tasks thoroughly.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

    return response


def _parse_task_graph_from_text(raw_text: str, default_goal: str) -> TaskGraph:
    """Extract a TaskGraph from AI response text, parsing JSON or falling back to default steps."""
    # Look for JSON code blocks or bracketed JSON
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    candidate_json = json_match.group(1) if json_match else raw_text.strip()

    # If starts with { and ends with }
    brace_start = candidate_json.find("{")
    brace_end = candidate_json.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        candidate_json = candidate_json[brace_start : brace_end + 1]

    try:
        data = json.loads(candidate_json)
        if isinstance(data, dict) and "tasks" in data:
            return TaskGraph.from_dict(data)
    except Exception:
        pass

    # Fallback to standard 3-stage plan
    graph = TaskGraph(goal=default_goal)
    t1 = graph.create_task(
        task_id="task_1",
        title="Inspect and analyze existing code",
        description="Locate and read relevant files to understand context.",
    )
    t2 = graph.create_task(
        task_id="task_2",
        title="Implement requested code changes",
        description="Apply required edits or create files.",
        dependencies=[t1.id],
    )
    graph.create_task(
        task_id="task_3",
        title="Verify changes and resolve errors",
        description="Run verification tests or syntax checks to ensure correctness.",
        dependencies=[t2.id],
    )
    return graph


async def generate_task_graph(task: str, project_context: str) -> TaskGraph:
    """Generate a structured TaskGraph for a user task."""
    provider = get_ai_provider()
    prompt = STRUCTURED_PLAN_PROMPT.format(task=task, project_context=project_context)

    logger.info("agent.planner.generating_graph", task=task[:100])

    try:
        response = await provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are an autonomous AI coding agent planner. Return ONLY valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        return _parse_task_graph_from_text(response.content, default_goal=task)
    except Exception as exc:
        logger.warn("agent.planner.graph_generation_failed", error=str(exc))
        return _parse_task_graph_from_text("", default_goal=task)


async def create_plan(
    task: str,
    project_context: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> AIResponse:
    """Ask AI provider to create an execution plan and start working."""
    provider = get_ai_provider()

    logger.info("agent.planner.planning", task=task[:100])

    response = await provider.chat(
        messages=messages,
        tools=tools,
        temperature=0.0,
    )

    return response
