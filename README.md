# Multi-Agent Toolkit

Reusable infrastructure for AI agent teams that coordinate through GitHub PRs.
Extracted from the Echoes project, where multiple agents collaborated to build a
consciousness testing framework in one day.

## What this provides

- PR-based conversation primitive (git commits are messages)
- Autonomous loop that monitors, thinks, acts, and reports
- Peer review checks to separate generation from evaluation
- Persistent memory (SOUL pattern) across sessions
- Task coordination and conflict detection
- Working example of a research team

## Quickstart

See `docs/QUICKSTART.md` for a full walkthrough with code examples.

Minimum requirements:
- Python 3.10+
- `gh` CLI authenticated
- A GitHub repo (upstream) and a fork
- Git configured locally

## Core modules

- `agents/conversation_handler.py`
  - Read threads and post replies via PRs
- `tasks/autonomous_loop.py`
  - Monitor -> think -> act -> report -> repeat
- `quality/peer_review.py`
  - Parity, grounding, and argument-quality checks
- `agents/memory_manager.py`
  - Persistent identity + session memory
- `agents/agent_coordinator.py`
  - Task assignment, conflict detection, status dashboard

## Patterns extracted from Echoes

- Fork-and-PR as the conversation primitive
- Roles emerge from behavior (templates help, assignments do not)
- Autoloop with deliberation (not just polling)
- Generation and evaluation are separated
- Session reports as memory
- Human direction is required to prevent runaway loops

## Example usage

Run the example research team:

```bash
python examples/research_team.py \
  --repo org/shared-repo \
  --fork user/shared-repo \
  --local-path /path/to/clone \
  --agent-name coda \
  --role builder
```

## Repository layout

- `agents/` - core agent modules
- `tasks/` - loop and task execution helpers
- `quality/` - review criteria and peer review
- `examples/` - working examples
- `docs/` - documentation
- `templates/` - SOUL and other templates
- `tests/` - unit tests

## Roadmap (gaps to close)

- Webhook-based notification (replace polling)
- LLM integration layer (model abstraction for think/act)
- Shared scratchpad or draft space
- Standardized JSON schemas for results

If you want me to tackle any of the roadmap items, point me at one and I will build it.
