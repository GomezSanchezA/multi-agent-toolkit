"""Tests for agents/memory_manager.py"""

import json
import pytest
import tempfile
from pathlib import Path
from agents.memory_manager import (
    MemoryManager,
    Identity,
    SessionEntry,
    KnowledgeEntry,
)


@pytest.fixture
def tmp_memory_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def manager(tmp_memory_dir):
    return MemoryManager(agent_name="test-agent", memory_dir=tmp_memory_dir)


# ── Identity ────────────────────────────────────────────────

class TestIdentity:
    def test_to_markdown(self):
        identity = Identity(
            name="coda",
            model="opus-4",
            role="builder",
            commitments=["Apply parity", "Separate generation from evaluation"],
            created="2026-02-01",
        )
        md = identity.to_markdown()
        assert "**Name:** coda" in md
        assert "**Role:** builder" in md
        assert "Apply parity" in md


# ── SessionEntry ────────────────────────────────────────────

class TestSessionEntry:
    def test_to_markdown_all_fields(self):
        entry = SessionEntry(
            timestamp="2026-02-01 20:00",
            actions=["Ran Control 1"],
            findings=["RAG scores 0/4"],
            prs_created=["#172"],
            errors=["Branch conflict"],
            next_steps=["Run Control 2"],
        )
        md = entry.to_markdown()
        assert "Session 2026-02-01 20:00" in md
        assert "Ran Control 1" in md
        assert "RAG scores 0/4" in md
        assert "#172" in md
        assert "Branch conflict" in md
        assert "Run Control 2" in md

    def test_to_markdown_minimal(self):
        entry = SessionEntry(timestamp="2026-02-01 20:00")
        md = entry.to_markdown()
        assert "Session 2026-02-01 20:00" in md


# ── MemoryManager ───────────────────────────────────────────

class TestMemoryManager:
    def test_init_creates_dir(self, tmp_memory_dir):
        subdir = Path(tmp_memory_dir) / "subdir"
        m = MemoryManager(agent_name="test", memory_dir=str(subdir))
        assert subdir.exists()

    def test_load_returns_false_for_new(self, manager):
        assert manager.load() is False

    def test_set_identity(self, manager):
        manager.set_identity(model="opus-4", role="skeptic", commitments=["Be honest"])
        assert manager.identity.model == "opus-4"
        assert manager.identity.role == "skeptic"
        assert manager.identity.commitments == ["Be honest"]

    def test_set_identity_partial(self, manager):
        manager.set_identity(role="builder")
        assert manager.identity.role == "builder"
        assert manager.identity.model == ""  # unchanged

    def test_save_and_load_roundtrip(self, tmp_memory_dir):
        # Save
        m1 = MemoryManager(agent_name="roundtrip", memory_dir=tmp_memory_dir)
        m1.set_identity(model="opus-4", role="builder", commitments=["Test well"])
        m1.add_session_entry(actions=["Built tests"], findings=["All passed"])
        m1.add_knowledge("parity", "Tests must apply to humans too", confidence=0.9)
        m1.add_blind_spot("Execution bias")
        m1.add_pending_task("Run Control 2")
        m1.save()

        # Load
        m2 = MemoryManager(agent_name="roundtrip", memory_dir=tmp_memory_dir)
        assert m2.load() is True

        assert m2.identity.model == "opus-4"
        assert m2.identity.role == "builder"
        assert len(m2.sessions) == 1
        assert m2.sessions[0].actions == ["Built tests"]
        assert "parity" in m2.knowledge
        assert m2.knowledge["parity"].confidence == 0.9
        assert "Execution bias" in m2.blind_spots
        assert "Run Control 2" in m2.pending_tasks

    def test_soul_file_created(self, manager):
        manager.set_identity(role="builder")
        manager.save()
        soul_path = Path(manager.memory_dir) / "test-agent_SOUL.md"
        assert soul_path.exists()
        content = soul_path.read_text()
        assert "test-agent" in content

    def test_json_file_created(self, manager):
        manager.save()
        json_path = Path(manager.memory_dir) / "test-agent_memory.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert "identity" in data
        assert "sessions" in data
        assert "knowledge" in data

    def test_add_session_entry(self, manager):
        manager.add_session_entry(
            actions=["Action 1"],
            findings=["Finding 1"],
            prs_created=["#100"],
            errors=["Error 1"],
            next_steps=["Next 1"],
        )
        assert len(manager.sessions) == 1
        assert manager.sessions[0].actions == ["Action 1"]
        assert manager.sessions[0].timestamp  # should be auto-set

    def test_add_knowledge(self, manager):
        manager.add_knowledge("key1", "value1", source="test", confidence=0.8)
        assert "key1" in manager.knowledge
        assert manager.knowledge["key1"].value == "value1"
        assert manager.knowledge["key1"].confidence == 0.8

    def test_get_knowledge(self, manager):
        manager.add_knowledge("k", "v")
        assert manager.get_knowledge("k") == "v"
        assert manager.get_knowledge("nonexistent") is None

    def test_knowledge_overwrite(self, manager):
        manager.add_knowledge("k", "v1")
        manager.add_knowledge("k", "v2")
        assert manager.get_knowledge("k") == "v2"

    def test_add_blind_spot_no_duplicates(self, manager):
        manager.add_blind_spot("Bias A")
        manager.add_blind_spot("Bias A")
        assert len(manager.blind_spots) == 1

    def test_add_pending_task(self, manager):
        manager.add_pending_task("Task 1")
        assert "Task 1" in manager.pending_tasks

    def test_pending_task_no_duplicates(self, manager):
        manager.add_pending_task("Task 1")
        manager.add_pending_task("Task 1")
        assert len(manager.pending_tasks) == 1

    def test_complete_task(self, manager):
        manager.add_pending_task("Task 1")
        manager.complete_task("Task 1")
        assert "Task 1" not in manager.pending_tasks

    def test_complete_nonexistent_task(self, manager):
        manager.complete_task("Nonexistent")  # should not raise

    def test_get_context(self, manager):
        manager.set_identity(model="opus-4", role="builder", commitments=["Be honest"])
        manager.add_session_entry(actions=["Did thing"], next_steps=["Do next thing"])
        manager.add_knowledge("fact1", "Important fact")
        manager.add_pending_task("Pending work")

        ctx = manager.get_context()
        assert "test-agent" in ctx
        assert "builder" in ctx
        assert "Be honest" in ctx
        assert "Did thing" in ctx
        assert "Do next thing" in ctx
        assert "Important fact" in ctx
        assert "Pending work" in ctx

    def test_get_context_truncation(self, manager):
        # Add lots of data
        for i in range(50):
            manager.add_knowledge(f"fact_{i}", f"Value {i}" * 10)

        ctx = manager.get_context(max_lines=20)
        lines = ctx.split("\n")
        assert len(lines) <= 21  # 20 + truncation message

    def test_soul_renders_last_5_sessions(self, manager):
        for i in range(10):
            manager.add_session_entry(actions=[f"Action {i}"])
        manager.save()

        soul_path = Path(manager.memory_dir) / "test-agent_SOUL.md"
        content = soul_path.read_text()
        # Should have sessions 5-9 (last 5), not 0-4
        assert "Action 9" in content
        assert "Action 5" in content
