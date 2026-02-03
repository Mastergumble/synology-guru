"""Learning-enabled base agent."""

from abc import abstractmethod
from typing import TYPE_CHECKING

from src.agents.base import BaseAgent, Feedback, Priority
from src.memory.models import Observation, Pattern, UserFeedback
from src.memory.store import MemoryStore

if TYPE_CHECKING:
    from src.api.client import SynologyClient


class LearningAgent(BaseAgent):
    """Base agent with learning capabilities.

    This agent can:
    - Record observations and build baselines over time
    - Detect anomalies based on learned patterns
    - Adjust sensitivity based on user feedback
    - Learn patterns to reduce false positives
    """

    # Minimum samples before using learned baselines
    MIN_SAMPLES_FOR_BASELINE = 10

    # Default anomaly sensitivity (standard deviations)
    DEFAULT_SENSITIVITY = 2.0

    def __init__(
        self,
        client: "SynologyClient",
        memory: MemoryStore | None = None,
    ) -> None:
        """Initialize learning agent."""
        super().__init__(client)
        self.memory = memory or MemoryStore()
        self._sensitivity: dict[str, float] = {}

    def observe(
        self,
        metric: str,
        value: float | int,
        context: dict | None = None,
    ) -> None:
        """Record an observation for learning."""
        observation = Observation(
            agent=self.name,
            metric=metric,
            value=value,
            context=context or {},
        )
        self.memory.record_observation(observation)

    def is_anomaly(self, metric: str, value: float) -> bool:
        """Check if a value is anomalous based on learned baseline."""
        sensitivity = self._sensitivity.get(metric, self.DEFAULT_SENSITIVITY)
        return self.memory.is_anomaly(self.name, metric, value, sensitivity)

    def get_baseline_value(self, metric: str) -> float | None:
        """Get the learned baseline mean for a metric."""
        baseline = self.memory.get_baseline(self.name, metric)
        return baseline.mean if baseline else None

    def has_sufficient_data(self, metric: str) -> bool:
        """Check if we have enough data to use learned baselines."""
        baseline = self.memory.get_baseline(self.name, metric)
        return baseline is not None and baseline.sample_count >= self.MIN_SAMPLES_FOR_BASELINE

    def get_trend(self, metric: str, days: int = 7) -> str:
        """Get trend direction for a metric."""
        return self.memory.get_trend(self.name, metric, days)

    def should_suppress_alert(self, alert_type: str, context: dict) -> bool:
        """Check if alert should be suppressed based on learned patterns."""
        patterns = self.memory.get_patterns(self.name)

        for pattern in patterns:
            if pattern.action != "ignore":
                continue
            if pattern.confidence < 0.7:
                continue

            # Check if pattern conditions match
            if self._matches_pattern(pattern, context):
                self.memory.trigger_pattern(self.name, pattern.name)
                return True

        return False

    def _matches_pattern(self, pattern: Pattern, context: dict) -> bool:
        """Check if context matches a pattern's conditions."""
        for key, expected in pattern.condition.items():
            if key not in context:
                return False
            if context[key] != expected:
                return False
        return True

    def add_feedback_with_context(
        self,
        priority: Priority,
        message: str,
        alert_type: str,
        context: dict | None = None,
        details: str | None = None,
    ) -> None:
        """Add feedback with learning context for future suppression."""
        ctx = context or {}

        # Check if we should suppress this alert
        if self.should_suppress_alert(alert_type, ctx):
            # Downgrade to INFO instead of suppressing completely
            priority = Priority.INFO
            message = f"[Suppressed] {message}"

        self.add_feedback(priority, message, details)

    def receive_user_feedback(
        self,
        alert_type: str,
        feedback: str,
        context: dict | None = None,
    ) -> None:
        """Process user feedback on an alert.

        Args:
            alert_type: Type of alert that received feedback
            feedback: One of "useful", "false_positive", "too_late", "too_sensitive"
            context: Context of the original alert
        """
        user_feedback = UserFeedback(
            agent=self.name,
            alert_type=alert_type,
            feedback=feedback,
            context=context or {},
        )
        self.memory.record_feedback(user_feedback)

        # Adjust sensitivity based on feedback
        if feedback == "too_sensitive":
            current = self._sensitivity.get(alert_type, self.DEFAULT_SENSITIVITY)
            self._sensitivity[alert_type] = min(4.0, current + 0.5)
        elif feedback == "too_late":
            current = self._sensitivity.get(alert_type, self.DEFAULT_SENSITIVITY)
            self._sensitivity[alert_type] = max(1.0, current - 0.5)

    def get_learning_status(self) -> dict:
        """Get learning status for this agent."""
        insights = self.memory.get_insights(self.name)
        return {
            "agent": self.name,
            **insights,
            "custom_sensitivities": len(self._sensitivity),
        }

    @abstractmethod
    async def check(self) -> list[Feedback]:
        """Run agent checks."""
        pass
