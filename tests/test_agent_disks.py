"""Tests for the DisksAgent."""

import pytest

from src.agents.base import Priority
from src.agents.disks.agent import DisksAgent
from src.memory.store import MemoryStore
from tests.conftest import make_disk


@pytest.fixture
def agent(mock_client, tmp_path):
    memory = MemoryStore(data_dir=tmp_path / "data")
    return DisksAgent(mock_client, memory=memory)


class TestDisksCheck:
    async def test_healthy_disk(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", status="normal", temp=35)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.LOW and "healthy" in f.message for f in fb)

    async def test_failed_disk(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", status="failed")]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "FAILED" in f.message for f in fb)

    async def test_smart_failing(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", smart_status="failing")]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "S.M.A.R.T." in f.message for f in fb)

    async def test_temp_critical(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", temp=65)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "overheating" in f.message for f in fb)

    async def test_temp_warning(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", temp=55)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "running hot" in f.message for f in fb)

    async def test_temp_cold(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", temp=10)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.MEDIUM and "running cold" in f.message for f in fb)

    async def test_bad_sectors(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", bad_sectors=5)]
        }
        fb = await agent.check()
        assert any("bad sectors" in f.message for f in fb)

    async def test_many_bad_sectors_critical(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", bad_sectors=150)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "150 bad sectors" in f.message for f in fb)

    async def test_old_disk(self, agent, mock_client):
        # 5+ years = 5 * 365 * 24 = 43800 hours
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk(name="Disk 1", power_on_hours=50000)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.MEDIUM and "years old" in f.message for f in fb)

    async def test_no_disks(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {"disks": []}
        fb = await agent.check()
        assert any("No disk information" in f.message for f in fb)


class TestRAIDStatus:
    async def test_raid_degraded(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk()],
            "storagePools": [{"id": "pool1", "status": "degraded"}],
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "DEGRADED" in f.message for f in fb)

    async def test_raid_crashed(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk()],
            "storagePools": [{"id": "pool1", "status": "crashed"}],
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "CRASHED" in f.message for f in fb)

    async def test_raid_rebuilding(self, agent, mock_client):
        mock_client.get_disk_info.return_value = {
            "disks": [make_disk()],
            "storagePools": [{"id": "pool1", "status": "rebuilding", "rebuild_progress": 45}],
        }
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "rebuilding" in f.message for f in fb)

    async def test_api_error(self, agent, mock_client):
        mock_client.get_disk_info.side_effect = Exception("Connection refused")
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "Could not retrieve" in f.message for f in fb)
