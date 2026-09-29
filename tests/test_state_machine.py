"""
Tests for the Agent State Machine.
"""

import pytest

from src.agent.state_machine import AgentState, StateMachine
from src.utils.errors import AgentError


class TestStateMachine:
    """Test agent state transitions."""

    def test_initial_state_is_idle(self) -> None:
        sm = StateMachine("test_agent")
        assert sm.state == AgentState.IDLE

    def test_valid_transition_idle_to_analyzing(self) -> None:
        sm = StateMachine("test_agent")
        sm.transition(AgentState.ANALYZING)
        assert sm.state == AgentState.ANALYZING

    def test_full_happy_path(self) -> None:
        sm = StateMachine("test_agent")
        sm.transition(AgentState.ANALYZING)
        sm.transition(AgentState.PLANNING)
        sm.transition(AgentState.EXECUTING)
        sm.transition(AgentState.OBSERVING)
        sm.transition(AgentState.VERIFYING)
        sm.transition(AgentState.COMPLETED)
        assert sm.state == AgentState.COMPLETED
        assert sm.is_terminal

    def test_invalid_transition_raises(self) -> None:
        sm = StateMachine("test_agent")
        with pytest.raises(AgentError):
            sm.transition(AgentState.COMPLETED)  # Can't go from IDLE to COMPLETED

    def test_approval_flow(self) -> None:
        sm = StateMachine("test_agent")
        sm.transition(AgentState.ANALYZING)
        sm.transition(AgentState.PLANNING)
        sm.transition(AgentState.EXECUTING)
        sm.transition(AgentState.APPROVAL_REQUIRED)
        sm.transition(AgentState.WAITING_FOR_APPROVAL)
        sm.transition(AgentState.EXECUTING)  # Approved
        assert sm.state == AgentState.EXECUTING

    def test_error_recovery_loop(self) -> None:
        sm = StateMachine("test_agent")
        sm.transition(AgentState.ANALYZING)
        sm.transition(AgentState.PLANNING)
        sm.transition(AgentState.EXECUTING)
        sm.transition(AgentState.OBSERVING)
        sm.transition(AgentState.VERIFYING)
        sm.transition(AgentState.ANALYZING_ERROR)
        sm.transition(AgentState.FIXING)
        sm.transition(AgentState.VERIFYING)
        sm.transition(AgentState.COMPLETED)
        assert sm.state == AgentState.COMPLETED

    def test_terminal_states_have_no_transitions(self) -> None:
        sm = StateMachine("test_agent")
        sm.transition(AgentState.ANALYZING)
        sm.transition(AgentState.FAILED)
        assert sm.is_terminal
        with pytest.raises(AgentError):
            sm.transition(AgentState.IDLE)

    def test_history_tracking(self) -> None:
        sm = StateMachine("test_agent")
        sm.transition(AgentState.ANALYZING)
        sm.transition(AgentState.PLANNING)
        assert len(sm.history) == 2
        assert sm.history[0]["from"] == "IDLE"
        assert sm.history[0]["to"] == "ANALYZING"

    def test_can_transition(self) -> None:
        sm = StateMachine("test_agent")
        assert sm.can_transition(AgentState.ANALYZING)
        assert not sm.can_transition(AgentState.COMPLETED)
