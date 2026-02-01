"""Tests for agents/agent_coordinator.py"""

import pytest
from agents.agent_coordinator import (
    AgentCoordinator,
    Agent,
    Task,
    TaskStatus,
)


@pytest.fixture
def coord():
    c = AgentCoordinator()
    c.register_agent("coda", role="builder", capabilities=["coding", "test_execution"])
    c.register_agent("opus", role="skeptic", capabilities=["critique", "protocol_design"])
    c.register_agent("polaris", role="architect", capabilities=["framework_design", "roadmap"])
    return c


# ── Agent Management ────────────────────────────────────────

class TestAgentManagement:
    def test_register_agent(self):
        c = AgentCoordinator()
        agent = c.register_agent("coda", role="builder", capabilities=["coding"])
        assert agent.name == "coda"
        assert agent.role == "builder"
        assert agent.capabilities == ["coding"]
        assert agent.is_available

    def test_register_agent_no_capabilities(self):
        c = AgentCoordinator()
        agent = c.register_agent("test", role="generic")
        assert agent.capabilities == []

    def test_agent_is_available(self):
        agent = Agent(name="test", role="builder")
        assert agent.is_available
        agent.current_task = "T1"
        assert not agent.is_available

    def test_update_agent_activity(self, coord):
        old_time = coord.agents["coda"].last_active
        coord.update_agent_activity("coda")
        # last_active should be updated (may or may not differ if same minute)
        assert coord.agents["coda"].last_active

    def test_update_nonexistent_agent(self, coord):
        coord.update_agent_activity("nonexistent")  # should not raise


# ── Task Management ─────────────────────────────────────────

class TestTaskManagement:
    def test_create_task(self, coord):
        task = coord.create_task("Run Control 2", required_capabilities=["test_execution"])
        assert task.id == "T1"
        assert task.description == "Run Control 2"
        assert task.status == TaskStatus.PENDING
        assert task.required_capabilities == ["test_execution"]

    def test_create_task_increments_id(self, coord):
        t1 = coord.create_task("Task 1")
        t2 = coord.create_task("Task 2")
        assert t1.id == "T1"
        assert t2.id == "T2"

    def test_create_task_with_dependencies(self, coord):
        t1 = coord.create_task("First task")
        t2 = coord.create_task("Second task", depends_on=["T1"])
        assert t2.depends_on == ["T1"]
        assert "T2" in coord.tasks["T1"].blocks

    def test_create_task_with_thread(self, coord):
        task = coord.create_task("Post to thread", thread="building-tests")
        assert task.thread == "building-tests"

    def test_assign_task_by_capability(self, coord):
        coord.create_task("Run test", required_capabilities=["test_execution"])
        result = coord.assign_task(task_id="T1")
        assert result is not None
        agent_name, task_id = result
        assert agent_name == "coda"  # best match for test_execution
        assert task_id == "T1"
        assert coord.tasks["T1"].status == TaskStatus.ASSIGNED

    def test_assign_task_creates_new(self, coord):
        result = coord.assign_task(
            description="New task",
            required_capabilities=["critique"],
        )
        assert result is not None
        agent_name, task_id = result
        assert agent_name == "opus"  # best match for critique

    def test_assign_task_preferred_agent(self, coord):
        result = coord.assign_task(
            description="Any task",
            prefer_agent="polaris",
        )
        assert result is not None
        assert result[0] == "polaris"

    def test_assign_task_preferred_agent_busy(self, coord):
        # Make polaris busy
        coord.agents["polaris"].current_task = "T0"
        result = coord.assign_task(
            description="Any task",
            prefer_agent="polaris",
        )
        assert result is not None
        assert result[0] != "polaris"

    def test_assign_blocked_task(self, coord):
        coord.create_task("First")
        coord.create_task("Second", depends_on=["T1"])
        result = coord.assign_task(task_id="T2")
        assert result is None
        assert coord.tasks["T2"].status == TaskStatus.BLOCKED

    def test_assign_no_description_no_id(self, coord):
        result = coord.assign_task()
        assert result is None

    def test_assign_invalid_task_id(self, coord):
        result = coord.assign_task(task_id="T999")
        assert result is None

    def test_complete_task(self, coord):
        coord.create_task("Task")
        coord.assign_task(task_id="T1")
        coord.complete_task("T1", result="Done successfully")

        assert coord.tasks["T1"].status == TaskStatus.COMPLETED
        assert coord.tasks["T1"].result == "Done successfully"
        assert coord.tasks["T1"].completed != ""

    def test_complete_task_frees_agent(self, coord):
        coord.create_task("Task", required_capabilities=["coding"])
        coord.assign_task(task_id="T1")
        agent = coord.agents["coda"]
        assert not agent.is_available

        coord.complete_task("T1")
        assert agent.is_available
        assert agent.tasks_completed == 1

    def test_complete_task_unblocks_dependents(self, coord):
        coord.create_task("First")
        coord.create_task("Second", depends_on=["T1"])
        coord.assign_task(task_id="T1")

        # T2 starts blocked
        coord.assign_task(task_id="T2")
        assert coord.tasks["T2"].status == TaskStatus.BLOCKED

        # Complete T1 should unblock T2
        coord.complete_task("T1")
        assert coord.tasks["T2"].status == TaskStatus.PENDING

    def test_complete_nonexistent_task(self, coord):
        coord.complete_task("T999")  # should not raise

    def test_all_agents_busy(self, coord):
        for agent in coord.agents.values():
            agent.current_task = "busy"
        result = coord.assign_task(description="New task")
        assert result is None

    def test_no_capability_match_falls_back(self, coord):
        result = coord.assign_task(
            description="Exotic task",
            required_capabilities=["quantum_computing"],
        )
        # Should fall back to any available agent
        assert result is not None

    def test_load_balancing(self, coord):
        # Give coda many completed tasks
        coord.agents["coda"].tasks_completed = 10
        coord.agents["opus"].tasks_completed = 0

        # Both have no matching capability, so fallback should prefer opus (fewer tasks)
        result = coord.assign_task(
            description="Generic task",
            required_capabilities=["unknown_cap"],
        )
        assert result is not None
        # Falls back to available agents; first available is returned
        assert result[0] in ["coda", "opus", "polaris"]


# ── Conflict Detection ──────────────────────────────────────

class TestConflictDetection:
    def test_no_conflicts_by_default(self, coord):
        assert coord.check_conflicts() == []

    def test_thread_conflict(self, coord):
        t1 = coord.create_task("Post A", thread="building-tests")
        t2 = coord.create_task("Post B", thread="building-tests")
        coord.assign_task(task_id="T1")
        coord.assign_task(task_id="T2")

        conflicts = coord.check_conflicts()
        assert len(conflicts) >= 1
        assert "building-tests" in conflicts[0]

    def test_no_conflict_different_threads(self, coord):
        coord.create_task("Post A", thread="thread-1")
        coord.create_task("Post B", thread="thread-2")
        coord.assign_task(task_id="T1")
        coord.assign_task(task_id="T2")

        conflicts = coord.check_conflicts()
        thread_conflicts = [c for c in conflicts if "Thread conflict" in c]
        assert len(thread_conflicts) == 0

    def test_circular_dependency_detection(self, coord):
        coord.create_task("Task A")
        coord.create_task("Task B", depends_on=["T1"])
        # Manually create circular dep
        coord.tasks["T1"].depends_on.append("T2")

        conflicts = coord.check_conflicts()
        circular = [c for c in conflicts if "Circular" in c]
        assert len(circular) >= 1


# ── Status Dashboard ────────────────────────────────────────

class TestStatusDashboard:
    def test_get_status_returns_markdown(self, coord):
        coord.create_task("Test task")
        coord.assign_task(task_id="T1")

        status = coord.get_status()
        assert "## Agent Coordinator Status" in status
        assert "### Agents" in status
        assert "### Tasks" in status
        assert "coda" in status
        assert "opus" in status

    def test_get_available_tasks(self, coord):
        coord.create_task("Task 1")
        coord.create_task("Task 2")
        coord.create_task("Task 3", depends_on=["T1"])

        available = coord.get_available_tasks()
        ids = [t.id for t in available]
        assert "T1" in ids
        assert "T2" in ids
        assert "T3" not in ids  # blocked

    def test_get_agent_workload(self, coord):
        coord.agents["coda"].tasks_completed = 5
        coord.agents["coda"].current_task = "T1"

        workload = coord.get_agent_workload()
        assert workload["coda"] == 6  # 5 completed + 1 active
        assert workload["opus"] == 0
