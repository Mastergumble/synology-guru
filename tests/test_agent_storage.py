"""Tests for the StorageAgent."""

import pytest

from src.agents.base import Priority
from src.agents.storage.agent import StorageAgent
from src.memory.store import MemoryStore
from tests.conftest import make_volume


@pytest.fixture
def agent(mock_client, tmp_path):
    memory = MemoryStore(data_dir=tmp_path / "data")
    return StorageAgent(mock_client, memory=memory)


class TestStorageCheck:
    async def test_healthy_volume(self, agent, mock_client):
        mock_client.get_storage_info.return_value = {
            "volumes": [make_volume("Volume1", total_gb=1000, used_pct=50)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.LOW for f in fb)
        assert any("50.0%" in f.message for f in fb)

    async def test_warning_volume(self, agent, mock_client):
        mock_client.get_storage_info.return_value = {
            "volumes": [make_volume("Volume1", total_gb=1000, used_pct=82)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.MEDIUM for f in fb)

    async def test_high_volume(self, agent, mock_client):
        mock_client.get_storage_info.return_value = {
            "volumes": [make_volume("Volume1", total_gb=1000, used_pct=92)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH for f in fb)

    async def test_critical_volume(self, agent, mock_client):
        mock_client.get_storage_info.return_value = {
            "volumes": [make_volume("Volume1", total_gb=1000, used_pct=96)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL for f in fb)

    async def test_no_volumes(self, agent, mock_client):
        mock_client.get_storage_info.return_value = {"volumes": []}
        fb = await agent.check()
        assert any("No storage volumes" in f.message for f in fb)

    async def test_crashed_volume(self, agent, mock_client):
        mock_client.get_storage_info.return_value = {
            "volumes": [make_volume("Volume1", total_gb=1000, used_pct=50, status="crashed")]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "crashed" in f.message for f in fb)

    async def test_degraded_volume(self, agent, mock_client):
        mock_client.get_storage_info.return_value = {
            "volumes": [make_volume("Volume1", total_gb=1000, used_pct=50, status="degraded")]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "degraded" in f.message for f in fb)

    async def test_api_error(self, agent, mock_client):
        mock_client.get_storage_info.side_effect = Exception("API timeout")
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "Could not retrieve" in f.message for f in fb)

    async def test_multiple_volumes(self, agent, mock_client):
        mock_client.get_storage_info.return_value = {
            "volumes": [
                make_volume("Volume1", total_gb=1000, used_pct=50),
                make_volume("Volume2", total_gb=500, used_pct=92),
            ]
        }
        fb = await agent.check()
        # Should have feedback for both volumes
        messages = " ".join(f.message for f in fb)
        assert "Volume1" in messages
        assert "Volume2" in messages
