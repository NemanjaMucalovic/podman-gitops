import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from pydantic import BaseModel

from .env_processor import EnvProcessor

logger = logging.getLogger(__name__)

class QuadletFile(BaseModel):
    """Represents a quadlet file configuration."""
    name: str
    content: str
    path: Path
    type: str  # container, image, network, volume, config

class QuadletHandler:
    """Handles processing and deployment of quadlet files."""

    # Define supported file types and their extensions
    QUADLET_TYPES = {
        'container': '.container',
        'image': '.image',
        'network': '.network',
        'volume': '.volume'
    }

    # Define additional configuration file patterns
    CONFIG_PATTERNS = [
        'settings.json',
        'config.json',
        '*.env',
        '*.toml',
        '*.yaml',
        '*.yml'
    ]

    def __init__(self,
                 systemd_dir: Path,
                 processed_dir: Optional[Path] = None,
                 systemd_manager=None):
        """Initialize the quadlet handler.

        Args:
            systemd_dir: Directory where processed quadlet files should be placed
            processed_dir: Directory for storing processed files before deployment
            systemd_manager: SystemdManager instance for interacting with systemd
        """
        self.systemd_dir = Path(os.path.expanduser(str(systemd_dir)))
        self.processed_dir = processed_dir or Path.home() / ".local/lib/podman-gitops/processed"
        self.systemd_manager = systemd_manager
        self.env_processor = EnvProcessor(self.processed_dir)

        # Ensure directories exist
        self._ensure_directory(self.systemd_dir)
        self._ensure_directory(self.processed_dir)

        logger.info(f"Using systemd directory: {self.systemd_dir}")
        logger.info(f"Using processed files directory: {self.processed_dir}")

    def _ensure_directory(self, directory: Path) -> None:
        """Ensure a directory exists."""
        if not directory.exists():
            logger.info(f"Creating directory: {directory}")
            directory.mkdir(parents=True, exist_ok=True)
        elif not directory.is_dir():
            raise ValueError(f"{directory} exists but is not a directory")

    def _get_file_type(self, file_path: Path) -> str:
        """Determine the type of file based on its extension."""
        suffix = file_path.suffix
        for file_type, extension in self.QUADLET_TYPES.items():
            if suffix == extension:
                return file_type
        return 'config'

    def find_quadlet_files(self, directory: Path) -> List[Path]:
        """Find all quadlet and configuration files in the given directory."""
        logger.info(f"Searching for files in: {directory}")

        # Check if directory exists
        if not directory.exists():
            logger.warning(f"Directory {directory} does not exist")
            return []

        # Convert to absolute path and expand user
        directory = Path(os.path.expanduser(str(directory)))

        # Find all quadlet files
        quadlet_files = []
        for extension in self.QUADLET_TYPES.values():
            quadlet_files.extend(directory.glob(f"*{extension}"))

        # Find configuration files
        config_files = []
        for pattern in self.CONFIG_PATTERNS:
            config_files.extend(directory.glob(pattern))

        all_files = quadlet_files + config_files
        logger.info(f"Found {len(all_files)} files: {[f.name for f in all_files]}")
        return all_files

    def parse_quadlet_file(self, file_path: Path) -> Optional[QuadletFile]:
        """Parse a file and return its configuration."""
        try:
            logger.info(f"Parsing file: {file_path}")

            # Convert to absolute path and expand user
            file_path = Path(os.path.expanduser(str(file_path)))

            # Check if file exists
            if not file_path.exists():
                logger.warning(f"File {file_path} does not exist")
                return None

            content = file_path.read_text()
            name = file_path.stem
            file_type = self._get_file_type(file_path)
            logger.info(f"Successfully parsed {file_type} file: {name}")
            return QuadletFile(
                name=name,
                content=content,
                path=file_path,
                type=file_type
            )
        except Exception as e:
            logger.error(f"Failed to parse file {file_path}: {e}")
            return None

    def process_and_deploy_app_quadlets(self,
                                        app_name: str,
                                        quadlet_dir: Path,
                                        env_vars: Optional[Dict[str, str]] = None) -> Tuple[bool, List[str]]:
        """Process all quadlet files for an application and deploy them.

        Args:
            app_name: Name of the application
            quadlet_dir: Directory containing quadlet files
            env_vars: Environment variables for template substitution

        Returns:
            (success, deployed_services): Tuple of success status and list of deployed service names
        """
        try:
            logger.info(f"Processing quadlet files for application {app_name}")

            # Find all quadlet files
            quadlet_files = self.find_quadlet_files(quadlet_dir)
            if not quadlet_files:
                logger.warning(f"No quadlet files found in {quadlet_dir}")
                return True, []

            # Group files by type for ordered processing
            files_by_type = {
                'network': [],
                'volume': [],
                'image': [],
                'container': [],
                'config': []
            }

            for file_path in quadlet_files:
                file_type = self._get_file_type(file_path)
                files_by_type[file_type].append(file_path)

            # Process all files
            processed_files = []
            deployed_services = []
            app_processed_dir = self.processed_dir / app_name

            # Order: network, volume, image, container
            processing_order = ['network', 'volume', 'image', 'container', 'config']

            for file_type in processing_order:
                for file_path in files_by_type[file_type]:
                    # Process the template
                    try:
                        processed_path = self.env_processor.process_quadlet_file(
                            file_path,
                            app_name,
                            env_vars,
                            app_processed_dir
                        )
                        processed_files.append((processed_path, file_type))

                        # Deploy to systemd directory
                        if self.deploy_processed_file(processed_path, file_type):
                            if file_type == 'container':
                                deployed_services.append(processed_path.stem)
                        else:
                            logger.error(f"Failed to deploy processed file: {processed_path}")
                            return False, deployed_services

                    except Exception as e:
                        logger.error(f"Failed to process quadlet file {file_path}: {e}")
                        return False, deployed_services

            return True, deployed_services

        except Exception as e:
            logger.error(f"Failed to process quadlet files for application {app_name}: {e}")
            return False, []

    def deploy_processed_file(self, processed_path: Path, file_type: str) -> bool:
        """Deploy a processed file to the systemd directory.

        Args:
            processed_path: Path to the processed file
            file_type: Type of the file (container, image, network, volume, config)

        Returns:
            Success status
        """
        try:
            logger.info(f"Deploying processed file: {processed_path}")

            # Determine target path in systemd directory
            if file_type in self.QUADLET_TYPES:
                target_path = self.systemd_dir / f"{processed_path.stem}{self.QUADLET_TYPES[file_type]}"
            else:
                target_path = self.systemd_dir / processed_path.name

            # Create backup if file exists
            if target_path.exists():
                backup_path = target_path.parent / f"{target_path.name}.bak"
                logger.info(f"Creating backup: {backup_path}")
                shutil.copy2(target_path, backup_path)

            # Copy the processed file to the systemd directory
            logger.info(f"Copying processed file to: {target_path}")
            shutil.copy2(processed_path, target_path)

            # Set permissions
            os.chmod(target_path, 0o644)  # rw-r--r--

            return True

        except Exception as e:
            logger.error(f"Failed to deploy processed file {processed_path}: {e}")
            return False

    def remove_quadlet_file(self, name: str, file_type: str) -> bool:
        """Remove a quadlet file from the systemd directory."""
        try:
            # Determine file path
            if file_type in self.QUADLET_TYPES:
                file_path = self.systemd_dir / f"{name}{self.QUADLET_TYPES[file_type]}"
            else:
                file_path = self.systemd_dir / name

            # Remove the file
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Removed {file_type} file: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove file {name}: {e}")
            return False

    def get_deployed_files(self) -> Dict[str, Set[str]]:
        """Get a list of all deployed files by type."""
        deployed_files = {
            'container': set(),
            'image': set(),
            'network': set(),
            'volume': set(),
            'config': set()
        }

        for file_path in self.systemd_dir.glob('*'):
            if file_path.is_file() and not file_path.name.endswith('.bak'):
                file_type = self._get_file_type(file_path)
                deployed_files[file_type].add(file_path.stem)

        return deployed_files

    def cleanup_processed_files(self, app_name: Optional[str] = None, older_than_days: int = 7) -> int:
        """Clean up old processed files.

        Args:
            app_name: Name of application to clean up (None for all)
            older_than_days: Remove files older than this many days

        Returns:
            Number of files removed
        """
        import time
        from datetime import datetime, timedelta

        try:
            logger.info(f"Cleaning up processed files older than {older_than_days} days")

            # Calculate cutoff time
            cutoff_time = datetime.now() - timedelta(days=older_than_days)
            cutoff_timestamp = cutoff_time.timestamp()

            # Determine directory to clean
            if app_name:
                cleanup_dir = self.processed_dir / app_name
            else:
                cleanup_dir = self.processed_dir

            # Check if directory exists
            if not cleanup_dir.exists():
                logger.warning(f"Cleanup directory {cleanup_dir} does not exist")
                return 0

            # Find and remove old files
            removed_count = 0
            for file_path in cleanup_dir.glob('**/*'):
                if file_path.is_file():
                    mod_time = file_path.stat().st_mtime
                    if mod_time < cutoff_timestamp:
                        try:
                            file_path.unlink()
                            removed_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to remove old file {file_path}: {e}")

            logger.info(f"Removed {removed_count} old processed files")
            return removed_count

        except Exception as e:
            logger.error(f"Failed to cleanup processed files: {e}")
            return 0