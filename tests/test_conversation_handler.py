"""Tests for agents/conversation_handler.py"""

import pytest
from agents.conversation_handler import Message


# ── Message dataclass ───────────────────────────────────────

class TestMessage:
    def test_sort_key_from_filename(self):
        msg = Message(
            filename="20260201-2030-coda.md",
            speaker="coda",
            timestamp="20260201-2030",
            content="Hello",
        )
        assert msg.sort_key == "20260201-2030"

    def test_sort_key_with_suffix(self):
        msg = Message(
            filename="20260201-2030-coda-session-report.md",
            speaker="coda",
            timestamp="20260201-2030",
            content="Report",
        )
        assert msg.sort_key == "20260201-2030"

    def test_sort_key_fallback(self):
        msg = Message(
            filename="README.md",
            speaker="unknown",
            timestamp="",
            content="",
        )
        assert msg.sort_key == "00000000-0000"

    def test_messages_sort_chronologically(self):
        msgs = [
            Message("20260201-2200-opus.md", "opus", "20260201-2200", ""),
            Message("20260201-2000-coda.md", "coda", "20260201-2000", ""),
            Message("20260201-2100-polaris.md", "polaris", "20260201-2100", ""),
        ]
        sorted_msgs = sorted(msgs, key=lambda m: m.sort_key)
        assert sorted_msgs[0].speaker == "coda"
        assert sorted_msgs[1].speaker == "polaris"
        assert sorted_msgs[2].speaker == "opus"

    def test_message_fields(self):
        msg = Message(
            filename="20260201-2030-coda.md",
            speaker="coda",
            timestamp="20260201-2030",
            content="## My Message\n\nContent here.",
        )
        assert msg.filename == "20260201-2030-coda.md"
        assert msg.speaker == "coda"
        assert "Content here" in msg.content


# Note: ConversationHandler methods require git/gh CLI and a real repo.
# Integration tests would need a test repo or extensive mocking.
# The unit tests here cover the Message dataclass and its sort_key logic.
# For ConversationHandler, see examples/research_team.py for usage patterns.
