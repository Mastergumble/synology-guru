"""Tests for configuration models and loader."""

import os
from pathlib import Path

import pytest

from src.config.models import AppConfig, EmailConfig, NASConfig
from src.config.loader import ConfigLoader


class TestNASConfig:
    def test_defaults(self):
        cfg = NASConfig(host="192.168.1.1")
        assert cfg.port == 5001
        assert cfg.https is True
        assert cfg.username == ""
        assert cfg.password == ""

    def test_custom_values(self):
        cfg = NASConfig(host="nas.local", port=5000, https=False,
                        username="admin", password="pass")
        assert cfg.host == "nas.local"
        assert cfg.port == 5000
        assert cfg.https is False


class TestAppConfig:
    def test_get_nas_default(self):
        cfg = AppConfig(
            default="main",
            nas={"main": NASConfig(host="192.168.1.1")},
        )
        nas = cfg.get_nas()
        assert nas.host == "192.168.1.1"

    def test_get_nas_by_name(self):
        cfg = AppConfig(
            default="main",
            nas={
                "main": NASConfig(host="192.168.1.1"),
                "backup": NASConfig(host="192.168.1.2"),
            },
        )
        nas = cfg.get_nas("backup")
        assert nas.host == "192.168.1.2"

    def test_get_nas_missing_raises(self):
        cfg = AppConfig(
            default="main",
            nas={"main": NASConfig(host="192.168.1.1")},
        )
        with pytest.raises(ValueError, match="not found"):
            cfg.get_nas("nonexistent")

    def test_get_data_dir_default(self):
        cfg = AppConfig(
            default="main",
            nas={"main": NASConfig(host="192.168.1.1")},
            data_dir=Path("/tmp/data"),
        )
        assert cfg.get_data_dir() == Path("/tmp/data/main")

    def test_get_data_dir_specific(self):
        cfg = AppConfig(
            default="main",
            nas={"main": NASConfig(host="192.168.1.1")},
            data_dir=Path("/tmp/data"),
        )
        assert cfg.get_data_dir("backup") == Path("/tmp/data/backup")

    def test_get_nas_names(self):
        cfg = AppConfig(
            default="main",
            nas={
                "main": NASConfig(host="192.168.1.1"),
                "backup": NASConfig(host="192.168.1.2"),
            },
        )
        names = cfg.get_nas_names()
        assert "main" in names
        assert "backup" in names
        assert len(names) == 2


class TestConfigLoaderSubstituteEnvVars:
    def test_simple_var(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "hello")
        loader = ConfigLoader()
        result = loader._substitute_env_vars("value: ${MY_VAR}")
        assert result == "value: hello"

    def test_var_with_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        loader = ConfigLoader()
        result = loader._substitute_env_vars("value: ${MISSING_VAR:-fallback}")
        assert result == "value: fallback"

    def test_var_set_ignores_default(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "actual")
        loader = ConfigLoader()
        result = loader._substitute_env_vars("value: ${MY_VAR:-fallback}")
        assert result == "value: actual"

    def test_unset_var_no_default_empty(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        loader = ConfigLoader()
        result = loader._substitute_env_vars("value: ${MISSING_VAR}")
        assert result == "value: "


class TestConfigLoaderYAML:
    def test_valid_yaml(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "nas.yaml"
        yaml_file.write_text("""
default: home
nas:
  home:
    host: 192.168.1.100
    port: 5001
    username: admin
    password: secret
""")
        loader = ConfigLoader(config_path=yaml_file)
        config = loader._load_from_yaml(yaml_file)

        assert config.default == "home"
        assert "home" in config.nas
        assert config.nas["home"].host == "192.168.1.100"

    def test_empty_host_skipped(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "nas.yaml"
        yaml_file.write_text("""
default: home
nas:
  home:
    host: 192.168.1.100
  empty:
    host: ""
""")
        loader = ConfigLoader(config_path=yaml_file)
        config = loader._load_from_yaml(yaml_file)

        assert "home" in config.nas
        assert "empty" not in config.nas

    def test_with_email(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "nas.yaml"
        yaml_file.write_text("""
default: home
nas:
  home:
    host: 192.168.1.100
email:
  smtp_host: smtp.example.com
  smtp_port: 587
  username: user@example.com
  password: pass
  from_addr: from@example.com
  to_addr: to@example.com
""")
        loader = ConfigLoader(config_path=yaml_file)
        config = loader._load_from_yaml(yaml_file)

        assert config.email is not None
        assert config.email.smtp_host == "smtp.example.com"

    def test_without_email(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "nas.yaml"
        yaml_file.write_text("""
default: home
nas:
  home:
    host: 192.168.1.100
""")
        loader = ConfigLoader(config_path=yaml_file)
        config = loader._load_from_yaml(yaml_file)
        assert config.email is None


class TestConfigLoaderEnv:
    def test_single_nas(self, monkeypatch):
        monkeypatch.setenv("SYNOLOGY_HOST", "192.168.1.1")
        monkeypatch.setenv("SYNOLOGY_PORT", "5001")
        monkeypatch.setenv("SYNOLOGY_USERNAME", "admin")
        monkeypatch.setenv("SYNOLOGY_PASSWORD", "pass")

        loader = ConfigLoader(config_path=Path("/nonexistent"))
        config = loader._load_from_env()

        assert "default" in config.nas
        assert config.nas["default"].host == "192.168.1.1"

    def test_multiple_nas(self, monkeypatch):
        monkeypatch.setenv("SYNOLOGY_HOST", "192.168.1.1")
        monkeypatch.setenv("HOME_NAS_HOST", "192.168.1.2")
        monkeypatch.setenv("HOME_NAS_PORT", "5002")

        loader = ConfigLoader(config_path=Path("/nonexistent"))
        config = loader._load_from_env()

        assert "default" in config.nas
        assert "home-nas" in config.nas
        assert config.nas["home-nas"].host == "192.168.1.2"

    def test_no_config_raises(self, monkeypatch):
        # Prevent load_dotenv from loading the project .env
        monkeypatch.setattr("src.config.loader.load_dotenv", lambda: None)

        # Clear all relevant env vars
        for key in list(os.environ.keys()):
            if "SYNOLOGY" in key or "_NAS_" in key or key.endswith("_NAS_HOST"):
                monkeypatch.delenv(key, raising=False)

        loader = ConfigLoader(config_path=Path("/nonexistent"))
        with pytest.raises(ValueError, match="No NAS configured"):
            loader._load_from_env()
