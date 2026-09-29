"""
CoreMind Backend — ID Generators.

Prefixed UUIDs for agents, sessions, sandboxes, and requests.
"""

from __future__ import annotations

import uuid


def agent_id() -> str:
    """Generate a unique agent ID."""
    return f"agent_{uuid.uuid4().hex[:12]}"


def session_id() -> str:
    """Generate a unique session ID."""
    return f"session_{uuid.uuid4().hex[:12]}"


def sandbox_id() -> str:
    """Generate a unique sandbox ID."""
    return f"sandbox_{uuid.uuid4().hex[:12]}"


def request_id() -> str:
    """Generate a unique request/correlation ID."""
    return f"req_{uuid.uuid4().hex[:16]}"


def generate_uuid() -> str:
    """Generate a raw UUID string."""
    return str(uuid.uuid4())
