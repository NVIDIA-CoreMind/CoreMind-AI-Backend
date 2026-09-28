import re
import time
from enum import Enum
from typing import Callable, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class AgentPhase(str, Enum):
    TASK = "TASK"
    PLAN = "PLAN"
    CODE = "CODE"
    RUN = "RUN"
    TEST = "TEST"
    DEBUG = "DEBUG"
    VERIFY = "VERIFY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PhaseTransitionRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_phase: AgentPhase = Field(alias="from")
    to_phase: AgentPhase = Field(alias="to")
    reason: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class AgentStateMachine:
    """Manages the 7-phase state loop: TASK -> PLAN -> CODE -> RUN -> TEST -> DEBUG -> VERIFY."""

    def __init__(
        self,
        max_debug_retries: int = 5,
        on_phase_change: Optional[Callable[[AgentPhase, AgentPhase, Optional[str]], None]] = None,
    ):
        self.max_debug_retries = max_debug_retries
        self.on_phase_change = on_phase_change
        self.current_phase: AgentPhase = AgentPhase.TASK
        self.debug_retry_count: int = 0
        self.start_time: float = time.time()
        self.history: List[PhaseTransitionRecord] = [
            PhaseTransitionRecord(
                **{"from": AgentPhase.TASK, "to": AgentPhase.TASK, "reason": "Agent initialized"}
            )
        ]

    def get_current_phase(self) -> AgentPhase:
        return self.current_phase

    def get_debug_retry_count(self) -> int:
        return self.debug_retry_count

    def get_history(self) -> List[PhaseTransitionRecord]:
        return list(self.history)

    def is_terminal(self) -> bool:
        return self.current_phase in (AgentPhase.COMPLETED, AgentPhase.FAILED)

    def transition_to(self, next_phase: AgentPhase, reason: Optional[str] = None) -> bool:
        if self.current_phase == next_phase:
            return True

        if self.is_terminal():
            return False

        if next_phase == AgentPhase.DEBUG:
            self.debug_retry_count += 1
            if self.debug_retry_count > self.max_debug_retries:
                self.transition_to(
                    AgentPhase.FAILED,
                    f"Exceeded maximum debug retries ({self.max_debug_retries})",
                )
                return False

        previous = self.current_phase
        self.current_phase = next_phase
        record = PhaseTransitionRecord(
            **{"from": previous, "to": next_phase, "reason": reason, "timestamp": time.time()}
        )
        self.history.append(record)

        if self.on_phase_change:
            self.on_phase_change(previous, next_phase, reason)

        return True

    def detect_and_transition_from_text(self, text: str) -> Optional[AgentPhase]:
        match = re.search(r"\[PHASE:\s*(TASK|PLAN|CODE|RUN|TEST|DEBUG|VERIFY)\]", text, re.IGNORECASE)
        if match:
            phase_str = match.group(1).upper()
            try:
                detected_phase = AgentPhase(phase_str)
                if detected_phase != self.current_phase:
                    self.transition_to(detected_phase, "Detected in model response")
                    return detected_phase
            except ValueError:
                pass
        return None

    def complete(self, reason: str = "Task verification successful") -> None:
        self.transition_to(AgentPhase.COMPLETED, reason)

    def fail(self, reason: str) -> None:
        self.transition_to(AgentPhase.FAILED, reason)

    def get_summary(self) -> dict:
        return {
            "current_phase": self.current_phase.value,
            "debug_retries": self.debug_retry_count,
            "total_transitions": len(self.history),
            "elapsed_ms": int((time.time() - self.start_time) * 1000),
            "history": [h.model_dump(by_alias=True) for h in self.history],
        }
