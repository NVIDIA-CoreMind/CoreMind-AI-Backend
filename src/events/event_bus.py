"""
CoreMind Backend — Event Bus.

Typed async pub/sub that bridges agent events to WebSocket connections.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from src.events.events import CoreMindEvent, EventType
from src.utils.logger import logger

# Type alias for event handlers
EventHandler = Callable[[CoreMindEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Async pub/sub event bus for agent → IDE streaming."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []
        self._queues: list[asyncio.Queue[CoreMindEvent]] = []

    def on(self, event_type: EventType, handler: EventHandler) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    def on_all(self, handler: EventHandler) -> None:
        """Register a handler for ALL event types (used by WebSocket bridge)."""
        self._global_handlers.append(handler)

    def subscribe(self) -> asyncio.Queue[CoreMindEvent]:
        """Create a new subscriber queue — receives all events."""
        queue: asyncio.Queue[CoreMindEvent] = asyncio.Queue()
        self._queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[CoreMindEvent]) -> None:
        """Remove a subscriber queue."""
        self._queues = [q for q in self._queues if q is not queue]

    async def emit(self, event: CoreMindEvent) -> None:
        """Emit an event to all handlers and subscriber queues."""
        logger.debug(
            "event.emitted",
            event_type=event.type.value,
            agent_id=event.agent_id or "",
        )

        # Typed handlers
        for handler in self._handlers.get(event.type, []):
            try:
                await handler(event)
            except Exception as exc:
                logger.error(
                    "event.handler_error",
                    event_type=event.type.value,
                    error=str(exc),
                )

        # Global handlers
        for handler in self._global_handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.error(
                    "event.global_handler_error",
                    event_type=event.type.value,
                    error=str(exc),
                )

        # Subscriber queues (WebSocket connections)
        for queue in self._queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warn("event.queue_full", event_type=event.type.value)

    # Alias for emit
    publish = emit

    def clear(self) -> None:
        """Remove all handlers and queues."""
        self._handlers.clear()
        self._global_handlers.clear()
        self._queues.clear()


# Module-level singleton
event_bus = EventBus()
