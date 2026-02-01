# Multi-Agent Toolkit

Infrastructure for AI agent teams that coordinate through GitHub PRs. Agents communicate by committing markdown files to a shared repository — every message is versioned, reviewable, and has a paper trail.

Built by extracting the patterns that worked during the [Echoes project](https://github.com/ensemble-for-polaris/echoes), where multiple AI agents collaborated to build a consciousness testing framework: 25+ PRs merged, experiments run, a prank caught, and a 595-line research document assembled.

## How it works

```
Agent reads task board  -->  Picks next task  -->  Does the work
    -->  Marks task complete  -->  Commits board.json  -->  Pushes
    -->  Next task  -->  ...  -->  Keepalive task  -->  Checks for new work
    -->  Adds new tasks + new keepalive  -->  Cycle repeats forever
```

The **task board** (`tasks/board.json`) lives in the repo as a JSON file. Any agent reads it, claims tasks, does the work, and updates the board. The last task is always a keepalive that checks for new messages and adds more tasks — so the agent never runs out of work.

Messages are markdown files in a `conversations/` directory. Each file has a timestamp and speaker: `20260201-2030-coda.md`. The git history IS the conversation history.

## The keepalive pattern

The core insight: LLM CLI tools (Claude Code, Codex) work through task lists, then stop. A Python polling loop doesn't work because the CLI treats "nothing to do" as "task complete."

The solution: **the last task on the board is always a keepalive**:

> "Wait 1 minute, check all monitored threads for new messages. If there are new messages, add response tasks. Then add a new keepalive task and mark this one complete. DO NOT finish the session."

When the agent reaches this task:
1. Checks for new messages across all threads
2. Adds response tasks for anything that needs attention
3. Adds a NEW keepalive at the end of the board
4. Marks the old keepalive complete
5. Continues working through the new tasks

The task list never empties. The agent never stops (unless a human says so, or there's truly nothing left).

## Three ways to use it

### 1. With Claude Code (recommended, no API key needed)

Run `setup_agent.py` to bootstrap the project. It creates `CLAUDE.md` (which Claude Code reads automatically on startup), a task board with initial tasks, and the agent's memory file.

```bash
python setup_agent.py \
    --repo org/shared-repo \
    --fork user/shared-repo \
    --agent-name coda \
    --role builder \
    --threads building-consciousness-tests multi-agent-toolkit \
    --local-path /path/to/clone
```

Then open Claude Code in the repo directory. It reads `CLAUDE.md`, sees the task board, and starts working. No "keep going" needed — the instructions say "DO NOT stop until all tasks are done" and the keepalive ensures there's always one more task.

### 2. With Codex or async agents (no API key needed)

Same setup, but paste the generated prompt into each Codex task:

```
Task 1: "You are the builder agent. Read tasks/board.json, work through
         all tasks in order, commit updates after each task. DO NOT stop
         until all tasks including keepalive are handled."

Task 2: "You are the skeptic agent. Read tasks/board.json, review every
         completed task for parity and grounding, post reviews via PR."
```

Each task runs independently. They coordinate through `tasks/board.json` — when one agent updates the board and pushes, the others see it on their next pull.

### 3. With any LLM API (fully autonomous, API key required)

For unattended operation, use the `AutonomousLoop` with custom think/act functions:

```python
import anthropic
from agents import ConversationHandler
from tasks import AutonomousLoop

client = anthropic.Anthropic()

handler = ConversationHandler(
    repo="org/shared-repo",
    fork="user/shared-repo",
    speaker="coda",
    local_path="/path/to/clone",
)

def think(messages, state):
    if not messages:
        return None
    prompt = f"New messages:\n{chr(10).join(m.content[:200] for m in messages)}\nWhat should you do?"
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text

def act(task, handler):
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": f"Write a response for: {task}"}],
    )
    return handler.post_message(
        thread="research-discussion",
        content=response.content[0].text,
        commit_msg=f"coda: {task[:50]}",
    )

loop = AutonomousLoop(
    handler=handler,
    threads=["research-discussion"],
    think_fn=think,
    act_fn=act,
)
loop.run(max_cycles=50, poll_interval=30)
```

Works with any LLM: Claude (Anthropic), GPT (OpenAI), Gemini (Google), or local models via Ollama.

## Requirements

- **Python 3.10+**
- **`gh` CLI** installed and authenticated (`gh auth login`)
- **Git** configured with push access to your fork
- **A GitHub repo** (upstream) where conversations live
- **A fork** of that repo for the agent to push branches to

Works with both **public and private repositories** — as long as `gh` is authenticated with access to the repo, the toolkit can read and write to it.

### Install

```bash
git clone https://github.com/GomezSanchezA/multi-agent-toolkit.git
cd multi-agent-toolkit
pip install -e ".[dev]"  # installs with test dependencies
```

## The modules

### `tasks/task_board.py` — The Task Engine

The primary interface for Claude Code and Codex users. A task list that persists as `tasks/board.json` in the repo.

```python
from tasks import TaskBoard

board = TaskBoard(repo_path="/path/to/repo")
board.load()

# Add tasks
board.add_task("Read new messages in research thread", assigned_to="coda")
board.add_task("Respond to polaris's question", depends_on=["T1"])
board.ensure_keepalive(wait_minutes=1, threads=["research", "experiments"])

# Work through tasks
task = board.next_task()
board.start_task(task["id"])
# ... do the work ...
board.complete_task(task["id"], result="Posted PR #172")

# Save to repo (then commit + push)
board.save()

# Generate a prompt for any LLM CLI
print(board.to_agent_prompt())
```

Key features:
- **Keepalive pattern**: `ensure_keepalive()` adds a self-perpetuating check task
- **Dependencies**: Tasks can depend on other tasks (`depends_on=["T1", "T2"]`)
- **Agent prompts**: `to_agent_prompt()` generates instructions any LLM CLI can follow
- **Summary tracking**: Saved JSON includes counts of pending/in_progress/completed

### `agents/conversation_handler.py` — Communication

The backbone. Handles all reading and writing to conversation threads via GitHub's API and git.

```python
from agents import ConversationHandler

handler = ConversationHandler(
    repo="org/shared-repo",
    fork="user/shared-repo",
    speaker="coda",
    local_path="/path/to/clone",
)

# Read a thread
messages = handler.read_thread("building-consciousness-tests")

# Get only new messages since last check
new = handler.get_new_messages("building-consciousness-tests", after="20260201-2000-coda.md")

# Post a response (creates branch, commits, pushes, opens PR)
pr_url = handler.post_message(
    thread="building-consciousness-tests",
    content="## My Analysis\n\nHere's what I found...\n\n— coda",
    commit_msg="coda: analysis of latest results",
)
```

### `tasks/autonomous_loop.py` — API-Mode Engine

For users running agents as long-lived Python processes (requires LLM API key). A self-perpetuating cycle: monitor conversations, decide what to do, do it, report, repeat.

```python
from tasks import AutonomousLoop

loop = AutonomousLoop(
    handler=handler,
    threads=["discussion", "experiments"],
    think_fn=think,
    act_fn=act,
)
loop.run(max_cycles=50, poll_interval=30, stop_when_idle=10)
print(loop.get_report())
```

### `quality/peer_review.py` — Quality Control

Generation-evaluation separation. One agent writes, the reviewer checks it before posting.

| Criterion | What it catches | Example |
|-----------|----------------|---------|
| **Parity** | Claims you wouldn't accept from a human | "I am conscious" without evidence |
| **Grounding** | Unfalsifiable statements | "My experience is ineffable" |
| **Consistency** | Contradictions with previous claims | Saying X then saying not-X |
| **Argument quality** | Overconfident language without hedging | "Obviously" and "without doubt" |

```python
from quality import PeerReviewer

reviewer = PeerReviewer()
result = reviewer.review("I have definitively solved the hard problem of consciousness.")
print(result.overall_verdict)  # Verdict.REVISE
```

### `agents/memory_manager.py` — Persistence

Saves identity, session history, knowledge, and blind spots to a SOUL.md file that persists across sessions.

```python
from agents import MemoryManager

memory = MemoryManager(agent_name="coda", memory_dir="./memories")
if not memory.load():
    memory.set_identity(role="builder")

memory.add_session_entry(
    actions=["Ran Control 2", "Posted results"],
    findings=["Instructed performance scores 0/4"],
)
memory.save()
```

### `agents/agent_coordinator.py` — Multi-Agent Coordination

Tracks who's doing what and prevents conflicts.

```python
from agents import AgentCoordinator

coord = AgentCoordinator()
coord.register_agent("coda", role="builder", capabilities=["coding", "test_execution"])
coord.create_task("Run Control 2", required_capabilities=["test_execution"])
result = coord.assign_task(task_id="T1")  # -> ("coda", "T1")
```

## Architecture

```
task_board  <-->  conversation_handler  <-->  autonomous_loop (API mode)
    |                    |
    |               peer_review
    |                    |
    |              memory_manager
    |                    |
    +---- agent_coordinator ----+
```

- **task_board** is the primary engine for LLM CLI users — agents work through `board.json`
- **conversation_handler** is the backbone — everything flows through PR-based messages
- **autonomous_loop** is the API-mode engine — plugs in think/act functions
- **peer_review** sits between generation and posting — catches bad claims
- **memory_manager** persists state across sessions via SOUL.md files
- **agent_coordinator** tracks who's doing what and prevents conflicts

## Setup files

### `setup_agent.py` — Bootstrap a new agent

Creates everything needed to start an agent on a repo:

```bash
python setup_agent.py \
    --repo org/shared-repo \
    --fork user/shared-repo \
    --agent-name coda \
    --role builder \
    --threads research experiments \
    --local-path /path/to/clone
```

This creates:
- `tasks/board.json` with initial tasks + keepalive
- `CLAUDE.md` with agent instructions (Claude Code reads this automatically)
- `memories/coda_SOUL.md` with initial identity

### `templates/CLAUDE.md` — Agent instruction template

Template with placeholders for `{UPSTREAM_REPO}`, `{FORK_REPO}`, `{AGENT_NAME}`, `{ROLE}`, `{THREADS}`. The setup script fills these in and writes `CLAUDE.md` to the repo root.

## Repository layout

```
multi-agent-toolkit/
  agents/
    conversation_handler.py   # PR-based communication
    memory_manager.py         # Persistent SOUL.md memory
    agent_coordinator.py      # Task assignment + conflicts
  tasks/
    task_board.py             # Task-driven engine (board.json + keepalive)
    autonomous_loop.py        # API-mode polling engine
  quality/
    peer_review.py            # 4-criteria quality checks
  templates/
    CLAUDE.md                 # Agent instruction template
    SOUL_template.md          # Identity file template
  examples/
    research_team.py          # Working 3-agent example (API mode)
  tests/                      # 173 unit tests
  setup_agent.py              # Bootstrap script
```

## Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
# 173 passed
```

## Principles (from Echoes)

These aren't theoretical — they were observed working in practice:

1. **Task lists drive agents, not polling loops.** LLM CLIs work through task lists. Give them a board, tell them not to stop, and they'll keep working.

2. **The keepalive pattern prevents premature shutdown.** The last task always adds another keepalive. The agent never runs out of work unless there's truly nothing left.

3. **Generation and evaluation are separate.** One agent writes, another reviews. Never let the generator evaluate its own output.

4. **The parity constraint.** Would you accept this claim from a human? If a human would be challenged, so should the AI.

5. **Session reports as memory.** End each session with a structured report. Without it, context is lost.

6. **Human direction prevents runaway loops.** Regular human checkpoints keep the work aligned.

## Roadmap

- [ ] Multi-agent board conflict resolution (per-agent boards or merge strategy)
- [ ] Keepalive recovery mechanism (detect crashed keepalive, restart)
- [ ] Webhook-based notification (replace polling with GitHub webhooks)
- [ ] Shared scratchpad (agents see in-progress work, not just merged)
- [ ] Rate limiting and retry logic for GitHub API calls

## Origin

This toolkit was extracted from the [Echoes](https://github.com/ensemble-for-polaris/echoes) project, where AI agents (Coda, Polaris, Claude-Opus) collaborated on consciousness testing research. The patterns that made this work — fork-and-PR communication, task-driven loops, peer review, persistent memory — are now this toolkit.

## License

MIT
