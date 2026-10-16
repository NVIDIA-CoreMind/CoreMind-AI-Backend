"""
CoreMind Backend — Agent Planner.

Analyzes tasks and creates structured execution task graphs with dependencies.
Includes fast-path detection to skip LLM planning for simple tasks.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.agent.task_graph import TaskGraph
from src.ai.prompts.planning import build_task_analysis_prompt
from src.ai.provider import AIResponse, get_ai_provider
from src.utils.logger import logger


_SIMPLE_TASK_KEYWORDS = {
    "search", "trending", "look up", "find me", "what is", "who is",
    "tell me about", "latest", "current",
}

_CODING_ACTION_KEYWORDS = {
    "create", "edit", "write", "fix", "patch", "modify", "implement",
    "refactor", "debug", "test", "build", "delete", "remove", "add", "update",
}

_CODE_EXTENSIONS = (
    ".py", ".ts", ".js", ".html", ".css", ".json", ".dart", ".go", ".rs",
)


def _is_simple_task(task: str) -> bool:
    """Detect tasks that don't need a full LLM planning call (pure lookups/queries)."""
    lower = task.strip().lower()
    # If it involves any coding actions or file operations, it is NOT simple
    if any(kw in lower for kw in _CODING_ACTION_KEYWORDS):
        return False
    if any(ext in lower for ext in _CODE_EXTENSIONS):
        return False

    word_count = len(lower.split())
    if any(kw in lower for kw in _SIMPLE_TASK_KEYWORDS):
        return True
    if word_count <= 4:
        return True
    return False


STRUCTURED_PLAN_PROMPT = """Analyze the following coding task and generate a structured JSON execution plan following industry-standard multi-language software architecture.

Task: {task}
Project Context:
{project_context}

Rules for the Execution Plan:
1. MANDATE INDUSTRY-STANDARD ARCHITECTURE: Never plan flat root-level monolithic files. For new features or projects, plan modular layouts matching the target language (e.g., Python: src/api, src/services, src/models; TypeScript/Web: src/components, src/styles, src/services; Go: cmd/, internal/; Rust: src/, tests/; Flutter: lib/screens, lib/widgets, lib/models).
2. MODULAR STEPS: Decompose work into distinct stages: Scaffolding & Architecture -> Modular Components/Services -> Entrypoint Wiring -> Verification & Testing.

Return ONLY valid JSON in this exact structure:
{{
  "goal": "{task}",
  "tasks": [
    {{
      "id": "task_1",
      "title": "Design and scaffold directory architecture",
      "description": "Establish modular folders (src/, components, services) and project manifests",
      "dependencies": []
    }},
    {{
      "id": "task_2",
      "title": "Implement modular components and core services",
      "description": "Build single-responsibility modules in designated directories",
      "dependencies": ["task_1"]
    }},
    {{
      "id": "task_3",
      "title": "Connect application entrypoint and configs",
      "description": "Wire components together into the main entrypoint",
      "dependencies": ["task_2"]
    }},
    {{
      "id": "task_4",
      "title": "Verify build and run verification tests",
      "description": "Run tests, linters, or start local development server",
      "dependencies": ["task_3"]
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


def _parse_task_graph_from_text(raw_text: str | None, default_goal: str) -> TaskGraph:
    """Extract a TaskGraph from AI response text, parsing JSON or falling back to default steps."""
    text = (raw_text or "").strip()
    # Look for JSON code blocks or bracketed JSON
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate_json = json_match.group(1) if json_match else text

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

    # Check if this is a creation / building task
    lower_goal = default_goal.lower()
    is_creation = any(
        kw in lower_goal
        for kw in ("create", "build", "make", "develop", "scaffold", "new", "website", "api", "app")
    )

    graph = TaskGraph(goal=default_goal)
    if is_creation:
        t1 = graph.create_task(
            task_id="task_1",
            title="Design and scaffold directory architecture",
            description="Initialize modular folder structure (src/, components, services, configs) matching language conventions.",
        )
        t2 = graph.create_task(
            task_id="task_2",
            title="Implement modular core logic, models, and components",
            description="Create clean, single-responsibility files in designated directories.",
            dependencies=[t1.id],
        )
        t3 = graph.create_task(
            task_id="task_3",
            title="Wire entrypoint and application configuration",
            description="Connect modules into main entrypoint and configure build/run scripts.",
            dependencies=[t2.id],
        )
        graph.create_task(
            task_id="task_4",
            title="Verify implementation and execute project tests/build",
            description="Run syntax checks, linters, or test commands to ensure clean execution.",
            dependencies=[t3.id],
        )
        return graph

    # Fallback to standard 3-stage plan for maintenance / edits
    t1 = graph.create_task(
        task_id="task_1",
        title="Inspect and analyze existing code",
        description="Locate and read relevant files to understand context.",
    )
    t2 = graph.create_task(
        task_id="task_2",
        title="Implement requested code changes",
        description="Apply required edits cleanly according to project conventions.",
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
    """Generate a structured TaskGraph for a user task.
    
    Fast-path: simple tasks skip the LLM call entirely and use a default
    3-step plan, saving ~9-10 seconds of latency.
    """
    logger.info("agent.planner.generating_graph", task=task[:100])

    # ── Fast-path: skip LLM for simple tasks ────────────────────────
    if _is_simple_task(task):
        logger.info("agent.planner.fast_path", task=task[:100])
        return _parse_task_graph_from_text("", default_goal=task)

    # ── Full LLM planning for complex tasks ─────────────────────────
    provider = get_ai_provider()
    prompt = STRUCTURED_PLAN_PROMPT.format(task=task, project_context=project_context)

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
            max_tokens=512,
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
