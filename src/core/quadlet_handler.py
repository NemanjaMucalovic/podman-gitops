import logging
from pathlib import Path
from typing import List, Optional, Dict, Set
from pydantic import BaseModel

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

    def __init__(self, quadlet_dir: Path, systemd_manager=None):
        self.quadlet_dir = quadlet_dir
        self.systemd_manager = systemd_manager
        if not self.quadlet_dir.exists():
            logger.info(f"Creating quadlet directory: {self.quadlet_dir}")
            self.quadlet_dir.mkdir(parents=True)
        logger.info(f"Using quadlet directory: {self.quadlet_dir}")

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

    def deploy_quadlet_file(self, file_path: Path) -> bool:
        """Deploy a quadlet file to the system directory."""
        try:
            # Get file type
            file_type = self._get_file_type(file_path)
            
            # Create QuadletFile instance
            quadlet_file = QuadletFile(
                name=file_path.stem,
                content=file_path.read_text(),
                path=file_path,
                type=file_type
            )
            
            # Determine target path
            if file_type in self.QUADLET_TYPES:
                target_path = self.quadlet_dir / f"{quadlet_file.name}{self.QUADLET_TYPES[file_type]}"
            else:
                target_path = self.quadlet_dir / file_path.name
            
            # Create backup if file exists
            if target_path.exists():
                backup_path = target_path.parent / f"{target_path.name}.bak"
                target_path.rename(backup_path)
            
            # Deploy the file
            target_path.write_text(quadlet_file.content)
            logger.info(f"Deployed {file_type} file: {quadlet_file.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to deploy file {file_path}: {e}")
            return False

    def remove_quadlet_file(self, name: str, file_type: str) -> bool:
        """Remove a quadlet file from the system directory."""
        try:
            # Determine file path
            if file_type in self.QUADLET_TYPES:
                file_path = self.quadlet_dir / f"{name}{self.QUADLET_TYPES[file_type]}"
            else:
                file_path = self.quadlet_dir / name
            
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
        
        for file_path in self.quadlet_dir.glob('*'):
            if file_path.is_file():
                file_type = self._get_file_type(file_path)
                deployed_files[file_type].add(file_path.stem)
        
        return deployed_files 