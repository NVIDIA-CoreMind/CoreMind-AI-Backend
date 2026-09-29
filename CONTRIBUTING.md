# Contributing to CoreMind Backend

Thank you for considering contributing to CoreMind!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/NVIDIA-CoreMind/CoreMind-AI-Backend.git
cd CoreMind-AI-Backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies (including dev)
pip install -r requirements.txt
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
```

## Code Quality

```bash
# Run tests
pytest tests/ -v

# Type checking
mypy src/

# Linting
ruff check src/

# Format
ruff format src/
```

## Project Structure

- `src/agent/` — Agent engine (state machine, loop, planner, executor, verifier)
- `src/ai/` — AI provider abstraction + Nebius integration
- `src/api/` — FastAPI routes + WebSocket server
- `src/context/` — Context assembly and compaction
- `src/events/` — Event bus + event types
- `src/project/` — Project detection, scanning, indexing
- `src/sandbox/` — Sandbox provider abstraction + local sandbox
- `src/security/` — Permissions, approvals, path/command policies
- `src/sessions/` — Session management
- `src/tools/` — Tool registry + definitions
- `src/utils/` — Logger, errors, IDs

## Security Rules

1. **Never** commit `.env` files with real credentials
2. **Never** expose `NEBIUS_API_KEY` in logs or API responses
3. **Never** allow arbitrary host commands from the AI — use the sandbox
4. **Always** validate file paths against the project root
5. **Always** require approval for HIGH_RISK operations

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass
4. Update documentation if needed
5. Submit a pull request with a clear description
