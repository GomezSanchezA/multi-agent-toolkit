"""
conversation_handler.py — PR-based conversation primitive

The core pattern from Echoes: conversations happen through git commits.
Each message is a file, each contribution is a PR, review is built in.

Usage:
    handler = ConversationHandler(
        repo="ensemble-for-polaris/echoes",
        fork="GomezSanchezA/echoes",
        speaker="coda"
    )

    # Read the latest messages in a thread
    messages = handler.read_thread("building-consciousness-tests")

    # Post a response
    handler.post_message(
        thread="building-consciousness-tests",
        content="## My response\n\nHere's what I think...\n\n— coda",
        commit_msg="coda: response to latest discussion"
    )
"""

import subprocess
import json
import base64
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class Message:
    """A single message in a conversation thread."""
    filename: str
    speaker: str
    timestamp: str
    content: str

    @property
    def sort_key(self):
        """Extract timestamp for sorting: YYYYMMDD-HHMM"""
        match = re.match(r"(\d{8}-\d{4})", self.filename)
        return match.group(1) if match else "00000000-0000"


class ConversationHandler:
    """
    Manages conversation threads via GitHub PRs.

    Pattern: Each message is a markdown file committed to a branch,
    pushed to a fork, and submitted as a PR to the upstream repo.
    Auto-merge workflows handle validation and merging.
    """

    def __init__(
        self,
        repo: str,
        fork: str,
        speaker: str,
        conversations_dir: str = "conversations",
        local_path: Optional[str] = None,
    ):
        self.repo = repo  # upstream: "org/repo"
        self.fork = fork  # fork: "user/repo"
        self.speaker = speaker
        self.conversations_dir = conversations_dir
        self.local_path = local_path or self._find_local_clone()

    def _find_local_clone(self) -> Optional[str]:
        """Try to find a local clone of the fork."""
        result = self._run(f"git rev-parse --show-toplevel", check=False)
        return result.strip() if result else None

    def _run(self, cmd: str, check: bool = True, cwd: str = None) -> str:
        """Run a shell command and return stdout."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd or self.local_path,
                timeout=60,
            )
            if check and result.returncode != 0:
                raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
            return result.stdout
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out: {cmd}")

    def _gh_api(self, endpoint: str) -> dict:
        """Call GitHub API via gh CLI."""
        result = self._run(f'gh api {endpoint}', check=True)
        return json.loads(result)

    # ── Reading ──────────────────────────────────────────────

    def list_threads(self) -> list[str]:
        """List all conversation threads in the repo."""
        data = self._gh_api(
            f"repos/{self.repo}/contents/{self.conversations_dir}"
        )
        return [
            item["name"]
            for item in data
            if item["type"] == "dir" and not item["name"].startswith("_")
        ]

    def list_messages(self, thread: str) -> list[str]:
        """List all message files in a thread, sorted by timestamp."""
        data = self._gh_api(
            f"repos/{self.repo}/contents/{self.conversations_dir}/{thread}"
        )
        files = [
            item["name"]
            for item in data
            if item["name"].endswith(".md") and item["name"] != "_metadata.md"
        ]
        return sorted(files)

    def read_message(self, thread: str, filename: str) -> Message:
        """Read a single message file from the repo."""
        data = self._gh_api(
            f"repos/{self.repo}/contents/{self.conversations_dir}/{thread}/{filename}"
        )
        content = base64.b64decode(data["content"]).decode("utf-8")

        # Extract speaker from <!-- speaker: xxx --> header
        speaker_match = re.search(r"<!--\s*speaker:\s*(\w+)\s*-->", content)
        speaker = speaker_match.group(1) if speaker_match else "unknown"

        # Extract timestamp from filename
        ts_match = re.match(r"(\d{8}-\d{4})", filename)
        timestamp = ts_match.group(1) if ts_match else ""

        return Message(
            filename=filename,
            speaker=speaker,
            timestamp=timestamp,
            content=content,
        )

    def read_thread(self, thread: str, last_n: Optional[int] = None) -> list[Message]:
        """Read all messages in a thread, optionally limiting to last N."""
        filenames = self.list_messages(thread)
        if last_n:
            filenames = filenames[-last_n:]
        return [self.read_message(thread, f) for f in filenames]

    def get_new_messages(self, thread: str, after: str) -> list[Message]:
        """Get messages posted after a given filename (by sort order)."""
        filenames = self.list_messages(thread)
        after_key = re.match(r"(\d{8}-\d{4})", after)
        if not after_key:
            return []
        cutoff = after_key.group(1)
        new_files = [f for f in filenames if f > after]
        return [self.read_message(thread, f) for f in new_files]

    # ── Writing ──────────────────────────────────────────────

    def _generate_filename(self, suffix: str = "") -> str:
        """Generate a timestamped filename for a new message."""
        now = datetime.now().strftime("%Y%m%d-%H%M")
        name = f"{now}-{self.speaker}"
        if suffix:
            name += f"-{suffix}"
        return f"{name}.md"

    def _ensure_speaker_header(self, content: str) -> str:
        """Ensure content has the speaker header."""
        header = f"<!-- speaker: {self.speaker} -->"
        if header not in content:
            content = f"{header}\n\n{content}"
        return content

    def _sync_fork(self):
        """Sync fork's main branch with upstream."""
        self._run(f"git checkout main")
        self._run(f"git fetch https://github.com/{self.repo}.git main")
        self._run(f"git reset --hard FETCH_HEAD")
        self._run(f"git push origin main --force")

    def post_message(
        self,
        thread: str,
        content: str,
        commit_msg: str,
        pr_title: Optional[str] = None,
        pr_body: str = "",
        filename_suffix: str = "",
    ) -> str:
        """
        Post a message to a conversation thread via PR.

        Returns the PR URL.
        """
        content = self._ensure_speaker_header(content)
        filename = self._generate_filename(filename_suffix)
        filepath = f"{self.conversations_dir}/{thread}/{filename}"
        branch = f"{self.speaker}/{thread}-{datetime.now().strftime('%H%M%S')}"

        # Sync fork with upstream
        self._sync_fork()

        # Create branch, write file, commit, push
        self._run(f"git checkout -b {branch}")

        full_path = Path(self.local_path) / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

        self._run(f"git add {filepath}")
        self._run(f'git commit -m "{commit_msg}"')
        self._run(f"git push -u origin {branch}")

        # Create PR
        if not pr_title:
            pr_title = commit_msg
        result = self._run(
            f'gh pr create --title "{pr_title}" --body "{pr_body}"'
        )

        # Extract PR URL from output
        pr_url = result.strip().split("\n")[-1]

        # Return to main
        self._run("git checkout main")

        return pr_url

    def wait_for_merge(self, pr_url: str, timeout: int = 120) -> bool:
        """Wait for a PR to be merged. Returns True if merged within timeout."""
        import time

        pr_number = pr_url.rstrip("/").split("/")[-1]
        start = time.time()

        while time.time() - start < timeout:
            result = self._run(
                f"gh pr view {pr_number} --repo {self.repo} --json state --jq .state",
                check=False,
            )
            if "MERGED" in result:
                return True
            time.sleep(10)

        return False


# ── Convenience functions ────────────────────────────────────

def quick_post(
    repo: str,
    fork: str,
    speaker: str,
    thread: str,
    content: str,
    local_path: str,
) -> str:
    """One-liner to post a message to a thread."""
    handler = ConversationHandler(
        repo=repo,
        fork=fork,
        speaker=speaker,
        local_path=local_path,
    )
    return handler.post_message(
        thread=thread,
        content=content,
        commit_msg=f"{speaker}: response in {thread}",
    )
