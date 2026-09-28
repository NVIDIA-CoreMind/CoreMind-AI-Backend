# CoreMind AI — Backend (FastAPI Edition)

> Autonomous Software Engineering Agent backend built with **Python & FastAPI**, powered by **NVIDIA open-source models** on **Nebius Token Factory / Nebius AI Cloud**.

---

## Overview

**CoreMind AI** is an autonomous software engineering agent embedded into the CoreMind IDE platform. It takes high-level software engineering tasks, formulates actionable multi-step plans, generates modular Python code, executes it inside an isolated sandbox, runs automated test suites, captures tracebacks, surgically patches errors, and verifies the solution before completion.

### The 7-Step Autonomous Engineering Loop

```text
       TASK
         ↓
       PLAN
         ↓
       CODE
         ↓
       RUN (Isolated Sandbox)
         ↓
       TEST (Pytest / Unittest)
         ↓
    FAIL ──→ DEBUG / FIX ──→ RETEST
         ↓
      VERIFY (Exit Code 0 & 100% Passed)
         ↓
     COMPLETED
```

---

## Infrastructure & Model Integration

- **Backend Framework**: [FastAPI](https://fastapi.tiangolo.com) + [Uvicorn](https://www.uvicorn.org) + [Pydantic V2](https://docs.pydantic.dev)
- **Model Host**: [Nebius Token Factory](https://tokenfactory.nebius.com) / Nebius AI Cloud
- **Target NVIDIA Foundation Models**:
  - `nvidia/llama-3.1-nemotron-70b-instruct` (Default recommended)
  - `nvidia/Llama-3.1-Nemotron-70B-Instruct-HF`
  - `meta-llama/Meta-Llama-3.1-70B-Instruct`
  - `meta-llama/Meta-Llama-3.1-8B-Instruct`
  - `Qwen/Qwen2.5-Coder-32B-Instruct`
- **Protocol**: OpenAI-compatible REST API / SDK with Function Calling and Server-Sent Events (SSE).

---

## Repository Architecture

```text
CoreMind-AI-Backend/
├── pyproject.toml             # Project metadata & dependencies
├── requirements.txt           # Pip dependencies
├── .env.example               # Environment variables template
├── .gitignore                 # Python, test cache, and sandbox work directory ignore rules
├── README.md                  # Complete setup, API specification, and architecture guide
├── 00-project-overview.md     # Hackathon track & MVP specification
├── app/
│   ├── __init__.py            # Package root
│   ├── main.py                # FastAPI entrypoint, CORS, lifespan & Uvicorn runner
│   ├── config.py              # Pydantic configuration loaded with python-dotenv
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── system_prompt.py   # Embedded system prompt enforcing the 7-phase loop
│   │   ├── state_machine.py   # State machine (TASK -> VERIFY) with retry limits
│   │   └── execution_engine.py# Multi-turn LLM agent loop & tool dispatcher
│   ├── providers/
│   │   ├── __init__.py
│   │   └── nebius_client.py   # Async Nebius Token Factory / NVIDIA client
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── types.py           # Pydantic models for workspace tools & results
│   │   ├── registry.py        # OpenAI tool definitions and async tool dispatcher
│   │   ├── file_tools.py      # Path-safe read_file, write_file, apply_diff
│   │   └── sandbox_tools.py   # Sandbox adapters for Python & test execution
│   ├── sandbox/
│   │   ├── __init__.py
│   │   └── python_runner.py   # Isolated process runner with traceback extraction
│   └── api/
│       ├── __init__.py
│       ├── routes.py          # FastAPI HTTP & SSE streaming endpoints
│       └── sse_handler.py     # Server-Sent Events stream manager
└── tests/
    ├── __init__.py
    ├── test_state_machine.py   # State Machine unit tests
    ├── test_python_runner.py   # Python Sandbox execution tests
    ├── test_file_tools.py      # Path-safe file read, write, and patch tests
    ├── test_tool_registry.py   # OpenAI tools schema and dispatcher tests
    └── test_execution_engine.py# End-to-end multi-turn loop tests with mock Nebius LLM
```

---

## Workspace & Sandbox Tools

| Tool | Parameters | Description |
|---|---|---|
| `read_file` | `path`, `start_line?`, `end_line?` | Reads workspace file with optional line-range slicing. Protected against directory traversal. |
| `write_file` | `path`, `content` | Creates directories recursively and writes UTF-8 content. |
| `apply_diff` | `path`, `patch` | Applies surgical search/replace block diffs (`<<<<<<< SEARCH ... ======= ... >>>>>>>`). |
| `run_sandbox_python` | `code?`, `script_path?`, `args?`, `timeout?` | Executes Python code or scripts inside the isolated sandbox with timeout and traceback extraction. |
| `run_sandbox_tests` | `test_command?`, `test_path?`, `timeout?` | Runs `pytest` or custom test runner, capturing stdout, stderr, and exit codes. |

---

## API Endpoints

### 1. `POST /api/agent/run` (Server-Sent Events)
Initiates the autonomous agent loop and streams real-time updates.

**Request Body**:
```json
{
  "task": "Create a robust LRU Cache class in Python with get/put methods and write unit tests.",
  "workspacePath": "./workspace_sandbox",
  "model": "nvidia/llama-3.1-nemotron-70b-instruct"
}
```

**SSE Event Types**:
- `phase_change`: Emitted on state transitions (`[PHASE: PLAN]`, `[PHASE: RUN]`, etc.)
- `thought`: Agent's intermediate reasoning and explanations
- `tool_call`: Dispatched tool arguments
- `tool_result`: Tool execution output and status
- `sandbox_output`: Python stdout, stderr, exit code, and tracebacks
- `diff_applied`: Surgical patches applied to files
- `verification`: Final verification outcome and summary
- `done`: Final execution summary and metrics

### 2. `GET /health`
Returns server status and connectivity to Nebius Token Factory.

### 3. `GET /api/models`
Returns list of available NVIDIA models on Nebius.

### 4. `POST /api/sandbox/execute`
Directly run Python code in the sandbox without the agent.

### 5. `POST /api/sandbox/test`
Directly run pytest in the sandbox workspace.

### 6. `GET /docs`
Interactive Swagger / OpenAPI documentation UI.

---

## Getting Started

### Prerequisites
- **Python**: 3.10+ (tested on Python 3.13)
- **Nebius API Key**: From [Nebius Token Factory](https://tokenfactory.nebius.com)

### Installation

```bash
# Clone the repository
git clone https://github.com/NVIDIA-CoreMind/CoreMind-AI-Backend.git
cd CoreMind-AI-Backend

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

### Configure `.env`

Edit `.env` with your Nebius Token Factory credentials:
```ini
PORT=4000
HOST=0.0.0.0
NEBIUS_API_KEY=your_nebius_api_key_here
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_MODEL=nvidia/llama-3.1-nemotron-70b-instruct
PYTHON_PATH=python
SANDBOX_WORK_DIR=./workspace_sandbox
```

### Running the Server

```bash
# Start with Uvicorn (with live reload)
python -m uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload

# Or directly:
python -m app.main
```

### Running Tests

```bash
# Run full unit and integration test suite
python -m pytest -v
```

---

## License

Apache-2.0
