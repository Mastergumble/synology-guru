"""Tests for base agent classes."""

import pytest

from src.agents.base import BaseAgent, Feedback, Priority


class TestPriority:
    def test_ordering(self):
        assert Priority.CRITICAL < Priority.HIGH < Priority.MEDIUM < Priority.LOW < Priority.INFO

    def test_int_values(self):
        assert int(Priority.CRITICAL) == 0
        assert int(Priority.HIGH) == 1
        assert int(Priority.MEDIUM) == 2
        assert int(Priority.LOW) == 3
        assert int(Priority.INFO) == 4

    def test_labels(self):
        assert Priority.CRITICAL.label == "CRITICAL"
        assert Priority.HIGH.label == "HIGH"
        assert Priority.MEDIUM.label == "MEDIUM"
        assert Priority.LOW.label == "LOW"
        assert Priority.INFO.label == "INFO"


class TestFeedback:
    def test_str(self):
        fb = Feedback(priority=Priority.HIGH, category="storage", message="Disk full")
        assert str(fb) == "[storage] Disk full"

    def test_timestamp_auto(self):
        from datetime import datetime
        fb = Feedback(priority=Priority.LOW, category="test", message="msg")
        assert isinstance(fb.timestamp, datetime)


class ConcreteAgent(BaseAgent):
    """Concrete implementation for testing."""
    name = "test"
    description = "Test agent"

    async def check(self):
        self.add_feedback(Priority.LOW, "All good")
        return self._feedback.copy()


class TestBaseAgent:
    def test_add_feedback(self, mock_client):
        agent = ConcreteAgent(mock_client)
        agent.add_feedback(Priority.HIGH, "Alert", details="Details here")
        assert len(agent._feedback) == 1
        assert agent._feedback[0].priority == Priority.HIGH
        assert agent._feedback[0].category == "test"

    def test_get_feedback_returns_and_clears(self, mock_client):
        agent = ConcreteAgent(mock_client)
        agent.add_feedback(Priority.LOW, "msg")
        fb = agent.get_feedback()
        assert len(fb) == 1
        assert len(agent._feedback) == 0

    async def test_run_calls_check(self, mock_client):
        agent = ConcreteAgent(mock_client)
        result = await agent.run()
        assert len(result) == 1
        assert result[0].message == "All good"

    async def test_run_returns_list(self, mock_client):
        agent = ConcreteAgent(mock_client)
        result = await agent.run()
        assert isinstance(result, list)
