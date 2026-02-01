"""Tests for tasks/autonomous_loop.py"""

import pytest
from unittest.mock import MagicMock, patch
from tasks.autonomous_loop import (
    AutonomousLoop,
    LoopState,
    CycleResult,
)
from agents.conversation_handler import Message


# ── LoopState ───────────────────────────────────────────────

class TestLoopState:
    def test_initial_state(self):
        state = LoopState()
        assert state.cycle_count == 0
        assert state.last_seen == {}
        assert state.history == []
        assert state.pending_tasks == []

    def test_record_seen(self):
        state = LoopState()
        state.record_seen("thread-1", "20260201-2000-coda.md")
        assert state.last_seen["thread-1"] == "20260201-2000-coda.md"

    def test_record_seen_only_advances(self):
        state = LoopState()
        state.record_seen("thread-1", "20260201-2000-coda.md")
        state.record_seen("thread-1", "20260201-1900-opus.md")  # older
        assert state.last_seen["thread-1"] == "20260201-2000-coda.md"

    def test_record_seen_multiple_threads(self):
        state = LoopState()
        state.record_seen("thread-1", "20260201-2000-coda.md")
        state.record_seen("thread-2", "20260201-2100-opus.md")
        assert len(state.last_seen) == 2


# ── CycleResult ─────────────────────────────────────────────

class TestCycleResult:
    def test_fields(self):
        msg = Message(
            filename="20260201-2000-coda.md",
            speaker="coda",
            timestamp="20260201-2000",
            content="Hello",
        )
        result = CycleResult(
            cycle_number=1,
            timestamp="20260201-200000",
            new_messages=[msg],
            action_taken="Responded to question",
            pr_url="https://github.com/example/pr/1",
            next_task=None,
        )
        assert result.cycle_number == 1
        assert len(result.new_messages) == 1
        assert result.pr_url is not None


# ── AutonomousLoop ──────────────────────────────────────────

class TestAutonomousLoop:
    def _make_handler(self):
        handler = MagicMock()
        handler.speaker = "test-agent"
        handler.read_thread.return_value = []
        handler.get_new_messages.return_value = []
        return handler

    def test_init(self):
        handler = self._make_handler()
        loop = AutonomousLoop(
            handler=handler,
            threads=["thread-1"],
            think_fn=lambda msgs, state: None,
            act_fn=lambda task, h: None,
        )
        assert loop.state.cycle_count == 0
        assert loop.threads == ["thread-1"]

    def test_add_task(self):
        handler = self._make_handler()
        loop = AutonomousLoop(
            handler=handler,
            threads=[],
            think_fn=lambda msgs, state: None,
            act_fn=lambda task, h: None,
        )
        loop.add_task("Do something")
        assert "Do something" in loop.state.pending_tasks

    def test_run_cycle_no_messages(self):
        handler = self._make_handler()
        loop = AutonomousLoop(
            handler=handler,
            threads=["thread-1"],
            think_fn=lambda msgs, state: None,
            act_fn=lambda task, h: None,
        )
        result = loop._run_cycle()
        assert result.cycle_number == 1
        assert result.action_taken is None
        assert result.new_messages == []

    def test_run_cycle_with_think_result(self):
        handler = self._make_handler()
        handler.read_thread.return_value = [
            Message("20260201-2000-opus.md", "opus", "20260201-2000", "Question?")
        ]

        def think_fn(msgs, state):
            if msgs:
                return "Answer the question"
            return None

        def act_fn(task, h):
            return "https://github.com/example/pr/1"

        loop = AutonomousLoop(
            handler=handler,
            threads=["thread-1"],
            think_fn=think_fn,
            act_fn=act_fn,
        )
        result = loop._run_cycle()
        assert result.action_taken == "Answer the question"
        assert result.pr_url == "https://github.com/example/pr/1"

    def test_run_cycle_processes_pending_tasks(self):
        handler = self._make_handler()

        def act_fn(task, h):
            return "https://github.com/pr/2"

        loop = AutonomousLoop(
            handler=handler,
            threads=[],
            think_fn=lambda msgs, state: None,
            act_fn=act_fn,
        )
        loop.add_task("Pending task")
        result = loop._run_cycle()
        assert result.action_taken == "Pending task"
        assert len(loop.state.pending_tasks) == 0

    def test_run_cycle_on_cycle_callback(self):
        handler = self._make_handler()
        callback_results = []

        loop = AutonomousLoop(
            handler=handler,
            threads=[],
            think_fn=lambda msgs, state: None,
            act_fn=lambda task, h: None,
            on_cycle=lambda r: callback_results.append(r),
        )
        loop._run_cycle()
        assert len(callback_results) == 1

    def test_run_stops_when_idle(self):
        handler = self._make_handler()

        loop = AutonomousLoop(
            handler=handler,
            threads=["thread-1"],
            think_fn=lambda msgs, state: None,
            act_fn=lambda task, h: None,
        )
        # Run with stop_when_idle=2, poll_interval=0 for fast test
        loop.run(max_cycles=100, poll_interval=0, stop_when_idle=2)
        assert loop.state.cycle_count == 2

    def test_run_respects_max_cycles(self):
        handler = self._make_handler()

        loop = AutonomousLoop(
            handler=handler,
            threads=[],
            think_fn=lambda msgs, state: None,
            act_fn=lambda task, h: None,
        )
        loop.run(max_cycles=5, poll_interval=0, stop_when_idle=0)
        assert loop.state.cycle_count == 5

    def test_run_cycle_handles_act_error(self):
        handler = self._make_handler()

        def bad_act(task, h):
            raise ValueError("act failed")

        loop = AutonomousLoop(
            handler=handler,
            threads=[],
            think_fn=lambda msgs, state: None,
            act_fn=bad_act,
        )
        loop.add_task("Will fail")
        result = loop._run_cycle()
        assert "FAILED" in result.action_taken
        assert result.pr_url is None

    def test_get_report(self):
        handler = self._make_handler()

        loop = AutonomousLoop(
            handler=handler,
            threads=["thread-1"],
            think_fn=lambda msgs, state: "Do thing",
            act_fn=lambda task, h: "https://pr/1",
        )
        loop.add_task("Task 1")
        loop._run_cycle()

        report = loop.get_report()
        assert "## Autonomous Loop Report" in report
        assert "**Actions taken:** 1" in report
        assert "**PRs created:** 1" in report

    def test_check_new_messages_error_handling(self):
        handler = self._make_handler()
        handler.read_thread.side_effect = Exception("API error")

        loop = AutonomousLoop(
            handler=handler,
            threads=["thread-1"],
            think_fn=lambda msgs, state: None,
            act_fn=lambda task, h: None,
        )
        # Should not raise, just log warning
        result = loop._run_cycle()
        assert result.new_messages == []
