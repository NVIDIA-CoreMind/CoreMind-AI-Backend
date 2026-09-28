# CoreMind AI — Backend

> Autonomous Software Engineering Agent backend powered by **NVIDIA open-source models** on **Nebius Token Factory / Nebius AI Cloud**.

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
├── package.json               # Dependencies & scripts
├── tsconfig.json              # TypeScript configuration (ES2022 / NodeNext)
├── .env.example               # Environment template
├── .gitignore                 # Ignored build & runtime artifacts
├── 00-project-overview.md     # Hackathon track & MVP specification
├── src/
│   ├── index.ts               # Application entrypoint & HTTP server setup
│   ├── config/
│   │   └── env.ts             # Type-safe Zod environment validation
│   ├── agent/
│   │   ├── systemPrompt.ts    # Embedded system prompt enforcing 7-phase loop
│   │   ├── stateMachine.ts    # State machine manager (TASK -> VERIFY) & retries
│   │   └── executionEngine.ts # Autonomous multi-turn LLM loop & tool dispatcher
│   ├── providers/
│   │   └── nebiusClient.ts    # Nebius Token Factory / NVIDIA client
│   ├── tools/
│   │   ├── types.ts           # Interfaces for workspace tools & execution results
│   │   ├── registry.ts        # OpenAI tool schemas and execution dispatcher
│   │   ├── fileTools.ts       # Path-safe read_file, write_file, apply_diff
│   │   └── sandboxTools.ts    # Sandbox tool adapters for Python & test execution
│   ├── sandbox/
│   │   └── pythonRunner.ts    # Isolated child process runner with traceback parser
│   └── server/
│       ├── routes.ts          # Express HTTP & SSE streaming endpoints
│       └── sseHandler.ts      # Server-Sent Events stream manager
└── tests/
    └── agent.test.ts          # Unit and integration test suite (Vitest)
```

---

## Workspace & Sandbox Tools

| Tool | Parameters | Description |
|---|---|---|
| `read_file` | `path`, `start_line?`, `end_line?` | Reads workspace file with optional line-range slicing. Protected against directory traversal. |
| `write_file` | `path`, `content` | Creates directories recursively and writes UTF-8 content. |
| `apply_diff` | `path`, `patch` | Applies surgical unified diffs or search/replace blocks (`<<<<<<< SEARCH ... ======= ... >>>>>>>`). |
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

---

## Getting Started

### Prerequisites
- **Node.js**: v18+ (tested on Node v25)
- **Python**: 3.10+ (tested on Python 3.13)
- **Nebius API Key**: From [Nebius Token Factory](https://tokenfactory.nebius.com)

### Installation

```bash
# Clone the repository
git clone https://github.com/NVIDIA-CoreMind/CoreMind-AI-Backend.git
cd CoreMind-AI-Backend

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env
```

### Configure `.env`

Edit `.env` with your Nebius Token Factory credentials:
```ini
PORT=4000
NEBIUS_API_KEY=your_nebius_api_key_here
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_MODEL=nvidia/llama-3.1-nemotron-70b-instruct
PYTHON_PATH=python
```

### Running the Server

```bash
# Development mode (with live reload)
npm run dev

# Production build & start
npm run build
npm start
```

### Running Tests

```bash
# Run unit and integration tests
npm test
```

---

## License

Apache-2.0
