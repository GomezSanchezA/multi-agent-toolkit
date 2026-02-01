"""Tests for tasks/task_board.py — Task board with keepalive pattern."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from tasks.task_board import TaskBoard


@pytest.fixture
def board_dir():
    """Create a temporary directory for task board tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def board(board_dir):
    """Create a fresh TaskBoard."""
    return TaskBoard(repo_path=board_dir)


# ── Load / Save ────────────────────────────────────────────


class TestLoadSave:
    def test_load_returns_false_when_no_file(self, board):
        assert board.load() is False
        assert board.tasks == []

    def test_save_creates_file(self, board):
        board.add_task("Test task")
        board.save()
        assert board.board_path.exists()

    def test_save_creates_parent_dirs(self, board_dir):
        board = TaskBoard(repo_path=board_dir, board_file="deep/nested/board.json")
        board.add_task("Test")
        board.save()
        assert board.board_path.exists()

    def test_roundtrip(self, board):
        board.add_task("Task A", assigned_to="coda")
        board.add_task("Task B", priority="high")
        board.save()

        board2 = TaskBoard(repo_path=str(board.repo_path))
        assert board2.load() is True
        assert len(board2.tasks) == 2
        assert board2.tasks[0]["description"] == "Task A"
        assert board2.tasks[1]["priority"] == "high"

    def test_counter_persists(self, board):
        board.add_task("A")
        board.add_task("B")
        board.save()

        board2 = TaskBoard(repo_path=str(board.repo_path))
        board2.load()
        board2.add_task("C")
        assert board2.tasks[-1]["id"] == "T3"

    def test_save_includes_summary(self, board):
        board.add_task("Pending task")
        board.add_task("Another")
        board.start_task("T1")
        board.complete_task("T1", result="done")
        board.save()

        with open(board.board_path) as f:
            data = json.load(f)

        assert data["summary"]["total"] == 2
        assert data["summary"]["pending"] == 1
        assert data["summary"]["completed"] == 1

    def test_save_includes_updated_timestamp(self, board):
        board.add_task("X")
        board.save()

        with open(board.board_path) as f:
            data = json.load(f)

        assert "updated" in data


# ── Add Task ───────────────────────────────────────────────


class TestAddTask:
    def test_add_task_basic(self, board):
        task = board.add_task("Do something")
        assert task["id"] == "T1"
        assert task["description"] == "Do something"
        assert task["status"] == "pending"
        assert task["assigned_to"] == ""

    def test_add_task_with_options(self, board):
        task = board.add_task(
            "Complex task",
            assigned_to="coda",
            depends_on=["T0"],
            priority="high",
            thread="research",
        )
        assert task["assigned_to"] == "coda"
        assert task["depends_on"] == ["T0"]
        assert task["priority"] == "high"
        assert task["thread"] == "research"

    def test_ids_increment(self, board):
        t1 = board.add_task("First")
        t2 = board.add_task("Second")
        t3 = board.add_task("Third")
        assert t1["id"] == "T1"
        assert t2["id"] == "T2"
        assert t3["id"] == "T3"

    def test_task_has_created_timestamp(self, board):
        task = board.add_task("Timestamped")
        assert task["created"] != ""

    def test_task_starts_with_empty_result(self, board):
        task = board.add_task("Fresh task")
        assert task["result"] == ""
        assert task["started"] == ""
        assert task["completed"] == ""


# ── Task Lifecycle ─────────────────────────────────────────


class TestTaskLifecycle:
    def test_start_task(self, board):
        board.add_task("Work item")
        board.start_task("T1")
        assert board.tasks[0]["status"] == "in_progress"
        assert board.tasks[0]["started"] != ""

    def test_complete_task(self, board):
        board.add_task("Work item")
        board.start_task("T1")
        board.complete_task("T1", result="All done")
        assert board.tasks[0]["status"] == "completed"
        assert board.tasks[0]["result"] == "All done"
        assert board.tasks[0]["completed"] != ""

    def test_complete_without_start(self, board):
        board.add_task("Quick task")
        board.complete_task("T1", result="Skipped ahead")
        assert board.tasks[0]["status"] == "completed"

    def test_block_task(self, board):
        board.add_task("Blocked item")
        board.block_task("T1", reason="waiting on upstream")
        assert board.tasks[0]["status"] == "blocked"
        assert "waiting on upstream" in board.tasks[0]["result"]

    def test_start_nonexistent_task(self, board):
        board.add_task("Real task")
        board.start_task("T999")  # should not crash
        assert board.tasks[0]["status"] == "pending"

    def test_complete_nonexistent_task(self, board):
        board.add_task("Real task")
        board.complete_task("T999")  # should not crash
        assert board.tasks[0]["status"] == "pending"


# ── Queries ────────────────────────────────────────────────


class TestQueries:
    def test_next_task_returns_first_pending(self, board):
        board.add_task("First")
        board.add_task("Second")
        assert board.next_task()["id"] == "T1"

    def test_next_task_skips_in_progress(self, board):
        board.add_task("First")
        board.add_task("Second")
        board.start_task("T1")
        assert board.next_task()["id"] == "T2"

    def test_next_task_skips_completed(self, board):
        board.add_task("First")
        board.add_task("Second")
        board.complete_task("T1")
        assert board.next_task()["id"] == "T2"

    def test_next_task_returns_none_when_empty(self, board):
        assert board.next_task() is None

    def test_next_task_returns_none_when_all_done(self, board):
        board.add_task("Only task")
        board.complete_task("T1")
        assert board.next_task() is None

    def test_next_task_skips_blocked(self, board):
        board.add_task("Blocked", depends_on=["T2"])
        board.add_task("Unblocked")
        assert board.next_task()["id"] == "T2"

    def test_pending_tasks(self, board):
        board.add_task("A")
        board.add_task("B")
        board.start_task("T1")
        assert len(board.pending_tasks()) == 1
        assert board.pending_tasks()[0]["id"] == "T2"

    def test_in_progress_tasks(self, board):
        board.add_task("A")
        board.add_task("B")
        board.start_task("T1")
        assert len(board.in_progress_tasks()) == 1

    def test_completed_tasks(self, board):
        board.add_task("A")
        board.complete_task("T1")
        assert len(board.completed_tasks()) == 1

    def test_is_done_true(self, board):
        board.add_task("A")
        board.add_task("B")
        board.complete_task("T1")
        board.complete_task("T2")
        assert board.is_done() is True

    def test_is_done_false(self, board):
        board.add_task("A")
        board.add_task("B")
        board.complete_task("T1")
        assert board.is_done() is False

    def test_is_done_empty_board(self, board):
        assert board.is_done() is True


# ── Dependencies ───────────────────────────────────────────


class TestDependencies:
    def test_blocked_by_pending_dep(self, board):
        board.add_task("Dependency")
        board.add_task("Blocked task", depends_on=["T1"])
        # T2 should be skipped because T1 is pending
        assert board.next_task()["id"] == "T1"

    def test_unblocked_when_dep_completed(self, board):
        board.add_task("Dependency")
        board.add_task("Was blocked", depends_on=["T1"])
        board.complete_task("T1")
        assert board.next_task()["id"] == "T2"

    def test_multiple_dependencies(self, board):
        board.add_task("Dep A")
        board.add_task("Dep B")
        board.add_task("Needs both", depends_on=["T1", "T2"])
        board.complete_task("T1")
        # T3 still blocked by T2
        assert board.next_task()["id"] == "T2"
        board.complete_task("T2")
        assert board.next_task()["id"] == "T3"

    def test_nonexistent_dependency_not_blocking(self, board):
        # If a dependency ID doesn't exist, _find returns None, so not blocked
        board.add_task("Has phantom dep", depends_on=["T999"])
        assert board.next_task()["id"] == "T1"


# ── Keepalive ──────────────────────────────────────────────


class TestKeepalive:
    def test_ensure_keepalive_adds_task(self, board):
        board.ensure_keepalive(wait_minutes=1, threads=["research"])
        assert len(board.tasks) == 1
        assert board.tasks[0]["priority"] == "keepalive"
        assert "research" in board.tasks[0]["description"]

    def test_ensure_keepalive_idempotent(self, board):
        board.ensure_keepalive()
        board.ensure_keepalive()
        board.ensure_keepalive()
        keepalives = [t for t in board.tasks if t["priority"] == "keepalive"]
        assert len(keepalives) == 1

    def test_has_keepalive(self, board):
        assert board.has_keepalive() is False
        board.ensure_keepalive()
        assert board.has_keepalive() is True

    def test_completed_keepalive_allows_new_one(self, board):
        board.ensure_keepalive()
        board.complete_task("T1")
        assert board.has_keepalive() is False
        board.ensure_keepalive()
        assert board.has_keepalive() is True
        assert len([t for t in board.tasks if t["priority"] == "keepalive"]) == 2

    def test_keepalive_with_multiple_threads(self, board):
        board.ensure_keepalive(threads=["research", "experiments", "meta"])
        desc = board.tasks[0]["description"]
        assert "research" in desc
        assert "experiments" in desc
        assert "meta" in desc

    def test_keepalive_default_threads(self, board):
        board.ensure_keepalive()
        assert "all monitored threads" in board.tasks[0]["description"]

    def test_keepalive_wait_minutes(self, board):
        board.ensure_keepalive(wait_minutes=5)
        assert "5 minute(s)" in board.tasks[0]["description"]


# ── Display ────────────────────────────────────────────────


class TestDisplay:
    def test_to_markdown_empty(self, board):
        md = board.to_markdown()
        assert "# Task Board" in md

    def test_to_markdown_with_tasks(self, board):
        board.add_task("Pending task")
        board.add_task("In progress")
        board.add_task("Done task")
        board.start_task("T2")
        board.complete_task("T3", result="Finished")

        md = board.to_markdown()
        assert "## Pending" in md
        assert "## In Progress" in md
        assert "## Completed" in md
        assert "Pending task" in md
        assert "In progress" in md
        assert "Done task" in md
        assert "Finished" in md

    def test_to_markdown_shows_blocked(self, board):
        board.add_task("Dep")
        board.add_task("Blocked", depends_on=["T1"])
        md = board.to_markdown()
        assert "(BLOCKED)" in md

    def test_to_markdown_limits_completed(self, board):
        for i in range(15):
            board.add_task(f"Task {i}")
            board.complete_task(f"T{i+1}")
        md = board.to_markdown()
        assert "and 5 more" in md

    def test_to_agent_prompt_contains_instructions(self, board):
        board.add_task("Test task")
        board.ensure_keepalive()
        prompt = board.to_agent_prompt()
        assert "autonomous agent" in prompt
        assert "DO NOT stop" in prompt
        assert "keepalive" in prompt
        assert "Test task" in prompt

    def test_to_agent_prompt_has_communication_section(self, board):
        prompt = board.to_agent_prompt()
        assert "How to communicate" in prompt
        assert "conversations/" in prompt

    def test_to_agent_prompt_has_stop_conditions(self, board):
        prompt = board.to_agent_prompt()
        assert "When to stop" in prompt
        assert "KEEP WORKING" in prompt
