"""Updates monitoring agent with learning capabilities."""

from datetime import datetime

from src.agents.learning import LearningAgent
from src.agents.base import Feedback, Priority


class UpdatesAgent(LearningAgent):
    """Agent for monitoring DSM and package updates with learning.

    Learning features:
    - Tracks update patterns and release frequency
    - Learns typical time between updates
    - Detects when updates are being ignored too long
    - Tracks update success/failure patterns
    """

    name = "updates"
    description = "Checks for available system and package updates"

    # Default thresholds
    DAYS_WITHOUT_UPDATE_WARNING = 30
    DAYS_WITHOUT_UPDATE_CRITICAL = 90

    async def check(self) -> list[Feedback]:
        """Check for available updates."""
        try:
            dsm_info = await self.client.get_dsm_info()
            update_info = await self.client.check_updates()
            await self._analyze_updates(dsm_info, update_info)
        except Exception as e:
            self.add_feedback(
                Priority.MEDIUM,
                f"Could not check for updates: {e}",
            )

        return self.get_feedback()

    async def _analyze_updates(self, dsm_info: dict, update_info: dict) -> None:
        """Analyze available updates with learning."""
        current_version = dsm_info.get("version_string", "Unknown")
        last_update_time = dsm_info.get("last_update_time", 0)

        # Record observations
        available = update_info.get("available", False)
        self.observe("update_available", 1 if available else 0)

        # Track days since last update
        if last_update_time:
            try:
                last_update = datetime.fromtimestamp(last_update_time)
                days_since_update = (datetime.now() - last_update).days
                self.observe("days_since_update", days_since_update)

                # Check for systems not being updated
                await self._check_update_cadence(days_since_update)
            except (ValueError, TypeError):
                pass

        # Check for available updates
        if available:
            await self._handle_available_update(update_info, current_version)
        else:
            self.add_feedback(
                Priority.LOW,
                f"DSM {current_version} is up to date",
            )

        # Check reboot required
        if update_info.get("reboot_needed", False):
            self.add_feedback_with_context(
                Priority.MEDIUM,
                "System reboot required to complete updates",
                alert_type="reboot_required",
                context={"pending": True},
            )

        # Track update availability trend
        await self._check_update_patterns()

    async def _handle_available_update(
        self,
        update_info: dict,
        current_version: str,
    ) -> None:
        """Handle available update with learned context."""
        new_version = update_info.get("version", "Unknown")
        update_type = update_info.get("type", "update")
        release_notes = update_info.get("release_notes", "")

        # Determine severity based on update type and content
        is_security = "security" in update_type.lower()
        has_critical_fixes = any(
            keyword in release_notes.lower()
            for keyword in ["critical", "vulnerability", "cve-", "security fix"]
        )

        context = {
            "current_version": current_version,
            "new_version": new_version,
            "is_security": is_security,
        }

        if is_security or has_critical_fixes:
            self.add_feedback_with_context(
                Priority.HIGH,
                f"Security update available: DSM {new_version}",
                alert_type="update_security",
                context=context,
                details=f"Current version: {current_version}",
            )

            if has_critical_fixes:
                self.add_feedback(
                    Priority.HIGH,
                    "Update contains critical security fixes",
                    details="Review release notes and update as soon as possible",
                )
        else:
            self.add_feedback_with_context(
                Priority.MEDIUM,
                f"DSM update available: {new_version}",
                alert_type="update_available",
                context=context,
                details=f"Current version: {current_version}",
            )

        # Track how long updates have been pending
        await self._track_pending_update(new_version)

    async def _check_update_cadence(self, days_since_update: int) -> None:
        """Check if system is being updated regularly."""
        # Get learned thresholds
        thresholds = self._get_adjusted_thresholds()

        if days_since_update >= thresholds["critical_days"]:
            self.add_feedback_with_context(
                Priority.HIGH,
                f"System not updated for {days_since_update} days",
                alert_type="update_overdue",
                context={"days": days_since_update},
                details="Regular updates are important for security",
            )
        elif days_since_update >= thresholds["warning_days"]:
            self.add_feedback_with_context(
                Priority.MEDIUM,
                f"System not updated for {days_since_update} days",
                alert_type="update_reminder",
                context={"days": days_since_update},
                details="Consider checking for available updates",
            )

    async def _track_pending_update(self, version: str) -> None:
        """Track how long an update has been pending."""
        # This would ideally track when we first saw this update
        # For now, just note that an update is pending
        pending_key = f"pending_update_{version.replace('.', '_')}"

        # Check if we've been alerting about this update
        pattern = self.memory.get_pattern(self.name, f"ignore_{pending_key}")
        if pattern and pattern.confidence >= 0.7:
            # User has indicated they want to ignore this update
            return

    async def _check_update_patterns(self) -> None:
        """Analyze update availability patterns."""
        if not self.has_sufficient_data("update_available"):
            return

        # Check if updates are frequently available but not installed
        trend = self.get_trend("update_available")
        if trend == "increasing":
            self.add_feedback(
                Priority.LOW,
                "Updates are being released frequently",
                details="Consider establishing a regular update schedule",
            )

    def _get_adjusted_thresholds(self) -> dict[str, int]:
        """Get update thresholds, possibly adjusted by learning."""
        thresholds = {
            "warning_days": self.DAYS_WITHOUT_UPDATE_WARNING,
            "critical_days": self.DAYS_WITHOUT_UPDATE_CRITICAL,
        }

        # Adjust based on learned update frequency
        baseline = self.memory.get_baseline(self.name, "days_since_update")
        if baseline and baseline.sample_count >= 5:
            # If user typically updates more frequently, adjust expectations
            typical_interval = baseline.mean
            if typical_interval < 14:  # User updates frequently
                thresholds["warning_days"] = max(14, int(typical_interval * 2))
                thresholds["critical_days"] = max(30, int(typical_interval * 4))

        # Reduce sensitivity if too many false positives
        fp_rate = self.memory.get_false_positive_rate(self.name, "update_reminder")
        if fp_rate > 0.5:
            thresholds["warning_days"] = int(thresholds["warning_days"] * 1.5)

        return thresholds
