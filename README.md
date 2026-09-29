# CoreMind Backend

**AI/Agent orchestration backend for CoreMind IDE — powered by NVIDIA Nemotron via Nebius Token Factory.**

CoreMind Backend is the local AI and agent orchestration service that connects the CoreMind IDE with NVIDIA Nemotron through Nebius Token Factory and with the CoreMind Sandbox for safe code execution.

## Architecture

```
┌─────────────────────────────────────────────────┐
│               CoreMind IDE                      │
│          Electron + React + TypeScript           │
└────────────────────┬────────────────────────────┘
                     │ WebSocket / HTTP
                     ▼
┌─────────────────────────────────────────────────┐
│             CoreMind Backend                    │
│                                                 │
│   API Layer (FastAPI)                           │
│   Agent Engine (Plan → Execute → Verify)        │
│   Context Manager (Layered context assembly)    │
│   Tool Registry (10+ registered tools)          │
│   AI Provider (Nebius → Nemotron)               │
│   Security (Permissions + Approvals)            │
│   Project Manager (Auto-detection)              │
│   Sandbox Provider (Local + future Nebius)      │
└──────────┬──────────────────┬───────────────────┘
           │                  │
           ▼                  ▼
┌──────────────────┐ ┌───────────────────────┐
│ Nebius Token     │ │  CoreMind Sandbox     │
│ Factory          │ │                       │
│ NVIDIA Nemotron  │ │  Isolated execution   │
└──────────────────┘ └───────────────────────┘
```

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A Nebius Token Factory API key

### 2. Clone & Install

```bash
git clone https://github.com/NVIDIA-CoreMind/CoreMind-AI-Backend.git
cd CoreMind-AI-Backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install -e ".[dev]"
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env and set your NEBIUS_API_KEY
```

### 4. Run

```bash
python -m src.app.bootstrap
```

The backend starts on `http://127.0.0.1:43110` by default.

### 5. Verify

```bash
# Health check
curl http://127.0.0.1:43110/health

# Test AI connectivity
curl -X POST http://127.0.0.1:43110/v1/ai/test
```

## NVIDIA & Nebius Integration

CoreMind uses **NVIDIA Nemotron** models accessed through **Nebius Token Factory**, which exposes an OpenAI-compatible API.

- **AI Provider Abstraction**: The agent engine communicates with an `AIProvider` interface, not directly with Nebius. This enables future provider swapping.
- **OpenAI SDK**: We use the official `openai` Python SDK pointed at the Nebius base URL — no custom HTTP plumbing.
- **Streaming**: Full support for streaming responses via WebSocket to the IDE.
- **Model Flexibility**: The model ID is configurable via `NEBIUS_MODEL` in `.env`. Never hardcoded.

```
Agent → AIProvider → NebiusProvider → Nebius Token Factory → NVIDIA Nemotron
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/v1/agent/run` | Start an agent task |
| `POST` | `/v1/agent/stop` | Stop a running agent |
| `GET` | `/v1/agent/status` | Get agent status |
| `POST` | `/v1/agent/approve` | Approve a pending action |
| `POST` | `/v1/agent/deny` | Deny a pending action |
| `POST` | `/v1/ai/test` | Test AI connectivity |
| `GET` | `/v1/ai/models` | List available models |
| `GET` | `/v1/ai/usage` | Get token usage stats |
| `POST` | `/v1/project/open` | Open a project |
| `GET` | `/v1/project/tree` | Get project file tree |
| `POST` | `/v1/tools/search` | Search files |
| `POST` | `/v1/tools/read` | Read a file |
| `POST` | `/v1/tools/write` | Write a file |
| `POST` | `/v1/tools/edit` | Edit a file |
| `POST` | `/v1/sandbox/create` | Create sandbox |
| `POST` | `/v1/sandbox/execute` | Execute in sandbox |
| `POST` | `/v1/sandbox/destroy` | Destroy sandbox |
| `WS` | `/ws` | WebSocket for streaming events |

## Agent Workflow

The agent follows an autonomous loop:

1. **Analyze** — Understand the user's task
2. **Plan** — Create a step-by-step execution plan
3. **Execute** — Call tools (read/write files, run commands)
4. **Verify** — Run tests to validate changes
5. **Fix** — If tests fail, analyze errors and apply fixes
6. **Complete** — Report results to the IDE

### Error Recovery Loop

```
VERIFYING → ANALYZING_ERROR → FIXING → VERIFYING → COMPLETED
```

The agent can retry failed verifications up to 3 times automatically.

## Security

- **API Key Protection**: `NEBIUS_API_KEY` is never exposed to the IDE renderer or logged
- **Path Policy**: All file operations are restricted to the project directory
- **Command Policy**: Dangerous commands (`rm -rf /`, `sudo`, etc.) are blocked
- **Approval Flow**: HIGH_RISK operations require user approval via WebSocket
- **Secret Redaction**: Logs automatically redact API keys, tokens, and passwords
- **Step Limits**: Configurable max steps (default: 20) prevent runaway agents

## Running Tests

```bash
pytest tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEBIUS_API_KEY` | — | Nebius Token Factory API key |
| `NEBIUS_BASE_URL` | `https://api.studio.nebius.com/v1` | Nebius API base URL |
| `NEBIUS_MODEL` | `nvidia/llama-3.3-nemotron-super-49b-v1` | Model ID |
| `COREMIND_BACKEND_HOST` | `127.0.0.1` | Backend host |
| `COREMIND_BACKEND_PORT` | `43110` | Backend port |
| `MAX_AGENT_STEPS` | `20` | Max agent steps per task |
| `DEFAULT_COMMAND_TIMEOUT_MS` | `120000` | Command timeout |
| `SANDBOX_TYPE` | `local` | Sandbox provider (`local`) |
| `LOG_LEVEL` | `info` | Log level |

## License

MIT — see [LICENSE](LICENSE)
