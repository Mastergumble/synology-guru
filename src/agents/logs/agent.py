"""Log monitoring agent with learning capabilities."""

import re
from collections import Counter

from src.agents.learning import LearningAgent
from src.agents.base import Feedback, Priority


class LogsAgent(LearningAgent):
    """Agent for monitoring and analyzing system logs with learning.

    Learning features:
    - Learns normal log volume patterns
    - Detects unusual error frequency spikes
    - Identifies recurring issues
    - Adapts to system-specific log patterns
    """

    name = "logs"
    description = "Monitors system logs for errors and anomalies"

    # Patterns to detect in logs
    ERROR_PATTERNS = [
        (r"critical|emergency|fatal", Priority.CRITICAL),
        (r"error|failed|failure", Priority.HIGH),
        (r"warning|warn", Priority.MEDIUM),
    ]

    # Keywords that indicate serious issues
    CRITICAL_KEYWORDS = [
        "disk failure",
        "raid degraded",
        "volume crashed",
        "out of memory",
        "kernel panic",
        "data corruption",
        "hardware error",
        "temperature critical",
    ]

    async def check(self) -> list[Feedback]:
        """Check system logs for issues."""
        try:
            logs = await self.client.get_system_logs(limit=500)
            await self._analyze_logs(logs)
        except Exception as e:
            self.add_feedback(
                Priority.MEDIUM,
                f"Could not retrieve system logs: {e}",
            )

        return self.get_feedback()

    async def _analyze_logs(self, logs: dict) -> None:
        """Analyze log entries with learning."""
        entries = logs.get("logs", [])

        if not entries:
            self.add_feedback(
                Priority.INFO,
                "No recent log entries to analyze",
            )
            return

        # Count issues by priority
        issue_counts = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 0,
            Priority.MEDIUM: 0,
        }
        critical_messages: list[str] = []
        error_categories: Counter = Counter()

        for entry in entries:
            message = entry.get("message", "").lower()
            level = entry.get("level", "").lower()
            source = entry.get("source", "unknown")

            # Check for critical keywords
            for keyword in self.CRITICAL_KEYWORDS:
                if keyword in message:
                    issue_counts[Priority.CRITICAL] += 1
                    error_categories[keyword] += 1
                    if len(critical_messages) < 3:
                        critical_messages.append(entry.get("message", "")[:100])
                    break
            else:
                # Check log level patterns
                for pattern, priority in self.ERROR_PATTERNS:
                    if re.search(pattern, level) or re.search(pattern, message):
                        issue_counts[priority] += 1
                        error_categories[source] += 1
                        break

        # Record observations for learning
        total_entries = len(entries)
        total_errors = issue_counts[Priority.CRITICAL] + issue_counts[Priority.HIGH]
        error_rate = (total_errors / total_entries * 100) if total_entries > 0 else 0

        self.observe("log_entries_count", total_entries)
        self.observe("error_count", total_errors)
        self.observe("error_rate", error_rate)
        self.observe("critical_count", issue_counts[Priority.CRITICAL])
        self.observe("warning_count", issue_counts[Priority.MEDIUM])

        # Check for anomalies
        await self._check_log_anomalies(issue_counts, total_entries)

        # Check for recurring issues
        await self._check_recurring_issues(error_categories)

        # Report findings with learning context
        await self._report_findings(issue_counts, critical_messages, total_entries)

    async def _check_log_anomalies(
        self,
        issue_counts: dict,
        total_entries: int,
    ) -> None:
        """Detect unusual log patterns."""
        # Check for error count anomaly
        total_errors = issue_counts[Priority.CRITICAL] + issue_counts[Priority.HIGH]

        if self.has_sufficient_data("error_count"):
            if self.is_anomaly("error_count", total_errors):
                baseline = self.get_baseline_value("error_count")
                if baseline and total_errors > baseline * 2:
                    self.add_feedback_with_context(
                        Priority.HIGH,
                        f"Unusual spike in log errors: {total_errors} errors",
                        alert_type="log_error_spike",
                        context={"error_count": total_errors},
                        details=f"Normal: ~{baseline:.0f} errors",
                    )

        # Check for log volume anomaly (could indicate issues or log spam)
        if self.has_sufficient_data("log_entries_count"):
            if self.is_anomaly("log_entries_count", total_entries):
                baseline = self.get_baseline_value("log_entries_count")
                if baseline:
                    if total_entries > baseline * 3:
                        self.add_feedback_with_context(
                            Priority.MEDIUM,
                            f"Unusual log volume: {total_entries} entries",
                            alert_type="log_volume_high",
                            context={"count": total_entries},
                            details=f"Normal: ~{baseline:.0f} entries - possible log spam or issues",
                        )
                    elif total_entries < baseline * 0.2:
                        self.add_feedback_with_context(
                            Priority.MEDIUM,
                            f"Unusually low log volume: {total_entries} entries",
                            alert_type="log_volume_low",
                            context={"count": total_entries},
                            details=f"Normal: ~{baseline:.0f} entries - logging may be broken",
                        )

    async def _check_recurring_issues(self, error_categories: Counter) -> None:
        """Detect recurring issues that need attention."""
        if not error_categories:
            return

        # Find most common error sources
        most_common = error_categories.most_common(3)

        for source, count in most_common:
            if count >= 5:  # Recurring threshold
                metric_name = f"recurring_{source.replace(' ', '_')}"
                self.observe(metric_name, count)

                # Check if this is getting worse
                trend = self.get_trend(metric_name)
                if trend == "increasing":
                    self.add_feedback_with_context(
                        Priority.MEDIUM,
                        f"Recurring issue increasing: '{source}' ({count} occurrences)",
                        alert_type="recurring_issue",
                        context={"source": source, "count": count},
                        details="This issue is becoming more frequent",
                    )

    async def _report_findings(
        self,
        issue_counts: dict,
        critical_messages: list[str],
        total_entries: int,
    ) -> None:
        """Report log analysis findings."""
        # Get trends for context
        error_trend = self.get_trend("error_count")
        trend_info = ""
        if error_trend == "increasing":
            trend_info = " (trending up)"
        elif error_trend == "decreasing":
            trend_info = " (improving)"

        if issue_counts[Priority.CRITICAL] > 0:
            self.add_feedback_with_context(
                Priority.CRITICAL,
                f"{issue_counts[Priority.CRITICAL]} critical events in logs{trend_info}",
                alert_type="log_critical",
                context={"count": issue_counts[Priority.CRITICAL]},
                details="; ".join(critical_messages) if critical_messages else None,
            )

        if issue_counts[Priority.HIGH] > 0:
            self.add_feedback_with_context(
                Priority.HIGH,
                f"{issue_counts[Priority.HIGH]} error events in logs{trend_info}",
                alert_type="log_errors",
                context={"count": issue_counts[Priority.HIGH]},
            )

        if issue_counts[Priority.MEDIUM] > 0:
            self.add_feedback_with_context(
                Priority.MEDIUM,
                f"{issue_counts[Priority.MEDIUM]} warning events in logs",
                alert_type="log_warnings",
                context={"count": issue_counts[Priority.MEDIUM]},
            )

        total_issues = sum(issue_counts.values())
        if total_issues == 0:
            self.add_feedback(
                Priority.LOW,
                f"{total_entries} log entries analyzed without anomalies",
            )
