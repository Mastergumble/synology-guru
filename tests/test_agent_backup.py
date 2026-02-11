"""Tests for the BackupAgent."""

import pytest

from src.agents.base import Priority
from src.agents.backup.agent import BackupAgent
from src.memory.store import MemoryStore
from tests.conftest import make_backup_task


@pytest.fixture
def agent(mock_client, tmp_path):
    memory = MemoryStore(data_dir=tmp_path / "data")
    return BackupAgent(mock_client, memory=memory)


class TestBackupCheck:
    async def test_recent_backup_ok(self, agent, mock_client):
        mock_client.get_hyper_backup_info.return_value = {
            "tasks": [make_backup_task(name="Daily", last_backup_days_ago=0)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.LOW and "completed" in f.message for f in fb)

    async def test_overdue_warning(self, agent, mock_client):
        mock_client.get_hyper_backup_info.return_value = {
            "tasks": [make_backup_task(name="Daily", last_backup_days_ago=4)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "4 days" in f.message for f in fb)

    async def test_overdue_critical(self, agent, mock_client):
        mock_client.get_hyper_backup_info.return_value = {
            "tasks": [make_backup_task(name="Daily", last_backup_days_ago=8)]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "8 days" in f.message for f in fb)

    async def test_error_state(self, agent, mock_client):
        mock_client.get_hyper_backup_info.return_value = {
            "tasks": [make_backup_task(name="Daily", status="error",
                                       error_message="Disk full")]
        }
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "error state" in f.message for f in fb)

    async def test_no_tasks(self, agent, mock_client):
        mock_client.get_hyper_backup_info.return_value = {"tasks": []}
        fb = await agent.check()
        assert any("No backup tasks" in f.message for f in fb)

    async def test_never_run(self, agent, mock_client):
        task = make_backup_task(name="Weekly")
        del task["last_backup_time"]
        mock_client.get_hyper_backup_info.return_value = {"tasks": [task]}
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "never run" in f.message for f in fb)

    async def test_api_error(self, agent, mock_client):
        mock_client.get_hyper_backup_info.side_effect = Exception("API error")
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "Failed to retrieve" in f.message for f in fb)

    async def test_running_task(self, agent, mock_client):
        mock_client.get_hyper_backup_info.return_value = {
            "tasks": [make_backup_task(name="Daily", status="running",
                                       duration_seconds=3600)]
        }
        fb = await agent.check()
        assert any("currently running" in f.message for f in fb)
