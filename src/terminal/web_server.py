"""
CoreMind Backend — Local Web Server Manager.

Automatically provisions and manages lightweight local HTTP servers
for previewing HTML/CSS/JS or frontend web projects created or edited by the agent.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
import socket
from typing import Any

from src.terminal.process_manager import process_manager
from src.utils.logger import logger


def find_available_port(start_port: int = 3000, max_port: int = 3050) -> int:
    """Find the first open TCP port in the specified range."""
    for port in range(start_port, max_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start_port


def get_running_project_server(project_path: str) -> dict[str, Any] | None:
    """
    Check if a web server process is currently running for the given project path.
    Returns process details with local preview URL if found.
    """
    resolved_path = str(Path(project_path).resolve())
    for proc in process_manager._processes.values():
        if proc.status == "running":
            proc_cwd = str(Path(proc.cwd).resolve())
            if proc_cwd == resolved_path:
                # Check command or logs for port
                port_match = re.search(r"(?:http\.server|serve|port|-p)\s+(\d+)", proc.command)
                port = int(port_match.group(1)) if port_match else 3000
                return {
                    "process_id": proc.process_id,
                    "command": proc.command,
                    "port": port,
                    "url": f"http://localhost:{port}",
                    "status": "running",
                }
    return None


async def ensure_project_web_server(project_path: str) -> dict[str, Any] | None:
    """
    Ensure a local web server is running for a project that has an index.html entrypoint.
    If already running, returns its info. If not, spawns a background http.server.
    """
    p = Path(project_path)
    index_html = p / "index.html"
    index_htm = p / "index.htm"

    if not (index_html.exists() or index_htm.exists()):
        return None

    # Check if one is already running
    existing = get_running_project_server(project_path)
    if existing:
        logger.info("web_server.already_running", project=project_path, url=existing["url"])
        return existing

    # Find open port
    port = find_available_port(3000, 3050)
    cmd = f"python3 -m http.server {port}"

    logger.info("web_server.starting", project=project_path, command=cmd, port=port)
    res = await process_manager.start_process(cmd, cwd=str(p.resolve()))
    if "error" in res:
        logger.warn("web_server.start_failed", error=res["error"], project=project_path)
        return None

    await asyncio.sleep(0.5)

    info = {
        "process_id": res.get("process_id"),
        "command": cmd,
        "port": port,
        "url": f"http://localhost:{port}",
        "status": "running",
    }
    logger.info("web_server.started", project=project_path, url=info["url"])
    return info
