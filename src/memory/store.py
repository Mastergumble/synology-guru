"""Persistent memory store for agent learning."""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import Baseline, Observation, Pattern, UserFeedback


class MemoryStore:
    """Persistent storage for agent observations and learned patterns."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        """Initialize memory store."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._observations_file = self.data_dir / "observations.json"
        self._baselines_file = self.data_dir / "baselines.json"
        self._patterns_file = self.data_dir / "patterns.json"
        self._feedback_file = self.data_dir / "feedback.json"

        # In-memory caches
        self._observations: list[Observation] = []
        self._baselines: dict[str, Baseline] = {}  # key: "agent:metric"
        self._patterns: dict[str, Pattern] = {}  # key: "agent:name"
        self._feedback: list[UserFeedback] = []

        self._load_all()

    def _load_all(self) -> None:
        """Load all data from disk."""
        self._load_observations()
        self._load_baselines()
        self._load_patterns()
        self._load_feedback()

    def _load_observations(self) -> None:
        """Load observations from disk."""
        if self._observations_file.exists():
            try:
                data = json.loads(self._observations_file.read_text())
                self._observations = [Observation.from_dict(o) for o in data]
            except (json.JSONDecodeError, KeyError):
                self._observations = []

    def _load_baselines(self) -> None:
        """Load baselines from disk."""
        if self._baselines_file.exists():
            try:
                data = json.loads(self._baselines_file.read_text())
                self._baselines = {
                    f"{b['agent']}:{b['metric']}": Baseline.from_dict(b)
                    for b in data
                }
            except (json.JSONDecodeError, KeyError):
                self._baselines = {}

    def _load_patterns(self) -> None:
        """Load patterns from disk."""
        if self._patterns_file.exists():
            try:
                data = json.loads(self._patterns_file.read_text())
                self._patterns = {
                    f"{p['agent']}:{p['name']}": Pattern.from_dict(p)
                    for p in data
                }
            except (json.JSONDecodeError, KeyError):
                self._patterns = {}

    def _load_feedback(self) -> None:
        """Load user feedback from disk."""
        if self._feedback_file.exists():
            try:
                data = json.loads(self._feedback_file.read_text())
                self._feedback = [UserFeedback(**f) for f in data]
            except (json.JSONDecodeError, KeyError):
                self._feedback = []

    def _save_observations(self) -> None:
        """Save observations to disk."""
        # Keep only last 30 days of observations
        cutoff = datetime.now() - timedelta(days=30)
        self._observations = [o for o in self._observations if o.timestamp > cutoff]

        data = [o.to_dict() for o in self._observations]
        self._observations_file.write_text(json.dumps(data, indent=2))

    def _save_baselines(self) -> None:
        """Save baselines to disk."""
        data = [b.to_dict() for b in self._baselines.values()]
        self._baselines_file.write_text(json.dumps(data, indent=2))

    def _save_patterns(self) -> None:
        """Save patterns to disk."""
        data = [p.to_dict() for p in self._patterns.values()]
        self._patterns_file.write_text(json.dumps(data, indent=2))

    def _save_feedback(self) -> None:
        """Save feedback to disk."""
        data = [f.to_dict() for f in self._feedback]
        self._feedback_file.write_text(json.dumps(data, indent=2))

    # ========== Observations ==========

    def record_observation(self, observation: Observation) -> None:
        """Record a new observation."""
        self._observations.append(observation)
        self._save_observations()

        # Update baseline with new observation
        if isinstance(observation.value, (int, float)):
            self._update_baseline(observation)

    def get_observations(
        self,
        agent: str,
        metric: str,
        since: datetime | None = None,
    ) -> list[Observation]:
        """Get observations for an agent/metric."""
        results = [
            o for o in self._observations
            if o.agent == agent and o.metric == metric
        ]
        if since:
            results = [o for o in results if o.timestamp > since]
        return sorted(results, key=lambda o: o.timestamp)

    # ========== Baselines ==========

    def _update_baseline(self, observation: Observation) -> None:
        """Update baseline with new observation using incremental statistics."""
        key = f"{observation.agent}:{observation.metric}"
        value = float(observation.value)

        if key not in self._baselines:
            # Create new baseline
            self._baselines[key] = Baseline(
                agent=observation.agent,
                metric=observation.metric,
                mean=value,
                std_dev=0.0,
                min_value=value,
                max_value=value,
                sample_count=1,
            )
        else:
            # Update existing baseline using Welford's algorithm
            baseline = self._baselines[key]
            n = baseline.sample_count + 1
            delta = value - baseline.mean
            new_mean = baseline.mean + delta / n

            # Update variance incrementally
            delta2 = value - new_mean
            new_variance = (
                (baseline.std_dev ** 2 * (n - 1) + delta * delta2) / n
                if n > 1 else 0
            )

            baseline.mean = new_mean
            baseline.std_dev = math.sqrt(new_variance)
            baseline.min_value = min(baseline.min_value, value)
            baseline.max_value = max(baseline.max_value, value)
            baseline.sample_count = n
            baseline.last_updated = datetime.now()

        self._save_baselines()

    def get_baseline(self, agent: str, metric: str) -> Baseline | None:
        """Get baseline for an agent/metric."""
        return self._baselines.get(f"{agent}:{metric}")

    def is_anomaly(
        self,
        agent: str,
        metric: str,
        value: float,
        sensitivity: float = 2.0,
    ) -> bool:
        """Check if value is anomalous compared to baseline."""
        baseline = self.get_baseline(agent, metric)
        if baseline is None or baseline.sample_count < 10:
            return False  # Not enough data
        return baseline.is_anomaly(value, sensitivity)

    # ========== Patterns ==========

    def add_pattern(self, pattern: Pattern) -> None:
        """Add or update a pattern."""
        key = f"{pattern.agent}:{pattern.name}"
        self._patterns[key] = pattern
        self._save_patterns()

    def get_patterns(self, agent: str) -> list[Pattern]:
        """Get all patterns for an agent."""
        return [p for p in self._patterns.values() if p.agent == agent]

    def get_pattern(self, agent: str, name: str) -> Pattern | None:
        """Get a specific pattern."""
        return self._patterns.get(f"{agent}:{name}")

    def trigger_pattern(self, agent: str, name: str) -> None:
        """Record that a pattern was triggered."""
        pattern = self.get_pattern(agent, name)
        if pattern:
            pattern.occurrences += 1
            pattern.last_triggered = datetime.now()
            self._save_patterns()

    # ========== User Feedback ==========

    def record_feedback(self, feedback: UserFeedback) -> None:
        """Record user feedback on an alert."""
        self._feedback.append(feedback)
        self._save_feedback()

        # Auto-learn from feedback
        self._learn_from_feedback(feedback)

    def _learn_from_feedback(self, feedback: UserFeedback) -> None:
        """Automatically adjust based on user feedback."""
        if feedback.feedback == "false_positive":
            # Create or strengthen a pattern to suppress similar alerts
            pattern_name = f"suppress_{feedback.alert_type}"
            existing = self.get_pattern(feedback.agent, pattern_name)

            if existing:
                existing.confidence = min(1.0, existing.confidence + 0.1)
                existing.occurrences += 1
            else:
                pattern = Pattern(
                    agent=feedback.agent,
                    name=pattern_name,
                    description=f"Auto-learned: suppress {feedback.alert_type} alerts",
                    condition=feedback.context,
                    action="ignore",
                    confidence=0.5,
                    occurrences=1,
                )
                self.add_pattern(pattern)

    def get_false_positive_rate(self, agent: str, alert_type: str) -> float:
        """Calculate false positive rate for an alert type."""
        relevant = [
            f for f in self._feedback
            if f.agent == agent and f.alert_type == alert_type
        ]
        if not relevant:
            return 0.0
        false_positives = sum(1 for f in relevant if f.feedback == "false_positive")
        return false_positives / len(relevant)

    # ========== Learning Insights ==========

    def get_trend(
        self,
        agent: str,
        metric: str,
        days: int = 7,
    ) -> str:
        """Get trend direction for a metric."""
        since = datetime.now() - timedelta(days=days)
        observations = self.get_observations(agent, metric, since)

        if len(observations) < 2:
            return "unknown"

        values = [o.value for o in observations if isinstance(o.value, (int, float))]
        if len(values) < 2:
            return "unknown"

        # Simple linear trend
        first_half = sum(values[:len(values)//2]) / (len(values)//2)
        second_half = sum(values[len(values)//2:]) / (len(values) - len(values)//2)

        diff_pct = (second_half - first_half) / first_half * 100 if first_half != 0 else 0

        if diff_pct > 10:
            return "increasing"
        elif diff_pct < -10:
            return "decreasing"
        return "stable"

    def get_insights(self, agent: str) -> dict[str, Any]:
        """Get learning insights for an agent."""
        baselines = {
            k.split(":")[1]: v
            for k, v in self._baselines.items()
            if k.startswith(f"{agent}:")
        }

        patterns = self.get_patterns(agent)
        active_patterns = [p for p in patterns if p.confidence >= 0.7]

        return {
            "baselines_learned": len(baselines),
            "patterns_learned": len(patterns),
            "active_patterns": len(active_patterns),
            "total_observations": sum(
                1 for o in self._observations if o.agent == agent
            ),
        }
