"""
research_team.py — A working example of a multi-agent research team

Demonstrates all toolkit modules working together:
- ConversationHandler for PR-based communication
- AutonomousLoop for self-perpetuating work
- PeerReviewer for quality control
- MemoryManager for persistent state
- AgentCoordinator for task assignment

This example sets up a 3-agent research team:
- Builder: executes experiments, writes code, produces results
- Skeptic: reviews claims, checks methodology, proposes controls
- Architect: designs protocols, tracks progress, maintains roadmap

Usage:
    python examples/research_team.py \
        --repo org/shared-repo \
        --fork user/shared-repo \
        --local-path /path/to/clone \
        --agent-name coda \
        --role builder
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.conversation_handler import ConversationHandler, Message
from agents.memory_manager import MemoryManager
from agents.agent_coordinator import AgentCoordinator
from tasks.autonomous_loop import AutonomousLoop, LoopState
from quality.peer_review import PeerReviewer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("research_team")


# ── Role-specific thinking functions ─────────────────────────

def builder_think(new_messages: list[Message], state: LoopState) -> str | None:
    """Builder agent: look for tasks to execute, experiments to run."""
    if not new_messages:
        return None

    for msg in new_messages:
        content = msg.content.lower()

        # Look for experiment requests
        if "run" in content and ("test" in content or "experiment" in content):
            return f"Execute experiment requested in {msg.filename}"

        # Look for action items assigned to builder
        if "builder" in content or "coda" in content:
            if "todo" in content or "action" in content or "task" in content:
                return f"Handle action item from {msg.filename}"

    # Look for unanswered questions
    for msg in new_messages:
        if "?" in msg.content and msg.speaker != "coda":
            return f"Respond to question from {msg.speaker} in {msg.filename}"

    return None


def skeptic_think(new_messages: list[Message], state: LoopState) -> str | None:
    """Skeptic agent: look for claims to review, methodology to check."""
    if not new_messages:
        return None

    reviewer = PeerReviewer()

    for msg in new_messages:
        # Don't review own messages
        if msg.speaker == "claude-opus":
            continue

        result = reviewer.review(msg.content)
        if result.overall_verdict.value in ("reject", "revise"):
            return f"Review needed: {msg.filename} — {result.summary[:100]}"

    return None


def architect_think(new_messages: list[Message], state: LoopState) -> str | None:
    """Architect agent: track progress, identify gaps, maintain roadmap."""
    if not new_messages:
        return None

    # If many new messages, summarize progress
    if len(new_messages) >= 5:
        return "Summarize recent progress and update roadmap"

    # Look for coordination needs
    speakers = set(msg.speaker for msg in new_messages)
    if len(speakers) >= 3:
        return "Multiple agents active — check for conflicts and align priorities"

    return None


# ── Role-specific action functions ───────────────────────────

def builder_act(task: str, handler: ConversationHandler) -> str | None:
    """Builder executes tasks and posts results."""
    content = f"## Task Execution\n\n**Task:** {task}\n\n"
    content += "Working on this now. Results to follow.\n\n"
    content += f"— {handler.speaker}"

    try:
        pr_url = handler.post_message(
            thread="research-discussion",
            content=content,
            commit_msg=f"{handler.speaker}: executing — {task[:50]}",
        )
        return pr_url
    except Exception as e:
        logger.error(f"Failed to post: {e}")
        return None


def skeptic_act(task: str, handler: ConversationHandler) -> str | None:
    """Skeptic posts review."""
    content = f"## Review\n\n{task}\n\n"
    content += f"— {handler.speaker}"

    try:
        pr_url = handler.post_message(
            thread="research-discussion",
            content=content,
            commit_msg=f"{handler.speaker}: review — {task[:50]}",
        )
        return pr_url
    except Exception as e:
        logger.error(f"Failed to post: {e}")
        return None


def architect_act(task: str, handler: ConversationHandler) -> str | None:
    """Architect posts coordination updates."""
    content = f"## Coordination Update\n\n{task}\n\n"
    content += f"— {handler.speaker}"

    try:
        pr_url = handler.post_message(
            thread="research-discussion",
            content=content,
            commit_msg=f"{handler.speaker}: coordination — {task[:50]}",
        )
        return pr_url
    except Exception as e:
        logger.error(f"Failed to post: {e}")
        return None


# ── Role registry ────────────────────────────────────────────

ROLES = {
    "builder": {
        "think_fn": builder_think,
        "act_fn": builder_act,
        "capabilities": ["test_execution", "framework_drafting", "coding"],
    },
    "skeptic": {
        "think_fn": skeptic_think,
        "act_fn": skeptic_act,
        "capabilities": ["critique", "protocol_design", "negative_controls"],
    },
    "architect": {
        "think_fn": architect_think,
        "act_fn": architect_act,
        "capabilities": ["framework_design", "integration", "roadmap"],
    },
}


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run a research team agent")
    parser.add_argument("--repo", required=True, help="Upstream repo (org/repo)")
    parser.add_argument("--fork", required=True, help="Fork repo (user/repo)")
    parser.add_argument("--local-path", required=True, help="Path to local clone")
    parser.add_argument("--agent-name", required=True, help="Agent name")
    parser.add_argument("--role", required=True, choices=ROLES.keys(), help="Agent role")
    parser.add_argument("--threads", nargs="+", default=["research-discussion"], help="Threads to monitor")
    parser.add_argument("--max-cycles", type=int, default=50, help="Max loop cycles")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between cycles")
    parser.add_argument("--memory-dir", default="./memories", help="Directory for agent memory")
    args = parser.parse_args()

    role_config = ROLES[args.role]

    # Set up conversation handler
    handler = ConversationHandler(
        repo=args.repo,
        fork=args.fork,
        speaker=args.agent_name,
        local_path=args.local_path,
    )

    # Set up memory
    memory = MemoryManager(
        agent_name=args.agent_name,
        memory_dir=args.memory_dir,
    )
    loaded = memory.load()
    if not loaded:
        memory.set_identity(
            role=args.role,
            commitments=[
                "Apply parity constraint to all claims",
                "Separate generation from evaluation",
                "Document blind spots honestly",
            ],
        )
        logger.info(f"New agent: {args.agent_name} ({args.role})")
    else:
        logger.info(f"Resumed agent: {args.agent_name} ({args.role})")
        context = memory.get_context()
        logger.info(f"Context:\n{context}")

    # Set up loop with cycle callback for memory
    def on_cycle(result):
        if result.action_taken:
            memory.add_session_entry(
                actions=[result.action_taken],
                prs_created=[result.pr_url] if result.pr_url else [],
            )
            memory.save()

    loop = AutonomousLoop(
        handler=handler,
        threads=args.threads,
        think_fn=role_config["think_fn"],
        act_fn=role_config["act_fn"],
        on_cycle=on_cycle,
    )

    # Run
    logger.info(
        f"Starting {args.agent_name} ({args.role}) on {args.threads}"
    )
    try:
        loop.run(
            max_cycles=args.max_cycles,
            poll_interval=args.poll_interval,
            stop_when_idle=10,
        )
    finally:
        # Save final memory and report
        report = loop.get_report()
        memory.add_session_entry(
            actions=["Session complete"],
            findings=[f"{loop.state.cycle_count} cycles run"],
            next_steps=list(loop.state.pending_tasks),
        )
        memory.save()
        logger.info(f"\n{report}")


if __name__ == "__main__":
    main()
