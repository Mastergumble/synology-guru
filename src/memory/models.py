"""Data models for agent memory and learning."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Observation:
    """A single observation recorded by an agent."""

    agent: str
    metric: str
    value: Any
    timestamp: datetime = field(default_factory=datetime.now)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "agent": self.agent,
            "metric": self.metric,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        """Create from dictionary."""
        return cls(
            agent=data["agent"],
            metric=data["metric"],
            value=data["value"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            context=data.get("context", {}),
        )


@dataclass
class Baseline:
    """Learned baseline for a metric."""

    agent: str
    metric: str
    mean: float
    std_dev: float
    min_value: float
    max_value: float
    sample_count: int
    last_updated: datetime = field(default_factory=datetime.now)

    def is_anomaly(self, value: float, sensitivity: float = 2.0) -> bool:
        """Check if value is anomalous based on baseline."""
        if self.std_dev == 0:
            return value != self.mean
        z_score = abs(value - self.mean) / self.std_dev
        return z_score > sensitivity

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "agent": self.agent,
            "metric": self.metric,
            "mean": self.mean,
            "std_dev": self.std_dev,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "sample_count": self.sample_count,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Baseline":
        """Create from dictionary."""
        return cls(
            agent=data["agent"],
            metric=data["metric"],
            mean=data["mean"],
            std_dev=data["std_dev"],
            min_value=data["min_value"],
            max_value=data["max_value"],
            sample_count=data["sample_count"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
        )


@dataclass
class Pattern:
    """A learned pattern or rule."""

    agent: str
    name: str
    description: str
    condition: dict[str, Any]  # Conditions that trigger this pattern
    action: str  # What to do: "ignore", "escalate", "adjust_threshold"
    confidence: float  # 0.0 to 1.0
    occurrences: int = 0
    last_triggered: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "agent": self.agent,
            "name": self.name,
            "description": self.description,
            "condition": self.condition,
            "action": self.action,
            "confidence": self.confidence,
            "occurrences": self.occurrences,
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Pattern":
        """Create from dictionary."""
        return cls(
            agent=data["agent"],
            name=data["name"],
            description=data["description"],
            condition=data["condition"],
            action=data["action"],
            confidence=data["confidence"],
            occurrences=data.get("occurrences", 0),
            last_triggered=(
                datetime.fromisoformat(data["last_triggered"])
                if data.get("last_triggered")
                else None
            ),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class UserFeedback:
    """User feedback on an alert to improve learning."""

    agent: str
    alert_type: str
    feedback: str  # "useful", "false_positive", "too_late", "too_sensitive"
    context: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "agent": self.agent,
            "alert_type": self.alert_type,
            "feedback": self.feedback,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }
