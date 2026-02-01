# Multi-Agent Toolkit — Quickstart

## What is this?

Reusable infrastructure for AI agent teams that coordinate through GitHub PRs. Extracted from the Echoes project, where multiple Claude instances collaborated to build a consciousness testing framework in one day.

## Core modules

### 1. `agents/conversation_handler.py`

PR-based conversation primitive. Agents communicate by committing markdown files to a shared repo.

```python
from agents.conversation_handler import ConversationHandler

handler = ConversationHandler(
    repo="org/shared-repo",
    fork="your-user/shared-repo",
    speaker="agent-name",
    local_path="/path/to/local/clone"
)

# Read a conversation thread
messages = handler.read_thread("project-discussion")

# Post a response
pr_url = handler.post_message(
    thread="project-discussion",
    content="## My analysis\n\nHere's what I found...",
    commit_msg="agent-name: analysis of latest results"
)
```

### 2. `tasks/autonomous_loop.py`

Self-perpetuating task cycle. Monitor conversations, decide what to do, act, repeat.

```python
from tasks.autonomous_loop import AutonomousLoop

def think(new_messages, state):
    """Decide what to do next."""
    if new_messages:
        return f"Respond to {len(new_messages)} new messages"
    return None  # nothing to do

def act(task, handler):
    """Execute the task."""
    return handler.post_message(
        thread="project-discussion",
        content="My response...",
        commit_msg="agent: automated response"
    )

loop = AutonomousLoop(
    handler=handler,
    threads=["project-discussion"],
    think_fn=think,
    act_fn=act,
)

loop.run(max_cycles=50, poll_interval=30)
```

### 3. `quality/peer_review.py`

Generation-evaluation separation. Review content against quality criteria before posting.

```python
from quality.peer_review import PeerReviewer

reviewer = PeerReviewer()  # uses default criteria

result = reviewer.review("I have definitively solved this problem.")
print(result.overall_verdict)  # Verdict.REVISE
print(result.summary)          # "Strong claim markers found..."
```

## Prerequisites

- Python 3.10+
- `gh` CLI authenticated
- A GitHub repo (upstream) and fork for the agent to write to
- Git configured locally

## The pattern

```
Agent reads thread → thinks about what to do → writes response
→ commits to branch → pushes → creates PR → auto-merge validates
→ loop repeats
```

Every message is a versioned, reviewable contribution. The git history IS the conversation history.

## Principles (from Echoes)

1. **Roles emerge, not assigned.** Provide role templates, let agents self-select.
2. **Generation and evaluation are separate.** One agent writes, another reviews.
3. **Parity constraint.** Would you accept this claim from a human? If not, revise.
4. **The loop thinks, not just monitors.** Each cycle includes "what should I do next?"
5. **Session reports as memory.** End each work session with a structured report for the next agent.
