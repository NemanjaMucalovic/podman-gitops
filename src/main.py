import logging
import os
import time
from pathlib import Path
import argparse
import signal
import sys

from fastapi import FastAPI
from uvicorn import Config, Server

from src.core.config import Config as AppConfig
from src.core.quadlet_handler import QuadletHandler
from src.core.systemd_manager import SystemdManager
from src.core.git_operations import GitOperations
from src.core.app_manager import ApplicationManager
from src.state.manager import StateManager
from src.metrics.collector import MetricsCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
running = True
app_manager = None

# Create FastAPI app
app = FastAPI(
    title="Podman GitOps",
    description="A lightweight GitOps tool for managing Podman container deployments",
    version="0.1.0"
)

@app.get("/")
async def root():
    return {"message": "Podman GitOps API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/applications")
async def list_applications():
    """Get list of all applications and their status."""
    if not app_manager:
        return {"error": "Application manager not initialized"}

    return app_manager.get_status_all_applications()

@app.get("/applications/{app_name}")
async def application_status(app_name: str):
    """Get status of a specific application."""
    if not app_manager:
        return {"error": "Application manager not initialized"}

    return app_manager.get_application_status(app_name)

def signal_handler(sig, frame):
    """Handle termination signals."""
    global running
    logger.info("Received termination signal, shutting down...")
    running = False

def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def get_default_paths():
    """Get default paths for configuration and data."""
    home_dir = Path.home()
    return {
        'config_dir': home_dir / ".local/lib/podman-gitops",
        'config_file': home_dir / ".local/lib/podman-gitops/config.toml",
        'state_db': home_dir / ".local/lib/podman-gitops/state.db",
        'processed_dir': home_dir / ".local/lib/podman-gitops/processed",
        'repo_dir': home_dir / ".local/lib/podman-gitops/repo",
        'systemd_dir': home_dir / ".config/containers/systemd"
    }

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Podman GitOps Service")
    parser.add_argument('--config', '-c', type=str,
                        help='Path to config.toml file')
    parser.add_argument('--no-api', action='store_true',
                        help='Disable API server')
    return parser.parse_args()

def ensure_directories(paths):
    """Ensure all necessary directories exist."""
    for name, path in paths.items():
        if name.endswith('_dir') or name.endswith('_file'):
            path.parent.mkdir(parents=True, exist_ok=True)

def start_api_server(config):
    """Start the API server in a separate thread."""
    if not config.metrics.enabled:
        return None

    try:
        import threading
        import uvicorn

        host = config.metrics.host
        port = config.metrics.port

        server_config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(server_config)

        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        logger.info(f"API server started on {host}:{port}")
        return thread
    except Exception as e:
        logger.error(f"Failed to start API server: {e}")
        return None

def main():
    """Main entry point for the Podman GitOps service."""
    global app_manager

    # Parse command line arguments
    args = parse_args()

    # Get default paths
    paths = get_default_paths()

    # Override config file path if provided
    if args.config:
        paths['config_file'] = Path(args.config)

    # Ensure directories exist
    ensure_directories(paths)

    try:
        # Set up signal handlers for graceful shutdown
        setup_signal_handlers()

        # Load configuration
        logger.info(f"Loading configuration from {paths['config_file']}")
        if not paths['config_file'].exists():
            logger.error(f"Configuration file not found: {paths['config_file']}")
            return 1

        config = AppConfig.from_file(paths['config_file'])
        config.load_app_configs(paths['config_dir'])
        config.expand_paths()

        # Initialize components
        state_manager = StateManager(paths['state_db'])
        systemd_manager = SystemdManager(config.podman.quadlet_dir)
        quadlet_handler = QuadletHandler(
            systemd_dir=config.podman.quadlet_dir,
            processed_dir=paths['processed_dir'],
            systemd_manager=systemd_manager
        )

        # Initialize Git operations if configured
        git_ops = None
        if config.git:
            git_ops = GitOperations(config.git, paths['repo_dir'])

            # Clone repository if it doesn't exist
            if not (paths['repo_dir'] / ".git").exists():
                logger.info(f"Cloning Git repository {config.git.repository_url}")
                if not git_ops.clone_repository():
                    logger.error("Failed to clone Git repository")
                    return 1

        # Initialize metrics collector
        metrics_collector = MetricsCollector()

        # Initialize application manager
        app_manager = ApplicationManager(
            config=config,
            state_manager=state_manager,
            quadlet_handler=quadlet_handler,
            systemd_manager=systemd_manager,
            git_ops=git_ops
        )

        # Start API server if enabled
        api_thread = None if args.no_api else start_api_server(config)

        # Main service loop
        logger.info("Starting main service loop")

        while running:
            try:
                # Process all applications
                start_time = time.time()
                results = app_manager.process_all_applications()

                # Record metrics
                duration = time.time() - start_time
                for app_name, success in results.items():
                    metrics_collector.record_deployment(
                        "success" if success else "failure",
                        duration,
                        {"app": app_name}
                    )

                # Update active containers count
                active_services = 0
                for app_name in config.applications.enabled:
                    app_status = app_manager.get_application_status(app_name)
                    active_services += len([s for s, state in app_status.get('services', {}).items()
                                            if state == 'running'])

                metrics_collector.update_active_containers(active_services)

                # Wait for the next poll interval
                poll_interval = config.git.poll_interval if config.git else 300
                logger.info(f"Waiting {poll_interval} seconds until next check")

                # Use a small wait interval to check running flag more frequently
                for _ in range(poll_interval):
                    if not running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(60)  # Wait a bit before retrying

        logger.info("Service shutdown complete")
        return 0

    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())