import pytest
from pathlib import Path
from src.terminal.web_server import find_available_port, ensure_project_web_server, get_running_project_server
from src.tools.definitions.terminal import execute_terminal
from src.terminal.process_manager import process_manager


def test_find_available_port():
    port = find_available_port(3000, 3050)
    assert 3000 <= port < 3050


@pytest.mark.asyncio
async def test_ensure_project_web_server_no_html(tmp_path: Path):
    res = await ensure_project_web_server(str(tmp_path))
    assert res is None


@pytest.mark.asyncio
async def test_ensure_project_web_server_with_html(tmp_path: Path):
    html_file = tmp_path / "index.html"
    html_file.write_text("<h1>Test Portfolio</h1>")

    res = await ensure_project_web_server(str(tmp_path))
    assert res is not None
    assert "url" in res
    assert res["url"].startswith("http://localhost:")
    assert res["status"] == "running"

    # Subsequent call should return existing server
    second = await ensure_project_web_server(str(tmp_path))
    assert second is not None
    assert second["url"] == res["url"]

    # Cleanup
    pid = res.get("process_id")
    if pid:
        await process_manager.stop_process(pid)


@pytest.mark.asyncio
async def test_execute_terminal_background_server(tmp_path: Path):
    html_file = tmp_path / "index.html"
    html_file.write_text("<h1>Live</h1>")

    res = await execute_terminal(
        project_path=str(tmp_path),
        command="python3 -m http.server 3044",
        is_background=True,
    )
    assert res.get("success") is True
    assert res.get("is_background") is True
    assert "process_id" in res

    # Cleanup
    pid = res.get("process_id")
    if pid:
        await process_manager.stop_process(pid)
