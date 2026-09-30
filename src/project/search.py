"""
CoreMind Backend — Hybrid Code Search.

Combines Exact Search, Symbol Search, and Keyword/Semantic Retrieval
into ranked code search results without external database dependencies.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.project.symbols import extract_symbols_from_file

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "coverage", ".dart_tool",
    ".pytest_cache", ".ruff_cache",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".tar",
    ".gz", ".exe", ".dll", ".so", ".dylib", ".pyc", ".pyo",
}

MAX_FILE_SIZE = 600_000  # 600 KB


@dataclass
class SearchMatch:
    """A single matched line/location from hybrid search."""

    file: str
    line: int
    content: str
    match_type: str  # "exact", "symbol", "semantic"
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "content": self.content,
            "match_type": self.match_type,
            "score": round(self.score, 3),
        }


def _tokenize(text: str) -> list[str]:
    """Tokenize code or query into lowercase alphanumeric words."""
    # Split camelCase and snake_case
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z]|\b)", text)
    if not words:
        words = re.findall(r"\w+", text)
    return [w.lower() for w in words if len(w) > 1]


class HybridCodeSearcher:
    """Lightweight hybrid code search engine."""

    def __init__(self, project_path: str) -> None:
        self.project_path = Path(project_path)

    def search(
        self,
        query: str,
        file_pattern: str | None = None,
        is_regex: bool = False,
        max_results: int = 30,
    ) -> list[SearchMatch]:
        """Perform hybrid search combining exact, symbol, and semantic ranking."""
        exact_matches = self._exact_search(query, file_pattern=file_pattern, is_regex=is_regex)
        symbol_matches = self._symbol_search(query, file_pattern=file_pattern)
        semantic_matches = self._semantic_search(query, file_pattern=file_pattern)

        # Merge and rank
        merged: dict[tuple[str, int], SearchMatch] = {}

        # 1. Exact matches get highest base score (1.0)
        for m in exact_matches:
            merged[(m.file, m.line)] = m

        # 2. Symbol matches (0.85 base score)
        for m in symbol_matches:
            key = (m.file, m.line)
            if key in merged:
                merged[key].score += 0.3
                merged[key].match_type = "exact+symbol"
            else:
                merged[key] = m

        # 3. Semantic matches (0.4 - 0.7 score based on term overlap)
        for m in semantic_matches:
            key = (m.file, m.line)
            if key in merged:
                merged[key].score += 0.2
            else:
                merged[key] = m

        results = list(merged.values())
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:max_results]

    def _exact_search(
        self,
        query: str,
        file_pattern: str | None = None,
        is_regex: bool = False,
    ) -> list[SearchMatch]:
        """Grep-like exact line search."""
        matches: list[SearchMatch] = []
        if not self.project_path.exists():
            return matches

        regex = None
        if is_regex:
            try:
                regex = re.compile(query, re.IGNORECASE)
            except re.error:
                regex = None

        query_lower = query.lower()

        for dirpath, dirnames, filenames in os.walk(self.project_path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix.lower() in BINARY_EXTENSIONS:
                    continue
                if file_pattern and not p.match(file_pattern):
                    continue

                try:
                    if p.stat().st_size > MAX_FILE_SIZE:
                        continue
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except (OSError, UnicodeDecodeError):
                    continue

                rel = str(p.relative_to(self.project_path))
                for line_idx, line in enumerate(text.splitlines(), start=1):
                    hit = False
                    if regex:
                        hit = bool(regex.search(line))
                    else:
                        hit = query_lower in line.lower()

                    if hit:
                        matches.append(
                            SearchMatch(
                                file=rel,
                                line=line_idx,
                                content=line.strip()[:200],
                                match_type="exact",
                                score=1.0,
                            )
                        )
                        if len(matches) >= 100:
                            return matches

        return matches

    def _symbol_search(
        self,
        query: str,
        file_pattern: str | None = None,
    ) -> list[SearchMatch]:
        """Find classes, methods, and functions matching the query."""
        matches: list[SearchMatch] = []
        tokens = set(_tokenize(query))
        if not tokens:
            return matches

        for dirpath, dirnames, filenames in os.walk(self.project_path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix.lower() not in {".py", ".dart", ".ts", ".tsx", ".js"}:
                    continue
                if file_pattern and not p.match(file_pattern):
                    continue

                rel = str(p.relative_to(self.project_path))
                syms = extract_symbols_from_file(p, rel)

                for s in syms:
                    s_tokens = set(_tokenize(s.name))
                    overlap = tokens.intersection(s_tokens)
                    if overlap:
                        score = 0.8 + (0.1 * len(overlap) / len(tokens))
                        matches.append(
                            SearchMatch(
                                file=rel,
                                line=s.line_number,
                                content=f"[{s.kind}] {s.signature or s.name}",
                                match_type="symbol",
                                score=score,
                            )
                        )
                    for child in s.children:
                        c_tokens = set(_tokenize(child.name))
                        c_overlap = tokens.intersection(c_tokens)
                        if c_overlap:
                            score = 0.75 + (0.1 * len(c_overlap) / len(tokens))
                            matches.append(
                                SearchMatch(
                                    file=rel,
                                    line=child.line_number,
                                    content=f"[{child.kind}] {child.signature or child.name}",
                                    match_type="symbol",
                                    score=score,
                                )
                            )

        return matches

    def _semantic_search(
        self,
        query: str,
        file_pattern: str | None = None,
    ) -> list[SearchMatch]:
        """Term-overlap / keyword relevance search across comments and code."""
        matches: list[SearchMatch] = []
        query_tokens = _tokenize(query)
        if not query_tokens:
            return matches

        q_token_set = set(query_tokens)

        for dirpath, dirnames, filenames in os.walk(self.project_path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix.lower() in BINARY_EXTENSIONS:
                    continue
                if file_pattern and not p.match(file_pattern):
                    continue

                try:
                    if p.stat().st_size > MAX_FILE_SIZE:
                        continue
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                rel = str(p.relative_to(self.project_path))
                for line_idx, line in enumerate(text.splitlines(), start=1):
                    line_tokens = set(_tokenize(line))
                    if not line_tokens:
                        continue

                    common = q_token_set.intersection(line_tokens)
                    if common:
                        score = len(common) / math.sqrt(len(q_token_set) * len(line_tokens) + 1)
                        if score > 0.25:
                            matches.append(
                                SearchMatch(
                                    file=rel,
                                    line=line_idx,
                                    content=line.strip()[:200],
                                    match_type="semantic",
                                    score=score * 0.7,
                                )
                            )
                            if len(matches) >= 50:
                                return matches

        return matches
