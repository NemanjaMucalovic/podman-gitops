import logging
import logging.handlers
from pathlib import Path
from typing import Optional

def setup_logging(
    log_dir: Path,
    log_level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> None:
    """Set up logging with rotation."""
    
    # Create log directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s: %(message)s'
    )
    
    # Set up file handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "podman-gitops.log",
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Set up component-specific loggers
    components = [
        "git_operations",
        "quadlet_handler",
        "systemd_manager",
        "health_checker",
        "state_manager"
    ]
    
    for component in components:
        logger = logging.getLogger(f"src.core.{component}")
        logger.setLevel(log_level)
        
        # Add component-specific file handler
        component_handler = logging.handlers.RotatingFileHandler(
            log_dir / f"{component}.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        component_handler.setFormatter(file_formatter)
        logger.addHandler(component_handler)

def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific component."""
    return logging.getLogger(name) 