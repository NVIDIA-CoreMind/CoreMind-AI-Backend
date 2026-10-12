"""
CoreMind Backend — WebSocket Server.

Bridges the EventBus to connected IDE clients via WebSocket.
Supports real-time streaming of agent events.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.events.event_bus import event_bus
from src.events.events import CoreMindEvent
from src.utils.logger import logger

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections from IDE clients."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("websocket.connected", total=len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections = [c for c in self._connections if c is not websocket]
        logger.info("websocket.disconnected", total=len(self._connections))

    async def broadcast(self, event: CoreMindEvent) -> None:
        """Send an event to all connected clients."""
        payload = event.model_dump_json()
        dead: list[WebSocket] = []
        for conn in self._connections:
            try:
                await conn.send_text(payload)
            except Exception:
                dead.append(conn)
        # Clean up dead connections
        for d in dead:
            self._connections = [c for c in self._connections if c is not d]

    @property
    def count(self) -> int:
        return len(self._connections)


# Module-level singleton
ws_manager = ConnectionManager()


async def _handle_client_connection(websocket: WebSocket, client_id: str = "default") -> None:
    """Core WebSocket connection lifecycle for IDE ↔ Backend streaming."""
    await ws_manager.connect(websocket)

    # Subscribe to all events and forward to this connection
    queue = event_bus.subscribe()

    async def _forward_events() -> None:
        """Forward events from bus → WebSocket."""
        try:
            while True:
                event = await queue.get()
                await websocket.send_text(event.model_dump_json())
        except Exception:
            pass  # Connection closed

    forward_task = asyncio.create_task(_forward_events())

    try:
        while True:
            # Receive messages from IDE (e.g., approvals, stop commands)
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                # Reconcile: support both 'type' and 'action' formats
                msg_type = message.get("type") or message.get("action", "")
                logger.debug("websocket.message_received", msg_type=msg_type, client_id=client_id)

                # 1. Approvals
                if msg_type in ("agent.approve", "human.approval"):
                    from src.security.approval_manager import approval_manager

                    is_approved = message.get("approved", True)
                    appr_id = message.get("approval_id", "")
                    if is_approved:
                        await approval_manager.approve(appr_id)
                    else:
                        await approval_manager.deny(appr_id, message.get("reason", "User denied"))

                elif msg_type == "agent.deny":
                    from src.security.approval_manager import approval_manager

                    await approval_manager.deny(
                        message.get("approval_id", ""),
                        message.get("reason", "User denied"),
                    )

                # 2. Interactive Questions
                elif msg_type in ("agent.question_answer", "agent.question", "human.question_response"):
                    from src.tools.definitions.ask_question import question_manager

                    q_id = message.get("question_id", "")
                    ans = message.get("answer") or message.get("response", "")
                    question_manager.answer_question(q_id, ans)

                # 3. Stop / Cancel
                elif msg_type in ("agent.stop", "agent.cancel"):
                    from src.api.routes.agent import agent_manager

                    target_id = message.get("agent_id") or message.get("task_id", "")
                    if target_id:
                        await agent_manager.stop_agent(target_id)

            except json.JSONDecodeError:
                logger.warn("websocket.invalid_json")
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        event_bus.unsubscribe(queue)
        ws_manager.disconnect(websocket)


@router.websocket("/ws")
async def websocket_root_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint at /ws."""
    await _handle_client_connection(websocket, client_id="root")


@router.websocket("/ws/{client_id}")
async def websocket_client_endpoint(websocket: WebSocket, client_id: str) -> None:
    """WebSocket endpoint at /ws/{client_id}."""
    await _handle_client_connection(websocket, client_id=client_id)

