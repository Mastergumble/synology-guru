"""Tests for the SecurityAgent."""

import pytest
from datetime import datetime

from src.agents.base import Priority
from src.agents.security.agent import SecurityAgent
from src.memory.store import MemoryStore
from tests.conftest import make_security_item, make_connection_log


@pytest.fixture
def agent(mock_client, tmp_path):
    memory = MemoryStore(data_dir=tmp_path / "data")
    return SecurityAgent(mock_client, memory=memory)


class TestSecurityCheck:
    async def test_clean_scan(self, agent, mock_client):
        mock_client.get_security_scan.return_value = {"items": []}
        mock_client.get_connection_logs.return_value = {"logs": []}
        fb = await agent.check()
        assert any(f.priority == Priority.LOW and "no issues" in f.message for f in fb)

    async def test_critical_issues(self, agent, mock_client):
        mock_client.get_security_scan.return_value = {
            "items": [
                make_security_item("Firewall", "danger", "Firewall disabled"),
                make_security_item("SSH", "danger", "Root SSH enabled"),
            ]
        }
        mock_client.get_connection_logs.return_value = {"logs": []}
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "2 critical" in f.message for f in fb)

    async def test_warnings(self, agent, mock_client):
        mock_client.get_security_scan.return_value = {
            "items": [
                make_security_item("Password", "warning", "Weak password policy"),
            ]
        }
        mock_client.get_connection_logs.return_value = {"logs": []}
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "1 security warning" in f.message for f in fb)

    async def test_few_failed_logins(self, agent, mock_client):
        mock_client.get_security_scan.return_value = {"items": []}
        logs = [make_connection_log(event_type="login_fail", ip=f"1.2.3.{i}") for i in range(3)]
        mock_client.get_connection_logs.return_value = {"logs": logs}
        fb = await agent.check()
        # 3 failed < warning threshold (10) -> INFO
        assert any(f.priority == Priority.INFO and "3 failed" in f.message for f in fb)

    async def test_warning_failed_logins(self, agent, mock_client):
        mock_client.get_security_scan.return_value = {"items": []}
        logs = [make_connection_log(event_type="login_fail", ip=f"1.2.3.{i}") for i in range(15)]
        mock_client.get_connection_logs.return_value = {"logs": logs}
        fb = await agent.check()
        assert any(f.priority == Priority.HIGH and "15 failed" in f.message for f in fb)

    async def test_critical_failed_logins(self, agent, mock_client):
        mock_client.get_security_scan.return_value = {"items": []}
        logs = [make_connection_log(event_type="login_fail", ip=f"1.2.{i // 256}.{i % 256}") for i in range(55)]
        mock_client.get_connection_logs.return_value = {"logs": logs}
        fb = await agent.check()
        assert any(f.priority == Priority.CRITICAL and "55 failed" in f.message for f in fb)

    async def test_security_scan_api_error(self, agent, mock_client):
        mock_client.get_security_scan.side_effect = Exception("Scan error")
        mock_client.get_connection_logs.return_value = {"logs": []}
        fb = await agent.check()
        assert any("Could not retrieve security scan" in f.message for f in fb)

    async def test_connection_logs_api_error(self, agent, mock_client):
        mock_client.get_security_scan.return_value = {"items": []}
        mock_client.get_connection_logs.side_effect = Exception("Log error")
        fb = await agent.check()
        assert any("Could not retrieve connection logs" in f.message for f in fb)
