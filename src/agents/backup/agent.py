"""Backup monitoring agent with learning capabilities."""

from datetime import datetime

from src.agents.learning import LearningAgent
from src.agents.base import Feedback, Priority


class BackupAgent(LearningAgent):
    """Agent for monitoring backup status with learning.

    Learning features:
    - Learns typical backup duration patterns
    - Detects unusual backup sizes (potential issues)
    - Tracks backup success rate trends
    - Adjusts alert timing based on backup schedules
    """

    name = "backup"
    description = "Monitors backup tasks and status"

    # Default thresholds (can be adjusted by learning)
    BACKUP_CRITICAL_DAYS = 7  # No backup in 7 days = critical
    BACKUP_WARNING_DAYS = 3  # No backup in 3 days = warning

    async def check(self) -> list[Feedback]:
        """Check backup status."""
        try:
            backup_info = await self.client.get_hyper_backup_info()
            await self._analyze_backup_tasks(backup_info)
        except Exception as e:
            self.add_feedback(
                Priority.HIGH,
                f"Failed to retrieve backup information: {e}",
            )

        return self.get_feedback()

    async def _analyze_backup_tasks(self, info: dict) -> None:
        """Analyze backup task status with learning."""
        tasks = info.get("tasks", [])

        if not tasks:
            self.add_feedback(
                Priority.MEDIUM,
                "No backup tasks configured",
                details="Consider setting up Hyper Backup for data protection",
            )
            return

        now = datetime.now()
        total_tasks = len(tasks)
        successful_tasks = 0
        failed_tasks = 0

        for task in tasks:
            task_name = task.get("name", "Unknown")
            status = task.get("status", "unknown")
            last_backup = task.get("last_backup_time")
            backup_size = task.get("transferred_bytes", 0)
            duration = task.get("duration_seconds", 0)

            # Record observations for learning
            if backup_size > 0:
                self.observe(
                    f"backup_size_{task_name}",
                    backup_size / (1024 ** 3),  # GB
                    {"task": task_name},
                )

            if duration > 0:
                self.observe(
                    f"backup_duration_{task_name}",
                    duration / 60,  # minutes
                    {"task": task_name},
                )

            # Check task status
            if status == "error":
                failed_tasks += 1
                self.add_feedback_with_context(
                    Priority.CRITICAL,
                    f"Backup task '{task_name}' in error state",
                    alert_type="backup_error",
                    context={"task": task_name, "status": status},
                    details=task.get("error_message"),
                )
                continue

            if status == "running":
                # Check if running longer than usual
                await self._check_running_duration(task_name, duration)
                self.add_feedback(
                    Priority.INFO,
                    f"Backup task '{task_name}' currently running",
                )
                continue

            # Check last backup time
            if last_backup:
                await self._analyze_backup_timing(task_name, last_backup, now)

                # Check for anomalous backup size
                if backup_size > 0:
                    await self._check_backup_size_anomaly(task_name, backup_size)

                successful_tasks += 1
            else:
                self.add_feedback_with_context(
                    Priority.HIGH,
                    f"Backup task '{task_name}' has never run",
                    alert_type="backup_never_run",
                    context={"task": task_name},
                )

        # Record overall success metrics
        if total_tasks > 0:
            success_rate = successful_tasks / total_tasks * 100
            self.observe("backup_success_rate", success_rate)

            # Check success rate trend
            trend = self.get_trend("backup_success_rate")
            if trend == "decreasing" and self.has_sufficient_data("backup_success_rate"):
                self.add_feedback(
                    Priority.HIGH,
                    "Backup success rate is declining",
                    details=f"Current: {success_rate:.0f}% tasks successful",
                )

    async def _analyze_backup_timing(
        self,
        task_name: str,
        last_backup: int,
        now: datetime,
    ) -> None:
        """Analyze backup timing with learned patterns."""
        try:
            last_time = datetime.fromtimestamp(last_backup)
            days_since = (now - last_time).days
            hours_since = (now - last_time).total_seconds() / 3600

            # Record observation
            self.observe(
                f"hours_since_backup_{task_name}",
                hours_since,
                {"task": task_name},
            )

            # Get adjusted thresholds based on learning
            thresholds = self._get_adjusted_thresholds(task_name)

            context = {"task": task_name, "days_since": days_since}

            if days_since >= thresholds["critical_days"]:
                self.add_feedback_with_context(
                    Priority.CRITICAL,
                    f"Backup '{task_name}' not run for {days_since} days",
                    alert_type="backup_overdue_critical",
                    context=context,
                    details=f"Last backup: {last_time.strftime('%Y-%m-%d %H:%M')}",
                )
            elif days_since >= thresholds["warning_days"]:
                self.add_feedback_with_context(
                    Priority.HIGH,
                    f"Backup '{task_name}' not run for {days_since} days",
                    alert_type="backup_overdue_warning",
                    context=context,
                    details=f"Last backup: {last_time.strftime('%Y-%m-%d %H:%M')}",
                )
            else:
                self.add_feedback(
                    Priority.LOW,
                    f"Backup '{task_name}' completed successfully",
                    details=f"Last backup: {last_time.strftime('%Y-%m-%d %H:%M')}",
                )
        except (ValueError, TypeError):
            self.add_feedback(
                Priority.MEDIUM,
                f"Unable to parse last backup time for '{task_name}'",
            )

    async def _check_running_duration(self, task_name: str, current_duration: int) -> None:
        """Check if backup is running longer than usual."""
        metric_name = f"backup_duration_{task_name}"

        if not self.has_sufficient_data(metric_name):
            return

        current_minutes = current_duration / 60
        if self.is_anomaly(metric_name, current_minutes):
            baseline = self.get_baseline_value(metric_name)
            if baseline and current_minutes > baseline * 1.5:
                self.add_feedback_with_context(
                    Priority.MEDIUM,
                    f"Backup '{task_name}' running longer than usual",
                    alert_type="backup_slow",
                    context={"task": task_name, "duration_minutes": current_minutes},
                    details=f"Current: {current_minutes:.0f}min, Normal: ~{baseline:.0f}min",
                )

    async def _check_backup_size_anomaly(self, task_name: str, backup_size: int) -> None:
        """Check for unusual backup sizes."""
        metric_name = f"backup_size_{task_name}"
        size_gb = backup_size / (1024 ** 3)

        if not self.has_sufficient_data(metric_name):
            return

        if self.is_anomaly(metric_name, size_gb):
            baseline = self.get_baseline_value(metric_name)
            if baseline:
                if size_gb > baseline * 2:
                    self.add_feedback_with_context(
                        Priority.MEDIUM,
                        f"Backup '{task_name}' unusually large",
                        alert_type="backup_size_high",
                        context={"task": task_name, "size_gb": size_gb},
                        details=f"Size: {size_gb:.1f}GB (normal: ~{baseline:.1f}GB)",
                    )
                elif size_gb < baseline * 0.5:
                    self.add_feedback_with_context(
                        Priority.MEDIUM,
                        f"Backup '{task_name}' unusually small",
                        alert_type="backup_size_low",
                        context={"task": task_name, "size_gb": size_gb},
                        details=f"Size: {size_gb:.1f}GB (normal: ~{baseline:.1f}GB) - verify backup integrity",
                    )

    def _get_adjusted_thresholds(self, task_name: str) -> dict[str, int]:
        """Get backup thresholds, possibly adjusted by learning."""
        thresholds = {
            "critical_days": self.BACKUP_CRITICAL_DAYS,
            "warning_days": self.BACKUP_WARNING_DAYS,
        }

        # If we have learned the typical backup interval, adjust thresholds
        metric_name = f"hours_since_backup_{task_name}"
        baseline = self.memory.get_baseline(self.name, metric_name)

        if baseline and baseline.sample_count >= 5:
            # Typical interval in days
            typical_interval_days = baseline.mean / 24

            # Adjust warning to be 1.5x typical interval
            if typical_interval_days > 0:
                learned_warning = int(typical_interval_days * 1.5)
                learned_critical = int(typical_interval_days * 3)

                # Only use learned values if they're reasonable
                if 1 <= learned_warning <= 14:
                    thresholds["warning_days"] = learned_warning
                if 2 <= learned_critical <= 30:
                    thresholds["critical_days"] = learned_critical

        return thresholds
