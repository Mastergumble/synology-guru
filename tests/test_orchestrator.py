"""Tests for the SynologyGuru orchestrator."""

import pytest
from unittest.mock import MagicMock

from src.agents.base import BaseAgent, Feedback, Priority
from src.orchestrator.orchestrator import AgentResult, SynologyGuru


class FakeAgent(BaseAgent):
    """Fake agent for orchestrator testing."""
    name = "fake"
    description = "Fake agent"

    def __init__(self, client, feedback_items=None, should_raise=False):
        super().__init__(client)
        self._preset_feedback = feedback_items or []
        self._should_raise = should_raise

    async def check(self):
        if self._should_raise:
            raise RuntimeError("Agent exploded")
        for fb in self._preset_feedback:
            self.add_feedback(fb.priority, fb.message, fb.details)
        return self._feedback.copy()


@pytest.fixture
def guru(mock_client):
    return SynologyGuru(mock_client)


class TestRegisterAgents:
    def test_register_agent(self, guru, mock_client):
        agent = FakeAgent(mock_client)
        guru.register_agent(agent)
        assert len(guru.agents) == 1

    def test_register_agents(self, guru, mock_client):
        agents = [FakeAgent(mock_client), FakeAgent(mock_client)]
        guru.register_agents(agents)
        assert len(guru.agents) == 2


class TestRunAgent:
    async def test_success(self, guru, mock_client):
        agent = FakeAgent(mock_client, feedback_items=[
            Feedback(priority=Priority.LOW, category="fake", message="All good"),
        ])
        result = await guru.run_agent(agent)
        assert result.agent_name == "fake"
        assert len(result.feedback) == 1
        assert result.error is None

    async def test_exception(self, guru, mock_client):
        agent = FakeAgent(mock_client, should_raise=True)
        result = await guru.run_agent(agent)
        assert result.agent_name == "fake"
        assert result.feedback == []
        assert result.error == "Agent exploded"


class TestRunAllAgents:
    async def test_concurrent_execution(self, guru, mock_client):
        a1 = FakeAgent(mock_client, feedback_items=[
            Feedback(priority=Priority.LOW, category="fake", message="OK"),
        ])
        a1.name = "agent1"
        a2 = FakeAgent(mock_client, feedback_items=[
            Feedback(priority=Priority.HIGH, category="fake", message="Alert"),
        ])
        a2.name = "agent2"

        guru.register_agents([a1, a2])
        results = await guru.run_all_agents()

        assert len(results) == 2
        names = {r.agent_name for r in results}
        assert "agent1" in names
        assert "agent2" in names


class TestAggregateFeedback:
    def test_sorted_by_priority(self, guru):
        results = [
            AgentResult(agent_name="a", feedback=[
                Feedback(priority=Priority.LOW, category="a", message="Low"),
                Feedback(priority=Priority.CRITICAL, category="a", message="Critical"),
            ]),
            AgentResult(agent_name="b", feedback=[
                Feedback(priority=Priority.HIGH, category="b", message="High"),
            ]),
        ]
        aggregated = guru.aggregate_feedback(results)
        priorities = [f.priority for f in aggregated]
        assert priorities == sorted(priorities)

    def test_errors_become_high(self, guru):
        results = [
            AgentResult(agent_name="broken", feedback=[], error="Connection refused"),
        ]
        aggregated = guru.aggregate_feedback(results)
        assert len(aggregated) == 1
        assert aggregated[0].priority == Priority.HIGH
        assert "Agent error" in aggregated[0].message

    def test_filter_min_priority(self, guru):
        results = [
            AgentResult(agent_name="a", feedback=[
                Feedback(priority=Priority.INFO, category="a", message="Info"),
                Feedback(priority=Priority.LOW, category="a", message="Low"),
                Feedback(priority=Priority.HIGH, category="a", message="High"),
            ]),
        ]
        # min_priority=MEDIUM means only CRITICAL, HIGH, MEDIUM pass (value <= 2)
        aggregated = guru.aggregate_feedback(results, min_priority=Priority.MEDIUM)
        assert len(aggregated) == 1
        assert aggregated[0].priority == Priority.HIGH

    def test_empty_results(self, guru):
        aggregated = guru.aggregate_feedback([])
        assert aggregated == []
