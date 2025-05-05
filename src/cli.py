import typer
import logging
import json
from pathlib import Path
from typing import Optional

from src.core.config import Config
from src.core.git_operations import GitOperations
from src.core.quadlet_handler import QuadletHandler
from src.core.systemd_manager import SystemdManager
from src.core.app_manager import ApplicationManager
from src.state.manager import StateManager
from src.core.logging import setup_logging, get_logger
from src.main import main as service_main, get_default_paths, ensure_directories

# Get logger for CLI
logger = get_logger("src.cli")

# Create Typer app
app = typer.Typer(help="Podman GitOps CLI tool")
app_cmd = typer.Typer(help="Manage applications")
app.add_typer(app_cmd, name="app")
config_cmd = typer.Typer(help="Manage configuration")
app.add_typer(config_cmd, name="config")

def initialize_components(config_file: Path):
    """Initialize all components based on configuration.

    Args:
        config_file: Path to the configuration file

    Returns:
        Tuple of (config, app_manager)
    """
    # Get user paths
    paths = get_default_paths()

    # Ensure all directories exist
    ensure_directories(paths)

    # Set up logging
    setup_logging(paths['log_dir'], "INFO")

    # Load configuration
    if not config_file.exists():
        raise typer.BadParameter(f"Configuration file not found: {config_file}")

    config = Config.from_file(config_file)
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

    # Initialize application manager
    app_manager = ApplicationManager(
        config=config,
        state_manager=state_manager,
        quadlet_handler=quadlet_handler,
        systemd_manager=systemd_manager,
        git_ops=git_ops
    )

    return config, app_manager

# Main service commands
@app.command()
def start(
    config: Optional[Path] = typer.Option(
        str(get_default_paths()['config_file']),
        "--config", "-c",
        help="Path to config.toml file",
        exists=True
    ),
    no_api: bool = typer.Option(
        False,
        help="Disable API server"
    )
):
    """Start the GitOps service."""
    try:
        # Call the main function directly with parameters
        exit_code = service_main(config_path=config, no_api=no_api)
        raise typer.Exit(code=exit_code)
    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise typer.Exit(code=1)

# Application commands
@app_cmd.command("list")
def list_apps(
    config: Optional[Path] = typer.Option(
        str(get_default_paths()['config_file']),
        "--config", "-c",
        help="Path to config.toml file",
        exists=True
    ),
    json_output: bool = typer.Option(
        False,
        "--json", "-j",
        help="Output in JSON format"
    )
):
    """List all configured applications."""
    try:
        # Initialize components
        config_path = Path(config)
        config_obj, app_manager = initialize_components(config_path)

        # Get application status
        app_status = app_manager.get_status_all_applications()

        if json_output:
            # Print JSON output
            typer.echo(json.dumps(app_status, indent=2))
        else:
            # Print formatted output
            typer.echo("\nConfigured Applications:")
            typer.echo("=" * 80)

            for app_name, status in app_status.items():
                status_symbol = "✅" if status.get('overall_status') == 'healthy' else "❌"
                typer.echo(f"\n{status_symbol} {app_name}")

                # Application description
                app_config = config_obj.app_configs.get(app_name)
                if app_config and app_config.description:
                    typer.echo(f"   Description: {app_config.description}")

                # Service count and status
                service_count = status.get('service_count', 0)
                typer.echo(f"   Services: {service_count}")

                # State counts
                state_counts = status.get('state_counts', {})
                if state_counts:
                    states = ", ".join([f"{state}: {count}" for state, count in state_counts.items()])
                    typer.echo(f"   States: {states}")

                # Last deployment
                last_deployment = status.get('last_deployment', {})
                if last_deployment:
                    deploy_status = last_deployment.get('status', 'unknown')
                    deploy_time = last_deployment.get('timestamp', 'unknown')
                    typer.echo(f"   Last Deployment: {deploy_status} at {deploy_time}")

                # Error count
                error_count = status.get('error_count', 0)
                if error_count > 0:
                    typer.echo(f"   Errors: {error_count}")

    except Exception as e:
        logger.error(f"Failed to list applications: {e}")
        raise typer.Exit(code=1)

@app_cmd.command("status")
def app_status(
    app_name: str = typer.Argument(..., help="Name of the application"),
    config: Optional[Path] = typer.Option(
        str(get_default_paths()['config_file']),
        "--config", "-c",
        help="Path to config.toml file",
        exists=True
    ),
    json_output: bool = typer.Option(
        False,
        "--json", "-j",
        help="Output in JSON format"
    )
):
    """Get detailed status of an application."""
    try:
        # Initialize components
        config_path = Path(config)
        config_obj, app_manager = initialize_components(config_path)

        # Check if application exists
        if app_name not in config_obj.applications.enabled:
            typer.echo(f"Application '{app_name}' is not enabled in configuration")
            return

        # Get application status
        status = app_manager.get_application_status(app_name)

        if json_output:
            # Print JSON output
            typer.echo(json.dumps(status, indent=2))
        else:
            # Print formatted output
            typer.echo(f"\nApplication: {app_name}")
            typer.echo("=" * 80)

            # Application description
            app_config = config_obj.app_configs.get(app_name)
            if app_config and app_config.description:
                typer.echo(f"Description: {app_config.description}")

            # Overall status
            overall_status = status.get('overall_status', 'unknown')
            typer.echo(f"Status: {overall_status}")

            # Last deployment
            last_deployment = status.get('last_deployment', {})
            if last_deployment:
                typer.echo("\nLast Deployment:")
                typer.echo(f"  Status: {last_deployment.get('status', 'unknown')}")
                typer.echo(f"  Time: {last_deployment.get('timestamp', 'unknown')}")
                typer.echo(f"  Commit: {last_deployment.get('commit_hash', 'unknown')}")
                if last_deployment.get('error_message'):
                    typer.echo(f"  Error: {last_deployment.get('error_message')}")

            # Services
            services = status.get('services', {})
            if services:
                typer.echo("\nServices:")
                for service_name, state in services.items():
                    typer.echo(f"  {service_name}: {state}")

            # Error count
            error_count = status.get('error_count', 0)
            if error_count > 0:
                typer.echo(f"\nErrors: {error_count}")

    except Exception as e:
        logger.error(f"Failed to get application status: {e}")
        raise typer.Exit(code=1)

# Additional commands omitted for brevity but would follow the same pattern
# This includes: start_app, stop_app, restart_app, deploy_app, status, list_services, restart, show_config

if __name__ == "__main__":
    app()