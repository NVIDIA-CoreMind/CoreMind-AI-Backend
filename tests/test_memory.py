"""
Tests for limited agent memory.
"""

from src.config import settings
from src.memory.store import AgentMemoryStore


class TestAgentMemoryStore:
    def test_save_and_recall(self, tmp_path) -> None:
        store = AgentMemoryStore(str(tmp_path / "memory.db"))
        project = str(tmp_path / "proj")
        saved = store.save(
            project,
            "Use pytest as the test runner",
            category="convention",
            importance=5,
        )
        hits = store.recall(project, query="pytest tests")
        assert saved.id.startswith("mem_")
        assert hits[0].content.startswith("Use pytest")
        assert store.count(project) == 1

    def test_duplicate_updates_instead_of_growing(self, tmp_path) -> None:
        store = AgentMemoryStore(str(tmp_path / "memory.db"))
        project = str(tmp_path / "proj")
        first = store.save(project, "Prefer FastAPI routers", category="convention", importance=2)
        second = store.save(project, "Prefer FastAPI routers", category="decision", importance=4)
        assert first.id == second.id
        assert store.count(project) == 1
        assert second.importance == 4
        assert second.category == "decision"

    def test_evicts_oldest_weakest(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "memory_max_items", 3)
        store = AgentMemoryStore(str(tmp_path / "memory.db"))
        project = str(tmp_path / "proj")
        store.save(project, "old weak note", importance=1)
        store.save(project, "keep this convention", importance=5)
        store.save(project, "another keep", importance=4)
        store.save(project, "new note that should stay", importance=3)
        assert store.count(project) == 3
        contents = [item.content for item in store.recall(project, limit=10)]
        assert "old weak note" not in contents
        assert "new note that should stay" in contents

    def test_forget(self, tmp_path) -> None:
        store = AgentMemoryStore(str(tmp_path / "memory.db"))
        project = str(tmp_path / "proj")
        item = store.save(project, "obsolete decision")
        assert store.forget(project, item.id) is True
        assert store.count(project) == 0
        assert store.forget(project, item.id) is False

    def test_content_is_clipped(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "memory_max_content_chars", 40)
        store = AgentMemoryStore(str(tmp_path / "memory.db"))
        project = str(tmp_path / "proj")
        item = store.save(project, "x" * 400)
        assert len(item.content) <= 40

    def test_prompt_digest_is_capped(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "memory_prompt_items", 2)
        store = AgentMemoryStore(str(tmp_path / "memory.db"))
        project = str(tmp_path / "proj")
        store.save(project, "note one about auth", importance=5)
        store.save(project, "note two about tests", importance=4)
        store.save(project, "note three about docker", importance=3)
        digest = store.build_prompt_digest(project, query="auth jwt")
        assert "Agent Memory" in digest
        assert digest.count("- [") <= 2
