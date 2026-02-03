"""Disk health monitoring agent with learning capabilities."""

from src.agents.learning import LearningAgent
from src.agents.base import Feedback, Priority


class DisksAgent(LearningAgent):
    """Agent for monitoring disk health with learning.

    Learning features:
    - Tracks disk temperature patterns over time
    - Learns normal I/O patterns per disk
    - Detects gradual S.M.A.R.T. degradation
    - Predicts potential disk failures
    - Adapts to environment-specific temperature norms
    """

    name = "disks"
    description = "Monitors disk health, S.M.A.R.T. data, and RAID status"

    # Default temperature thresholds (Celsius)
    # Can be adjusted by learning based on environment
    TEMP_CRITICAL = 60
    TEMP_WARNING = 50
    TEMP_LOW_WARNING = 15  # Too cold can also be a problem

    # S.M.A.R.T. attributes that indicate problems
    CRITICAL_SMART_ATTRS = [
        "reallocated_sector_count",
        "current_pending_sector",
        "offline_uncorrectable",
        "reallocated_event_count",
    ]

    async def check(self) -> list[Feedback]:
        """Check disk health status."""
        try:
            disk_info = await self.client.get_disk_info()
            await self._analyze_disks(disk_info)
        except Exception as e:
            self.add_feedback(
                Priority.HIGH,
                f"Could not retrieve disk information: {e}",
            )

        return self.get_feedback()

    async def _analyze_disks(self, info: dict) -> None:
        """Analyze disk health with learning."""
        disks = info.get("disks", [])

        if not disks:
            self.add_feedback(
                Priority.MEDIUM,
                "No disk information available",
            )
            return

        healthy_disks = 0
        total_disks = len(disks)

        for disk in disks:
            disk_id = disk.get("id", "Unknown")
            disk_name = disk.get("name", disk_id)

            # Analyze individual disk
            is_healthy = await self._analyze_single_disk(disk, disk_name)
            if is_healthy:
                healthy_disks += 1

        # Record overall health metrics
        health_rate = (healthy_disks / total_disks * 100) if total_disks > 0 else 0
        self.observe("disk_health_rate", health_rate)
        self.observe("healthy_disk_count", healthy_disks)
        self.observe("total_disk_count", total_disks)

        # Check RAID status
        raids = info.get("storagePools", info.get("raids", []))
        await self._analyze_raids(raids)

    async def _analyze_single_disk(self, disk: dict, disk_name: str) -> bool:
        """Analyze a single disk and return True if healthy."""
        status = disk.get("status", "unknown")
        smart_status = disk.get("smart_status", "")
        temp = disk.get("temp", 0)
        bad_sectors = disk.get("bad_sector_count", 0)
        power_on_hours = disk.get("power_on_hours", 0)

        is_healthy = True

        # Record observations for learning
        if temp > 0:
            self.observe(f"temp_{disk_name}", temp, {"disk": disk_name})

        if bad_sectors >= 0:
            self.observe(f"bad_sectors_{disk_name}", bad_sectors, {"disk": disk_name})

        if power_on_hours > 0:
            self.observe(f"power_hours_{disk_name}", power_on_hours, {"disk": disk_name})

        # Check overall status
        if status in ("crashed", "failed"):
            self.add_feedback(
                Priority.CRITICAL,
                f"Disk {disk_name} has FAILED",
                details="Replace disk immediately",
            )
            return False
        elif status == "warning":
            self.add_feedback_with_context(
                Priority.HIGH,
                f"Disk {disk_name} showing warnings",
                alert_type="disk_warning",
                context={"disk": disk_name, "status": status},
                details="Monitor closely and prepare replacement",
            )
            is_healthy = False

        # Check S.M.A.R.T. status
        if smart_status == "failing":
            self.add_feedback(
                Priority.CRITICAL,
                f"Disk {disk_name} S.M.A.R.T. predicting failure",
                details="Replace disk as soon as possible",
            )
            return False
        elif smart_status == "warning":
            self.add_feedback_with_context(
                Priority.HIGH,
                f"Disk {disk_name} S.M.A.R.T. warnings",
                alert_type="smart_warning",
                context={"disk": disk_name},
            )
            is_healthy = False

        # Check temperature with learning
        await self._check_temperature(disk_name, temp)

        # Check bad sectors with learning
        await self._check_bad_sectors(disk_name, bad_sectors)

        # Check disk age/wear
        await self._check_disk_wear(disk_name, power_on_hours)

        # Report healthy disk
        if is_healthy and status in ("normal", "healthy"):
            details = f"Temperature: {temp}°C" if temp > 0 else None
            self.add_feedback(
                Priority.LOW,
                f"Disk {disk_name} healthy",
                details=details,
            )

        return is_healthy

    async def _check_temperature(self, disk_name: str, temp: int) -> None:
        """Check disk temperature with learned baselines."""
        if temp <= 0:
            return

        metric_name = f"temp_{disk_name}"

        # Get adjusted thresholds based on learning
        thresholds = self._get_temp_thresholds(disk_name)

        context = {"disk": disk_name, "temp": temp}

        if temp >= thresholds["critical"]:
            self.add_feedback_with_context(
                Priority.CRITICAL,
                f"Disk {disk_name} overheating: {temp}°C",
                alert_type="disk_temp_critical",
                context=context,
                details="Check cooling system immediately",
            )
        elif temp >= thresholds["warning"]:
            self.add_feedback_with_context(
                Priority.HIGH,
                f"Disk {disk_name} running hot: {temp}°C",
                alert_type="disk_temp_high",
                context=context,
                details="Consider improving cooling",
            )
        elif temp <= thresholds["low"]:
            self.add_feedback_with_context(
                Priority.MEDIUM,
                f"Disk {disk_name} running cold: {temp}°C",
                alert_type="disk_temp_low",
                context=context,
                details="Very low temperatures can affect disk reliability",
            )

        # Check for temperature anomalies
        if self.has_sufficient_data(metric_name):
            if self.is_anomaly(metric_name, temp):
                baseline = self.get_baseline_value(metric_name)
                if baseline and abs(temp - baseline) > 5:
                    trend = "higher" if temp > baseline else "lower"
                    self.add_feedback_with_context(
                        Priority.MEDIUM,
                        f"Disk {disk_name} temperature anomaly: {temp}°C ({trend} than usual)",
                        alert_type="disk_temp_anomaly",
                        context=context,
                        details=f"Normal: ~{baseline:.0f}°C",
                    )

    async def _check_bad_sectors(self, disk_name: str, bad_sectors: int) -> None:
        """Check bad sectors with trend analysis."""
        if bad_sectors <= 0:
            return

        metric_name = f"bad_sectors_{disk_name}"
        context = {"disk": disk_name, "bad_sectors": bad_sectors}

        # Check for increasing bad sectors (very concerning)
        trend = self.get_trend(metric_name)

        if bad_sectors > 100:
            self.add_feedback_with_context(
                Priority.CRITICAL,
                f"Disk {disk_name} has {bad_sectors} bad sectors",
                alert_type="bad_sectors_critical",
                context=context,
                details="Disk replacement recommended",
            )
        elif bad_sectors > 0:
            trend_info = ""
            priority = Priority.HIGH

            if trend == "increasing":
                trend_info = " (increasing!)"
                priority = Priority.CRITICAL

            self.add_feedback_with_context(
                priority,
                f"Disk {disk_name} has {bad_sectors} bad sectors{trend_info}",
                alert_type="bad_sectors_warning",
                context=context,
                details="Monitor disk health closely",
            )

    async def _check_disk_wear(self, disk_name: str, power_on_hours: int) -> None:
        """Check disk wear based on power-on hours."""
        if power_on_hours <= 0:
            return

        # Convert to years for readability
        power_on_years = power_on_hours / (24 * 365)

        self.observe(f"power_years_{disk_name}", power_on_years, {"disk": disk_name})

        # Typical HDD lifespan warnings
        if power_on_years >= 5:
            self.add_feedback_with_context(
                Priority.MEDIUM,
                f"Disk {disk_name} is {power_on_years:.1f} years old",
                alert_type="disk_age_warning",
                context={"disk": disk_name, "years": power_on_years},
                details="Consider proactive replacement - average HDD lifespan is 3-5 years",
            )
        elif power_on_years >= 3:
            self.add_feedback(
                Priority.LOW,
                f"Disk {disk_name} approaching typical lifespan ({power_on_years:.1f} years)",
                details="Monitor S.M.A.R.T. data closely",
            )

    async def _analyze_raids(self, raids: list) -> None:
        """Analyze RAID array status."""
        for raid in raids:
            raid_id = raid.get("id", "Unknown")
            raid_status = raid.get("status", "")

            # Record RAID health
            is_healthy = raid_status in ("normal", "healthy", "")
            self.observe(f"raid_healthy_{raid_id}", 1 if is_healthy else 0)

            if raid_status == "degraded":
                self.add_feedback(
                    Priority.CRITICAL,
                    f"RAID {raid_id} is DEGRADED",
                    details="Replace failed disk to restore redundancy",
                )
            elif raid_status == "crashed":
                self.add_feedback(
                    Priority.CRITICAL,
                    f"RAID {raid_id} has CRASHED",
                    details="Data loss may have occurred",
                )
            elif raid_status == "rebuilding":
                progress = raid.get("rebuild_progress", 0)
                self.add_feedback_with_context(
                    Priority.HIGH,
                    f"RAID {raid_id} is rebuilding ({progress}%)",
                    alert_type="raid_rebuilding",
                    context={"raid": raid_id, "progress": progress},
                    details="Avoid heavy I/O until complete",
                )

    def _get_temp_thresholds(self, disk_name: str) -> dict[str, int]:
        """Get temperature thresholds, adjusted by learning."""
        thresholds = {
            "critical": self.TEMP_CRITICAL,
            "warning": self.TEMP_WARNING,
            "low": self.TEMP_LOW_WARNING,
        }

        # Adjust based on learned normal temperature for this disk
        metric_name = f"temp_{disk_name}"
        baseline = self.memory.get_baseline(self.name, metric_name)

        if baseline and baseline.sample_count >= 20:
            normal_temp = baseline.mean

            # Adjust warning threshold based on normal operating temp
            # If disk normally runs at 45°C, warn at 55°C instead of 50°C
            if normal_temp > 40:
                thresholds["warning"] = max(50, int(normal_temp + 10))
                thresholds["critical"] = max(60, int(normal_temp + 15))

            # Adjust low threshold
            if normal_temp > 30:
                thresholds["low"] = max(15, int(normal_temp - 15))

        return thresholds
