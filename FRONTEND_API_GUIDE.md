# CoreMind Backend — Frontend Integration & API Guide

> **Audience**: CoreMind IDE Frontend Team (Electron, React, TypeScript, Next.js)  
> **Backend Service**: CoreMind AI Agentic Backend (FastAPI + WebSocket + Nebius/NVIDIA Nemotron)  
> **Default Base URL**: `http://localhost:43110`  
> **Default WebSocket URL**: `ws://localhost:43110/ws`  
> **Interactive Swagger UI**: `http://localhost:43110/docs`  
> **ReDoc**: `http://localhost:43110/redoc`

---

## Table of Contents

1. [Quick Start & Connectivity](#1-quick-start--connectivity)
2. [Authentication & User Management (Google OAuth & JWT)](#2-authentication--user-management)
3. [Agent Orchestration Lifecycle](#3-agent-orchestration-lifecycle)
4. [Real-time WebSocket Streaming Protocol](#4-real-time-websocket-streaming-protocol)
5. [Interactive Clarifications & Human-in-the-Loop Approvals](#5-interactive-clarifications--human-in-the-loop-approvals)
6. [Unified Diff & Change Review System](#6-unified-diff--change-review-system)
7. [Project & Code Intelligence APIs](#7-project--code-intelligence-apis)
8. [Persistent Terminal & Background Processes](#8-persistent-terminal--background-processes)
9. [Direct Tools & Sandbox APIs](#9-direct-tools--sandbox-apis)
10. [Settings & AI Provider Diagnostics](#10-settings--ai-provider-diagnostics)
11. [Error Handling & Status Codes](#11-error-handling--status-codes)
12. [Ready-to-Use TypeScript SDK & React Hooks](#12-ready-to-use-typescript-sdk--react-hooks)

---

## 1. Quick Start & Connectivity

### Server Endpoints

| Resource | Protocol | URL | Description |
|---|---|---|---|
| **API Root** | HTTP | `http://localhost:43110/` | Service metadata and endpoint catalog |
| **Health Check** | HTTP | `http://localhost:43110/health` | Fast readiness probe (`{"status": "ok"}`) |
| **Swagger Docs** | HTTP | `http://localhost:43110/docs` | Interactive API explorer & tester |
| **Event Stream** | WebSocket | `ws://localhost:43110/ws` | Bi-directional streaming for agent events and controls |
| **Auth Portal** | HTTP | `http://localhost:43110/auth` | Built-in web login portal for testing |

### CORS Configuration
The backend enables full CORS with `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, and `allow_headers=["*"]`. No Electron CORS proxy or extra bypass headers are required.

### Starting the Backend Locally
```bash
# In the backend directory:
source .venv/bin/activate
uvicorn src.app.application:create_app --factory --host 127.0.0.1 --port 43110 --reload
# Or:
python -m src.app.bootstrap
```

---

## 2. Authentication & User Management

The backend supports **Google OAuth 2.0** and issues secure JWT `access_token` (7 days expiry) and `refresh_token` (30 days expiry).

### Authentication Methods
The frontend can authenticate using either:
1. **Webview / External Browser Consent Flow** (Recommended for Electron desktop IDE):
   - Call `GET /v1/auth/google/url` to retrieve the Google OAuth URL.
   - Open in an Electron `BrowserWindow` or external browser.
   - The user completes sign-in, Google redirects to `/v1/auth/google/callback`.
   - The callback page automatically dispatches a message via `window.opener.postMessage` with the token payload and writes to `localStorage.getItem('coremind_auth')`.
2. **Direct Google ID Token** (If using Google Identity Services / One-Tap SDK in renderer):
   - POST the raw Google JWT ID token directly to `POST /v1/auth/google`.

---

### Auth Endpoints Reference

#### 1. Get Google OAuth URL
```http
GET /v1/auth/google/url?redirect_uri={custom_redirect}&state={client_state}
```
**Response (200 OK):**
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&response_type=code&scope=openid+email+profile...",
  "client_id": "your-client-id.apps.googleusercontent.com",
  "state": "random_uuid_state"
}
```

#### 2. Sign In / Exchange Token
```http
POST /v1/auth/google
Content-Type: application/json
```
**Request Body (Option A — ID Token):**
```json
{
  "id_token": "eyJhbGciOiJSUzI1NiIs..."
}
```
**Request Body (Option B — Auth Code):**
```json
{
  "code": "4/0AeanS0...",
  "redirect_uri": "http://localhost:43110/v1/auth/google/callback"
}
```
**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 604800,
  "user": {
    "id": "usr_9c7f1a2b",
    "email": "developer@example.com",
    "name": "Jane Doe",
    "avatar_url": "https://lh3.googleusercontent.com/a/...",
    "provider": "google",
    "role": "user",
    "created_at": "2026-09-30T10:00:00Z",
    "last_login_at": "2026-09-30T10:00:00Z"
  }
}
```

#### 3. Get Current User Profile (Protected)
```http
GET /v1/auth/me
Authorization: Bearer <access_token>
```
**Response (200 OK):** Returns `UserResponse` object (same as `user` above).

#### 4. Update Profile
```http
PATCH /v1/auth/profile
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Jane Doe (Staff Dev)",
  "avatar_url": "https://example.com/new-avatar.png"
}
```

#### 5. Refresh Access Token
```http
POST /v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "<refresh_token>"
}
```
**Response (200 OK):** Returns fresh `TokenResponse` with new `access_token` and `refresh_token`.

#### 6. Logout
```http
POST /v1/auth/logout
Authorization: Bearer <access_token>
```
**Response (200 OK):**
```json
{
  "status": "ok",
  "message": "Successfully logged out."
}
```

---

## 3. Agent Orchestration Lifecycle

The agent executes the full self-healing lifecycle:
```text
[IDLE] ──► [ANALYZING] ──► [PLANNING] ──► [EXECUTING] ──► [OBSERVING] ──► [VERIFYING]
                                ▲                                             │ (failed tests)
                                └────────────── [FIXING] ◄────────────────────┘
```

### Agent Endpoints Reference

#### 1. Start Agent Task
```http
POST /v1/agent/run
Content-Type: application/json
```
**Request Body:**
```json
{
  "task": "Fix the authentication session timeout bug and add unit tests",
  "project_path": "/Users/developer/projects/my-web-app",
  "session_id": "optional-custom-session-uuid"
}
```
**Response (200 OK):**
```json
{
  "agent_id": "agent_a1b2c3d4",
  "session_id": "sess_e5f6g7h8",
  "status": "started"
}
```

#### 2. Check Agent Status
```http
GET /v1/agent/{agent_id}
# Or query param style:
GET /v1/agent/status?agent_id={agent_id}
```
**Response (200 OK):**
```json
{
  "task_id": "agent_a1b2c3d4",
  "session_id": "sess_e5f6g7h8",
  "agent_id": "agent_a1b2c3d4",
  "task": "Fix the authentication session timeout bug and add unit tests",
  "project_path": "/Users/developer/projects/my-web-app",
  "status": "running",
  "created_at": "2026-09-30T10:05:00Z",
  "completed_at": null,
  "steps_completed": 3,
  "files_changed": ["src/auth.py", "tests/test_auth.py"],
  "tool_calls_count": 5,
  "error": null,
  "task_graph": {
    "nodes": [
      {
        "id": "task_1",
        "title": "Analyze session timeout logic",
        "description": "Read src/auth.py and inspect expiration checking",
        "status": "completed",
        "dependencies": [],
        "priority": 0
      },
      {
        "id": "task_2",
        "title": "Patch expiration math and update test suite",
        "description": "Edit src/auth.py with accurate delta arithmetic",
        "status": "in_progress",
        "dependencies": ["task_1"],
        "priority": 1
      }
    ],
    "in_progress_ids": ["task_2"],
    "completed_ids": ["task_1"],
    "is_completed": false
  }
}
```

#### 3. Stop / Cancel Agent
```http
POST /v1/agent/stop
# Or alias:
POST /v1/agent/cancel
Content-Type: application/json

{
  "agent_id": "agent_a1b2c3d4"
}
```
**Response (200 OK):**
```json
{
  "status": "stopped",
  "agent_id": "agent_a1b2c3d4"
}
```

---

## 4. Real-time WebSocket Streaming Protocol

### Connecting to WebSocket
- **URL**: `ws://localhost:43110/ws`
- Connect immediately when the IDE initializes.
- Handle unexpected disconnections with an exponential backoff reconnect loop (e.g. 1s, 2s, 5s).

### Streamed Message Format (Backend ➔ IDE)
Every message pushed from the backend adheres to this unified JSON structure:
```json
{
  "type": "event.name",
  "agent_id": "agent_a1b2c3d4",
  "session_id": "sess_e5f6g7h8",
  "timestamp": "2026-09-30T10:06:15.123456Z",
  "data": {}
}
```

### Complete Event Catalog & Data Payloads

| Event Name (`type`) | Trigger / Meaning | Payload Format (`data`) |
|---|---|---|
| `agent.started` | Agent initialization began | `{"task": "...", "project_path": "..."}` |
| `agent.planning` | Agent is building task graph plan | `{}` |
| `plan.created` | New task graph created | `{"nodes": [...], "task_graph": {...}}` |
| `task.started` | Specific subtask began execution | `{"task_id": "task_1", "title": "Inspect file"}` |
| `task.completed` | Specific subtask succeeded | `{"task_id": "task_1", "title": "Inspect file"}` |
| `agent.thinking` | Agent generating LLM inference | `{"step": 2, "max_steps": 20}` |
| `agent.ai.token` | Token streaming chunk (if streaming) | `{"token": "string"}` |
| `agent.ai.usage` | Accumulated tokens & cost stats | `{"prompt_tokens": 1200, "completion_tokens": 340, "total_tokens": 1540}` |
| `tool.started` | Agent calling a tool | `{"tool": "read_file", "args": {"file_path": "src/auth.py"}}` |
| `tool.completed` | Tool finished executing | `{"tool": "read_file", "success": true, "result": "..."}` |
| `file.read` | File accessed | `{"path": "src/auth.py"}` |
| `file.created` | New file created | `{"path": "tests/test_auth.py"}` |
| `file.changed` | Existing file modified | `{"path": "src/auth.py"}` |
| `file.deleted` | File removed | `{"path": "old_file.py"}` |
| `diff.created` | Unified diff generated | `{"path": "src/auth.py", "diff": "@@ -10,4 +10,4 @@...", "additions": 3, "deletions": 1}` |
| `command.started` | Shell / Sandbox command started | `{"command": "pytest tests/test_auth.py", "cwd": "..."}` |
| `command.output` | Live stdout/stderr chunk | `{"output": "test_auth.py . [100%]\n"}` |
| `command.completed` | Command finished | `{"command": "...", "exit_code": 0, "duration_ms": 420}` |
| `verification.started`| Test suite / compilation started | `{"attempt": 1}` |
| `verification.passed` | Self-test succeeded | `{"attempt": 1, "command": "pytest"}` |
| `verification.failed` | Test failed; agent starts self-healing | `{"attempt": 1, "exit_code": 1, "error": "AssertionError..."}` |
| `agent.waiting_for_user` | **Action Required**: Agent asks user question | `{"question_id": "q_123", "question": "...", "options": ["Option A", "Option B"]}` |
| `agent.approval.required`| **Action Required**: Risky tool needs approval | `{"approval_id": "req_456", "tool": "terminal_run", "args": {...}, "description": "..."}` |
| `agent.approval.granted` | Approval confirmed | `{"approval_id": "req_456", "tool": "terminal_run"}` |
| `agent.approval.denied`  | Approval rejected | `{"approval_id": "req_456", "reason": "User denied"}` |
| `agent.completed` | Entire task completed! | `{"files_changed": [...], "steps": 4, "change_id": "chg_9988", "task_graph": {...}}` |
| `agent.failed` | Task failed after retries | `{"error": "Verification failed..."}` |
| `agent.stopped` | Agent was stopped by user | `{}` |
| `agent.error` | Internal unhandled error | `{"error": "Detailed error string"}` |

---

## 5. Interactive Clarifications & Human-in-the-Loop Approvals

The backend gives full interactive control to the frontend via both **REST API** and **WebSocket**.

### Scenario A: Agent Asks a Question (`ask_question`)

When the AI encounters ambiguity (e.g. choice between two state management libraries or auth providers), it pauses in `WAITING_FOR_USER` state and emits `agent.waiting_for_user`.

#### 1. Incoming Event:
```json
{
  "type": "agent.waiting_for_user",
  "agent_id": "agent_a1b2c3d4",
  "data": {
    "question_id": "q_a7b9c1d2",
    "question": "Should we use Redis or in-memory LRU cache for session storage?",
    "options": ["Redis", "In-Memory LRU Cache"]
  }
}
```

#### 2. Submitting the Answer
**Via WebSocket (Fastest):**
```json
{
  "type": "agent.question_answer",
  "question_id": "q_a7b9c1d2",
  "answer": "Redis"
}
```
**Or via REST API:**
```http
POST /v1/agent/question
Content-Type: application/json

{
  "question_id": "q_a7b9c1d2",
  "answer": "Redis"
}
```

---

### Scenario B: Security Approvals for High-Risk Actions

When the AI attempts to execute high-risk operations (e.g., executing arbitrary bash commands or mutating sensitive directories), it pauses in `WAITING_FOR_APPROVAL` state and emits `agent.approval.required`.

#### 1. Incoming Event:
```json
{
  "type": "agent.approval.required",
  "agent_id": "agent_a1b2c3d4",
  "data": {
    "approval_id": "req_9f8e7d6c",
    "tool": "terminal_run",
    "args": {
      "command": "npm install --save redis"
    },
    "description": "Execute terminal command 'npm install --save redis' in project root"
  }
}
```

#### 2. Approving the Action
**Via WebSocket:**
```json
{
  "type": "agent.approve",
  "approval_id": "req_9f8e7d6c"
}
```
**Or via REST API:**
```http
POST /v1/agent/approve
Content-Type: application/json

{
  "agent_id": "agent_a1b2c3d4",
  "approval_id": "req_9f8e7d6c"
}
```

#### 3. Denying the Action
**Via WebSocket:**
```json
{
  "type": "agent.deny",
  "approval_id": "req_9f8e7d6c",
  "reason": "Do not install new npm dependencies"
}
```
**Or via REST API:**
```http
POST /v1/agent/deny
Content-Type: application/json

{
  "agent_id": "agent_a1b2c3d4",
  "approval_id": "req_9f8e7d6c",
  "reason": "Do not install new npm dependencies"
}
```

---

## 6. Unified Diff & Change Review System

When the agent modifies files, it creates an atomic **ChangeSet** identified by `change_id` (received in the `agent.completed` event). The frontend can render a rich side-by-side or inline diff review and let the user accept or reject changes atomically or per file.

### Endpoints Reference

#### 1. Preview ChangeSet Diffs
```http
GET /v1/changes/{change_id}
```
**Response (200 OK):**
```json
{
  "change_id": "chg_a1b2c3d4",
  "agent_id": "agent_a1b2c3d4",
  "project_path": "/Users/developer/projects/my-web-app",
  "created_at": "2026-09-30T10:12:00Z",
  "files": [
    {
      "path": "src/auth.py",
      "diff": "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -24,3 +24,3 @@\n-    timeout = 300\n+    timeout = 3600\n",
      "status": "modified",
      "additions": 1,
      "deletions": 1,
      "accepted": false
    },
    {
      "path": "tests/test_auth.py",
      "diff": "--- /dev/null\n+++ b/tests/test_auth.py\n@@ -0,0 +1,15 @@\n+def test_timeout():\n+    assert True\n",
      "status": "created",
      "additions": 15,
      "deletions": 0,
      "accepted": false
    }
  ]
}
```

#### 2. Accept All Changes
```http
POST /v1/changes/{change_id}/accept
```
**Response (200 OK):** `{"status": "accepted", "change_id": "chg_a1b2c3d4"}`

#### 3. Reject & Rollback All Changes
Reverts all modified files to original state and deletes any new files created by the AI.
```http
POST /v1/changes/{change_id}/reject
```
**Response (200 OK):** `{"status": "rejected", "change_id": "chg_a1b2c3d4"}`

#### 4. Accept Single File
```http
POST /v1/changes/{change_id}/accept_file
Content-Type: application/json

{
  "file_path": "src/auth.py"
}
```

#### 5. Reject Single File (Reverts only this file)
```http
POST /v1/changes/{change_id}/reject_file
Content-Type: application/json

{
  "file_path": "tests/test_auth.py"
}
```

---

## 7. Project & Code Intelligence APIs

Use these endpoints to power the IDE sidebar, project opener, code search, and symbol outlines.

### 1. Open / Register Project
```http
POST /v1/project/open
Content-Type: application/json

{
  "path": "/Users/developer/projects/my-web-app"
}
```
**Response (200 OK):**
```json
{
  "path": "/Users/developer/projects/my-web-app",
  "name": "my-web-app",
  "language": "python",
  "framework": "fastapi",
  "package_manager": "pip",
  "main_entry": "main.py",
  "test_command": "pytest",
  "config_file": "pyproject.toml",
  "file_count": 142,
  "total_size": 184920
}
```

### 2. Get Project File Tree
```http
GET /v1/project/tree?path=/Users/developer/projects/my-web-app
```
**Response (200 OK):**
```json
{
  "project_path": "/Users/developer/projects/my-web-app",
  "tree": [
    {
      "name": "src",
      "path": "src",
      "is_dir": true,
      "children": [
        {
          "name": "auth.py",
          "path": "src/auth.py",
          "is_dir": false,
          "size": 2400
        }
      ]
    }
  ]
}
```

### 3. Hybrid Code Search (Text + Regex + AST Symbols)
```http
GET /v1/project/search?path=/Users/developer/projects/my-web-app&query=UserSession&file_pattern=*.py&is_regex=false&max_results=20
```
**Response (200 OK):**
```json
{
  "project_path": "/Users/developer/projects/my-web-app",
  "query": "UserSession",
  "total": 3,
  "matches": [
    {
      "file_path": "src/models/user.py",
      "line_number": 42,
      "match_type": "symbol",
      "score": 0.95,
      "preview": "class UserSession(BaseModel):",
      "context_lines": ["@dataclass", "class UserSession(BaseModel):", "    id: str"]
    }
  ]
}
```

### 4. Compact Repo Map & Symbols
Returns an AST symbol map of functions, classes, and signatures across Python, TypeScript/JavaScript, Dart/Flutter, and more.
```http
GET /v1/project/repo_map?path=/Users/developer/projects/my-web-app
```
**Response (200 OK):**
```json
{
  "project_path": "/Users/developer/projects/my-web-app",
  "summary": "Repository contains 28 classes and 114 functions across 18 source files.",
  "details": {
    "files": {
      "src/auth.py": {
        "classes": ["AuthManager", "SessionToken"],
        "functions": ["verify_token(token: str) -> bool", "hash_password(pw: str) -> str"]
      }
    }
  }
}
```

---

## 8. Persistent Terminal & Background Processes

The backend provides stateful terminal sessions where shell state (`cd` directory, exported environment variables, virtualenvs) persists across calls, as well as background process management for running dev servers (`npm run dev`, `flutter run`).

### Persistent Terminal Sessions

#### 1. Create Session
```http
POST /v1/terminal/session
Content-Type: application/json

{
  "project_path": "/Users/developer/projects/my-web-app",
  "session_id": "optional-custom-term-id"
}
```
**Response (200 OK):**
```json
{
  "session_id": "term_a1b2c3d4",
  "project_path": "/Users/developer/projects/my-web-app",
  "cwd": "/Users/developer/projects/my-web-app",
  "is_active": true
}
```

#### 2. Execute Command in Session
```http
POST /v1/terminal/session/{session_id}/execute
Content-Type: application/json

{
  "command": "cd backend && pwd && export FOO=BAR",
  "timeout_seconds": 60.0
}
```
**Response (200 OK):**
```json
{
  "command": "cd backend && pwd && export FOO=BAR",
  "stdout": "/Users/developer/projects/my-web-app/backend\n",
  "stderr": "",
  "exit_code": 0,
  "cwd": "/Users/developer/projects/my-web-app/backend"
}
```

#### 3. List Active Sessions
```http
GET /v1/terminal/sessions
```

#### 4. Delete Session
```http
DELETE /v1/terminal/session/{session_id}
```

---

### Managed Background Processes (Dev Servers / Watchers)

#### 1. Start Process
```http
POST /v1/terminal/process/start
Content-Type: application/json

{
  "command": "npm run dev",
  "cwd": "/Users/developer/projects/my-web-app"
}
```
**Response (200 OK):**
```json
{
  "process_id": "proc_123456",
  "pid": 48219,
  "command": "npm run dev",
  "cwd": "/Users/developer/projects/my-web-app",
  "is_running": true
}
```

#### 2. Get Process Status
```http
GET /v1/terminal/process/{process_id}/status
```

#### 3. Stream / Tail Process Logs
```http
GET /v1/terminal/process/{process_id}/logs?tail=100
```
**Response (200 OK):**
```json
{
  "process_id": "proc_123456",
  "logs": [
    "VITE v5.4.2 ready in 240 ms\n",
    "➜ Local:   http://localhost:5173/\n"
  ]
}
```

#### 4. Stop Process
```http
POST /v1/terminal/process/{process_id}/stop
```

---

## 9. Direct Tools & Sandbox APIs

The IDE can also trigger file tools and sandboxes directly outside the agent loop:

| Method | Endpoint | Description | Payload |
|---|---|---|---|
| `POST` | `/v1/tools/search` | Fast file grep/search | `{"tool": "search_files", "args": {"query": "..."}, "project_path": "..."}` |
| `POST` | `/v1/tools/web-search` | Live internet web search | `{"tool": "web_search", "args": {"query": "..."}, "project_path": "..."}` |
| `POST` | `/v1/tools/read` | Read file (supports offset & limits) | `{"tool": "read_file", "args": {"file_path": "...", "start_line": 1, "end_line": 100}, "project_path": "..."}` |
| `POST` | `/v1/tools/write` | Write / overwrite file | `{"tool": "write_file", "args": {"file_path": "...", "content": "..."}, "project_path": "..."}` |
| `POST` | `/v1/tools/edit` | Surgical search-and-replace edit | `{"tool": "edit_file", "args": {"file_path": "...", "target_content": "...", "replacement_content": "..."}, "project_path": "..."}` |
| `POST` | `/v1/sandbox/create` | Spawn isolated code execution sandbox | `{"project_path": "..."}` |
| `POST` | `/v1/sandbox/execute`| Execute code in sandbox | `{"sandbox_id": "...", "command": "...", "timeout_ms": 30000}` |
| `POST` | `/v1/sandbox/destroy`| Destroy sandbox instance | `{"sandbox_id": "..."}` |

---

## 10. Settings & AI Provider Diagnostics

#### 1. Safe Settings (Non-Secret)
```http
GET /v1/settings
```
**Response (200 OK):**
```json
{
  "model": "nvidia/llama-3.3-nemotron-super-49b-v1",
  "max_agent_steps": 20,
  "command_timeout_ms": 120000,
  "sandbox_type": "local",
  "host": "127.0.0.1",
  "port": 43110
}
```

#### 2. Test AI Connection
```http
POST /v1/ai/test
```
**Response (200 OK):**
```json
{
  "status": "ok",
  "provider": "nebius",
  "model": "nvidia/llama-3.3-nemotron-super-49b-v1",
  "response": "CoreMind connected."
}
```

#### 3. AI Token Usage
```http
GET /v1/ai/usage
```

---

## 11. Error Handling & Status Codes

All errors returned by the backend adhere to a clean, typed JSON format:
```json
{
  "error": {
    "code": "AUTH_TOKEN_EXPIRED",
    "message": "Token expired at 2026-09-30 09:00:00 UTC",
    "details": {
      "expired_at": "2026-09-30T09:00:00Z"
    }
  }
}
```

### Standard Error Codes

| HTTP Status | Error Code (`code`) | Meaning / Recommended Frontend Action |
|---|---|---|
| `401 Unauthorized` | `AUTH_UNAUTHORIZED` | Missing `Authorization: Bearer <token>` header; prompt user to sign in |
| `401 Unauthorized` | `AUTH_TOKEN_EXPIRED` | Access token expired; call `/v1/auth/refresh` |
| `401 Unauthorized` | `AUTH_TOKEN_INVALID` | Malformed JWT; clear stored credentials and re-authenticate |
| `403 Forbidden` | `AUTH_FORBIDDEN` | User disabled or lacks permissions |
| `404 Not Found` | `AGENT_NOT_FOUND` | Specified `agent_id` does not exist |
| `404 Not Found` | `TOOL_FILE_NOT_FOUND` | Target file does not exist in project |
| `400 Bad Request` | `TOOL_INVALID_ARGS` | Missing required parameters for tool |
| `429 Rate Limit` | `AI_RATE_LIMIT` | Provider rate limited; show cooldown indicator |
| `504 Gateway Timeout`| `AI_TIMEOUT` | Nebius / AI inference timed out |
| `500 Server Error` | `INTERNAL_ERROR` | Unhandled backend exception |

---

## 12. Ready-to-Use TypeScript SDK & React Hooks

Here are production-ready TypeScript code snippets you can drop straight into the frontend project.

### 1. TypeScript Types (`types/coremind.ts`)

```typescript
export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url?: string;
  provider: string;
  role: 'user' | 'admin';
  created_at: string;
  last_login_at?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export type AgentEventType =
  | 'agent.started'
  | 'agent.planning'
  | 'agent.thinking'
  | 'agent.waiting_for_user'
  | 'agent.approval.required'
  | 'agent.approval.granted'
  | 'agent.approval.denied'
  | 'agent.completed'
  | 'agent.failed'
  | 'agent.stopped'
  | 'plan.created'
  | 'task.started'
  | 'task.completed'
  | 'tool.started'
  | 'tool.completed'
  | 'file.read'
  | 'file.changed'
  | 'file.created'
  | 'file.deleted'
  | 'diff.created'
  | 'command.started'
  | 'command.output'
  | 'command.completed'
  | 'verification.started'
  | 'verification.passed'
  | 'verification.failed';

export interface CoreMindEvent<T = any> {
  type: AgentEventType;
  agent_id?: string;
  session_id?: string;
  timestamp: string;
  data: T;
}

export interface TaskNode {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' | 'failed' | 'skipped';
  dependencies: string[];
  priority: number;
}
```

### 2. CoreMind API Client (`services/coremind-client.ts`)

```typescript
import { AuthTokens, User } from '../types/coremind';

export class CoreMindClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = 'http://localhost:43110') {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null) {
    this.token = token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData?.error?.message || `HTTP error ${response.status}`);
    }

    return response.json();
  }

  // --- Auth ---
  async getGoogleAuthUrl(redirectUri?: string) {
    const query = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : '';
    return this.request<{ auth_url: string; client_id: string; state: string }>(`/v1/auth/google/url${query}`);
  }

  async loginWithGoogleToken(idToken: string): Promise<AuthTokens> {
    return this.request<AuthTokens>('/v1/auth/google', {
      method: 'POST',
      body: JSON.stringify({ id_token: idToken }),
    });
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/v1/auth/me');
  }

  // --- Agent ---
  async startAgent(task: string, projectPath: string, sessionId?: string) {
    return this.request<{ agent_id: string; session_id: string; status: string }>('/v1/agent/run', {
      method: 'POST',
      body: JSON.stringify({ task, project_path: projectPath, session_id: sessionId }),
    });
  }

  async stopAgent(agentId: string) {
    return this.request<{ status: string; agent_id: string }>('/v1/agent/stop', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId }),
    });
  }

  async answerQuestion(questionId: string, answer: string) {
    return this.request<{ status: string }>('/v1/agent/question', {
      method: 'POST',
      body: JSON.stringify({ question_id: questionId, answer }),
    });
  }

  async approveAction(agentId: string, approvalId: string) {
    return this.request<{ status: string }>('/v1/agent/approve', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, approval_id: approvalId }),
    });
  }

  async denyAction(agentId: string, approvalId: string, reason?: string) {
    return this.request<{ status: string }>('/v1/agent/deny', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, approval_id: approvalId, reason }),
    });
  }

  // --- Project ---
  async openProject(projectPath: string) {
    return this.request<any>('/v1/project/open', {
      method: 'POST',
      body: JSON.stringify({ path: projectPath }),
    });
  }

  // --- Change Review ---
  async getChanges(changeId: string) {
    return this.request<any>(`/v1/changes/${changeId}`);
  }

  async acceptChanges(changeId: string) {
    return this.request<any>(`/v1/changes/${changeId}/accept`, { method: 'POST' });
  }

  async rejectChanges(changeId: string) {
    return this.request<any>(`/v1/changes/${changeId}/reject`, { method: 'POST' });
  }
}

export const coremindClient = new CoreMindClient();
```

### 3. React WebSocket Hook (`hooks/useCoreMindAgent.ts`)

```typescript
import { useEffect, useRef, useState, useCallback } from 'react';
import { CoreMindEvent, AgentEventType, TaskNode } from '../types/coremind';

export function useCoreMindAgent(wsUrl: string = 'ws://localhost:43110/ws') {
  const socketRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [currentEvent, setCurrentEvent] = useState<CoreMindEvent | null>(null);
  const [tasks, setTasks] = useState<TaskNode[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<{ id: string; text: string; options: string[] } | null>(null);
  const [pendingApproval, setPendingApproval] = useState<{ id: string; tool: string; description: string } | null>(null);
  const [latestDiff, setLatestDiff] = useState<any>(null);

  useEffect(() => {
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);

    ws.onmessage = (event) => {
      try {
        const parsed: CoreMindEvent = JSON.parse(event.data);
        setCurrentEvent(parsed);

        switch (parsed.type) {
          case 'plan.created':
            if (parsed.data?.nodes) setTasks(parsed.data.nodes);
            break;
          case 'task.started':
          case 'task.completed':
            setTasks((prev) =>
              prev.map((t) =>
                t.id === parsed.data.task_id
                  ? { ...t, status: parsed.type === 'task.started' ? 'in_progress' : 'completed' }
                  : t
              )
            );
            break;
          case 'agent.waiting_for_user':
            setPendingQuestion({
              id: parsed.data.question_id,
              text: parsed.data.question,
              options: parsed.data.options || [],
            });
            break;
          case 'agent.approval.required':
            setPendingApproval({
              id: parsed.data.approval_id,
              tool: parsed.data.tool,
              description: parsed.data.description,
            });
            break;
          case 'diff.created':
            setLatestDiff(parsed.data);
            break;
        }
      } catch (err) {
        console.error('Failed to parse WS event:', err);
      }
    };

    return () => {
      ws.close();
    };
  }, [wsUrl]);

  const send = useCallback((message: object) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    }
  }, []);

  const answerQuestion = useCallback(
    (questionId: string, answer: string) => {
      send({ type: 'agent.question_answer', question_id: questionId, answer });
      setPendingQuestion(null);
    },
    [send]
  );

  const approve = useCallback(
    (approvalId: string) => {
      send({ type: 'agent.approve', approval_id: approvalId });
      setPendingApproval(null);
    },
    [send]
  );

  const deny = useCallback(
    (approvalId: string, reason?: string) => {
      send({ type: 'agent.deny', approval_id: approvalId, reason });
      setPendingApproval(null);
    },
    [send]
  );

  return {
    isConnected,
    currentEvent,
    tasks,
    pendingQuestion,
    pendingApproval,
    latestDiff,
    answerQuestion,
    approve,
    deny,
  };
}
```

---

## 13. Summary Checklist for Frontend Developers

- [ ] **Configure Base URL**: Default to `http://localhost:43110` with user setting override.
- [ ] **Initialize WebSocket**: Connect to `ws://localhost:43110/ws` for real-time progress, diffs, and logs.
- [ ] **Implement Google Auth**: Direct users to `GET /v1/auth/google/url` or pass tokens to `POST /v1/auth/google`. Store JWT in secure storage.
- [ ] **Wire Agent Execution**: Submit prompts to `POST /v1/agent/run` and render dynamic task graph progress from `plan.created` and `task.started`.
- [ ] **Handle Human-in-the-Loop Prompts**:
  - Show modal / prompt UI when `agent.waiting_for_user` arrives (send answer back via WS or POST `/v1/agent/question`).
  - Show approval banner when `agent.approval.required` arrives (approve/deny via WS or API).
- [ ] **Connect Diff Review**: On `agent.completed`, query `GET /v1/changes/{change_id}` to let users review, accept, or reject code changes before finalizing.
- [ ] **Mount Persistent Terminal**: Use `/v1/terminal/session` for interactive terminal tabs with maintained directory and environment context.
