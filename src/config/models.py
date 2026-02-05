"""Configuration models for Synology Guru."""

from pathlib import Path

from pydantic import BaseModel, Field


class NASConfig(BaseModel):
    """Configuration for a single NAS."""

    host: str
    port: int = 5001
    https: bool = True
    username: str = ""
    password: str = ""


class EmailConfig(BaseModel):
    """Email notification configuration."""

    smtp_host: str
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addr: str = ""
    use_tls: bool = True


class AppConfig(BaseModel):
    """Application configuration with multi-NAS support."""

    default: str = "default"
    nas: dict[str, NASConfig] = Field(default_factory=dict)
    email: EmailConfig | None = None
    data_dir: Path = Path("data")

    def get_nas(self, name: str | None = None) -> NASConfig:
        """Get NAS configuration by name, or default if not specified."""
        target = name or self.default
        if target not in self.nas:
            raise ValueError(f"NAS '{target}' not found in configuration")
        return self.nas[target]

    def get_nas_names(self) -> list[str]:
        """Get list of configured NAS names."""
        return list(self.nas.keys())

    def get_data_dir(self, nas_name: str | None = None) -> Path:
        """Get data directory for a specific NAS."""
        target = nas_name or self.default
        return self.data_dir / target
