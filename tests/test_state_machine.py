import pytest
from app.agent.state_machine import AgentPhase, AgentStateMachine


def test_initial_phase():
    sm = AgentStateMachine()
    assert sm.get_current_phase() == AgentPhase.TASK
    assert not sm.is_terminal()


def test_phase_transitions():
    transitions = []
    sm = AgentStateMachine(on_phase_change=lambda f, t, r: transitions.append(t))

    assert sm.transition_to(AgentPhase.PLAN, "Planning")
    assert sm.transition_to(AgentPhase.CODE, "Writing code")
    assert sm.transition_to(AgentPhase.RUN, "Running script")
    assert sm.transition_to(AgentPhase.TEST, "Running tests")
    assert sm.transition_to(AgentPhase.DEBUG, "Debugging")
    assert sm.transition_to(AgentPhase.VERIFY, "Verifying")
    sm.complete("All tests passed")

    assert sm.get_current_phase() == AgentPhase.COMPLETED
    assert sm.is_terminal()
    assert transitions == [
        AgentPhase.PLAN,
        AgentPhase.CODE,
        AgentPhase.RUN,
        AgentPhase.TEST,
        AgentPhase.DEBUG,
        AgentPhase.VERIFY,
        AgentPhase.COMPLETED,
    ]


def test_detect_phase_from_text():
    sm = AgentStateMachine()
    p1 = sm.detect_and_transition_from_text("[PHASE: PLAN]\nAnalyzing dependencies...")
    assert p1 == AgentPhase.PLAN
    assert sm.get_current_phase() == AgentPhase.PLAN

    p2 = sm.detect_and_transition_from_text("Now implementing functions: [PHASE: CODE]")
    assert p2 == AgentPhase.CODE
    assert sm.get_current_phase() == AgentPhase.CODE


def test_max_debug_retries():
    sm = AgentStateMachine(max_debug_retries=2)

    sm.transition_to(AgentPhase.DEBUG, "Error 1")
    assert sm.get_debug_retry_count() == 1

    sm.transition_to(AgentPhase.CODE, "Fix 1")
    sm.transition_to(AgentPhase.DEBUG, "Error 2")
    assert sm.get_debug_retry_count() == 2

    sm.transition_to(AgentPhase.CODE, "Fix 2")
    sm.transition_to(AgentPhase.DEBUG, "Error 3 - exceeds limit")

    assert sm.get_current_phase() == AgentPhase.FAILED
    assert sm.is_terminal()


def test_terminal_phase_cannot_transition():
    sm = AgentStateMachine()
    sm.complete("Finished")
    assert not sm.transition_to(AgentPhase.PLAN)
    assert sm.get_current_phase() == AgentPhase.COMPLETED
