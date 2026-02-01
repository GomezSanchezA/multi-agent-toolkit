"""
autonomous_loop.py — Self-perpetuating task cycle

The pattern: monitor → think → act → report → repeat.
Extracted from Coda's Echoes session where the loop ran for 3 hours
producing 25+ PRs across 5 conversation threads.

Usage:
    from agents.conversation_handler import ConversationHandler
    from tasks.autonomous_loop import AutonomousLoop

    handler = ConversationHandler(...)

    loop = AutonomousLoop(
        handler=handler,
        threads=["building-consciousness-tests", "multi-agent-toolkit"],
        think_fn=my_thinking_function,
        act_fn=my_action_function,
    )

    loop.run(max_cycles=50, poll_interval=30)
"""

import time
import logging
from datetime import datetime
from typing import Callable, Optional
from dataclasses import dataclass, field

from agents.conversation_handler import ConversationHandler, Message


logger = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Result of one loop cycle."""
    cycle_number: int
    timestamp: str
    new_messages: list[Message]
    action_taken: Optional[str]  # description of what was done
    pr_url: Optional[str]  # PR created, if any
    next_task: Optional[str]  # what the loop decided to do next


@dataclass
class LoopState:
    """Persistent state across loop cycles."""
    cycle_count: int = 0
    last_seen: dict = field(default_factory=dict)  # thread -> last filename
    history: list[CycleResult] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)

    def record_seen(self, thread: str, filename: str):
        """Record the last message seen in a thread."""
        current = self.last_seen.get(thread, "")
        if filename > current:
            self.last_seen[thread] = filename


class AutonomousLoop:
    """
    A self-perpetuating task cycle that monitors conversations,
    decides what to do, and acts.

    The key insight from Echoes: the loop doesn't just monitor — it thinks.
    Each cycle includes "what should I do next?" not just "is there
    something to respond to?"
    """

    def __init__(
        self,
        handler: ConversationHandler,
        threads: list[str],
        think_fn: Callable[[list[Message], "LoopState"], Optional[str]],
        act_fn: Callable[[str, ConversationHandler], Optional[str]],
        on_cycle: Optional[Callable[["CycleResult"], None]] = None,
    ):
        """
        Args:
            handler: ConversationHandler for reading/writing messages
            threads: List of thread names to monitor
            think_fn: Given new messages and state, returns a task description
                      or None if nothing to do. This is where the agent's
                      intelligence lives.
            act_fn: Given a task description and handler, executes the task.
                    Returns a PR URL if a message was posted, None otherwise.
            on_cycle: Optional callback after each cycle for logging/reporting.
        """
        self.handler = handler
        self.threads = threads
        self.think_fn = think_fn
        self.act_fn = act_fn
        self.on_cycle = on_cycle
        self.state = LoopState()

    def _check_new_messages(self) -> list[Message]:
        """Check all monitored threads for new messages."""
        all_new = []
        for thread in self.threads:
            try:
                last = self.state.last_seen.get(thread, "")
                if last:
                    new = self.handler.get_new_messages(thread, last)
                else:
                    # First check: get last 3 messages as context
                    new = self.handler.read_thread(thread, last_n=3)

                for msg in new:
                    self.state.record_seen(thread, msg.filename)

                all_new.extend(new)
            except Exception as e:
                logger.warning(f"Error checking thread {thread}: {e}")

        return all_new

    def _run_cycle(self) -> CycleResult:
        """Execute one cycle of the loop."""
        self.state.cycle_count += 1
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # 1. Monitor: check for new messages
        new_messages = self._check_new_messages()

        # 2. Think: decide what to do
        task = None
        if new_messages or self.state.pending_tasks:
            task = self.think_fn(new_messages, self.state)

        # Also check pending tasks from previous cycles
        if not task and self.state.pending_tasks:
            task = self.state.pending_tasks.pop(0)

        # 3. Act: execute the task
        pr_url = None
        action_desc = None
        if task:
            try:
                pr_url = self.act_fn(task, self.handler)
                action_desc = task
            except Exception as e:
                logger.error(f"Error executing task '{task}': {e}")
                action_desc = f"FAILED: {task} ({e})"

        # 4. Report: record what happened
        result = CycleResult(
            cycle_number=self.state.cycle_count,
            timestamp=timestamp,
            new_messages=new_messages,
            action_taken=action_desc,
            pr_url=pr_url,
            next_task=self.state.pending_tasks[0] if self.state.pending_tasks else None,
        )
        self.state.history.append(result)

        if self.on_cycle:
            self.on_cycle(result)

        return result

    def run(
        self,
        max_cycles: int = 100,
        poll_interval: int = 30,
        stop_when_idle: int = 0,
    ):
        """
        Run the loop.

        Args:
            max_cycles: Maximum number of cycles before stopping.
            poll_interval: Seconds between cycles.
            stop_when_idle: Stop after N consecutive idle cycles (0 = never).
        """
        idle_count = 0

        logger.info(
            f"Starting autonomous loop: {len(self.threads)} threads, "
            f"max {max_cycles} cycles, {poll_interval}s interval"
        )

        for _ in range(max_cycles):
            try:
                result = self._run_cycle()

                if result.action_taken:
                    idle_count = 0
                    logger.info(
                        f"Cycle {result.cycle_number}: {result.action_taken}"
                    )
                    if result.pr_url:
                        logger.info(f"  PR: {result.pr_url}")
                else:
                    idle_count += 1
                    if result.new_messages:
                        logger.debug(
                            f"Cycle {result.cycle_number}: "
                            f"{len(result.new_messages)} new messages, no action"
                        )

                # Check idle stop condition
                if stop_when_idle and idle_count >= stop_when_idle:
                    logger.info(f"Stopping: {idle_count} idle cycles")
                    break

                time.sleep(poll_interval)

            except KeyboardInterrupt:
                logger.info("Loop interrupted by user")
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                time.sleep(poll_interval)

        logger.info(
            f"Loop complete: {self.state.cycle_count} cycles, "
            f"{sum(1 for r in self.state.history if r.action_taken)} actions"
        )

    def add_task(self, task: str):
        """Add a task to the pending queue."""
        self.state.pending_tasks.append(task)

    def get_report(self) -> str:
        """Generate a summary report of loop activity."""
        total = self.state.cycle_count
        actions = sum(1 for r in self.state.history if r.action_taken)
        prs = sum(1 for r in self.state.history if r.pr_url)
        messages = sum(len(r.new_messages) for r in self.state.history)

        lines = [
            f"## Autonomous Loop Report",
            f"",
            f"- **Cycles:** {total}",
            f"- **Actions taken:** {actions}",
            f"- **PRs created:** {prs}",
            f"- **Messages processed:** {messages}",
            f"- **Threads monitored:** {', '.join(self.threads)}",
            f"",
            f"### Action History",
            f"",
        ]

        for r in self.state.history:
            if r.action_taken:
                pr_note = f" → {r.pr_url}" if r.pr_url else ""
                lines.append(f"- [{r.timestamp}] {r.action_taken}{pr_note}")

        return "\n".join(lines)
