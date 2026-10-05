"""
CoreMind Backend — Tool: web_search

Look up current public information (docs, errors, APIs) with a hard result cap.
Permission: READ
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from src.config import settings
from src.tools.registry import PermissionLevel, ToolDefinition
from src.utils.logger import logger

_TAG_RE = re.compile(r"<[^>]+>")
_DDG_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'(?:.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>)?',
    re.IGNORECASE | re.DOTALL,
)
_USER_AGENT = (
    "Mozilla/5.0 (compatible; CoreMindAgent/1.0; +https://github.com/NVIDIA-CoreMind)"
)


def _strip_html(value: str) -> str:
    text = _TAG_RE.sub(" ", html.unescape(value or ""))
    return " ".join(text.split())


def _unwrap_ddg_url(raw: str) -> str:
    href = html.unescape(raw)
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    if "uddg" in qs:
        return unquote(qs["uddg"][0])
    return href


def _clip(text: str, limit: int = 280) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


async def _duckduckgo_html(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
) -> list[dict[str, str]]:
    response = await client.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _DDG_RESULT_RE.finditer(response.text):
        url = _unwrap_ddg_url(match.group("href"))
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        results.append({
            "title": _clip(_strip_html(match.group("title")), 120),
            "url": url,
            "snippet": _clip(_strip_html(match.group("snippet") or "")),
            "source": "web",
        })
        if len(results) >= limit:
            break
    return results


def _topic_items(payload: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not isinstance(payload, list):
        return items
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if "Topics" in entry:
            items.extend(_topic_items(entry["Topics"]))
            continue
        url = str(entry.get("FirstURL") or "")
        text = str(entry.get("Text") or "")
        if url.startswith("http") and text:
            items.append({
                "title": _clip(text.split(" - ", 1)[0], 120),
                "url": url,
                "snippet": _clip(text),
                "source": "duckduckgo",
            })
    return items


async def _duckduckgo_instant(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
) -> list[dict[str, str]]:
    response = await client.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()
    data = response.json()
    results: list[dict[str, str]] = []

    abstract = str(data.get("AbstractText") or "").strip()
    abstract_url = str(data.get("AbstractURL") or "").strip()
    heading = str(data.get("Heading") or query)
    if abstract and abstract_url:
        results.append({
            "title": _clip(heading, 120),
            "url": abstract_url,
            "snippet": _clip(abstract),
            "source": "duckduckgo",
        })

    results.extend(_topic_items(data.get("Results") or []))
    results.extend(_topic_items(data.get("RelatedTopics") or []))

    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in results:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


async def _wikipedia(client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, str]]:
    response = await client.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "utf8": "1",
            "srlimit": str(limit),
        },
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()
    hits = response.json().get("query", {}).get("search", [])
    results: list[dict[str, str]] = []
    for hit in hits[:limit]:
        title = str(hit.get("title") or "")
        if not title:
            continue
        results.append({
            "title": title,
            "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
            "snippet": _clip(_strip_html(str(hit.get("snippet") or ""))),
            "source": "wikipedia",
        })
    return results


async def _tavily_search(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
) -> list[dict[str, str]]:
    response = await client.post(
        "https://api.tavily.com/search",
        json={
            "api_key": settings.tavily_api_key,
            "query": query,
            "max_results": limit,
            "include_answer": False,
        },
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()
    results: list[dict[str, str]] = []
    for item in data.get("results", []):
        results.append({
            "title": _clip(str(item.get("title") or ""), 120),
            "url": str(item.get("url") or ""),
            "snippet": _clip(str(item.get("content") or "")),
            "source": "tavily",
        })
    return results


def _merge(*groups: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            url = item.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


async def execute_web_search(
    query: str,
    max_results: int | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Search the public web. Never used for secrets or private code."""
    cleaned = " ".join(query.strip().split())
    if not cleaned:
        return {"query": query, "results": [], "error": "Query cannot be empty"}

    cap = max_results or settings.web_search_max_results
    limit = max(1, min(settings.web_search_max_results, cap))
    timeout = httpx.Timeout(settings.web_search_timeout_s)
    html_results: list[dict[str, str]] = []
    instant_results: list[dict[str, str]] = []
    wiki_results: list[dict[str, str]] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        if settings.tavily_api_key:
            try:
                tavily_results = await _tavily_search(client, cleaned, limit)
                results = _merge(tavily_results, limit=limit)
            except Exception as exc:
                errors.append(f"tavily: {exc}")
                logger.warn("tools.web_search.tavily_failed", error=str(exc))
                results = []
        else:
            try:
                html_results = await _duckduckgo_html(client, cleaned, limit)
            except Exception as exc:
                errors.append(f"duckduckgo_html: {exc}")
                logger.warn("tools.web_search.html_failed", error=str(exc))

            try:
                instant_results = await _duckduckgo_instant(client, cleaned, limit)
            except Exception as exc:
                errors.append(f"duckduckgo_instant: {exc}")
                logger.warn("tools.web_search.instant_failed", error=str(exc))

            if len(html_results) + len(instant_results) < limit:
                try:
                    wiki_results = await _wikipedia(client, cleaned, limit)
                except Exception as exc:
                    errors.append(f"wikipedia: {exc}")
                    logger.warn("tools.web_search.wikipedia_failed", error=str(exc))

            results = _merge(html_results, instant_results, wiki_results, limit=limit)

    logger.info("tools.web_search.completed", query=cleaned[:80], results=len(results))
    payload: dict[str, Any] = {
        "query": cleaned,
        "results": results,
        "returned": len(results),
        "max_results": limit,
    }
    if not results and errors:
        payload["error"] = "Web search returned no results"
        payload["detail"] = errors[:3]
    return payload


web_search_tool = ToolDefinition(
    name="web_search",
    description=(
        "Search the public web for documentation, library APIs, error explanations, "
        "and current facts. Returns a small set of titles, URLs, and snippets. "
        "Use when the local codebase is not enough."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (be specific: library + version + error)",
            },
            "max_results": {
                "type": "integer",
                "description": "How many results to return (capped by server config)",
            },
        },
        "required": ["query"],
    },
    permission=PermissionLevel.READ,
    executor=execute_web_search,
    timeout_ms=20_000,
)
