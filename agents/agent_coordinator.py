"""
agent_coordinator.py — Multi-agent task assignment and coordination

The pattern from Echoes: roles emerge from behavior, not assignment.
But someone needs to track who's doing what and prevent conflicts.

This module provides:
- Agent registration with roles and capabilities
- Task assignment based on role fit
- Conflict detection (two agents writing to same thread)
- Dependency tracking between agents' work
- Status dashboard

Usage:
    coord = AgentCoordinator()

    # Register agents
    coord.register_agent("coda", role="builder",
        capabilities=["test_execution", "framework_drafting", "coding"])
    coord.register_agent("claude-opus", role="skeptic",
        capabilities=["critique", "protocol_design", "negative_controls"])
    coord.register_agent("polaris", role="architect",
        capabilities=["framework_design", "integration", "roadmap"])

    # Assign tasks
    coord.assign_task(
        task="Run Control 2 on domain-comparison",
        required_capabilities=["test_execution"],
    )
    # Returns: assigned to "coda" (best fit)

    # Check for conflicts
    coord.check_conflicts()
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class Agent:
    """A registered agent with role and capabilities."""
    name: str
    role: str
    capabilities: list[str] = field(default_factory=list)
    current_task: Optional[str] = None
    tasks_completed: int = 0
    last_active: str = ""

    @property
    def is_available(self) -> bool:
        return self.current_task is None


@dataclass
class Task:
    """A task in the coordination system."""
    id: str
    description: str
    required_capabilities: list[str] = field(default_factory=list)
    assigned_to: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    created: str = ""
    completed: str = ""
    depends_on: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    thread: Optional[str] = None  # conversation thread this task writes to
    result: Optional[str] = None


class AgentCoordinator:
    """
    Coordinates multiple agents working on shared tasks.

    Design principle: suggest, don't mandate. Agents can override
    assignments. The coordinator tracks state, not controls it.
    """

    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.tasks: dict[str, Task] = {}
        self._task_counter = 0

    # ── Agent Management ─────────────────────────────────────

    def register_agent(
        self,
        name: str,
        role: str,
        capabilities: list[str] = None,
    ) -> Agent:
        """Register an agent with the coordinator."""
        agent = Agent(
            name=name,
            role=role,
            capabilities=capabilities or [],
            last_active=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        self.agents[name] = agent
        return agent

    def update_agent_activity(self, name: str):
        """Mark an agent as recently active."""
        if name in self.agents:
            self.agents[name].last_active = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Task Management ──────────────────────────────────────

    def create_task(
        self,
        description: str,
        required_capabilities: list[str] = None,
        depends_on: list[str] = None,
        thread: Optional[str] = None,
    ) -> Task:
        """Create a new task."""
        self._task_counter += 1
        task_id = f"T{self._task_counter}"

        task = Task(
            id=task_id,
            description=description,
            required_capabilities=required_capabilities or [],
            created=datetime.now().strftime("%Y-%m-%d %H:%M"),
            depends_on=depends_on or [],
            thread=thread,
        )
        self.tasks[task_id] = task

        # Update blocking relationships
        for dep_id in task.depends_on:
            if dep_id in self.tasks:
                self.tasks[dep_id].blocks.append(task_id)

        return task

    def assign_task(
        self,
        task_id: Optional[str] = None,
        description: Optional[str] = None,
        required_capabilities: list[str] = None,
        prefer_agent: Optional[str] = None,
    ) -> Optional[tuple[str, str]]:
        """
        Assign a task to the best-fit available agent.

        Can pass an existing task_id or create a new task with description.
        Returns (agent_name, task_id) or None if no agent available.
        """
        # Create task if needed
        if task_id is None and description:
            task = self.create_task(description, required_capabilities)
            task_id = task.id
        elif task_id and task_id in self.tasks:
            task = self.tasks[task_id]
        else:
            return None

        # Check dependencies
        if self._is_blocked(task_id):
            task.status = TaskStatus.BLOCKED
            return None

        # Find best agent
        agent = self._find_best_agent(
            task.required_capabilities,
            prefer=prefer_agent,
        )

        if agent is None:
            return None

        # Assign
        task.assigned_to = agent.name
        task.status = TaskStatus.ASSIGNED
        agent.current_task = task_id

        return (agent.name, task_id)

    def complete_task(self, task_id: str, result: str = ""):
        """Mark a task as completed."""
        if task_id not in self.tasks:
            return

        task = self.tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.completed = datetime.now().strftime("%Y-%m-%d %H:%M")
        task.result = result

        # Free up the agent
        if task.assigned_to and task.assigned_to in self.agents:
            agent = self.agents[task.assigned_to]
            agent.current_task = None
            agent.tasks_completed += 1

        # Unblock dependent tasks
        for blocked_id in task.blocks:
            if blocked_id in self.tasks:
                blocked_task = self.tasks[blocked_id]
                if not self._is_blocked(blocked_id):
                    blocked_task.status = TaskStatus.PENDING

    def _is_blocked(self, task_id: str) -> bool:
        """Check if a task is blocked by incomplete dependencies."""
        task = self.tasks.get(task_id)
        if not task:
            return False
        return any(
            self.tasks.get(dep_id, Task(id="")).status != TaskStatus.COMPLETED
            for dep_id in task.depends_on
        )

    def _find_best_agent(
        self,
        required_capabilities: list[str],
        prefer: Optional[str] = None,
    ) -> Optional[Agent]:
        """Find the best available agent for a task."""
        # If preferred agent is available and capable, use them
        if prefer and prefer in self.agents:
            agent = self.agents[prefer]
            if agent.is_available:
                return agent

        # Score agents by capability match
        candidates = []
        for agent in self.agents.values():
            if not agent.is_available:
                continue

            if not required_capabilities:
                candidates.append((agent, 0))
                continue

            match_count = sum(
                1 for cap in required_capabilities
                if cap in agent.capabilities
            )
            if match_count > 0:
                candidates.append((agent, match_count))

        if not candidates:
            # Fall back to any available agent
            available = [a for a in self.agents.values() if a.is_available]
            return available[0] if available else None

        # Sort by match count (descending), then by tasks completed (ascending for load balance)
        candidates.sort(key=lambda x: (-x[1], x[0].tasks_completed))
        return candidates[0][0]

    # ── Conflict Detection ───────────────────────────────────

    def check_conflicts(self) -> list[str]:
        """
        Check for potential conflicts:
        - Two agents writing to the same thread simultaneously
        - Circular dependencies
        - Stale assignments (agent hasn't been active)
        """
        conflicts = []

        # Thread conflicts: multiple in-progress tasks on same thread
        thread_tasks: dict[str, list[str]] = {}
        for task in self.tasks.values():
            if task.thread and task.status in (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS):
                thread_tasks.setdefault(task.thread, []).append(
                    f"{task.id} ({task.assigned_to})"
                )

        for thread, tasks in thread_tasks.items():
            if len(tasks) > 1:
                conflicts.append(
                    f"Thread conflict on '{thread}': {', '.join(tasks)}"
                )

        # Circular dependencies
        for task_id in self.tasks:
            if self._has_circular_dep(task_id, set()):
                conflicts.append(f"Circular dependency involving {task_id}")

        return conflicts

    def _has_circular_dep(self, task_id: str, visited: set) -> bool:
        """Check for circular dependencies via DFS."""
        if task_id in visited:
            return True
        visited.add(task_id)
        task = self.tasks.get(task_id)
        if not task:
            return False
        for dep_id in task.depends_on:
            if self._has_circular_dep(dep_id, visited.copy()):
                return True
        return False

    # ── Status Dashboard ─────────────────────────────────────

    def get_status(self) -> str:
        """Generate a markdown status dashboard."""
        lines = [
            "## Agent Coordinator Status",
            "",
            "### Agents",
            "",
            "| Agent | Role | Status | Tasks Done |",
            "|-------|------|--------|------------|",
        ]

        for agent in self.agents.values():
            status = f"Working on {agent.current_task}" if agent.current_task else "Available"
            lines.append(
                f"| {agent.name} | {agent.role} | {status} | {agent.tasks_completed} |"
            )

        lines.extend(["", "### Tasks", "", "| ID | Description | Status | Assigned | Blocked By |", "|-----|-------------|--------|----------|------------|"])

        for task in self.tasks.values():
            blocked = ", ".join(task.depends_on) if task.depends_on else "—"
            assigned = task.assigned_to or "—"
            lines.append(
                f"| {task.id} | {task.description[:40]} | {task.status.value} | {assigned} | {blocked} |"
            )

        # Conflicts
        conflicts = self.check_conflicts()
        if conflicts:
            lines.extend(["", "### Conflicts", ""])
            for c in conflicts:
                lines.append(f"- {c}")

        return "\n".join(lines)

    def get_available_tasks(self) -> list[Task]:
        """Get tasks that are ready to be worked on."""
        return [
            task for task in self.tasks.values()
            if task.status == TaskStatus.PENDING and not self._is_blocked(task.id)
        ]

    def get_agent_workload(self) -> dict[str, int]:
        """Get task count per agent (completed + in progress)."""
        workload = {}
        for agent in self.agents.values():
            active = 1 if agent.current_task else 0
            workload[agent.name] = agent.tasks_completed + active
        return workload
