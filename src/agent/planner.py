"""
CoreMind Backend — Agent Planner.

Asks Nemotron to analyze a task and create an execution plan.
"""

from __future__ import annotations

from typing import Any

from src.ai.prompts.planning import build_task_analysis_prompt
from src.ai.provider import AIResponse, get_ai_provider
from src.utils.logger import logger


async def analyze_task(task: str, project_context: str) -> AIResponse:
    """Ask Nemotron to analyze a task before planning."""
    provider = get_ai_provider()
    prompt = build_task_analysis_prompt(task, project_context)

    logger.info("agent.planner.analyzing", task=task[:100])

    response = await provider.chat(
        messages=[
            {
                "role": "system",
                "content": "You are an expert software engineer."
                " Analyze tasks thoroughly.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

    return response


async def create_plan(
    task: str,
    project_context: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> AIResponse:
    """Ask Nemotron to create an execution plan and start working."""
    provider = get_ai_provider()

    logger.info("agent.planner.planning", task=task[:100])

    response = await provider.chat(
        messages=messages,
        tools=tools,
        temperature=0.0,
    )

    return response
