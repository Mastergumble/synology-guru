"""Configuration loader for Synology Guru."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

from .models import AppConfig, EmailConfig, NASConfig


class ConfigLoader:
    """Load configuration from YAML file or environment variables."""

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize config loader.

        Args:
            config_path: Path to YAML config file. If None, searches for
                        config/nas.yaml in the project root.
        """
        self.config_path = config_path

    def load(self) -> AppConfig:
        """Load configuration from YAML or fallback to .env."""
        # Try to find YAML config
        yaml_path = self._find_yaml_config()

        if yaml_path and yaml_path.exists():
            return self._load_from_yaml(yaml_path)

        return self._load_from_env()

    def _find_yaml_config(self) -> Path | None:
        """Find YAML configuration file."""
        if self.config_path:
            return self.config_path

        # Search in common locations
        search_paths = [
            Path("config/nas.yaml"),
            Path("nas.yaml"),
            Path(__file__).parent.parent.parent / "config" / "nas.yaml",
        ]

        for path in search_paths:
            if path.exists():
                return path

        return None

    def _load_from_yaml(self, path: Path) -> AppConfig:
        """Load configuration from YAML file."""
        try:
            import yaml
        except ImportError as err:
            raise ImportError(
                "PyYAML is required for YAML config. Install with: pip install pyyaml"
            ) from err

        # Load environment variables for substitution
        load_dotenv()

        content = path.read_text(encoding="utf-8")

        # Substitute environment variables: ${VAR} or ${VAR:-default}
        content = self._substitute_env_vars(content)

        data = yaml.safe_load(content)

        return self._parse_yaml_config(data)

    def _substitute_env_vars(self, content: str) -> str:
        """Substitute ${VAR} and ${VAR:-default} patterns with environment values."""
        pattern = r"\$\{([^}:]+)(?::-([^}]*))?\}"

        def replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2) or ""
            return os.getenv(var_name, default)

        return re.sub(pattern, replace, content)

    def _parse_yaml_config(self, data: dict) -> AppConfig:
        """Parse YAML data into AppConfig."""
        nas_configs: dict[str, NASConfig] = {}
        skipped: list[str] = []

        # Parse NAS configurations
        nas_data = data.get("nas", {})
        for name, config in nas_data.items():
            host = config.get("host", "")
            # Skip NAS configs with missing host (not configured yet)
            if not host:
                skipped.append(name)
                continue
            nas_configs[name] = NASConfig(
                host=host,
                port=config.get("port", 5001),
                https=config.get("https", True),
                username=config.get("username", ""),
                password=config.get("password", ""),
            )

        # Parse email configuration
        email_config = None
        email_data = data.get("email")
        if email_data and email_data.get("smtp_host"):
            email_config = EmailConfig(
                smtp_host=email_data.get("smtp_host", ""),
                smtp_port=email_data.get("smtp_port", 587),
                username=email_data.get("username", ""),
                password=email_data.get("password", ""),
                from_addr=email_data.get("from_addr", ""),
                to_addr=email_data.get("to_addr", ""),
                use_tls=email_data.get("use_tls", True),
            )

        # Get data directory
        data_dir = Path(data.get("data_dir", "data"))

        return AppConfig(
            default=data.get("default", "default"),
            nas=nas_configs,
            email=email_config,
            data_dir=data_dir,
        )

    def _load_from_env(self) -> AppConfig:
        """Load configuration from environment variables (backward compatibility)."""
        load_dotenv()

        nas_configs: dict[str, NASConfig] = {}

        # Load default NAS from SYNOLOGY_* vars
        host = os.getenv("SYNOLOGY_HOST")
        if host:
            nas_configs["default"] = NASConfig(
                host=host,
                port=int(os.getenv("SYNOLOGY_PORT", "5001")),
                https=os.getenv("SYNOLOGY_HTTPS", "true").lower() == "true",
                username=os.getenv("SYNOLOGY_USERNAME", ""),
                password=os.getenv("SYNOLOGY_PASSWORD", ""),
            )

        # Load additional NAS from {PREFIX}_NAS_HOST pattern
        # Supports: HOME_NAS_*, OFFICE_NAS_*, BACKUP_NAS_*, etc.
        prefixes = set()
        for key in os.environ:
            if key.endswith("_NAS_HOST") and not key.startswith("SYNOLOGY"):
                prefix = key.replace("_NAS_HOST", "")
                prefixes.add(prefix)

        for prefix in prefixes:
            nas_host = os.getenv(f"{prefix}_NAS_HOST")
            if nas_host:
                nas_name = prefix.lower().replace("_", "-") + "-nas"
                nas_configs[nas_name] = NASConfig(
                    host=nas_host,
                    port=int(os.getenv(f"{prefix}_NAS_PORT", "5001")),
                    https=os.getenv(f"{prefix}_NAS_HTTPS", "true").lower() == "true",
                    username=os.getenv(f"{prefix}_NAS_USERNAME", ""),
                    password=os.getenv(f"{prefix}_NAS_PASSWORD", ""),
                )

        if not nas_configs:
            raise ValueError("No NAS configured. Set SYNOLOGY_HOST or {NAME}_NAS_HOST in environment.")

        # Determine default NAS
        default_nas = "default" if "default" in nas_configs else list(nas_configs.keys())[0]

        # Create email config if configured
        email_config = None
        smtp_host = os.getenv("EMAIL_SMTP_HOST")
        if smtp_host:
            email_config = EmailConfig(
                smtp_host=smtp_host,
                smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")),
                username=os.getenv("EMAIL_USERNAME", ""),
                password=os.getenv("EMAIL_PASSWORD", ""),
                from_addr=os.getenv("EMAIL_FROM", ""),
                to_addr=os.getenv("EMAIL_TO", ""),
                use_tls=os.getenv("EMAIL_USE_TLS", "true").lower() == "true",
            )

        return AppConfig(
            default=default_nas,
            nas=nas_configs,
            email=email_config,
            data_dir=Path("data"),
        )
