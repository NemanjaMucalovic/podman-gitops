import logging
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class RollbackManager:
    """Manages rollback operations for failed deployments."""

    def __init__(self, backup_dir: Path):
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, file_path: Path) -> Optional[Path]:
        """Create a backup of a file."""
        try:
            if not file_path.exists():
                return None

            # Create backup with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
            
            # Copy the file
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup of {file_path}: {e}")
            return None

    def restore_backup(self, file_path: Path, backup_path: Path) -> bool:
        """Restore a file from backup."""
        try:
            if not backup_path.exists():
                logger.error(f"Backup file not found: {backup_path}")
                return False

            # Create backup of current file if it exists
            if file_path.exists():
                self.create_backup(file_path)

            # Restore from backup
            shutil.copy2(backup_path, file_path)
            logger.info(f"Restored from backup: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore from backup {backup_path}: {e}")
            return False

    def get_latest_backup(self, file_name: str) -> Optional[Path]:
        """Get the latest backup for a file."""
        try:
            # Find all backups for the file
            backups = list(self.backup_dir.glob(f"{file_name}_*"))
            if not backups:
                return None

            # Sort by modification time and get the latest
            return max(backups, key=lambda p: p.stat().st_mtime)
        except Exception as e:
            logger.error(f"Failed to get latest backup for {file_name}: {e}")
            return None

    def cleanup_old_backups(self, max_backups: int = 5) -> None:
        """Clean up old backups, keeping only the most recent ones."""
        try:
            # Group backups by base name
            backup_groups = {}
            for backup in self.backup_dir.glob("*_*"):
                base_name = backup.stem.split("_")[0]
                if base_name not in backup_groups:
                    backup_groups[base_name] = []
                backup_groups[base_name].append(backup)

            # Clean up each group
            for base_name, backups in backup_groups.items():
                # Sort by modification time
                backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                
                # Remove old backups
                for backup in backups[max_backups:]:
                    backup.unlink()
                    logger.info(f"Removed old backup: {backup}")
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")

    def list_backups(self) -> List[Path]:
        """List all available backups."""
        try:
            return sorted(self.backup_dir.glob("*_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return [] 