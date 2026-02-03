"""Storage monitoring agent with learning capabilities."""

from src.agents.learning import LearningAgent
from src.agents.base import Feedback, Priority


class StorageAgent(LearningAgent):
    """Agent for monitoring storage capacity and usage with learning.

    Learning features:
    - Learns normal usage patterns per volume
    - Detects unusual growth spikes
    - Predicts when storage will be full
    - Adjusts thresholds based on historical data
    """

    name = "storage"
    description = "Monitors volume capacity and usage trends"

    # Default thresholds (can be adjusted by learning)
    SPACE_CRITICAL = 95  # Critical if >95% used
    SPACE_HIGH = 90  # High if >90% used
    SPACE_WARNING = 80  # Warning if >80% used

    # Growth rate thresholds (GB per day)
    GROWTH_WARNING_GB_DAY = 10  # Warn if growing >10GB/day
    GROWTH_CRITICAL_GB_DAY = 50  # Critical if growing >50GB/day

    async def check(self) -> list[Feedback]:
        """Check storage status."""
        try:
            storage_info = await self.client.get_storage_info()
            await self._analyze_storage(storage_info)
        except Exception as e:
            self.add_feedback(
                Priority.HIGH,
                f"Could not retrieve storage information: {e}",
            )

        return self.get_feedback()

    async def _analyze_storage(self, info: dict) -> None:
        """Analyze storage volumes with learning."""
        volumes = info.get("volumes", [])

        if not volumes:
            self.add_feedback(
                Priority.MEDIUM,
                "No storage volumes found",
            )
            return

        for volume in volumes:
            vol_name = volume.get("display_name", volume.get("id", "Unknown"))
            total = volume.get("size", {}).get("total", 0)
            used = volume.get("size", {}).get("used", 0)

            if total == 0:
                continue

            usage_percent = (used / total) * 100
            free_bytes = total - used
            free_gb = free_bytes / (1024 ** 3)
            used_gb = used / (1024 ** 3)

            # Record observation for learning
            metric_name = f"usage_percent_{vol_name}"
            self.observe(metric_name, usage_percent, {"volume": vol_name})

            # Also track absolute usage for growth detection
            self.observe(f"used_gb_{vol_name}", used_gb, {"volume": vol_name})

            # Check for anomalous growth
            await self._check_growth_anomaly(vol_name, used_gb, free_gb)

            # Get trend for additional context
            trend = self.get_trend(metric_name)
            trend_info = self._format_trend(trend)

            # Determine thresholds (possibly adjusted by learning)
            thresholds = self._get_adjusted_thresholds(vol_name)

            # Determine priority based on usage
            context = {"volume": vol_name, "usage_percent": usage_percent}

            if usage_percent >= thresholds["critical"]:
                self.add_feedback_with_context(
                    Priority.CRITICAL,
                    f"Volume {vol_name} critically low on space: {usage_percent:.1f}% used",
                    alert_type="storage_critical",
                    context=context,
                    details=f"Only {free_gb:.1f} GB free. {trend_info}",
                )
            elif usage_percent >= thresholds["high"]:
                self.add_feedback_with_context(
                    Priority.HIGH,
                    f"Volume {vol_name} running low on space: {usage_percent:.1f}% used",
                    alert_type="storage_high",
                    context=context,
                    details=f"{free_gb:.1f} GB free. {trend_info}",
                )
            elif usage_percent >= thresholds["warning"]:
                self.add_feedback_with_context(
                    Priority.MEDIUM,
                    f"Volume {vol_name} at {usage_percent:.1f}% capacity",
                    alert_type="storage_warning",
                    context=context,
                    details=f"{free_gb:.1f} GB free. {trend_info}",
                )
            else:
                self.add_feedback(
                    Priority.LOW,
                    f"Volume {vol_name} healthy: {usage_percent:.1f}% used",
                    details=f"{free_gb:.1f} GB free. {trend_info}",
                )

            # Predict when volume will be full
            await self._predict_full(vol_name, usage_percent, free_gb)

        # Check for degraded volumes
        await self._check_volume_status(volumes)

    async def _check_growth_anomaly(
        self,
        vol_name: str,
        used_gb: float,
        free_gb: float,
    ) -> None:
        """Detect unusual storage growth patterns."""
        metric_name = f"used_gb_{vol_name}"

        if not self.has_sufficient_data(metric_name):
            return  # Not enough data yet

        # Check if current growth is anomalous
        if self.is_anomaly(metric_name, used_gb):
            baseline = self.get_baseline_value(metric_name)
            if baseline and used_gb > baseline:
                growth = used_gb - baseline
                self.add_feedback_with_context(
                    Priority.HIGH,
                    f"Unusual storage growth on {vol_name}: +{growth:.1f} GB above normal",
                    alert_type="storage_growth_anomaly",
                    context={"volume": vol_name, "growth_gb": growth},
                    details="This is significantly above the learned baseline",
                )

    def _get_adjusted_thresholds(self, vol_name: str) -> dict[str, float]:
        """Get thresholds, possibly adjusted by learning."""
        # Start with defaults
        thresholds = {
            "critical": self.SPACE_CRITICAL,
            "high": self.SPACE_HIGH,
            "warning": self.SPACE_WARNING,
        }

        # Check false positive rate and adjust if needed
        fp_rate = self.memory.get_false_positive_rate(self.name, "storage_warning")
        if fp_rate > 0.3:  # >30% false positives
            # Raise warning threshold slightly
            thresholds["warning"] = min(85, thresholds["warning"] + 5)

        fp_rate = self.memory.get_false_positive_rate(self.name, "storage_high")
        if fp_rate > 0.3:
            thresholds["high"] = min(92, thresholds["high"] + 2)

        return thresholds

    def _format_trend(self, trend: str) -> str:
        """Format trend for display."""
        if trend == "increasing":
            return "Trend: increasing"
        elif trend == "decreasing":
            return "Trend: decreasing"
        elif trend == "stable":
            return "Trend: stable"
        return ""

    async def _predict_full(
        self,
        vol_name: str,
        usage_percent: float,
        free_gb: float,
    ) -> None:
        """Predict when volume will be full based on growth trend."""
        metric_name = f"used_gb_{vol_name}"

        if not self.has_sufficient_data(metric_name):
            return

        trend = self.get_trend(metric_name)

        if trend == "increasing":
            # Estimate days until full based on recent growth
            baseline = self.memory.get_baseline(self.name, metric_name)
            if baseline and baseline.std_dev > 0:
                # Rough estimate: daily growth ≈ std_dev (simplified)
                daily_growth = baseline.std_dev
                if daily_growth > 0:
                    days_until_full = free_gb / daily_growth

                    if days_until_full < 7:
                        self.add_feedback(
                            Priority.CRITICAL,
                            f"Volume {vol_name} may be full in ~{days_until_full:.0f} days",
                            details="Based on recent growth patterns",
                        )
                    elif days_until_full < 30:
                        self.add_feedback(
                            Priority.HIGH,
                            f"Volume {vol_name} may be full in ~{days_until_full:.0f} days",
                            details="Consider expanding storage or cleaning up",
                        )

    async def _check_volume_status(self, volumes: list) -> None:
        """Check for degraded/crashed volumes."""
        for volume in volumes:
            status = volume.get("status", "")
            vol_name = volume.get("display_name", volume.get("id", "Unknown"))

            if status == "crashed":
                self.add_feedback(
                    Priority.CRITICAL,
                    f"Volume {vol_name} has crashed!",
                    details="Immediate attention required",
                )
            elif status == "degraded":
                self.add_feedback(
                    Priority.CRITICAL,
                    f"Volume {vol_name} is degraded",
                    details="Check disk status and replace failed disk",
                )
            elif status not in ("normal", "healthy", ""):
                self.add_feedback(
                    Priority.HIGH,
                    f"Volume {vol_name} status: {status}",
                )
