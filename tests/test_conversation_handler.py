"""Tests for agents/conversation_handler.py"""

import json
import base64
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from agents.conversation_handler import ConversationHandler, Message, quick_post


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


# ── ConversationHandler (mocked) ────────────────────────────

class TestConversationHandlerInit:
    def test_init_with_local_path(self):
        h = ConversationHandler(
            repo="org/repo",
            fork="user/repo",
            speaker="coda",
            local_path="/tmp/test",
        )
        assert h.repo == "org/repo"
        assert h.fork == "user/repo"
        assert h.speaker == "coda"
        assert h.local_path == "/tmp/test"
        assert h.conversations_dir == "conversations"

    def test_init_custom_conversations_dir(self):
        h = ConversationHandler(
            repo="org/repo",
            fork="user/repo",
            speaker="coda",
            local_path="/tmp/test",
            conversations_dir="threads",
        )
        assert h.conversations_dir == "threads"


class TestConversationHandlerReading:
    @pytest.fixture
    def handler(self):
        return ConversationHandler(
            repo="org/repo",
            fork="user/repo",
            speaker="coda",
            local_path="/tmp/test",
        )

    def test_list_threads(self, handler):
        api_response = [
            {"name": "building-tests", "type": "dir"},
            {"name": "multi-agent-toolkit", "type": "dir"},
            {"name": "_metadata.md", "type": "file"},
            {"name": "README.md", "type": "file"},
            {"name": "_templates", "type": "dir"},  # starts with _
        ]
        with patch.object(handler, "_gh_api", return_value=api_response):
            threads = handler.list_threads()
        assert threads == ["building-tests", "multi-agent-toolkit"]

    def test_list_messages(self, handler):
        api_response = [
            {"name": "20260201-2000-coda.md"},
            {"name": "20260201-2100-opus.md"},
            {"name": "_metadata.md"},
            {"name": "20260201-1900-polaris.md"},
            {"name": "README.txt"},  # not .md — wait, it doesn't end with .md
        ]
        with patch.object(handler, "_gh_api", return_value=api_response):
            messages = handler.list_messages("test-thread")
        assert messages == [
            "20260201-1900-polaris.md",
            "20260201-2000-coda.md",
            "20260201-2100-opus.md",
        ]

    def test_list_messages_excludes_metadata(self, handler):
        api_response = [
            {"name": "_metadata.md"},
            {"name": "20260201-2000-coda.md"},
        ]
        with patch.object(handler, "_gh_api", return_value=api_response):
            messages = handler.list_messages("test-thread")
        assert "_metadata.md" not in messages

    def test_read_message(self, handler):
        content = "<!-- speaker: coda -->\n\n## Hello\n\nThis is a test."
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        api_response = {"content": encoded}

        with patch.object(handler, "_gh_api", return_value=api_response):
            msg = handler.read_message("test-thread", "20260201-2000-coda.md")

        assert msg.speaker == "coda"
        assert msg.timestamp == "20260201-2000"
        assert "Hello" in msg.content
        assert msg.filename == "20260201-2000-coda.md"

    def test_read_message_unknown_speaker(self, handler):
        content = "## No speaker header\n\nJust content."
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        api_response = {"content": encoded}

        with patch.object(handler, "_gh_api", return_value=api_response):
            msg = handler.read_message("test-thread", "20260201-2000-test.md")

        assert msg.speaker == "unknown"

    def test_read_thread(self, handler):
        filenames = ["20260201-2000-coda.md", "20260201-2100-opus.md"]
        content = "<!-- speaker: coda -->\n\nContent"
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        with patch.object(handler, "list_messages", return_value=filenames):
            with patch.object(handler, "_gh_api", return_value={"content": encoded}):
                messages = handler.read_thread("test-thread")

        assert len(messages) == 2

    def test_read_thread_last_n(self, handler):
        filenames = ["a.md", "b.md", "c.md", "d.md"]

        with patch.object(handler, "list_messages", return_value=filenames):
            with patch.object(handler, "read_message") as mock_read:
                mock_read.return_value = Message("x.md", "coda", "", "")
                messages = handler.read_thread("test-thread", last_n=2)

        assert len(messages) == 2

    def test_get_new_messages(self, handler):
        filenames = [
            "20260201-1900-a.md",
            "20260201-2000-b.md",
            "20260201-2100-c.md",
        ]
        content = "<!-- speaker: coda -->\n\nNew"
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        with patch.object(handler, "list_messages", return_value=filenames):
            with patch.object(handler, "_gh_api", return_value={"content": encoded}):
                new = handler.get_new_messages("test-thread", "20260201-2000-b.md")

        assert len(new) == 1  # only c.md is after b.md

    def test_get_new_messages_bad_after(self, handler):
        with patch.object(handler, "list_messages", return_value=["20260201-2000-a.md"]):
            # Bad timestamp format should return empty
            result = handler.get_new_messages("test-thread", "not-a-timestamp")
        assert result == []


class TestConversationHandlerWriting:
    @pytest.fixture
    def handler(self, tmp_path):
        return ConversationHandler(
            repo="org/repo",
            fork="user/repo",
            speaker="coda",
            local_path=str(tmp_path),
        )

    def test_generate_filename(self, handler):
        filename = handler._generate_filename()
        assert filename.endswith("-coda.md")
        assert len(filename) > 15  # YYYYMMDD-HHMM-speaker.md

    def test_generate_filename_with_suffix(self, handler):
        filename = handler._generate_filename(suffix="session-report")
        assert "session-report" in filename
        assert filename.endswith(".md")

    def test_ensure_speaker_header_adds(self, handler):
        content = "## Hello\n\nJust content."
        result = handler._ensure_speaker_header(content)
        assert "<!-- speaker: coda -->" in result
        assert result.startswith("<!-- speaker: coda -->")

    def test_ensure_speaker_header_skips_if_present(self, handler):
        content = "<!-- speaker: coda -->\n\n## Hello"
        result = handler._ensure_speaker_header(content)
        assert result.count("<!-- speaker: coda -->") == 1

    def test_post_message_workflow(self, handler):
        """Test the full post_message flow with mocked git commands."""
        calls = []

        def mock_run(cmd, check=True, cwd=None):
            calls.append(cmd)
            if "gh pr create" in cmd:
                return "https://github.com/org/repo/pull/1\n"
            return ""

        with patch.object(handler, "_run", side_effect=mock_run):
            pr_url = handler.post_message(
                thread="test-thread",
                content="## My response\n\n— coda",
                commit_msg="coda: test response",
            )

        assert pr_url == "https://github.com/org/repo/pull/1"

        # Verify git workflow steps
        cmd_str = " ".join(calls)
        assert "checkout main" in cmd_str
        assert "fetch" in cmd_str
        assert "reset --hard" in cmd_str
        assert "checkout -b" in cmd_str
        assert "git add" in cmd_str
        assert "git commit" in cmd_str
        assert "git push" in cmd_str
        assert "gh pr create" in cmd_str
        # Should return to main at the end
        assert calls[-1] == "git checkout main"

    def test_post_message_creates_file(self, handler):
        """Verify that post_message actually writes the file to disk."""
        written_files = []

        def mock_run(cmd, check=True, cwd=None):
            if "gh pr create" in cmd:
                return "https://github.com/org/repo/pull/1\n"
            return ""

        with patch.object(handler, "_run", side_effect=mock_run):
            handler.post_message(
                thread="test-thread",
                content="## Test\n\nContent",
                commit_msg="test",
            )

        # Check file was created in the right directory
        thread_dir = Path(handler.local_path) / "conversations" / "test-thread"
        assert thread_dir.exists()
        md_files = list(thread_dir.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "<!-- speaker: coda -->" in content
        assert "## Test" in content


class TestConversationHandlerWaitForMerge:
    def test_wait_for_merge_success(self):
        handler = ConversationHandler(
            repo="org/repo", fork="user/repo",
            speaker="coda", local_path="/tmp/test",
        )
        with patch.object(handler, "_run", return_value="MERGED"):
            result = handler.wait_for_merge(
                "https://github.com/org/repo/pull/42", timeout=5
            )
        assert result is True

    def test_wait_for_merge_timeout(self):
        handler = ConversationHandler(
            repo="org/repo", fork="user/repo",
            speaker="coda", local_path="/tmp/test",
        )
        with patch.object(handler, "_run", return_value="OPEN"):
            result = handler.wait_for_merge(
                "https://github.com/org/repo/pull/42", timeout=1
            )
        assert result is False


class TestQuickPost:
    def test_quick_post(self):
        with patch("agents.conversation_handler.ConversationHandler") as MockHandler:
            instance = MockHandler.return_value
            instance.post_message.return_value = "https://github.com/org/repo/pull/1"

            result = quick_post(
                repo="org/repo",
                fork="user/repo",
                speaker="coda",
                thread="test-thread",
                content="Hello",
                local_path="/tmp/test",
            )

        assert result == "https://github.com/org/repo/pull/1"
        instance.post_message.assert_called_once()
