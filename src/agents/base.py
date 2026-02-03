"""Base agent class and feedback system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.api.client import SynologyClient


class Priority(IntEnum):
    """Feedback priority levels."""

    CRITICAL = 0  # P0 - Immediate action required
    HIGH = 1  # P1 - Urgent attention needed
    MEDIUM = 2  # P2 - Planned attention
    LOW = 3  # P3 - Informational
    INFO = 4  # P4 - Logging only

    @property
    def label(self) -> str:
        """Return human-readable label."""
        labels = {
            Priority.CRITICAL: "CRITICAL",
            Priority.HIGH: "HIGH",
            Priority.MEDIUM: "MEDIUM",
            Priority.LOW: "LOW",
            Priority.INFO: "INFO",
        }
        return labels[self]

    @property
    def emoji(self) -> str:
        """Return emoji indicator."""
        emojis = {
            Priority.CRITICAL: "\U0001f534",  # Red circle
            Priority.HIGH: "\U0001f7e0",  # Orange circle
            Priority.MEDIUM: "\U0001f7e1",  # Yellow circle
            Priority.LOW: "\U0001f7e2",  # Green circle
            Priority.INFO: "\u2139\ufe0f",  # Info
        }
        return emojis[self]


@dataclass
class Feedback:
    """Feedback item from an agent."""

    priority: Priority
    category: str
    message: str
    details: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        """Format feedback for display."""
        return f"[{self.category}] {self.message}"


class BaseAgent(ABC):
    """Base class for all specialized agents."""

    name: str = "base"
    description: str = "Base agent"

    def __init__(self, client: "SynologyClient") -> None:
        """Initialize agent with Synology API client."""
        self.client = client
        self._feedback: list[Feedback] = []

    def add_feedback(
        self,
        priority: Priority,
        message: str,
        details: str | None = None,
    ) -> None:
        """Add feedback item."""
        self._feedback.append(
            Feedback(
                priority=priority,
                category=self.name,
                message=message,
                details=details,
            )
        )

    def get_feedback(self) -> list[Feedback]:
        """Get all feedback and clear internal list."""
        feedback = self._feedback.copy()
        self._feedback.clear()
        return feedback

    @abstractmethod
    async def check(self) -> list[Feedback]:
        """Run agent checks and return feedback.

        Subclasses must implement this method to perform their specific checks.
        """
        pass

    async def run(self) -> list[Feedback]:
        """Execute agent and return feedback."""
        await self.check()
        return self.get_feedback()
