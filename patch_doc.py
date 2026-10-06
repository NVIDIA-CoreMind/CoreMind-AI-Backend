import re

with open("FRONTEND_API_GUIDE.md", "r") as f:
    content = f.read()

# 1. Add missing agent endpoints before Section 4
agent_endpoints = """
#### 4. Stop All Agents (Emergency)
```http
POST /v1/agent/stop_all
```
**Response (200 OK):** `{"status": "emergency_stop_executed", "agents_stopped": 2}`

#### 5. List All Tasks
```http
GET /v1/agent/tasks
```
**Response (200 OK):** Returns a list of agent status objects.

#### 6. List Pending Questions
```http
GET /v1/agent/questions
# Optionally query by agent_id:
GET /v1/agent/questions?agent_id={agent_id}
```
**Response (200 OK):** Returns a list of pending question objects.

#### 7. Security Audit Logs
```http
GET /v1/agent/audit_logs?limit=100
```
**Response (200 OK):** Returns a list of audit log objects.
"""

content = content.replace("## 4. Real-time WebSocket", agent_endpoints + "\n---\n\n## 4. Real-time WebSocket")

# 2. Add TS client methods
ts_methods = """  async stopAllAgents() {
    return this.request<{ status: string; agents_stopped: number }>('/v1/agent/stop_all', { method: 'POST' });
  }

  async getTasks() {
    return this.request<any[]>('/v1/agent/tasks');
  }

  async getPendingQuestions(agentId?: string) {
    const query = agentId ? `?agent_id=${agentId}` : '';
    return this.request<any[]>(`/v1/agent/questions${query}`);
  }

  async getAuditLogs(limit: number = 100) {
    return this.request<any[]>(`/v1/agent/audit_logs?limit=${limit}`);
  }

  async answerQuestion(questionId: string, answer: string) {"""

content = content.replace("  async answerQuestion(questionId: string, answer: string) {", ts_methods)

with open("FRONTEND_API_GUIDE.md", "w") as f:
    f.write(content)

print("Patched FRONTEND_API_GUIDE.md")
