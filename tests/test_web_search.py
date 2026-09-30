"""
Tests for the web_search tool.
"""

from typing import Any

import pytest

import src.tools.registry  # noqa: F401  — register tools before importing definitions
from src.tools.definitions import web_search as web_search_mod


class _FakeResponse:
    def __init__(self, payload: Any, text: str = "") -> None:
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, routes: dict[str, _FakeResponse]) -> None:
        self._routes = routes

    async def get(self, url: str, **_kwargs: Any) -> _FakeResponse:
        for prefix, response in self._routes.items():
            if url.startswith(prefix):
                return response
        raise AssertionError(f"Unexpected URL: {url}")

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_web_search_merges_capped_results(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <a class="result__a" href="https://docs.python.org/3/library/asyncio.html">asyncio docs</a>
    <a class="result__snippet">Official asyncio documentation</a>
    """
    instant = {
        "Heading": "asyncio",
        "AbstractText": "asyncio is a library to write concurrent code.",
        "AbstractURL": "https://docs.python.org/3/library/asyncio.html",
        "RelatedTopics": [
            {"Text": "aiohttp - Async HTTP client", "FirstURL": "https://docs.aiohttp.org/"},
        ],
        "Results": [],
    }
    wiki = {
        "query": {
            "search": [
                {
                    "title": "Asyncio",
                    "snippet": "asyncio is a Python library",
                }
            ]
        }
    }

    client = _FakeClient({
        "https://html.duckduckgo.com/html/": _FakeResponse({}, text=html),
        "https://api.duckduckgo.com/": _FakeResponse(instant),
        "https://en.wikipedia.org/w/api.php": _FakeResponse(wiki),
    })
    monkeypatch.setattr(web_search_mod.httpx, "AsyncClient", lambda **_kwargs: client)

    result = await web_search_mod.execute_web_search("python asyncio", max_results=2)
    assert result["query"] == "python asyncio"
    assert result["returned"] == 2
    urls = [item["url"] for item in result["results"]]
    assert "https://docs.python.org/3/library/asyncio.html" in urls
    assert len(result["results"]) <= 2


@pytest.mark.asyncio
async def test_web_search_rejects_empty_query() -> None:
    result = await web_search_mod.execute_web_search("   ")
    assert result["results"] == []
    assert "empty" in result["error"].lower()
