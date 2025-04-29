from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import toml

class GitConfig(BaseModel):
    """Configuration for Git operations."""
    repository_url: str = Field(..., description="URL of the Git repository")
    branch: str = Field(default="main", description="Branch to track")
    poll_interval: int = Field(default=300, description="Polling interval in seconds")
    ssh_key_path: Optional[Path] = Field(default=None, description="Path to SSH private key")
    ssh_key_password: Optional[str] = Field(default=None, description="Password for SSH key (if encrypted)")
    repo_dir: Optional[Path] = Field(default=None, description="Custom directory for repository checkout")
    quadlet_files_dir: str = Field(default="", description="Directory inside repository containing quadlet files (e.g., 'draw' or 'quadlets')")

class PodmanConfig(BaseModel):
    """Configuration for Podman operations."""
    quadlet_dir: Path = Field(default=Path("/etc/containers/systemd"), description="Directory for quadlet files")
    backup_dir: Path = Field(default=Path("/var/lib/podman-gitops/backups"), description="Directory for backups")

class MetricsConfig(BaseModel):
    """Configuration for metrics endpoint."""
    enabled: bool = Field(default=True, description="Enable metrics endpoint")
    port: int = Field(default=8000, description="Port for metrics endpoint")
    host: str = Field(default="0.0.0.0", description="Host for metrics endpoint")

class Config(BaseModel):
    """Main configuration model."""
    git: GitConfig
    podman: PodmanConfig = Field(default_factory=PodmanConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    log_level: str = Field(default="INFO", description="Logging level")

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_toml(cls, toml_str: str) -> 'Config':
        """Create a Config instance from a TOML string."""
        try:
            config_dict = toml.loads(toml_str)
            return cls(**config_dict)
        except Exception as e:
            raise ValueError(f"Failed to parse TOML configuration: {e}")

    @classmethod
    def from_file(cls, file_path: Path) -> 'Config':
        """Create a Config instance from a TOML file."""
        try:
            with open(file_path, 'r') as f:
                return cls.from_toml(f.read())
        except Exception as e:
            raise ValueError(f"Failed to read configuration file {file_path}: {e}") 