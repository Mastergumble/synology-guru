"""Security monitoring agent with learning capabilities."""

from datetime import datetime, timedelta

from src.agents.learning import LearningAgent
from src.agents.base import Feedback, Priority


class SecurityAgent(LearningAgent):
    """Agent for monitoring security status with learning.

    Learning features:
    - Learns normal login patterns (time, frequency, IPs)
    - Detects unusual authentication activity
    - Adapts to legitimate access patterns
    - Tracks security scan trends over time
    """

    name = "security"
    description = "Monitors security settings and threats"

    # Default thresholds (can be adjusted by learning)
    FAILED_LOGIN_CRITICAL = 50  # Critical if >50 failed logins
    FAILED_LOGIN_WARNING = 10  # Warning if >10 failed logins

    async def check(self) -> list[Feedback]:
        """Check security status."""
        # Check security scan results
        try:
            security_info = await self.client.get_security_scan()
            await self._analyze_security_scan(security_info)
        except Exception as e:
            self.add_feedback(
                Priority.MEDIUM,
                f"Could not retrieve security scan: {e}",
            )

        # Check login attempts
        try:
            logs = await self.client.get_connection_logs(limit=500)
            await self._analyze_login_attempts(logs)
        except Exception as e:
            self.add_feedback(
                Priority.MEDIUM,
                f"Could not retrieve connection logs: {e}",
            )

        return self.get_feedback()

    async def _analyze_security_scan(self, info: dict) -> None:
        """Analyze security scan results with learning."""
        items = info.get("items", [])

        critical_items = []
        warning_items = []

        for item in items:
            status = item.get("status", "")
            category = item.get("category", "Unknown")
            description = item.get("description", "")

            if status == "danger":
                critical_items.append(f"{category}: {description}")
            elif status == "warning":
                warning_items.append(f"{category}: {description}")

        # Record observations
        total_issues = len(critical_items) + len(warning_items)
        self.observe("security_issues_total", total_issues)
        self.observe("security_critical_count", len(critical_items))
        self.observe("security_warning_count", len(warning_items))

        # Check for trend changes
        trend = self.get_trend("security_issues_total")

        if critical_items:
            self.add_feedback_with_context(
                Priority.CRITICAL,
                f"{len(critical_items)} critical security issues found",
                alert_type="security_critical",
                context={"count": len(critical_items)},
                details="; ".join(critical_items[:3]),
            )

        if warning_items:
            # Check if warnings are increasing
            trend_info = ""
            if trend == "increasing":
                trend_info = " (trending up)"

            self.add_feedback_with_context(
                Priority.HIGH,
                f"{len(warning_items)} security warnings{trend_info}",
                alert_type="security_warning",
                context={"count": len(warning_items)},
                details="; ".join(warning_items[:3]),
            )

        if not critical_items and not warning_items:
            self.add_feedback(
                Priority.LOW,
                "Security scan passed with no issues",
            )

    async def _analyze_login_attempts(self, logs: dict) -> None:
        """Analyze login attempts with learning."""
        entries = logs.get("logs", [])

        failed_attempts = 0
        successful_logins = 0
        blocked_ips: set[str] = set()
        login_hours: list[int] = []
        users_seen: set[str] = set()

        now = datetime.now()
        last_24h = now - timedelta(hours=24)

        for entry in entries:
            event_type = entry.get("event_type", "").lower()
            ip_address = entry.get("ip", "")
            username = entry.get("username", "")
            timestamp = entry.get("timestamp", 0)

            # Track login times for pattern learning
            if timestamp:
                try:
                    entry_time = datetime.fromtimestamp(timestamp)
                    if entry_time > last_24h:
                        login_hours.append(entry_time.hour)
                except (ValueError, TypeError):
                    pass

            if "fail" in event_type or "denied" in event_type:
                failed_attempts += 1
                if ip_address:
                    blocked_ips.add(ip_address)
            elif "success" in event_type or "login" in event_type:
                successful_logins += 1
                if username:
                    users_seen.add(username)

        # Record observations for learning
        self.observe("failed_logins_24h", failed_attempts)
        self.observe("successful_logins_24h", successful_logins)
        self.observe("unique_ips_failed", len(blocked_ips))

        # Calculate failure rate
        total_attempts = failed_attempts + successful_logins
        if total_attempts > 0:
            failure_rate = failed_attempts / total_attempts * 100
            self.observe("login_failure_rate", failure_rate)

        # Get adjusted thresholds
        thresholds = self._get_adjusted_thresholds()

        # Analyze with learning context
        context = {
            "failed_attempts": failed_attempts,
            "unique_ips": len(blocked_ips),
        }

        # Check for anomalous failed login count
        is_anomaly = False
        if self.has_sufficient_data("failed_logins_24h"):
            is_anomaly = self.is_anomaly("failed_logins_24h", failed_attempts)

        if failed_attempts >= thresholds["critical"]:
            self.add_feedback_with_context(
                Priority.CRITICAL,
                f"{failed_attempts} failed login attempts detected",
                alert_type="login_failed_critical",
                context=context,
                details=f"From {len(blocked_ips)} unique IPs",
            )
        elif failed_attempts >= thresholds["warning"] or is_anomaly:
            priority = Priority.HIGH if is_anomaly else Priority.HIGH
            anomaly_note = " (unusual spike)" if is_anomaly else ""

            self.add_feedback_with_context(
                priority,
                f"{failed_attempts} failed login attempts{anomaly_note}",
                alert_type="login_failed_warning",
                context=context,
                details=f"From {len(blocked_ips)} unique IPs",
            )
        elif failed_attempts > 0:
            self.add_feedback(
                Priority.INFO,
                f"{failed_attempts} failed login attempts (normal range)",
            )

        # Check for unusual login times
        await self._check_unusual_login_times(login_hours)

        # Check for new IPs if we have baseline
        await self._check_new_attack_sources(blocked_ips)

    async def _check_unusual_login_times(self, login_hours: list[int]) -> None:
        """Detect logins at unusual times."""
        if not login_hours:
            return

        # Record hourly distribution
        for hour in login_hours:
            self.observe("login_hour", hour)

        # Check for logins at unusual hours (simplified: 2-5 AM)
        unusual_hours = [h for h in login_hours if 2 <= h <= 5]
        if unusual_hours and len(unusual_hours) > 2:
            self.add_feedback_with_context(
                Priority.MEDIUM,
                f"{len(unusual_hours)} logins at unusual hours (2-5 AM)",
                alert_type="unusual_login_time",
                context={"count": len(unusual_hours)},
                details="Verify these are legitimate",
            )

    async def _check_new_attack_sources(self, blocked_ips: set[str]) -> None:
        """Track and alert on new attack source IPs."""
        if not blocked_ips:
            return

        # Record unique attacking IP count
        self.observe("attack_source_count", len(blocked_ips))

        # Check for sudden increase in attack sources
        if self.has_sufficient_data("attack_source_count"):
            if self.is_anomaly("attack_source_count", len(blocked_ips)):
                baseline = self.get_baseline_value("attack_source_count")
                if baseline and len(blocked_ips) > baseline * 2:
                    self.add_feedback_with_context(
                        Priority.HIGH,
                        f"Unusual number of attack sources: {len(blocked_ips)} IPs",
                        alert_type="attack_sources_spike",
                        context={"ip_count": len(blocked_ips)},
                        details=f"Normal: ~{baseline:.0f} IPs",
                    )

    def _get_adjusted_thresholds(self) -> dict[str, int]:
        """Get login thresholds, possibly adjusted by learning."""
        thresholds = {
            "critical": self.FAILED_LOGIN_CRITICAL,
            "warning": self.FAILED_LOGIN_WARNING,
        }

        # Adjust based on learned baseline
        baseline = self.memory.get_baseline(self.name, "failed_logins_24h")
        if baseline and baseline.sample_count >= 10:
            # Set warning at 2x normal, critical at 5x normal
            learned_warning = max(10, int(baseline.mean + 2 * baseline.std_dev))
            learned_critical = max(20, int(baseline.mean + 4 * baseline.std_dev))

            thresholds["warning"] = learned_warning
            thresholds["critical"] = learned_critical

        # Reduce thresholds if too many false positives
        fp_rate = self.memory.get_false_positive_rate(self.name, "login_failed_warning")
        if fp_rate > 0.4:
            thresholds["warning"] = int(thresholds["warning"] * 1.5)

        return thresholds
