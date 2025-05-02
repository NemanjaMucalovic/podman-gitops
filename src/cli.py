import click
import logging
import os
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional

from src.core.config import Config
from src.core.git_operations import GitOperations
from src.core.quadlet_handler import QuadletHandler
from src.core.systemd_manager import SystemdManager
from src.core.app_manager import ApplicationManager
from src.core.env_processor import EnvProcessor
from src.state.manager import StateManager
from src.core.logging import setup_logging, get_logger

# Get logger for CLI
logger = get_logger("src.cli")

def get_user_paths():
    """Get user-specific paths for rootless operation."""
    user_home = Path.home()
    return {
        'config_dir': user_home / '.local/lib/podman-gitops',
        'config_file': user_home / '.local/lib/podman-gitops/main.toml',
        'repo_dir': user_home / '.local/lib/podman-gitops/repo',
        'backup_dir': user_home / '.local/lib/podman-gitops/backups',
        'state_db': user_home / '.local/lib/podman-gitops/state.db',
        'processed_dir': user_home / '.local/lib/podman-gitops/processed',
        'log_dir': user_home / '.local/lib/podman-gitops/logs'
    }

def ensure_directories(paths):
    """Ensure all necessary directories exist."""
    for path in paths.values():
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)

def initialize_components(config_file: Path):
    """Initialize all components based on configuration.

    Args:
        config_file: Path to the configuration file

    Returns:
        Tuple of (config, app_manager)
    """
    # Get user paths
    paths = get_user_paths()

    # Ensure all directories exist
    ensure_directories(paths)

    # Set up logging
    setup_logging(paths['log_dir'], "INFO")

    # Load configuration
    if not config_file.exists():
        raise click.ClickException(f"Configuration file not found: {config_file}")

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

@click.group()
def cli():
    """Podman GitOps CLI tool."""
    pass

# Main service commands
@cli.command()
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def start(config):
    """Start the GitOps service."""
    try:
        from src.main import main as service_main
        import sys

        # Pass the config file to the main service
        sys.argv = ['main.py', '--config', config]
        sys.exit(service_main())

    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise click.ClickException(str(e))

# Application commands
@cli.group()
def app():
    """Manage applications."""
    pass

@app.command('list')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
@click.option('--json', '-j', is_flag=True, help='Output in JSON format')
def list_apps(config, json):
    """List all configured applications."""
    try:
        # Initialize components
        config_path = Path(config)
        config_obj, app_manager = initialize_components(config_path)

        # Get application status
        app_status = app_manager.get_status_all_applications()

        if json:
            # Print JSON output
            click.echo(json.dumps(app_status, indent=2))
        else:
            # Print formatted output
            click.echo("\nConfigured Applications:")
            click.echo("=" * 80)

            for app_name, status in app_status.items():
                status_symbol = "✅" if status.get('overall_status') == 'healthy' else "❌"
                click.echo(f"\n{status_symbol} {app_name}")

                # Application description
                app_config = config_obj.app_configs.get(app_name)
                if app_config and app_config.description:
                    click.echo(f"   Description: {app_config.description}")

                # Service count and status
                service_count = status.get('service_count', 0)
                click.echo(f"   Services: {service_count}")

                # State counts
                state_counts = status.get('state_counts', {})
                if state_counts:
                    states = ", ".join([f"{state}: {count}" for state, count in state_counts.items()])
                    click.echo(f"   States: {states}")

                # Last deployment
                last_deployment = status.get('last_deployment', {})
                if last_deployment:
                    deploy_status = last_deployment.get('status', 'unknown')
                    deploy_time = last_deployment.get('timestamp', 'unknown')
                    click.echo(f"   Last Deployment: {deploy_status} at {deploy_time}")

                # Error count
                error_count = status.get('error_count', 0)
                if error_count > 0:
                    click.echo(f"   Errors: {error_count}")

    except Exception as e:
        logger.error(f"Failed to list applications: {e}")
        raise click.ClickException(str(e))

@app.command('status')
@click.argument('app_name')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
@click.option('--json', '-j', is_flag=True, help='Output in JSON format')
def app_status(app_name, config, json):
    """Get detailed status of an application."""
    try:
        # Initialize components
        config_path = Path(config)
        config_obj, app_manager = initialize_components(config_path)

        # Check if application exists
        if app_name not in config_obj.applications.enabled:
            click.echo(f"Application '{app_name}' is not enabled in configuration")
            return

        # Get application status
        status = app_manager.get_application_status(app_name)

        if json:
            # Print JSON output
            click.echo(json.dumps(status, indent=2))
        else:
            # Print formatted output
            click.echo(f"\nApplication: {app_name}")
            click.echo("=" * 80)

            # Application description
            app_config = config_obj.app_configs.get(app_name)
            if app_config and app_config.description:
                click.echo(f"Description: {app_config.description}")

            # Overall status
            overall_status = status.get('overall_status', 'unknown')
            click.echo(f"Status: {overall_status}")

            # Last deployment
            last_deployment = status.get('last_deployment', {})
            if last_deployment:
                click.echo("\nLast Deployment:")
                click.echo(f"  Status: {last_deployment.get('status', 'unknown')}")
                click.echo(f"  Time: {last_deployment.get('timestamp', 'unknown')}")
                click.echo(f"  Commit: {last_deployment.get('commit_hash', 'unknown')}")
                if last_deployment.get('error_message'):
                    click.echo(f"  Error: {last_deployment.get('error_message')}")

            # Services
            services = status.get('services', {})
            if services:
                click.echo("\nServices:")
                for service_name, state in services.items():
                    click.echo(f"  {service_name}: {state}")

            # Error count
            error_count = status.get('error_count', 0)
            if error_count > 0:
                click.echo(f"\nErrors: {error_count}")

    except Exception as e:
        logger.error(f"Failed to get application status: {e}")
        raise click.ClickException(str(e))

@app.command('start')
@click.argument('app_name')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def start_app(app_name, config):
    """Start all services for an application."""
    try:
        # Initialize components
        config_path = Path(config)
        config_obj, app_manager = initialize_components(config_path)

        # Check if application exists
        if app_name not in config_obj.applications.enabled:
            click.echo(f"Application '{app_name}' is not enabled in configuration")
            return

        # Start the application
        click.echo(f"Starting application: {app_name}")
        if app_manager.start_application(app_name):
            click.echo(f"Application {app_name} started successfully")
        else:
            click.echo(f"Failed to start application {app_name}")

    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise click.ClickException(str(e))

@app.command('stop')
@click.argument('app_name')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def stop_app(app_name, config):
    """Stop all services for an application."""
    try:
        # Initialize components
        config_path = Path(config)
        config_obj, app_manager = initialize_components(config_path)

        # Check if application exists
        if app_name not in config_obj.applications.enabled:
            click.echo(f"Application '{app_name}' is not enabled in configuration")
            return

        # Stop the application
        click.echo(f"Stopping application: {app_name}")
        if app_manager.stop_application(app_name):
            click.echo(f"Application {app_name} stopped successfully")
        else:
            click.echo(f"Failed to stop application {app_name}")

    except Exception as e:
        logger.error(f"Failed to stop application: {e}")
        raise click.ClickException(str(e))

@app.command('restart')
@click.argument('app_name')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def restart_app(app_name, config):
    """Restart all services for an application."""
    try:
        # Initialize components
        config_path = Path(config)
        config_obj, app_manager = initialize_components(config_path)

        # Check if application exists
        if app_name not in config_obj.applications.enabled:
            click.echo(f"Application '{app_name}' is not enabled in configuration")
            return

        # Restart the application
        click.echo(f"Restarting application: {app_name}")
        if app_manager.restart_application(app_name):
            click.echo(f"Application {app_name} restarted successfully")
        else:
            click.echo(f"Failed to restart application {app_name}")

    except Exception as e:
        logger.error(f"Failed to restart application: {e}")
        raise click.ClickException(str(e))

@app.command('deploy')
@click.argument('app_name')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def deploy_app(app_name, config):
    """Deploy or update an application."""
    try:
        # Initialize components
        config_path = Path(config)
        config_obj, app_manager = initialize_components(config_path)

        # Check if application exists
        if app_name not in config_obj.applications.enabled:
            click.echo(f"Application '{app_name}' is not enabled in configuration")
            return

        # Deploy the application
        click.echo(f"Deploying application: {app_name}")
        if app_manager.process_application(app_name):
            click.echo(f"Application {app_name} deployed successfully")
        else:
            click.echo(f"Failed to deploy application {app_name}")

    except Exception as e:
        logger.error(f"Failed to deploy application: {e}")
        raise click.ClickException(str(e))

# Service commands
@cli.command()
@click.argument('service_name')
@click.option('--app', '-a', help='Application name')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def status(service_name, app, config):
    """Get the status of a service."""
    try:
        # Initialize components
        config_path = Path(config)
        _, app_manager = initialize_components(config_path)

        # Get systemd status
        systemd_status = app_manager.systemd_manager.get_service_status(service_name)

        # Try to determine the application if not provided
        if not app:
            all_status = app_manager.get_status_all_applications()
            for app_name, status in all_status.items():
                if service_name in status.get('services', {}):
                    app = app_name
                    break

        # Get service state from state manager if possible
        service_state = None
        if app:
            service_state = app_manager.state_manager.get_service_state(app, service_name)

        click.echo(f"Service: {service_name}")
        if app:
            click.echo(f"Application: {app}")
        click.echo(f"Systemd Status: {systemd_status['active']}")
        if service_state:
            click.echo(f"Tracked State: {service_state}")

        click.echo("\nSystemd Details:")
        click.echo(systemd_status['details'])

    except Exception as e:
        logger.error(f"Failed to get service status: {e}")
        raise click.ClickException(str(e))

@cli.command('list-services')
@click.option('--app', '-a', help='Filter by application name')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def list_services(app, config):
    """List all managed services."""
    try:
        # Initialize components
        config_path = Path(config)
        _, app_manager = initialize_components(config_path)

        if app:
            # Show services for a specific application
            app_status = app_manager.get_application_status(app)
            services = app_status.get('services', {})

            if not services:
                click.echo(f"No services found for application {app}")
                return

            click.echo(f"\nServices for application {app}:")
            for service_name, state in services.items():
                click.echo(f"- {service_name}: {state}")
        else:
            # Show all services
            all_status = app_manager.get_status_all_applications()

            if not all_status:
                click.echo("No services found")
                return

            click.echo("\nAll managed services:")
            for app_name, status in all_status.items():
                services = status.get('services', {})
                if services:
                    click.echo(f"\nApplication: {app_name}")
                    for service_name, state in services.items():
                        click.echo(f"- {service_name}: {state}")

    except Exception as e:
        logger.error(f"Failed to list services: {e}")
        raise click.ClickException(str(e))

@cli.command()
@click.argument('service_name')
@click.option('--app', '-a', help='Application name')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def restart(service_name, app, config):
    """Restart a service."""
    try:
        # Initialize components
        config_path = Path(config)
        _, app_manager = initialize_components(config_path)

        # Try to determine the application if not provided
        if not app:
            all_status = app_manager.get_status_all_applications()
            for app_name, status in all_status.items():
                if service_name in status.get('services', {}):
                    app = app_name
                    break

        if app_manager.systemd_manager.restart_service(service_name):
            click.echo(f"Service {service_name} restarted successfully")

            # Update state if application is known
            if app:
                app_manager.state_manager.set_service_state(app, service_name, "running")
        else:
            click.echo(f"Failed to restart service {service_name}")

    except Exception as e:
        logger.error(f"Failed to restart service: {e}")
        raise click.ClickException(str(e))

# Config commands
@cli.group()
def config():
    """Manage configuration."""
    pass

@config.command('show')
@click.option('--app', '-a', help='Show configuration for a specific application')
@click.option('--config', '-c', type=click.Path(exists=True),
              default=str(get_user_paths()['config_file']),
              help='Path to config.toml file')
def show_config(app, config):
    """Show the current configuration."""
    try:
        # Load configuration
        config_path = Path(config)
        config_obj = Config.from_file(config_path)
        config_obj.load_app_configs(config_path.parent)

        if app:
            # Show configuration for a specific application
            if app not in config_obj.app_configs:
                click.echo(f"Application '{app}' not found in configuration")
                return

            app_config = config_obj.app_configs[app]
            click.echo(f"\nConfiguration for application: {app}")
            click.echo(f"Description: {app_config.description or 'N/A'}")
            click.echo(f"Quadlet Directory: {app_config.quadlet_dir}")

            if app_config.env:
                click.echo("\nEnvironment Variables:")
                for key, value in app_config.env.items():
                    click.echo(f"  {key}={value}")
        else:
            # Show global configuration
            click.echo("\nGlobal Configuration:")

            if config_obj.git:
                click.echo("\nGit Configuration:")
                click.echo(f"  Repository URL: {config_obj.git.repository_url}")
                click.echo(f"  Branch: {config_obj.git.branch}")
                click.echo(f"  Poll Interval: {config_obj.git.poll_interval} seconds")

            click.echo("\nPodman Configuration:")
            click.echo(f"  Quadlet Directory: {config_obj.podman.quadlet_dir}")
            click.echo(f"  Backup Directory: {config_obj.podman.backup_dir}")

            click.echo("\nMetrics Configuration:")
            click.echo(f"  Enabled: {config_obj.metrics.enabled}")
            if config_obj.metrics.enabled:
                click.echo(f"  Host: {config_obj.metrics.host}")
                click.echo(f"  Port: {config_obj.metrics.port}")

            click.echo("\nEnabled Applications:")
            for app_name in config_obj.applications.enabled:
                click.echo(f"  - {app_name}")

    except Exception as e:
        logger.error(f"Failed to show configuration: {e}")
        raise click.ClickException(str(e))

if __name__ == '__main__':
    cli()