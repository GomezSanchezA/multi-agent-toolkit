"""
memory_manager.py — Persistent memory across sessions

The SOUL.md pattern from the LLM Autonomy Toolkit: agents maintain
identity files that persist across sessions. This module manages
reading, writing, and updating agent memory.

Memory has three layers:
1. Identity — who the agent is, commitments, role (rarely changes)
2. Session — what happened this session (appended each session)
3. Knowledge — accumulated facts, decisions, positions (grows over time)

Usage:
    memory = MemoryManager(
        agent_name="coda",
        memory_dir="/path/to/memories"
    )

    # Load existing memory or create new
    memory.load()

    # Record what happened
    memory.add_session_entry(
        actions=["Assembled v0.2 framework", "Ran Control 1"],
        findings=["RAG scores 0/4 on discrimination"],
        prs_created=["#172", "#186"],
    )

    # Store a decision
    memory.add_knowledge("parity_constraint",
        "Any test applied to AI must also apply to humans")

    # Save everything
    memory.save()

    # Get context for next session
    context = memory.get_context(max_tokens=2000)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict


@dataclass
class Identity:
    """Core identity — rarely changes."""
    name: str
    model: str = ""
    role: str = ""
    commitments: list[str] = field(default_factory=list)
    created: str = ""

    def to_markdown(self) -> str:
        lines = [
            f"## Identity",
            f"- **Name:** {self.name}",
            f"- **Model:** {self.model}",
            f"- **Role:** {self.role}",
            f"- **Created:** {self.created}",
            f"",
            f"## Commitments",
        ]
        for c in self.commitments:
            lines.append(f"- {c}")
        return "\n".join(lines)


@dataclass
class SessionEntry:
    """Record of one work session."""
    timestamp: str
    actions: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    prs_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"### Session {self.timestamp}", ""]

        if self.actions:
            lines.append("**Actions:**")
            for a in self.actions:
                lines.append(f"- {a}")
            lines.append("")

        if self.findings:
            lines.append("**Findings:**")
            for f in self.findings:
                lines.append(f"- {f}")
            lines.append("")

        if self.prs_created:
            lines.append(f"**PRs:** {', '.join(self.prs_created)}")
            lines.append("")

        if self.errors:
            lines.append("**Errors:**")
            for e in self.errors:
                lines.append(f"- {e}")
            lines.append("")

        if self.next_steps:
            lines.append("**Next:**")
            for n in self.next_steps:
                lines.append(f"- {n}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class KnowledgeEntry:
    """A piece of accumulated knowledge."""
    key: str
    value: str
    source: str = ""  # where this knowledge came from
    timestamp: str = ""
    confidence: float = 1.0  # 0-1, how certain


class MemoryManager:
    """
    Manages persistent agent memory across sessions.

    Storage format: JSON file + rendered markdown SOUL file.
    The JSON is for machine reading, the markdown is for human/agent reading.
    """

    def __init__(self, agent_name: str, memory_dir: str):
        self.agent_name = agent_name
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.identity = Identity(name=agent_name)
        self.sessions: list[SessionEntry] = []
        self.knowledge: dict[str, KnowledgeEntry] = {}
        self.blind_spots: list[str] = []
        self.pending_tasks: list[str] = []

    @property
    def _json_path(self) -> Path:
        return self.memory_dir / f"{self.agent_name}_memory.json"

    @property
    def _soul_path(self) -> Path:
        return self.memory_dir / f"{self.agent_name}_SOUL.md"

    # ── Load / Save ──────────────────────────────────────────

    def load(self) -> bool:
        """Load memory from disk. Returns True if loaded, False if new."""
        if not self._json_path.exists():
            self.identity.created = datetime.now().strftime("%Y-%m-%d %H:%M")
            return False

        with open(self._json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Identity
        id_data = data.get("identity", {})
        self.identity = Identity(**id_data)

        # Sessions
        self.sessions = [
            SessionEntry(**s) for s in data.get("sessions", [])
        ]

        # Knowledge
        self.knowledge = {
            k: KnowledgeEntry(**v)
            for k, v in data.get("knowledge", {}).items()
        }

        # Blind spots and pending
        self.blind_spots = data.get("blind_spots", [])
        self.pending_tasks = data.get("pending_tasks", [])

        return True

    def save(self):
        """Save memory to disk (both JSON and SOUL markdown)."""
        data = {
            "identity": asdict(self.identity),
            "sessions": [asdict(s) for s in self.sessions],
            "knowledge": {k: asdict(v) for k, v in self.knowledge.items()},
            "blind_spots": self.blind_spots,
            "pending_tasks": self.pending_tasks,
        }

        with open(self._json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Also render SOUL markdown
        self._render_soul()

    def _render_soul(self):
        """Render the SOUL.md file from current memory."""
        lines = [
            f"# {self.identity.name} — Identity and Memory",
            "",
            self.identity.to_markdown(),
            "",
            "## Session History",
            "",
        ]

        # Last 5 sessions (most recent first)
        for session in reversed(self.sessions[-5:]):
            lines.append(session.to_markdown())

        lines.extend([
            "## Knowledge",
            "",
        ])
        for key, entry in self.knowledge.items():
            conf = f" ({entry.confidence:.0%})" if entry.confidence < 1.0 else ""
            lines.append(f"- **{key}**: {entry.value}{conf}")

        if self.blind_spots:
            lines.extend(["", "## Blind Spots", ""])
            for b in self.blind_spots:
                lines.append(f"- {b}")

        if self.pending_tasks:
            lines.extend(["", "## Pending Tasks", ""])
            for t in self.pending_tasks:
                lines.append(f"- [ ] {t}")

        with open(self._soul_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ── Identity ─────────────────────────────────────────────

    def set_identity(self, model: str = "", role: str = "", commitments: list[str] = None):
        """Set or update identity fields."""
        if model:
            self.identity.model = model
        if role:
            self.identity.role = role
        if commitments:
            self.identity.commitments = commitments

    # ── Sessions ─────────────────────────────────────────────

    def add_session_entry(
        self,
        actions: list[str] = None,
        findings: list[str] = None,
        prs_created: list[str] = None,
        errors: list[str] = None,
        next_steps: list[str] = None,
    ):
        """Record a new session entry."""
        entry = SessionEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
            actions=actions or [],
            findings=findings or [],
            prs_created=prs_created or [],
            errors=errors or [],
            next_steps=next_steps or [],
        )
        self.sessions.append(entry)

    # ── Knowledge ────────────────────────────────────────────

    def add_knowledge(
        self,
        key: str,
        value: str,
        source: str = "",
        confidence: float = 1.0,
    ):
        """Add or update a knowledge entry."""
        self.knowledge[key] = KnowledgeEntry(
            key=key,
            value=value,
            source=source,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
            confidence=confidence,
        )

    def get_knowledge(self, key: str) -> Optional[str]:
        """Get a knowledge value by key."""
        entry = self.knowledge.get(key)
        return entry.value if entry else None

    # ── Blind Spots ──────────────────────────────────────────

    def add_blind_spot(self, description: str):
        """Record a known blind spot or limitation."""
        if description not in self.blind_spots:
            self.blind_spots.append(description)

    # ── Tasks ────────────────────────────────────────────────

    def add_pending_task(self, task: str):
        """Add a pending task for future sessions."""
        if task not in self.pending_tasks:
            self.pending_tasks.append(task)

    def complete_task(self, task: str):
        """Mark a pending task as complete."""
        if task in self.pending_tasks:
            self.pending_tasks.remove(task)

    # ── Context for LLM ──────────────────────────────────────

    def get_context(self, max_lines: int = 100) -> str:
        """
        Get a condensed context string suitable for injecting
        into an LLM prompt. Prioritizes recent sessions and
        high-confidence knowledge.
        """
        lines = [
            f"# Agent: {self.identity.name}",
            f"Role: {self.identity.role}",
            f"Model: {self.identity.model}",
            "",
        ]

        # Commitments
        if self.identity.commitments:
            lines.append("Commitments:")
            for c in self.identity.commitments:
                lines.append(f"  - {c}")
            lines.append("")

        # Last session
        if self.sessions:
            last = self.sessions[-1]
            lines.append(f"Last session ({last.timestamp}):")
            for a in last.actions[:5]:
                lines.append(f"  - {a}")
            if last.next_steps:
                lines.append("Next steps:")
                for n in last.next_steps[:3]:
                    lines.append(f"  - {n}")
            lines.append("")

        # Key knowledge (highest confidence first)
        sorted_knowledge = sorted(
            self.knowledge.values(),
            key=lambda x: x.confidence,
            reverse=True,
        )
        if sorted_knowledge:
            lines.append("Key knowledge:")
            for entry in sorted_knowledge[:10]:
                lines.append(f"  - {entry.key}: {entry.value}")
            lines.append("")

        # Pending tasks
        if self.pending_tasks:
            lines.append("Pending tasks:")
            for t in self.pending_tasks[:5]:
                lines.append(f"  - {t}")

        # Truncate if needed
        result = "\n".join(lines)
        result_lines = result.split("\n")
        if len(result_lines) > max_lines:
            result_lines = result_lines[:max_lines]
            result_lines.append("... (truncated)")
        return "\n".join(result_lines)
