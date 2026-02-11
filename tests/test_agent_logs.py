"""Tests for the LogsAgent."""

import pytest

from src.agents.base import Priority
from src.agents.logs.agent import LogsAgent
from src.memory.store import MemoryStore
from tests.conftest import make_log_entry


@pytest.fixture
def agent(mock_client, tmp_path):
    memory = MemoryStore(data_dir=tmp_path / "data")
    return LogsAgent(mock_client, memory=memory)


class TestLogsCheck:
    async def test_clean_logs(self, agent, mock_client):
        entries = [make_log_entry("Normal operation", "info") for _ in range(10)]
        mock_client.get_system_logs.return_value = {"logs": entries}
        fb = await agent.check()
        assert any(f.priority == Priority.LOW and "without anomalies" in f.message for f in fb)

    async def test_critical_keywords(self, agent, mock_client):
        entries = [
            make_log_entry("disk failure detected on drive 3", "error"),
            make_log_entry("Normal operation", "info"),
        ]
        mock_client.get_system_logs.return_value = {"logs": entries}
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL for f in fb)

    async def test_error_messages(self, agent, mock_client):
        entries = [
            make_log_entry("Service restart failed", "error"),
            make_log_entry("Normal operation", "info"),
        ]
        mock_client.get_system_logs.return_value = {"logs": entries}
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH for f in fb)

    async def test_warning_messages(self, agent, mock_client):
        entries = [
            make_log_entry("Certificate expiring", "warning"),
            make_log_entry("Normal operation", "info"),
        ]
        mock_client.get_system_logs.return_value = {"logs": entries}
        fb = await agent.check()
        assert any(f.priority == Priority.MEDIUM for f in fb)

    async def test_no_entries(self, agent, mock_client):
        mock_client.get_system_logs.return_value = {"logs": []}
        fb = await agent.check()
        assert any("No recent log entries" in f.message for f in fb)

    async def test_api_error(self, agent, mock_client):
        mock_client.get_system_logs.side_effect = Exception("Timeout")
        fb = await agent.check()
        assert any("Could not retrieve system logs" in f.message for f in fb)

    async def test_multiple_critical_keywords(self, agent, mock_client):
        entries = [
            make_log_entry("kernel panic on boot", "error"),
            make_log_entry("out of memory killed process", "error"),
            make_log_entry("Normal operation", "info"),
        ]
        mock_client.get_system_logs.return_value = {"logs": entries}
        fb = await agent.check()
        critical_fb = [f for f in fb if f.priority == Priority.CRITICAL]
        assert len(critical_fb) >= 1
