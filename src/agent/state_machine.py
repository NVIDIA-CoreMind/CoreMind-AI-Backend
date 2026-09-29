"""
CoreMind Backend — Agent State Machine.

Explicit states with validated transitions per the PRD:

    IDLE → ANALYZING → PLANNING → EXECUTING → OBSERVING → VERIFYING → COMPLETED
                                      ↓
                              APPROVAL_REQUIRED → WAITING_FOR_APPROVAL
                                                      ↓          ↓
                                                   APPROVED    DENIED
                                                      ↓
                                                  EXECUTING

    VERIFYING → ANALYZING_ERROR → FIXING → VERIFYING (error recovery loop)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from src.utils.errors import AgentError, ErrorCode
from src.utils.logger import logger


class AgentState(StrEnum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    # Approval states
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"

    # Error recovery states
    ANALYZING_ERROR = "ANALYZING_ERROR"
    FIXING = "FIXING"

    # Stop states
    STOPPED = "STOPPED"


# Valid state transitions
TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.IDLE: {AgentState.ANALYZING},
    AgentState.ANALYZING: {AgentState.PLANNING, AgentState.FAILED},
    AgentState.PLANNING: {AgentState.EXECUTING, AgentState.FAILED},
    AgentState.EXECUTING: {
        AgentState.OBSERVING,
        AgentState.APPROVAL_REQUIRED,
        AgentState.FAILED,
        AgentState.STOPPED,
    },
    AgentState.OBSERVING: {
        AgentState.EXECUTING,
        AgentState.VERIFYING,
        AgentState.FAILED,
    },
    AgentState.VERIFYING: {
        AgentState.COMPLETED,
        AgentState.ANALYZING_ERROR,
        AgentState.FAILED,
    },
    AgentState.COMPLETED: set(),  # Terminal state
    AgentState.FAILED: set(),  # Terminal state
    AgentState.STOPPED: set(),  # Terminal state

    # Approval flow
    AgentState.APPROVAL_REQUIRED: {AgentState.WAITING_FOR_APPROVAL},
    AgentState.WAITING_FOR_APPROVAL: {
        AgentState.EXECUTING,  # Approved
        AgentState.STOPPED,    # Denied
    },

    # Error recovery loop
    AgentState.ANALYZING_ERROR: {AgentState.FIXING, AgentState.FAILED},
    AgentState.FIXING: {AgentState.VERIFYING, AgentState.FAILED},
}


class StateMachine:
    """Agent state machine with validated transitions."""

    def __init__(self, agent_id: str) -> None:
        self._state = AgentState.IDLE
        self._agent_id = agent_id
        self._history: list[dict[str, Any]] = []

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in {AgentState.COMPLETED, AgentState.FAILED, AgentState.STOPPED}

    def transition(self, new_state: AgentState) -> None:
        """Transition to a new state. Raises if the transition is invalid."""
        valid = TRANSITIONS.get(self._state, set())
        if new_state not in valid:
            raise AgentError(
                ErrorCode.AGENT_INVALID_STATE,
                f"Invalid state transition: {self._state.value} → {new_state.value}. "
                f"Valid targets: {[s.value for s in valid]}",
            )

        old_state = self._state
        self._state = new_state
        self._history.append({
            "from": old_state.value,
            "to": new_state.value,
        })

        logger.info(
            "agent.state.transition",
            agent_id=self._agent_id,
            from_state=old_state.value,
            to_state=new_state.value,
        )

    def can_transition(self, new_state: AgentState) -> bool:
        """Check if a transition is valid without performing it."""
        return new_state in TRANSITIONS.get(self._state, set())

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)
