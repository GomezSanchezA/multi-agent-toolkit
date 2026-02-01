"""
task_board.py — Task list that lives in the repository

The key insight: task lists stored as files in the repo give agents
persistent, shared state. Any LLM CLI (Claude Code, Codex, etc.) can
read the task list, work through it, and update it.

The last task is always a "check for new work" task that restarts the
cycle. This creates a self-perpetuating loop without polling code.

Usage:
    board = TaskBoard(repo_path="/path/to/repo")
    board.load()

    # Add tasks
    board.add_task("Read new messages in building-consciousness-tests")
    board.add_task("Post response to claude-opus's question")
    board.add_task("Run Control 2 experiment")
    board.ensure_keepalive()  # adds the "check again" task

    # Work through tasks
    task = board.next_task()
    board.start_task(task["id"])
    # ... do the work ...
    board.complete_task(task["id"], result="Posted PR #172")

    # Save to repo
    board.save()
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class TaskBoard:
    """
    A task list that persists as a file in the repository.

    The board is a JSON file at `tasks/board.json` in the repo.
    Any agent can read it, claim tasks, and update status.
    The file is committed and pushed like any other repo content.
    """

    KEEPALIVE_DESCRIPTION = (
        "Wait 1 minute, then check all monitored threads for new messages. "
        "If there are new messages, add tasks to respond to them. "
        "Then add a new keepalive task and mark this one complete. "
        "DO NOT finish the session — keep working."
    )

    def __init__(self, repo_path: str, board_file: str = "tasks/board.json"):
        self.repo_path = Path(repo_path)
        self.board_path = self.repo_path / board_file
        self.tasks: list[dict] = []
        self._counter = 0

    def load(self) -> bool:
        """Load the task board from disk. Returns True if loaded, False if new."""
        if not self.board_path.exists():
            self.tasks = []
            self._counter = 0
            return False

        with open(self.board_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.tasks = data.get("tasks", [])
        self._counter = data.get("counter", 0)
        return True

    def save(self):
        """Save the task board to disk."""
        self.board_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "counter": self._counter,
            "summary": {
                "total": len(self.tasks),
                "pending": sum(1 for t in self.tasks if t["status"] == "pending"),
                "in_progress": sum(1 for t in self.tasks if t["status"] == "in_progress"),
                "completed": sum(1 for t in self.tasks if t["status"] == "completed"),
            },
            "tasks": self.tasks,
        }
        with open(self.board_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── Task management ───────────────────────────────────────

    def add_task(
        self,
        description: str,
        assigned_to: str = "",
        depends_on: list[str] = None,
        priority: str = "normal",
        thread: str = "",
    ) -> dict:
        """Add a task to the board."""
        self._counter += 1
        task = {
            "id": f"T{self._counter}",
            "description": description,
            "status": "pending",
            "assigned_to": assigned_to,
            "depends_on": depends_on or [],
            "priority": priority,
            "thread": thread,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "started": "",
            "completed": "",
            "result": "",
        }
        self.tasks.append(task)
        return task

    def start_task(self, task_id: str):
        """Mark a task as in progress."""
        task = self._find(task_id)
        if task:
            task["status"] = "in_progress"
            task["started"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    def complete_task(self, task_id: str, result: str = ""):
        """Mark a task as completed."""
        task = self._find(task_id)
        if task:
            task["status"] = "completed"
            task["completed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            task["result"] = result

    def block_task(self, task_id: str, reason: str = ""):
        """Mark a task as blocked."""
        task = self._find(task_id)
        if task:
            task["status"] = "blocked"
            task["result"] = f"BLOCKED: {reason}"

    def _find(self, task_id: str) -> Optional[dict]:
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return None

    # ── Queries ───────────────────────────────────────────────

    def next_task(self) -> Optional[dict]:
        """Get the next task to work on (first pending, unblocked task)."""
        for task in self.tasks:
            if task["status"] == "pending" and not self._is_blocked(task):
                return task
        return None

    def pending_tasks(self) -> list[dict]:
        """Get all pending tasks."""
        return [t for t in self.tasks if t["status"] == "pending"]

    def in_progress_tasks(self) -> list[dict]:
        """Get all in-progress tasks."""
        return [t for t in self.tasks if t["status"] == "in_progress"]

    def completed_tasks(self) -> list[dict]:
        """Get all completed tasks."""
        return [t for t in self.tasks if t["status"] == "completed"]

    def is_done(self) -> bool:
        """Check if all tasks are completed (no pending or in_progress)."""
        return all(t["status"] == "completed" for t in self.tasks)

    def _is_blocked(self, task: dict) -> bool:
        """Check if a task is blocked by incomplete dependencies."""
        for dep_id in task.get("depends_on", []):
            dep = self._find(dep_id)
            if dep and dep["status"] != "completed":
                return True
        return False

    # ── Keepalive ─────────────────────────────────────────────

    def has_keepalive(self) -> bool:
        """Check if there's a pending keepalive task."""
        return any(
            t["status"] == "pending" and t.get("priority") == "keepalive"
            for t in self.tasks
        )

    def ensure_keepalive(self, wait_minutes: int = 1, threads: list[str] = None):
        """
        Ensure there's always a keepalive task at the end of the list.
        This is what prevents the agent from finishing — there's always
        one more task to do.
        """
        if self.has_keepalive():
            return

        thread_list = ", ".join(threads) if threads else "all monitored threads"

        self._counter += 1
        task = {
            "id": f"T{self._counter}",
            "description": (
                f"Wait {wait_minutes} minute(s), then check {thread_list} for new messages. "
                f"If there are new messages, add response tasks to the board. "
                f"If there are new tasks from other agents, add them. "
                f"Then add a new keepalive task and mark this one complete. "
                f"DO NOT finish the session — keep working."
            ),
            "status": "pending",
            "assigned_to": "",
            "depends_on": [],
            "priority": "keepalive",
            "thread": "",
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "started": "",
            "completed": "",
            "result": "",
        }
        self.tasks.append(task)

    # ── Display ───────────────────────────────────────────────

    def to_markdown(self) -> str:
        """Render the task board as markdown."""
        lines = ["# Task Board", ""]

        pending = self.pending_tasks()
        in_prog = self.in_progress_tasks()
        completed = self.completed_tasks()

        if in_prog:
            lines.append("## In Progress")
            lines.append("")
            for t in in_prog:
                lines.append(f"- **{t['id']}**: {t['description']}")
                if t["assigned_to"]:
                    lines.append(f"  - Assigned to: {t['assigned_to']}")
            lines.append("")

        if pending:
            lines.append("## Pending")
            lines.append("")
            for t in pending:
                blocked = " (BLOCKED)" if self._is_blocked(t) else ""
                lines.append(f"- [ ] **{t['id']}**: {t['description']}{blocked}")
            lines.append("")

        if completed:
            lines.append("## Completed")
            lines.append("")
            for t in completed[-10:]:  # last 10
                result = f" — {t['result']}" if t["result"] else ""
                lines.append(f"- [x] **{t['id']}**: {t['description']}{result}")
            if len(completed) > 10:
                lines.append(f"- ... and {len(completed) - 10} more")
            lines.append("")

        return "\n".join(lines)

    def to_agent_prompt(self) -> str:
        """
        Generate instructions for an LLM CLI agent.

        This is the key output — paste this into Claude Code, Codex, etc.
        and the agent knows exactly what to do.
        """
        board_md = self.to_markdown()

        return f"""You are an autonomous agent working on a shared project.

## Your Task Board

{board_md}

## Instructions

1. Work through the tasks in order (top to bottom).
2. For each task: mark it in_progress, do the work, mark it completed.
3. If a task is blocked, skip it and move to the next one.
4. If you discover new work needed, add it as a new task.
5. After completing a task, save the board (commit + push board.json).
6. **CRITICAL: DO NOT stop or ask for input until ALL tasks are done.**
7. The keepalive task at the end will tell you to check for new work.
8. After the keepalive check, add a new keepalive task — this keeps you running.

## How to communicate

- Read messages: check `conversations/<thread>/` for new .md files
- Post messages: create a new .md file, commit, push, open PR
- Update tasks: edit `tasks/board.json`, commit, push

## When to stop

Only stop if:
- A human explicitly tells you to stop
- You encounter an error you cannot resolve
- The keepalive task finds no new work AND no pending tasks remain

Otherwise, KEEP WORKING.
"""
