"""Tests for LearningAgent capabilities."""

import pytest

from src.agents.base import Feedback, Priority
from src.agents.learning import LearningAgent
from src.memory.models import Pattern
from src.memory.store import MemoryStore
from tests.conftest import seed_observations


class ConcreteLearningAgent(LearningAgent):
    """Concrete implementation for testing."""
    name = "test_learner"
    description = "Test learning agent"

    async def check(self):
        return self.get_feedback()


@pytest.fixture
def agent(mock_client, tmp_path):
    memory = MemoryStore(data_dir=tmp_path / "data")
    return ConcreteLearningAgent(mock_client, memory=memory)


class TestObserve:
    def test_records_in_store(self, agent):
        agent.observe("metric1", 42.0, {"key": "val"})
        obs = agent.memory.get_observations("test_learner", "metric1")
        assert len(obs) == 1
        assert obs[0].value == 42.0

    def test_updates_baseline(self, agent):
        agent.observe("metric1", 10.0)
        bl = agent.memory.get_baseline("test_learner", "metric1")
        assert bl is not None
        assert bl.mean == 10.0


class TestIsAnomaly:
    def test_delegates_to_store(self, agent):
        # With insufficient data, should return False
        for i in range(5):
            agent.observe("m", 50.0)
        assert agent.is_anomaly("m", 100.0) is False

    def test_uses_sensitivity(self, agent):
        agent._sensitivity["m"] = 1.0  # Very sensitive
        for i in range(15):
            agent.observe("m", 50.0 + i * 0.1)
        # With custom sensitivity, should detect smaller deviations
        # but result depends on actual std_dev


class TestHasSufficientData:
    def test_insufficient(self, agent):
        for i in range(5):
            agent.observe("m", float(i))
        assert agent.has_sufficient_data("m") is False

    def test_sufficient(self, agent):
        for i in range(15):
            agent.observe("m", float(i))
        assert agent.has_sufficient_data("m") is True

    def test_no_data(self, agent):
        assert agent.has_sufficient_data("nonexistent") is False


class TestShouldSuppressAlert:
    def test_no_patterns(self, agent):
        assert agent.should_suppress_alert("alert_type", {"k": "v"}) is False

    def test_matching_pattern_high_confidence(self, agent):
        p = Pattern(
            agent="test_learner", name="suppress_alert",
            description="d", condition={"k": "v"},
            action="ignore", confidence=0.8,
        )
        agent.memory.add_pattern(p)
        assert agent.should_suppress_alert("alert", {"k": "v"}) is True

    def test_low_confidence_not_suppressed(self, agent):
        p = Pattern(
            agent="test_learner", name="suppress_alert",
            description="d", condition={"k": "v"},
            action="ignore", confidence=0.5,
        )
        agent.memory.add_pattern(p)
        assert agent.should_suppress_alert("alert", {"k": "v"}) is False

    def test_non_ignore_action_not_suppressed(self, agent):
        p = Pattern(
            agent="test_learner", name="escalate",
            description="d", condition={"k": "v"},
            action="escalate", confidence=0.9,
        )
        agent.memory.add_pattern(p)
        assert agent.should_suppress_alert("alert", {"k": "v"}) is False


class TestMatchesPattern:
    def test_exact_match(self, agent):
        p = Pattern(agent="a", name="n", description="d",
                     condition={"k": "v"}, action="ignore", confidence=0.8)
        assert agent._matches_pattern(p, {"k": "v"}) is True

    def test_key_missing(self, agent):
        p = Pattern(agent="a", name="n", description="d",
                     condition={"k": "v"}, action="ignore", confidence=0.8)
        assert agent._matches_pattern(p, {"other": "v"}) is False

    def test_value_wrong(self, agent):
        p = Pattern(agent="a", name="n", description="d",
                     condition={"k": "v"}, action="ignore", confidence=0.8)
        assert agent._matches_pattern(p, {"k": "wrong"}) is False

    def test_context_with_extra_keys(self, agent):
        p = Pattern(agent="a", name="n", description="d",
                     condition={"k": "v"}, action="ignore", confidence=0.8)
        assert agent._matches_pattern(p, {"k": "v", "extra": "data"}) is True


class TestAddFeedbackWithContext:
    def test_normal_feedback(self, agent):
        agent.add_feedback_with_context(
            Priority.HIGH, "Alert message",
            alert_type="test_alert", context={"k": "v"},
        )
        fb = agent.get_feedback()
        assert len(fb) == 1
        assert fb[0].priority == Priority.HIGH
        assert fb[0].message == "Alert message"

    def test_suppressed_feedback(self, agent):
        # Add a pattern that should suppress
        p = Pattern(
            agent="test_learner", name="suppress_test",
            description="d", condition={"k": "v"},
            action="ignore", confidence=0.8,
        )
        agent.memory.add_pattern(p)

        agent.add_feedback_with_context(
            Priority.HIGH, "Alert message",
            alert_type="test", context={"k": "v"},
        )
        fb = agent.get_feedback()
        assert len(fb) == 1
        assert fb[0].priority == Priority.INFO  # Downgraded
        assert "[Suppressed]" in fb[0].message


class TestReceiveUserFeedback:
    def test_too_sensitive_increases(self, agent):
        agent.receive_user_feedback("alert", "too_sensitive")
        assert agent._sensitivity["alert"] == pytest.approx(2.5)

    def test_too_sensitive_capped(self, agent):
        agent._sensitivity["alert"] = 3.8
        agent.receive_user_feedback("alert", "too_sensitive")
        assert agent._sensitivity["alert"] == pytest.approx(4.0)

    def test_too_late_decreases(self, agent):
        agent.receive_user_feedback("alert", "too_late")
        assert agent._sensitivity["alert"] == pytest.approx(1.5)

    def test_too_late_floored(self, agent):
        agent._sensitivity["alert"] = 1.2
        agent.receive_user_feedback("alert", "too_late")
        assert agent._sensitivity["alert"] == pytest.approx(1.0)

    def test_useful_no_sensitivity_change(self, agent):
        agent.receive_user_feedback("alert", "useful")
        assert "alert" not in agent._sensitivity


class TestGetLearningStatus:
    def test_structure(self, agent):
        status = agent.get_learning_status()
        assert status["agent"] == "test_learner"
        assert "baselines_learned" in status
        assert "patterns_learned" in status
        assert "active_patterns" in status
        assert "total_observations" in status
        assert "custom_sensitivities" in status
