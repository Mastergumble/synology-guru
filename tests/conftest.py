"""Shared fixtures for Synology Guru tests."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.api.client import SynologyClient
from src.memory.models import Observation
from src.memory.store import MemoryStore


@pytest.fixture
def mock_client():
    """SynologyClient with all methods as AsyncMock."""
    client = MagicMock(spec=SynologyClient)
    client.get_storage_info = AsyncMock(return_value={"volumes": []})
    client.get_volume_info = AsyncMock(return_value={})
    client.get_disk_info = AsyncMock(return_value={"disks": []})
    client.get_system_info = AsyncMock(return_value={})
    client.get_dsm_info = AsyncMock(return_value={})
    client.check_updates = AsyncMock(return_value={})
    client.get_hyper_backup_info = AsyncMock(return_value={"tasks": []})
    client.get_security_scan = AsyncMock(return_value={"items": []})
    client.get_connection_logs = AsyncMock(return_value={"logs": []})
    client.get_system_logs = AsyncMock(return_value={"logs": []})
    client.get_installed_packages = AsyncMock(return_value={"packages": []})
    client.get_available_packages = AsyncMock(return_value={"packages": []})
    client.get_package_updates = AsyncMock(return_value=[])
    return client


@pytest.fixture
def memory_store(tmp_path):
    """MemoryStore with a temporary directory."""
    return MemoryStore(data_dir=tmp_path / "data")


def seed_observations(store: MemoryStore, agent: str, metric: str, values: list[float]):
    """Populate store with observations from a list of values.

    Values are spaced 1 day apart, ending at now.
    """
    now = datetime.now()
    for i, val in enumerate(values):
        ts = now - timedelta(days=len(values) - 1 - i)
        obs = Observation(
            agent=agent,
            metric=metric,
            value=val,
            timestamp=ts,
        )
        store.record_observation(obs)


# ===== API Response Factories =====

def make_volume(name="Volume1", total_gb=1000, used_pct=50, status="normal"):
    """Create a volume dict for storage API responses."""
    total = int(total_gb * (1024 ** 3))
    used = int(total * used_pct / 100)
    return {
        "id": name.lower().replace(" ", "_"),
        "display_name": name,
        "size": {"total": total, "used": used},
        "status": status,
    }


def make_disk(
    disk_id="disk1",
    name="Disk 1",
    status="normal",
    smart_status="normal",
    temp=35,
    bad_sectors=0,
    power_on_hours=10000,
):
    """Create a disk dict for disk API responses."""
    return {
        "id": disk_id,
        "name": name,
        "status": status,
        "smart_status": smart_status,
        "temp": temp,
        "bad_sector_count": bad_sectors,
        "power_on_hours": power_on_hours,
    }


def make_backup_task(
    name="DailyBackup",
    status="completed",
    last_backup_days_ago=0,
    transferred_bytes=0,
    duration_seconds=0,
    error_message=None,
):
    """Create a backup task dict for backup API responses."""
    task = {
        "name": name,
        "status": status,
        "transferred_bytes": transferred_bytes,
        "duration_seconds": duration_seconds,
    }
    if last_backup_days_ago is not None:
        ts = datetime.now() - timedelta(days=last_backup_days_ago)
        task["last_backup_time"] = int(ts.timestamp())
    if error_message:
        task["error_message"] = error_message
    return task


def make_security_item(category="Firewall", status="safe", description="All clear"):
    """Create a security scan item."""
    return {
        "category": category,
        "status": status,
        "description": description,
    }


def make_log_entry(message="Normal operation", level="info", source="system", timestamp=None):
    """Create a log entry."""
    return {
        "message": message,
        "level": level,
        "source": source,
        "timestamp": timestamp or int(datetime.now().timestamp()),
    }


def make_connection_log(event_type="login_success", ip="192.168.1.1", username="admin", timestamp=None):
    """Create a connection log entry."""
    return {
        "event_type": event_type,
        "ip": ip,
        "username": username,
        "timestamp": timestamp or int(datetime.now().timestamp()),
    }
