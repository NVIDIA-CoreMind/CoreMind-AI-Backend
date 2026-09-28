/**
 * CoreMind Agent State Machine
 * Manages transitions between the 7 phases:
 * TASK -> PLAN -> CODE -> RUN -> TEST -> DEBUG -> VERIFY (-> COMPLETED / FAILED)
 */

export enum AgentPhase {
  TASK = 'TASK',
  PLAN = 'PLAN',
  CODE = 'CODE',
  RUN = 'RUN',
  TEST = 'TEST',
  DEBUG = 'DEBUG',
  VERIFY = 'VERIFY',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
}

export interface PhaseTransitionRecord {
  from: AgentPhase;
  to: AgentPhase;
  reason?: string;
  timestamp: number;
}

export interface StateMachineOptions {
  maxDebugRetries?: number;
  onPhaseChange?: (from: AgentPhase, to: AgentPhase, reason?: string) => void;
}

export class AgentStateMachine {
  private currentPhase: AgentPhase = AgentPhase.TASK;
  private history: PhaseTransitionRecord[] = [];
  private debugRetryCount: number = 0;
  private readonly maxDebugRetries: number;
  private onPhaseChange?: (from: AgentPhase, to: AgentPhase, reason?: string) => void;
  private startTime: number = Date.now();

  constructor(options?: StateMachineOptions) {
    this.maxDebugRetries = options?.maxDebugRetries ?? 5;
    this.onPhaseChange = options?.onPhaseChange;
    this.history.push({
      from: AgentPhase.TASK,
      to: AgentPhase.TASK,
      reason: 'Agent initialized',
      timestamp: this.startTime,
    });
  }

  public getCurrentPhase(): AgentPhase {
    return this.currentPhase;
  }

  public getDebugRetryCount(): number {
    return this.debugRetryCount;
  }

  public getHistory(): PhaseTransitionRecord[] {
    return [...this.history];
  }

  public isTerminal(): boolean {
    return this.currentPhase === AgentPhase.COMPLETED || this.currentPhase === AgentPhase.FAILED;
  }

  /**
   * Transition to a new phase if allowed
   */
  public transitionTo(nextPhase: AgentPhase, reason?: string): boolean {
    if (this.currentPhase === nextPhase) {
      return true; // No-op
    }

    if (this.isTerminal()) {
      console.warn(`[StateMachine] Cannot transition from terminal phase ${this.currentPhase} to ${nextPhase}`);
      return false;
    }

    // Increment retry count when entering DEBUG
    if (nextPhase === AgentPhase.DEBUG) {
      this.debugRetryCount++;
      if (this.debugRetryCount > this.maxDebugRetries) {
        console.warn(`[StateMachine] Maximum debug retries (${this.maxDebugRetries}) exceeded. Failing task.`);
        this.transitionTo(AgentPhase.FAILED, `Exceeded max debug retries (${this.maxDebugRetries})`);
        return false;
      }
    }

    const previous = this.currentPhase;
    this.currentPhase = nextPhase;

    const record: PhaseTransitionRecord = {
      from: previous,
      to: nextPhase,
      reason,
      timestamp: Date.now(),
    };
    this.history.push(record);

    if (this.onPhaseChange) {
      this.onPhaseChange(previous, nextPhase, reason);
    }

    return true;
  }

  /**
   * Automatically detect phase from assistant message text containing [PHASE: XYZ]
   */
  public detectAndTransitionFromText(text: string): AgentPhase | null {
    const match = text.match(/\[PHASE:\s*(TASK|PLAN|CODE|RUN|TEST|DEBUG|VERIFY)\]/i);
    if (match && match[1]) {
      const detected = match[1].toUpperCase() as AgentPhase;
      if (detected !== this.currentPhase) {
        this.transitionTo(detected, 'Detected in model response');
        return detected;
      }
    }
    return null;
  }

  /**
   * Mark as successfully completed
   */
  public complete(reason: string = 'Task verification successful'): void {
    this.transitionTo(AgentPhase.COMPLETED, reason);
  }

  /**
   * Mark as failed
   */
  public fail(reason: string): void {
    this.transitionTo(AgentPhase.FAILED, reason);
  }

  public getSummary() {
    return {
      currentPhase: this.currentPhase,
      debugRetries: this.debugRetryCount,
      totalTransitions: this.history.length,
      elapsedMs: Date.now() - this.startTime,
      history: this.history,
    };
  }
}
