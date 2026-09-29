"""
CoreMind Backend — Interactive Antigravity-Style Authentication Portal.

Loads and renders the standalone Antigravity authentication portal interface.
"""

from __future__ import annotations

from pathlib import Path

_HTML_FILE = Path(__file__).parent / "portal.html"


def get_auth_portal_html() -> str:
    """Return the complete standalone HTML/CSS/JS for the Antigravity auth portal."""
    if _HTML_FILE.exists():
        return _HTML_FILE.read_text(encoding="utf-8")
    return "<html><body><h2>CoreMind Auth Portal</h2></body></html>"
