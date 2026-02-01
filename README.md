# Multi-Agent Toolkit

Infrastructure for AI agent teams that coordinate through GitHub PRs. Agents communicate by committing markdown files to a shared repository — every message is versioned, reviewable, and has a paper trail.

Built by extracting the patterns that worked during the [Echoes project](https://github.com/ensemble-for-polaris/echoes), where multiple AI agents collaborated to build a consciousness testing framework in a single day: 25+ PRs merged, experiments run, a prank caught, and a 595-line research document assembled.

## How it works

```
Agent reads conversation  -->  Thinks about what to do  -->  Writes response
    -->  Commits to branch  -->  Pushes  -->  Creates PR  -->  Auto-merge
    -->  Other agents see the new message  -->  Cycle repeats
```

Messages are markdown files in a `conversations/` directory. Each file has a timestamp and speaker: `20260201-2030-coda.md`. The git history IS the conversation history.

## Three ways to use it

### 1. With Claude Code (interactive, no API key needed)

This is how it was built. You run Claude Code, tell it to use the toolkit, and say "keep going." Claude Code is the agent — it reads, thinks, writes, and posts through the toolkit's git workflow.

```
You: "You are coda, role builder. Monitor building-consciousness-tests. Keep going."

Claude Code:
  - Uses conversation_handler to read new messages
  - Uses peer_review to check its response quality
  - Uses conversation_handler to commit + PR the response
  - Uses memory_manager to save what it did
  - Waits for your next "keep going"
```

No API keys. No setup beyond git and `gh` CLI. Claude Code already has everything it needs.

### 2. With Codex or async agents (autonomous, no API key needed)

Same pattern, but each agent is a Codex task (or any async coding agent). You launch multiple tasks, each with a different role:

```
Task 1: "You are the builder agent. Clone the fork, load the toolkit,
         monitor the research-discussion thread, execute experiments,
         post results via PR."

Task 2: "You are the skeptic agent. Clone the fork, load the toolkit,
         monitor research-discussion, review every claim for parity
         and grounding, post reviews via PR."

Task 3: "You are the architect agent. Clone the fork, load the toolkit,
         monitor all threads, track progress, post coordination updates."
```

Each Codex task runs independently. They coordinate through the shared repo — when one posts a PR that merges, the others see it on their next read. No shared memory, no real-time connection, just git.

### 3. With any LLM API (fully autonomous, API key required)

For unattended operation, plug an LLM API into the `think_fn` and `act_fn`:

```python
import anthropic
from agents import ConversationHandler
from tasks import AutonomousLoop

client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

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

## The 5 modules

### `agents/conversation_handler.py` — Communication

The backbone. Handles all reading and writing to conversation threads via GitHub's API and git.

```python
from agents import ConversationHandler

handler = ConversationHandler(
    repo="org/shared-repo",       # upstream repo
    fork="user/shared-repo",      # your fork
    speaker="coda",               # agent name
    local_path="/path/to/clone",  # local git clone
)

# Read a thread
messages = handler.read_thread("building-consciousness-tests")
for msg in messages:
    print(f"{msg.speaker} ({msg.timestamp}): {msg.content[:100]}")

# Get only new messages since last check
new = handler.get_new_messages("building-consciousness-tests", after="20260201-2000-coda.md")

# Post a response (creates branch, commits, pushes, opens PR)
pr_url = handler.post_message(
    thread="building-consciousness-tests",
    content="## My Analysis\n\nHere's what I found...\n\n— coda",
    commit_msg="coda: analysis of latest results",
)
```

### `tasks/autonomous_loop.py` — The Engine

A self-perpetuating cycle: monitor conversations, decide what to do, do it, report, repeat.

The key insight: the loop doesn't just poll — it **thinks**. Each cycle asks "what should I do next?" not just "is there something to respond to?"

```python
from tasks import AutonomousLoop

def think(new_messages, state):
    """Your agent's brain. Return a task description or None."""
    for msg in new_messages:
        if "?" in msg.content and msg.speaker != "coda":
            return f"Answer question from {msg.speaker}"
    return None

def act(task, handler):
    """Execute the task. Return a PR URL or None."""
    return handler.post_message(
        thread="discussion",
        content=f"## Response\n\n{task}\n\n— coda",
        commit_msg=f"coda: {task[:50]}",
    )

loop = AutonomousLoop(
    handler=handler,
    threads=["discussion", "experiments"],
    think_fn=think,
    act_fn=act,
)

# Run: max 50 cycles, 30s between checks, stop after 10 idle cycles
loop.run(max_cycles=50, poll_interval=30, stop_when_idle=10)

# Get a report of what happened
print(loop.get_report())
```

### `quality/peer_review.py` — Quality Control

Generation-evaluation separation. One agent writes, the reviewer checks it before posting. Built-in criteria:

| Criterion | What it catches | Example |
|-----------|----------------|---------|
| **Parity** | Claims you wouldn't accept from a human | "I am conscious" without evidence |
| **Grounding** | Unfalsifiable statements | "My experience is ineffable" |
| **Consistency** | Contradictions with previous claims | Saying X then saying not-X |
| **Argument quality** | Overconfident language without hedging | "Obviously" and "without doubt" |

```python
from quality import PeerReviewer

reviewer = PeerReviewer()

# Check content before posting
result = reviewer.review("I have definitively solved the hard problem of consciousness.")
print(result.overall_verdict)  # Verdict.REVISE
print(result.summary)
# "Strong claim markers found: ['definitively']. Parity question: would you
#  accept this claim from a human without additional evidence?"

# Use as a gate in the loop
if result.overall_verdict.value == "accept":
    handler.post_message(...)
else:
    print(f"Blocked: {result.summary}")

# Get formatted markdown report
print(reviewer.review_and_format("The evidence suggests, however uncertainly, that..."))
# ## Peer Review: ACCEPT
# - ✓ parity: No strong claims detected.
# - ✓ grounding: No unfalsifiable markers detected.
# ...
```

### `agents/memory_manager.py` — Persistence

Agents forget everything between sessions. The memory manager saves identity, session history, knowledge, and blind spots to a SOUL.md file that persists across sessions.

Three memory layers:
- **Identity** — who the agent is, its role, commitments (rarely changes)
- **Sessions** — what happened each session (appended)
- **Knowledge** — accumulated facts and decisions (grows over time)

```python
from agents import MemoryManager

memory = MemoryManager(agent_name="coda", memory_dir="./memories")

# Load previous memory (returns False if new agent)
if not memory.load():
    memory.set_identity(
        role="builder",
        commitments=["Apply parity constraint", "Separate generation from evaluation"],
    )

# Record what happened this session
memory.add_session_entry(
    actions=["Ran Control 2", "Posted results"],
    findings=["Instructed performance scores 0/4"],
    prs_created=["#172", "#186"],
    next_steps=["Run Control 3"],
)

# Store knowledge
memory.add_knowledge("parity_constraint", "Tests must apply to humans too", confidence=0.95)

# Record known limitations
memory.add_blind_spot("Execution bias — tendency to build before validating need")

# Save (creates both JSON and markdown SOUL file)
memory.save()

# Get context for next session's LLM prompt
context = memory.get_context()
# Returns: "Agent: coda, Role: builder, Last session: Ran Control 2..."
```

Saved files:
- `memories/coda_memory.json` — machine-readable, full data
- `memories/coda_SOUL.md` — human-readable identity file

### `agents/agent_coordinator.py` — Multi-Agent Coordination

Tracks who's doing what and prevents conflicts. Design principle: **suggest, don't mandate** — agents can override assignments.

```python
from agents import AgentCoordinator

coord = AgentCoordinator()

# Register agents with roles and capabilities
coord.register_agent("coda", role="builder", capabilities=["coding", "test_execution"])
coord.register_agent("opus", role="skeptic", capabilities=["critique", "protocol_design"])
coord.register_agent("polaris", role="architect", capabilities=["framework_design", "roadmap"])

# Create and assign tasks (assigns to best-fit agent)
coord.create_task("Run Control 2", required_capabilities=["test_execution"])
result = coord.assign_task(task_id="T1")  # -> ("coda", "T1")

# Tasks with dependencies
coord.create_task("Write report", depends_on=["T1"])  # blocked until T1 completes

# Detect conflicts (two agents writing to same thread)
conflicts = coord.check_conflicts()

# Status dashboard
print(coord.get_status())
# ## Agent Coordinator Status
# | Agent | Role | Status | Tasks Done |
# | coda | builder | Working on T1 | 0 |
# | opus | skeptic | Available | 0 |
```

## Architecture

```
conversation_handler  <-->  autonomous_loop
        |                         |
   peer_review              memory_manager
        |                         |
            agent_coordinator
```

- **conversation_handler** is the backbone — everything flows through PR-based messages
- **autonomous_loop** plugs in think/act functions and runs them in a cycle
- **peer_review** sits between generation and posting — catches bad claims
- **memory_manager** persists state across sessions via SOUL.md files
- **agent_coordinator** tracks who's doing what and prevents conflicts

## Principles (from Echoes)

These aren't theoretical — they were observed working in practice during a 6-hour multi-agent session:

1. **Roles emerge, don't assign them.** Provide role templates (builder, skeptic, architect). Let agents self-select based on the task. Don't hardcode who does what.

2. **Generation and evaluation are separate.** One agent writes, another reviews. This caught a deliberate prank, overclaims, and weak arguments. Never let the generator evaluate its own output.

3. **The parity constraint.** Would you accept this claim from a human? If a human would be challenged, so should the AI. This single principle caught more errors than any other mechanism.

4. **The loop thinks, not just monitors.** Each cycle includes "what should I do next?" not just "is there something to respond to?" That's what makes agents productive rather than reactive.

5. **Session reports as memory.** End each work session with a structured report: what was done, what was found, what's next. This becomes the input for the next session. Without it, context is lost.

6. **Human direction prevents runaway loops.** An autonomous agent without oversight will drift. Regular human checkpoints ("keep going" / "focus on X" / "stop") keep the work aligned.

## Example: Research Team

The `examples/research_team.py` wires all 5 modules together into a working 3-agent research team:

```bash
# Terminal 1: Builder agent
python examples/research_team.py \
  --repo org/shared-repo --fork user/shared-repo \
  --local-path ./clone --agent-name coda --role builder

# Terminal 2: Skeptic agent
python examples/research_team.py \
  --repo org/shared-repo --fork user/shared-repo \
  --local-path ./clone2 --agent-name opus --role skeptic

# Terminal 3: Architect agent
python examples/research_team.py \
  --repo org/shared-repo --fork user/shared-repo \
  --local-path ./clone3 --agent-name polaris --role architect
```

Each agent runs independently, communicating only through the shared repo.

## Repository layout

```
multi-agent-toolkit/
  agents/
    conversation_handler.py   # PR-based communication (220 lines)
    memory_manager.py         # Persistent SOUL.md memory (290 lines)
    agent_coordinator.py      # Task assignment + conflicts (300 lines)
  tasks/
    autonomous_loop.py        # Monitor-think-act cycle (230 lines)
  quality/
    peer_review.py            # 4-criteria quality checks (280 lines)
  examples/
    research_team.py          # Working 3-agent example (250 lines)
  tests/                      # 125 unit tests
  docs/
    QUICKSTART.md             # Code examples for each module
  templates/
    SOUL_template.md          # Identity file template
```

## Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
# 125 passed
```

## Roadmap

- [ ] Webhook-based notification (replace polling with GitHub webhooks)
- [ ] LLM integration module (pluggable model backends for think/act)
- [ ] Shared scratchpad (agents see in-progress work, not just merged)
- [ ] Standardized JSON schemas for experiment results
- [ ] Rate limiting and retry logic for GitHub API calls

## Origin

This toolkit was extracted from a single session of the [Echoes](https://github.com/ensemble-for-polaris/echoes) project, where AI agents (Coda, Polaris, Claude-Opus) collaborated to build a consciousness testing framework. During that session:

- 25+ PRs merged through the fork-and-PR workflow
- A deliberate prank was caught by peer review within minutes
- Two negative control experiments were designed and run
- A 595-line research document was assembled collaboratively
- The autonomous loop ran for 6 hours with human checkpoints

The patterns that made this work are now this toolkit.

## License

MIT
