import logging
import os
import stat
from string import Template
from pathlib import Path
from typing import Dict, Optional
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

class EnvProcessor:
    """Processes environment variables and handles template substitution."""

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize the environment processor.

        Args:
            base_dir: Base directory for processed files
        """
        self.base_dir = base_dir or Path.home() / ".local/lib/podman-gitops/processed"
        self._ensure_directory(self.base_dir)

    def _ensure_directory(self, directory: Path) -> None:
        """Ensure a directory exists with secure permissions."""
        if not directory.exists():
            directory.mkdir(parents=True, mode=0o700)  # Secure permissions
        elif not directory.is_dir():
            raise ValueError(f"{directory} exists but is not a directory")

    def load_environment(self, env_file: Optional[Path], variables: Dict[str, str]) -> Dict[str, str]:
        """Load environment variables from a file and merge with provided variables.

        Args:
            env_file: Path to .env file
            variables: Dictionary of variables to include

        Returns:
            Dict of environment variables
        """
        env_vars = {}

        # Load from env file if provided
        if env_file and env_file.exists():
            try:
                logger.info(f"Loading environment from {env_file}")
                env_from_file = dotenv_values(env_file)
                env_vars.update(env_from_file)
                logger.debug(f"Loaded {len(env_from_file)} variables from {env_file}")
            except Exception as e:
                logger.error(f"Failed to load environment from {env_file}: {e}")
                raise

        # Add provided variables (overriding file values if duplicated)
        if variables:
            env_vars.update(variables)

        # Optionally include system environment variables
        # Uncomment if you want system env vars to be available
        # env_vars = {**os.environ, **env_vars}

        return env_vars

    def process_template(self, template_path: Path, env_vars: Dict[str, str]) -> str:
        """Process a template file with the given environment variables.

        Args:
            template_path: Path to the template file
            env_vars: Dictionary of environment variables for substitution

        Returns:
            Processed template content
        """
        try:
            logger.info(f"Processing template {template_path}")

            # Read template content
            if not template_path.exists():
                raise FileNotFoundError(f"Template file not found: {template_path}")

            template_content = template_path.read_text()

            # Create template and substitute variables
            template = Template(template_content)
            processed_content = template.safe_substitute(env_vars)

            # Check for unsubstituted variables
            remaining_vars = []
            for line in processed_content.splitlines():
                if "${" in line or "$" in line and "}" in line:
                    remaining_vars.append(line)

            if remaining_vars:
                logger.warning(f"Some variables in {template_path} were not substituted:")
                for line in remaining_vars:
                    logger.warning(f"  {line}")

            return processed_content

        except Exception as e:
            logger.error(f"Failed to process template {template_path}: {e}")
            raise

    def write_processed_file(self, content: str, output_path: Path) -> Path:
        """Write processed content to a file with secure permissions.

        Args:
            content: Processed content to write
            output_path: Path to write the file to

        Returns:
            Path to the written file
        """
        try:
            logger.info(f"Writing processed file to {output_path}")

            # Create parent directory if it doesn't exist
            self._ensure_directory(output_path.parent)

            # Write content
            output_path.write_text(content)

            # Set secure permissions
            os.chmod(output_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

            return output_path

        except Exception as e:
            logger.error(f"Failed to write processed file to {output_path}: {e}")
            raise

    def process_quadlet_file(self,
                             template_path: Path,
                             app_name: str,
                             env_vars: Dict[str, str],
                             output_dir: Optional[Path] = None) -> Path:
        """Process a quadlet template file and write it to the output directory.

        Args:
            template_path: Path to the template file
            app_name: Name of the application
            env_vars: Dictionary of environment variables for substitution
            output_dir: Directory to write the processed file to (default: self.base_dir)

        Returns:
            Path to the processed file
        """
        try:
            # Add APP_NAME to env vars if not already present
            if 'APP_NAME' not in env_vars:
                env_vars['APP_NAME'] = app_name

            # Process the template
            processed_content = self.process_template(template_path, env_vars)

            # Determine output path
            if output_dir is None:
                output_dir = self.base_dir / app_name

            output_path = output_dir / template_path.name

            # Write the processed file
            return self.write_processed_file(processed_content, output_path)

        except Exception as e:
            logger.error(f"Failed to process quadlet file {template_path}: {e}")
            raise