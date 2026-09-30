"""
CoreMind Backend — Tool: ask_question & Question Manager.

Pauses agent execution and prompts the user for clarification when critical
architectural or functional decisions cannot be determined autonomously.
State transitions to WAITING_FOR_USER, then resumes EXECUTING when answered.
Permission: READ
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent, EventType
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.errors import ErrorCode, ToolError
from src.utils.ids import short_id
from src.utils.logger import logger


@dataclass
class PendingQuestion:
    """A question awaiting user response in the IDE."""

    question_id: str
    agent_id: str
    question: str
    options: list[str] = field(default_factory=list)
    status: str = "pending"  # "pending", "answered", "cancelled"
    answer: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    future: asyncio.Future[str] = field(default_factory=lambda: asyncio.get_running_loop().create_future())

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "agent_id": self.agent_id,
            "question": self.question,
            "options": self.options,
            "status": self.status,
            "answer": self.answer,
            "created_at": self.created_at.isoformat(),
        }


class QuestionManager:
    """Coordinates questions between agent loop and user API/WebSocket."""

    def __init__(self) -> None:
        self._questions: dict[str, PendingQuestion] = {}

    async def ask(
        self,
        agent_id: str,
        question: str,
        options: list[str] | None = None,
        timeout_seconds: float = 300.0,
    ) -> str:
        """Create a pending question and wait for the user's answer."""
        qid = f"q_{short_id()}"
        loop = asyncio.get_running_loop()
        pq = PendingQuestion(
            question_id=qid,
            agent_id=agent_id,
            question=question,
            options=options or [],
            future=loop.create_future(),
        )
        self._questions[qid] = pq

        logger.info("question.created", id=qid, agent_id=agent_id, question=question[:100])

        # Emit waiting for user event
        await event_bus.emit(
            CoreMindEvent(
                type=EventType.AGENT_WAITING_FOR_USER,
                agent_id=agent_id,
                data={
                    "question_id": qid,
                    "question": question,
                    "options": options or [],
                },
            )
        )

        try:
            answer = await asyncio.wait_for(pq.future, timeout=timeout_seconds)
            pq.status = "answered"
            pq.answer = answer
            return answer
        except TimeoutError:
            pq.status = "cancelled"
            raise ToolError(
                ErrorCode.TOOL_TIMEOUT,
                f"Timed out waiting for user answer to: '{question[:80]}'",
            )

    def answer_question(self, question_id: str, answer: str) -> bool:
        """Submit the user's answer to release the waiting agent."""
        pq = self._questions.get(question_id)
        if not pq or pq.status != "pending":
            return False

        pq.status = "answered"
        pq.answer = answer
        if not pq.future.done():
            pq.future.set_result(answer)

        logger.info("question.answered", id=question_id, answer=answer[:80])
        return True

    def get_pending(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """Get all pending questions."""
        return [
            pq.to_dict()
            for pq in self._questions.values()
            if pq.status == "pending" and (agent_id is None or pq.agent_id == agent_id)
        ]


question_manager = QuestionManager()


async def execute_ask_question(
    project_path: str,
    question: str,
    options: list[str] | None = None,
    agent_id: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    """Ask the user a clarifying question and await their decision."""
    if not agent_id:
        # Fallback if agent_id not passed
        return {
            "question": question,
            "answer": "Proceed autonomously with recommended best practice.",
        }

    answer = await question_manager.ask(
        agent_id=agent_id,
        question=question,
        options=options or [],
    )

    return {
        "question": question,
        "user_answer": answer,
    }


ask_question_tool = ToolDefinition(
    name="ask_question",
    description=(
        "Ask the user a question when critical clarification or architectural decisions "
        "cannot be inferred autonomously. Pauses the agent until the user selects or types an answer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Clear question to present to the user",
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of distinct choices (e.g. ['Option A', 'Option B'])",
            },
        },
        "required": ["question"],
    },
    permission=PermissionLevel.READ,
    executor=execute_ask_question,
    timeout_ms=300_000,
)
