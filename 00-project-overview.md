# CodeForge AI — Project Overview

## Hackathon Track
**Coding and Agentic Engineering Track**

## Project
CodeForge AI — Autonomous Software Engineering Agent

## Core Workflow

```text
TASK
  ↓
PLAN
  ↓
CODE
  ↓
RUN
  ↓
TEST
  ↓
FAIL → DEBUG → FIX → RETEST
  ↓
VERIFY
```

## Hackathon Requirements Relevant to the MVP

The submitted project must:
- Run on Nebius Token Factory or Nebius AI Cloud.
- Use at least one NVIDIA open-source model.
- Be a working software project.
- Have a public source repository with an open-source license.
- Include a README with setup/run instructions and explanation of NVIDIA/Nebius usage.
- Include a public demo video of 3 minutes or less.
- Provide a working demo URL where applicable.

## MVP Objective

Demonstrate one real end-to-end software-engineering task:

1. User submits a coding task.
2. Agent plans the implementation.
3. Agent creates/edits files.
4. Code is executed in an isolated sandbox.
5. Tests are executed.
6. Failures are captured.
7. Agent analyzes the failure.
8. Agent patches the implementation.
9. Tests are rerun.
10. Agent verifies the final result.

## MVP Scope

### Must Have
- Python support
- Task input
- Agent planning
- Code generation
- File operations
- Sandbox execution
- Test execution
- Error capture
- Debug/fix loop
- Retry limit
- Final verification
- Frontend activity/status display
- Nebius + NVIDIA model integration

### Out of Scope for MVP
- Multiple programming languages
- Full IDE
- GitHub automation
- Multi-user collaboration
- Production Kubernetes platform
- Complex multi-agent framework
- Mobile app

## Team Ownership

| Team | Primary Ownership |
|---|---|
| AI-Core | Agent, model integration, orchestration, backend |
| Execution-Platform | Sandbox, execution, testing, security |
| Product-Experience | Frontend, UI/UX, integration, QA |

## Final Demo Statement

> Give CodeForge AI a software task. It plans, writes, runs, tests, fixes, retests, and verifies the software.
