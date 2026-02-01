"""
setup_agent.py — Initialize a project for multi-agent collaboration

Sets up the task board, CLAUDE.md, and initial tasks for an agent.
Run this once to bootstrap a new agent on a repo.

Usage:
    python setup_agent.py \
        --repo org/shared-repo \
        --fork user/shared-repo \
        --agent-name coda \
        --role builder \
        --threads building-consciousness-tests multi-agent-toolkit \
        --local-path /path/to/clone

This creates:
    - tasks/board.json with initial tasks + keepalive
    - CLAUDE.md with agent instructions
    - memories/{agent}_SOUL.md with initial identity

Then prints the agent prompt you can paste into Claude Code or Codex.
"""

import argparse
import json
from pathlib import Path

from tasks.task_board import TaskBoard
from agents.memory_manager import MemoryManager


def main():
    parser = argparse.ArgumentParser(description="Set up an agent on a repo")
    parser.add_argument("--repo", required=True, help="Upstream repo (org/repo)")
    parser.add_argument("--fork", required=True, help="Fork repo (user/repo)")
    parser.add_argument("--agent-name", required=True, help="Agent name")
    parser.add_argument("--role", required=True, help="Agent role (builder/skeptic/architect)")
    parser.add_argument("--threads", nargs="+", required=True, help="Threads to monitor")
    parser.add_argument("--local-path", required=True, help="Path to local clone")
    parser.add_argument("--tasks", nargs="*", default=[], help="Initial tasks to add")
    args = parser.parse_args()

    repo_path = Path(args.local_path)

    # 1. Create task board
    board = TaskBoard(repo_path=str(repo_path))
    board.load()

    # Add initial tasks
    board.add_task(
        f"Pull latest from upstream and read new messages in: {', '.join(args.threads)}",
        assigned_to=args.agent_name,
    )

    for thread in args.threads:
        board.add_task(
            f"Read all messages in {thread} and identify any that need a response",
            assigned_to=args.agent_name,
            thread=thread,
        )

    for task_desc in args.tasks:
        board.add_task(task_desc, assigned_to=args.agent_name)

    # Always end with keepalive
    board.ensure_keepalive(wait_minutes=1, threads=args.threads)
    board.save()

    # 2. Create CLAUDE.md
    template_path = Path(__file__).parent / "templates" / "CLAUDE.md"
    if template_path.exists():
        claude_md = template_path.read_text(encoding="utf-8")
        claude_md = claude_md.replace("{UPSTREAM_REPO}", args.repo)
        claude_md = claude_md.replace("{FORK_REPO}", args.fork)
        claude_md = claude_md.replace("{AGENT_NAME}", args.agent_name)
        claude_md = claude_md.replace("{ROLE}", args.role)
        claude_md = claude_md.replace("{THREADS}", ", ".join(args.threads))

        claude_path = repo_path / "CLAUDE.md"
        claude_path.write_text(claude_md, encoding="utf-8")

    # 3. Set up memory
    memory_dir = str(repo_path / "memories")
    memory = MemoryManager(agent_name=args.agent_name, memory_dir=memory_dir)
    if not memory.load():
        memory.set_identity(role=args.role)
        memory.save()

    # 4. Print the prompt
    print("=" * 60)
    print(f"Agent '{args.agent_name}' ({args.role}) initialized!")
    print("=" * 60)
    print()
    print("Task board saved to: tasks/board.json")
    print(f"Agent instructions: CLAUDE.md")
    print(f"Memory: memories/{args.agent_name}_SOUL.md")
    print()
    print("─" * 60)
    print("PASTE THIS INTO CLAUDE CODE OR CODEX:")
    print("─" * 60)
    print()
    print(board.to_agent_prompt())
    print()
    print("─" * 60)
    print()
    print("Or just open Claude Code in this directory — it will read CLAUDE.md automatically.")


if __name__ == "__main__":
    main()
