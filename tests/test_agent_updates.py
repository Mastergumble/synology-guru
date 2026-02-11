"""Tests for the UpdatesAgent."""

import pytest
from datetime import datetime, timedelta

from src.agents.base import Priority
from src.agents.updates.agent import UpdatesAgent
from src.memory.store import MemoryStore


@pytest.fixture
def agent(mock_client, tmp_path):
    memory = MemoryStore(data_dir=tmp_path / "data")
    return UpdatesAgent(mock_client, memory=memory)


def dsm_info(version="7.2.1-69057", last_update_days_ago=None):
    info = {"version_string": version}
    if last_update_days_ago is not None:
        ts = datetime.now() - timedelta(days=last_update_days_ago)
        info["last_update_time"] = int(ts.timestamp())
    return info


class TestUpdatesCheck:
    async def test_no_updates(self, agent, mock_client):
        mock_client.get_dsm_info.return_value = dsm_info()
        mock_client.check_updates.return_value = {"available": False}
        fb = await agent.check()
        assert any(f.priority == Priority.LOW and "up to date" in f.message for f in fb)

    async def test_regular_update(self, agent, mock_client):
        mock_client.get_dsm_info.return_value = dsm_info()
        mock_client.check_updates.return_value = {
            "available": True,
            "version": "7.2.2-69100",
            "type": "update",
            "release_notes": "Bug fixes and improvements",
        }
        fb = await agent.check()
        assert any(f.priority == Priority.MEDIUM and "update available" in f.message for f in fb)

    async def test_security_update(self, agent, mock_client):
        mock_client.get_dsm_info.return_value = dsm_info()
        mock_client.check_updates.return_value = {
            "available": True,
            "version": "7.2.2-69100",
            "type": "security",
            "release_notes": "Security fixes",
        }
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "Security update" in f.message for f in fb)

    async def test_critical_security_fixes(self, agent, mock_client):
        mock_client.get_dsm_info.return_value = dsm_info()
        mock_client.check_updates.return_value = {
            "available": True,
            "version": "7.2.2-69100",
            "type": "update",
            "release_notes": "Fix CVE-2024-1234 critical vulnerability",
        }
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "Security update" in f.message for f in fb)
        assert any("critical security fixes" in f.message for f in fb)

    async def test_reboot_required(self, agent, mock_client):
        mock_client.get_dsm_info.return_value = dsm_info()
        mock_client.check_updates.return_value = {
            "available": False,
            "reboot_needed": True,
        }
        fb = await agent.check()
        assert any(f.priority == Priority.MEDIUM and "reboot required" in f.message for f in fb)

    async def test_overdue_update(self, agent, mock_client):
        mock_client.get_dsm_info.return_value = dsm_info(last_update_days_ago=95)
        mock_client.check_updates.return_value = {"available": False}
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "95 days" in f.message for f in fb)

    async def test_api_error(self, agent, mock_client):
        mock_client.get_dsm_info.side_effect = Exception("Connection refused")
        fb = await agent.check()
        assert any("Could not check for updates" in f.message for f in fb)
