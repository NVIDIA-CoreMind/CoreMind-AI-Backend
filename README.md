# CoreMind Backend — Agentic Coding Engine

**Production-oriented AI coding agent backend for the CoreMind IDE — powered by NVIDIA Nemotron via Nebius Token Factory.**

CoreMind Backend powers autonomous software engineering within the CoreMind IDE following the strict lifecycle:
> **Understand → Inspect Context → Create Plan → Execute Task → Observe Result → Verify → Fix → Re-verify → Complete**

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                       CoreMind IDE                          │
│                Electron + React + TypeScript                │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket Events & REST APIs
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    CoreMind Backend                         │
│                                                             │
│   Agent Execution Engine (TaskGraph + Retry/Fix Loop)       │
│   Code Intelligence (RepoMap + Symbol Extractor + Hybrid)   │
│   Safe File Engine (Windowed Read + Multi-Strategy Edit)    │
│   Diff & Review (Unified Diff + Patch + Change Review)      │
│   Stateful Terminal (Persistent Sessions + Background Procs)│
│   Git Checkpoints (Pre-edit Snapshots + Isolated Rollback)  │
│   Context Prioritizer (Rules + Symbols + Compactor)         │
│   AI Provider (Nebius Token Factory → NVIDIA Nemotron)      │
│   Security & Guardrails (Command Policies + Approvals)      │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
    ┌──────────────────────┐      ┌───────────────────────┐
    │ Nebius Token Factory │      │   Local Environment   │
    │   NVIDIA Nemotron    │      │ (Tests, Linter, Git)  │
    └──────────────────────┘      └───────────────────────┘
```

---

## Key Agentic Features

### 1. Robust Agent Execution Loop & Self-Healing
- **Deterministic State Machine**: `IDLE` → `ANALYZING` → `PLANNING` → `EXECUTING` → `OBSERVING` → `VERIFYING` → `FIXING` → `WAITING_FOR_USER` → `COMPLETED` / `FAILED` / `CANCELLED`.
- **Automatic Self-Healing**: Automatically catches compiler/test failures, analyzes error traces, applies targeted fixes, and re-verifies (capped at `MAX_REPAIR_ATTEMPTS = 3`).
- **Graceful Cancellation & Limits**: Enforces step limits, timeouts, and responsive cancellation.

### 2. Dynamic Task Graph & Todo System
- Replaces static string planning with a directed, dependency-aware task graph (`TaskNodeStatus`: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `FAILED`, `SKIPPED`).
- The AI autonomously creates tasks, satisfies dependencies, tracks in-flight work, and streams task updates to the IDE.

### 3. Repository Code Intelligence & Compact Repo Map
- **AST & Symbol Extraction**: Extracts classes, methods, functions, interfaces, signatures, and docstrings across Python, Dart/Flutter, TypeScript/JavaScript, etc.
- **Context-Efficient Repo Maps**: Feeds compact structural summaries to the LLM without swamping the context window with full files.

### 4. Hybrid Code Search
- Multi-channel retrieval combining:
  1. **Exact string & regex matching**
  2. **Symbol lookup** (classes, methods, interfaces)
  3. **Semantic/concept search** (term overlap, keyword ranking)
- Ranked results with confidence scores and deduplication.

### 5. Safe Multi-Strategy File Editing
- Never relies on naive broad replacements.
- **Strategy 1**: Exact search-and-replace with uniqueness checks.
- **Strategy 2**: Multi-chunk atomic replacements in a single pass.
- **Strategy 3**: Line-range surgical editing.
- **Strategy 4**: Whitespace-tolerant fuzzy fallback.
- **Pre-Write Syntax Validation**: Validates AST/delimiters before writing to disk; invalid syntax is rejected before touching the file.

### 6. Unified Diff Engine & Change Review
- Every code modification generates standard unified diffs with added/deleted line statistics.
- **Change Review Model**: Backend tracks changes in `ChangeSet` objects, enabling frontend review with `preview_changes()`, `accept_changes()`, `reject_changes()`, `accept_file()`, and `reject_file()`.

### 7. Git Checkpoints & Rollback
- Automatic checkpoint snapshot before multi-file modifications begin.
- Distinguishes prior user edits from AI modifications; if verification fails or is rejected, rolls back only the AI modifications.

### 8. Project Rules Support
- Automatically detects `.coremindrules`, `AGENTS.md`, and `.cursorrules` in the project root.
- Injects coding standards and architectural rules directly into the agent's context.

### 9. Persistent Terminal Sessions & Background Processes
- **Persistent Sessions**: Retains working directory (`cd` navigation), environment variables (`source .venv/bin/activate`), and command history across turns.
- **Background Processes**: Safely manages long-running services (`npm run dev`, `flutter run`) with buffered log access and stop controls.

### 10. Ask-User Clarification
- When facing architectural decisions with multiple valid choices, the agent calls `ask_question` and pauses in `WAITING_FOR_USER` state until answered via API or WebSocket.

---

## Developer Onboarding & Local Setup

Follow these step-by-step instructions to clone, configure, test, and run the backend locally.

### 1. Prerequisites

Before starting, ensure you have the following installed on your machine:
- **Git**: `git --version`
- **Python 3.11+**: Check with `python3 --version` (or `python --version` on Windows)
- **Pip**: Latest version (`python3 -m pip install --upgrade pip`)
- **Nebius Token Factory API Key**: Sign up at [Nebius AI Studio](https://studio.nebius.ai/) to obtain an API key for NVIDIA Nemotron inference.

---

### 2. Clone the Repository

Clone the project from GitHub and navigate to the directory:

```bash
git clone https://github.com/NVIDIA-CoreMind/CoreMind-AI-Backend.git
cd CoreMind-AI-Backend
```

---

### 3. Create & Activate Virtual Environment

It is strongly recommended to isolate dependencies inside a virtual environment (`.venv`):

**On macOS & Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**On Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

> **Tip**: Once activated, your terminal prompt will be prefixed with `(.venv)`.

---

### 4. Install Dependencies

Install all core and development dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"
```

---

### 5. Configure Environment Variables

Create your local `.env` file by copying the provided example:

**On macOS / Linux:**
```bash
cp .env.example .env
```

**On Windows:**
```cmd
copy .env.example .env
```

Open `.env` in your editor and configure the necessary variables:

```env
# ─── Nebius / NVIDIA Nemotron ───────────────────────────────────────
NEBIUS_API_KEY=your-nebius-token-factory-key
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
NEBIUS_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1

# ─── CoreMind Backend Server ────────────────────────────────────────
COREMIND_BACKEND_HOST=127.0.0.1
COREMIND_BACKEND_PORT=43110

# ─── Agent Settings ────────────────────────────────────────────────
MAX_AGENT_STEPS=20
DEFAULT_COMMAND_TIMEOUT_MS=120000

# ─── Authentication & JWT (Optional for local dev) ─────────────────
JWT_SECRET_KEY=coremind-super-secret-jwt-key-2026-production-ready
GOOGLE_CLIENT_ID=your-google-oauth-client-id
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_REDIRECT_URI=http://localhost:43110/v1/auth/google/callback
```

> 🔒 **Security Notice**: Never commit `.env` to git. It is already included in `.gitignore`.

---

### 6. Verify Installation with Tests

Run the full automated test suite to ensure your environment is configured correctly:

```bash
pytest -v
```

You should see all **89 tests passing**.

---

### 7. Run the Backend

Choose one of the following methods to start the server:

#### Option A: Quick Run
```bash
python3 main.py
```

#### Option B: Live Auto-Reload (Recommended for Development)
Reloads the server automatically whenever you modify source files:
```bash
uvicorn src.app.bootstrap:app --host 127.0.0.1 --port 43110 --reload
```

---

### 8. Verify Server Readiness

Once the server is running, check the following endpoints in your browser:
- **Readiness / Health Check**: [http://127.0.0.1:43110/health](http://127.0.0.1:43110/health) → `{"status":"ok"}`
- **Interactive OpenAPI Docs**: [http://127.0.0.1:43110/docs](http://127.0.0.1:43110/docs)
- **ReDoc API Explorer**: [http://127.0.0.1:43110/redoc](http://127.0.0.1:43110/redoc)
- **Authentication Test Portal**: [http://127.0.0.1:43110/auth](http://127.0.0.1:43110/auth)
- **WebSocket Streaming URL**: `ws://127.0.0.1:43110/ws`

---

## Running Tests

Run the comprehensive test suite (89 passed tests):

```bash
pytest -v
```

Run specific subsystem test suites:
- `pytest tests/test_phase1.py` — TaskGraph, ReadFile, EditFile, Diff/Patch, Verifier
- `pytest tests/test_phase2.py` — Symbols, RepoMap, Hybrid Search, Project Rules, Compactor
- `pytest tests/test_phase3.py` — Ask User, Checkpoints, Persistent Terminal, Background Processes, Change Review
- `pytest tests/test_integration.py` — End-to-end integration and API endpoints

---

## API Reference

> 📖 **Frontend Team Documentation**: For full integration instructions, WebSocket event tables, authentication flows, and ready-to-use TypeScript/React SDK snippets, see the dedicated [Frontend Integration Guide](FRONTEND_API_GUIDE.md).

### Agent APIs
- `POST /v1/agent/run` — Start autonomous coding task
- `POST /v1/agent/cancel` / `POST /v1/agent/stop` — Stop/cancel running agent
- `GET /v1/agent/{agent_id}` / `GET /v1/agent/status` — Get agent task status and progress
- `POST /v1/agent/question` — Submit answer to pending question
- `GET /v1/agent/questions` — List pending questions
- `POST /v1/agent/approve` / `POST /v1/agent/deny` — Approve/deny privileged tools

### Project APIs
- `POST /v1/project/open` — Open directory and detect framework/language
- `GET /v1/project/tree` — Get file hierarchy tree
- `GET /v1/project/search` — Execute hybrid code search
- `GET /v1/project/repo_map` — Get symbol map and architectural summary

### Change Review APIs
- `GET /v1/changes/{change_id}` — Preview diffs and modified files
- `POST /v1/changes/{change_id}/accept` — Accept all changes
- `POST /v1/changes/{change_id}/reject` — Reject and revert all changes
- `POST /v1/changes/{change_id}/accept_file` — Accept individual file
- `POST /v1/changes/{change_id}/reject_file` — Reject and revert individual file

### Persistent Terminal & Process APIs
- `POST /v1/terminal/session` — Create persistent terminal session
- `POST /v1/terminal/session/{id}/execute` — Run command in session (preserves CWD/env)
- `DELETE /v1/terminal/session/{id}` — Terminate terminal session
- `POST /v1/terminal/process/start` — Start background process (e.g. dev server)
- `GET /v1/terminal/process/{id}/status` — Get process status
- `GET /v1/terminal/process/{id}/logs` — Tail process logs
- `POST /v1/terminal/process/{id}/stop` — Stop background process

### Streaming WebSocket
- `ws://127.0.0.1:43110/ws` — Real-time event stream (`agent.started`, `plan.created`, `task.started`, `diff.created`, `verification.started`, `verification.passed`, `agent.waiting_for_user`, `agent.completed`).
