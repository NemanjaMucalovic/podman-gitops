from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, root_validator
import toml
import os

import logging
logger = logging.getLogger(__name__)

class EnvironmentConfig(BaseModel):
    """Configuration for environment variables."""
    env_file: Optional[Path] = Field(default=None, description="Path to environment file")
    variables: Dict[str, str] = Field(default_factory=dict, description="Environment variables")

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"  # Allow extra fields to be included as environment variables

    @root_validator(pre=True)
    def extract_env_variables(cls, values):
        """Extract environment variables from the config."""
        env_file = values.get('env_file')
        # Create a copy of the input values
        result = dict(values)

        # Move all fields except env_file to variables
        variables = {}
        to_remove = []

        for key, value in values.items():
            if key != 'env_file':
                variables[key] = value
                to_remove.append(key)

        # Remove the keys we've moved
        for key in to_remove:
            result.pop(key, None)

        # Set the variables field
        result['variables'] = variables

        return result

class ApplicationConfig(BaseModel):
    """Configuration for an application."""
    name: str = Field(..., description="Name of the application")
    description: Optional[str] = Field(default=None, description="Description of the application")
    quadlet_dir: Path = Field(..., description="Directory containing quadlet files")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")

    class Config:
        arbitrary_types_allowed = True


class GitConfig(BaseModel):
    """Configuration for Git operations."""
    repository_url: str = Field(..., description="URL of the Git repository")
    branch: str = Field(default="main", description="Branch to track")
    poll_interval: int = Field(default=300, description="Polling interval in seconds")
    ssh_key_path: Optional[Path] = Field(default=None, description="Path to SSH private key")
    ssh_key_password: Optional[str] = Field(default=None, description="Password for SSH key (if encrypted)")
    repo_dir: Optional[Path] = Field(default=None, description="Custom directory for repository checkout")
    quadlet_files_dir: str = Field(default="", description="Directory inside repository containing quadlet files (e.g., 'draw' or 'quadlets')")

class MetricsConfig(BaseModel):
    """Configuration for metrics endpoint."""
    enabled: bool = Field(default=True, description="Enable metrics endpoint")
    port: int = Field(default=8000, description="Port for metrics endpoint")
    host: str = Field(default="0.0.0.0", description="Host for metrics endpoint")

class ApplicationsConfig(BaseModel):
    """Configuration for applications."""
    enabled: List[str] = Field(default_factory=list, description="List of enabled applications")

class SystemConfig(BaseModel):
    """Configuration for system settings."""
    log_level: str = Field(default="INFO", description="Logging level")
    state_db: Path = Field(default=Path("~/.local/lib/podman-gitops/state.db"), description="Path to state database")
    config_dir: Optional[Path] = Field(default=None, description="Directory for application config files")

class PodmanConfig(BaseModel):
    """Configuration for Podman operations."""
    quadlet_dir: Path = Field(default=Path("~/.config/containers/systemd"),
                             description="Directory for quadlet files")
    backup_dir: Optional[Path] = Field(default=Path("~/.local/lib/podman-gitops/backups"),
                                     description="Directory for backups")

    class Config:
        arbitrary_types_allowed = True

class Config(BaseModel):
    """Main configuration model."""
    system: SystemConfig = Field(default_factory=SystemConfig)
    git: Optional[GitConfig] = Field(default=None)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    applications: ApplicationsConfig = Field(default_factory=ApplicationsConfig)
    app_configs: Dict[str, ApplicationConfig] = Field(default_factory=dict)
    podman: PodmanConfig = Field(default_factory=PodmanConfig)

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

    # @classmethod
    # def from_directory(cls, config_dir: Path) -> 'Config':
    #     """Create a Config instance from a directory of TOML files."""
    #     try:
    #         # Read main config file
    #         main_config_path = config_dir / "main.toml"
    #         if not main_config_path.exists():
    #             raise ValueError(f"Main configuration file not found at {main_config_path}")
    #
    #         with open(main_config_path, 'r') as f:
    #             config_dict = toml.loads(f.read())
    #
    #         # Initialize config object
    #         config = cls(**config_dict)
    #
    #         # Read application config files
    #         for app_name in config.applications.enabled:
    #             app_config_path = config_dir / f"{app_name}.toml"
    #             if not app_config_path.exists():
    #                 raise ValueError(f"Application configuration file not found for {app_name} at {app_config_path}")
    #
    #             with open(app_config_path, 'r') as f:
    #                 app_config_dict = toml.loads(f.read())
    #                 app_config = ApplicationConfig(**app_config_dict.get('application', {}))
    #
    #                 # Handle environment section
    #                 if 'env' in app_config_dict:
    #                     app_config.env = EnvironmentConfig(**app_config_dict.get('env', {}))
    #
    #                 config.app_configs[app_name] = app_config
    #         logger.info(f"Config {config}")
    #         return config
    #     except Exception as e:
    #         raise ValueError(f"Failed to read configuration from directory {config_dir}: {e}")


    def expand_paths(self) -> 'Config':
        """Expand all path variables to absolute paths."""
        # Expand Podman paths
        self.podman.quadlet_dir = Path(os.path.expanduser(str(self.podman.quadlet_dir)))
        if self.podman.backup_dir:
            self.podman.backup_dir = Path(os.path.expanduser(str(self.podman.backup_dir)))

        # Expand Git paths
        if self.git and self.git.ssh_key_path:
            self.git.ssh_key_path = Path(os.path.expanduser(str(self.git.ssh_key_path)))
        if self.git and self.git.repo_dir:
            self.git.repo_dir = Path(os.path.expanduser(str(self.git.repo_dir)))

        # Expand application paths
        for app_name, app_config in self.app_configs.items():
            app_config.quadlet_dir = Path(os.path.expanduser(str(app_config.quadlet_dir)))

            # Note: we're no longer checking for environment.env_file
            # If you need to handle env_file paths, add that logic here

        return self

    def load_app_configs(self, config_dir: Path) -> 'Config':
        """Load application configurations from a directory.

        Args:
            config_dir: Directory containing application configuration files

        Returns:
            Self with loaded application configurations
        """
        try:
            # Read application config files
            for app_name in self.applications.enabled:
                app_config_path = config_dir / f"{app_name}.toml"
                if not app_config_path.exists():
                    logger.warning(f"Application configuration file not found for {app_name} at {app_config_path}")
                    continue

                with open(app_config_path, 'r') as f:
                    app_config_dict = toml.loads(f.read())

                if 'application' not in app_config_dict:
                    logger.warning(f"No application section found in {app_config_path}")
                    continue

                app_section = app_config_dict['application']

                # Ensure application has a name
                if 'name' not in app_section:
                    app_section['name'] = app_name

                # Create ApplicationConfig
                app_config = ApplicationConfig(**app_section)

                # Add environment variables if present
                if 'env' in app_config_dict:
                    app_config.env = {k: str(v) for k, v in app_config_dict['env'].items()}
                else:
                    app_config.env = {}

                self.app_configs[app_name] = app_config
                logger.info(f"Loaded configuration for application {app_name}")

            return self
        except Exception as e:
            logger.error(f"Failed to load application configurations: {e}")
            raise