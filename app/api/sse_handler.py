import asyncio
import json
import time
from typing import Any, AsyncGenerator, Optional


class SSEEventStream:
    """Async Queue-based Server-Sent Events stream manager."""

    def __init__(self):
        self.queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self.closed: bool = False

    def emit(self, event_type: str, payload: Any) -> None:
        if self.closed:
            return

        message = {
            "type": event_type,
            "payload": payload,
            "timestamp": int(time.time() * 1000),
        }
        data_str = f"event: {event_type}\ndata: {json.dumps(message)}\n\n"
        self.queue.put_nowait(data_str)

    def close(self, final_payload: Optional[Any] = None) -> None:
        if self.closed:
            return
        self.closed = True

        if final_payload is not None:
            self.emit("done", final_payload)

        self.queue.put_nowait(None)

    async def stream(self) -> AsyncGenerator[str, None]:
        while True:
            try:
                # Wait for next event or timeout to send heartbeat
                item = await asyncio.wait_for(self.queue.get(), timeout=15.0)
                if item is None:
                    break
                yield item
            except asyncio.TimeoutError:
                if not self.closed:
                    heartbeat_data = {
                        "type": "heartbeat",
                        "payload": {"ping": int(time.time() * 1000)},
                        "timestamp": int(time.time() * 1000),
                    }
                    yield f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"
