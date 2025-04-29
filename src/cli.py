import click
import logging
import os
import time
from pathlib import Path
from .core.config import Config
from .core.git_operations import GitOperations
from .core.quadlet_handler import QuadletHandler
from .core.systemd_manager import SystemdManager
from .core.health_checker import HealthChecker
from .core.logging import setup_logging, get_logger
from .state.manager import StateManager
from .core.rollback import RollbackManager
from datetime import datetime

# Get logger for CLI
logger = get_logger("src.cli")

def get_user_paths():
    """Get user-specific paths for rootless operation."""
    user_home = Path.home()
    return {
        'repo_dir': user_home / '.local/lib/podman-gitops/repo',
        'backup_dir': user_home / '.local/lib/podman-gitops/backups',
        'config_dir': user_home / '.config/podman-gitops',
        'state_db': user_home / '.local/lib/podman-gitops/state.db',
        'quadlet_dir': user_home / '.config/containers/systemd',
        'log_dir': user_home / '.local/lib/podman-gitops/logs'
    }

def ensure_directories(paths):
    """Ensure all necessary directories exist."""
    for path in paths.values():
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)

def process_quadlet_files(quadlet_handler: QuadletHandler, systemd_manager: SystemdManager, health_checker: HealthChecker, state_manager: StateManager, repo_dir: Path, quadlet_dir: str):
    """Process quadlet files from the repository."""
    try:
        # Find all files in the specified directory
        quadlet_path = repo_dir / quadlet_dir
        files = list(quadlet_path.glob("*.*"))
        
        # Group files by type
        files_by_type = {
            'network': [],
            'volume': [],
            'image': [],
            'container': []
        }
        
        for file in files:
            file_type = quadlet_handler._get_file_type(file)
            if file_type in files_by_type:
                files_by_type[file_type].append(file)
        
        # Process all files first without starting services
        deployed_files = []
        for file_type, files in files_by_type.items():
            for file_path in files:
                name = file_path.stem
                logger.info(f"Processing {file_type} file: {name}")
                
                # Deploy the file
                if quadlet_handler.deploy_quadlet_file(file_path):
                    deployed_files.append((name, file_type))
                    # Set initial service state
                    state_manager.set_service_state(name, "deployed")
                else:
                    logger.error(f"Failed to deploy {file_type} file: {name}")
                    # Record the error
                    state_manager.set_last_error(name, f"Failed to deploy {file_type} file")
                    # Roll back all changes
                    for deployed_name, deployed_type in deployed_files:
                        quadlet_handler.remove_quadlet_file(deployed_name, deployed_type)
                    return False
        
        # After all files are deployed, reload systemd
        if deployed_files:
            logger.info("Reloading systemd daemon")
            systemd_manager.reload_daemon()
        
        # Now start services in the correct order
        for file_type in ['network', 'volume', 'image', 'container']:
            if file_type in files_by_type:
                for file_path in files_by_type[file_type]:
                    name = file_path.stem
                    if file_type == 'container':
                        logger.info(f"Starting service: {name}")
                        if systemd_manager.start_service(name):
                            # Update service state
                            state_manager.set_service_state(name, "starting")
                            # Wait for container to become healthy
                            if health_checker.wait_for_healthy(name):
                                logger.info(f"Service {name} started successfully and is healthy")
                                # Update service state and record health check
                                state_manager.set_service_state(name, "running")
                                health_data = health_checker.check_container_health(name)
                                state_manager.add_health_check(name, health_data)
                            else:
                                logger.error(f"Service {name} started but failed health check")
                                # Update service state and record error
                                state_manager.set_service_state(name, "unhealthy")
                                state_manager.set_last_error(name, "Health check failed")
                                # Get container logs for debugging
                                logs = health_checker.get_container_logs(name)
                                if logs:
                                    logger.error(f"Container logs:\n{logs}")
                                # Roll back all changes
                                for deployed_name, deployed_type in deployed_files:
                                    quadlet_handler.remove_quadlet_file(deployed_name, deployed_type)
                                    state_manager.remove_service_state(deployed_name)
                                return False
                        else:
                            logger.error(f"Failed to start service {name}")
                            # Update service state and record error
                            state_manager.set_service_state(name, "failed")
                            state_manager.set_last_error(name, "Failed to start service")
                            # Roll back all changes
                            for deployed_name, deployed_type in deployed_files:
                                quadlet_handler.remove_quadlet_file(deployed_name, deployed_type)
                                state_manager.remove_service_state(deployed_name)
                            return False
        
        return True
    except Exception as e:
        logger.error(f"Error processing quadlet files: {e}")
        # Record the error in state manager
        state_manager.set_last_error("system", str(e))
        return False

@click.group()
def cli():
    """Podman GitOps CLI tool."""
    pass

@cli.command()
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to config.toml file')
def start(config):
    """Start the GitOps service."""
    try:
        # Load configuration
        config_path = Path(config)
        config_data = Config.from_file(config_path)
        
        # Get user paths
        paths = get_user_paths()
        
        # Ensure all directories exist
        ensure_directories(paths)
        
        # Set up logging
        setup_logging(paths['log_dir'], config_data.log_level)
        
        # Initialize components
        git_ops = GitOperations(config_data.git, paths['repo_dir'])
        systemd_manager = SystemdManager(paths['quadlet_dir'])
        quadlet_handler = QuadletHandler(paths['quadlet_dir'], systemd_manager)
        health_checker = HealthChecker()
        state_manager = StateManager(paths['state_db'])
        
        # Start the service
        logger.info("Starting Podman GitOps service")
        
        # Clone repository if it doesn't exist
        if git_ops.clone_repository():
            logger.info("Repository cloned successfully")
        
        while True:
            try:
                # Pull latest changes
                if git_ops.pull_changes():
                    logger.info("Changes pulled successfully")
                    
                    # Get current commit hash
                    commit_hash = git_ops.get_current_commit()
                    
                    # Process quadlet files
                    if process_quadlet_files(
                        quadlet_handler, 
                        systemd_manager,
                        health_checker,
                        state_manager,
                        paths['repo_dir'],
                        config_data.git.quadlet_files_dir
                    ):
                        # Record successful deployment
                        state_manager.record_deployment(commit_hash, "success")
                    else:
                        # Record failed deployment
                        state_manager.record_deployment(commit_hash, "failed", "Deployment failed")
                    
                # Wait for the next poll interval
                time.sleep(config_data.git.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in service loop: {e}")
                # Record failed deployment
                state_manager.record_deployment(git_ops.get_current_commit(), "failed", str(e))
                time.sleep(config_data.git.poll_interval)
        
    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise click.ClickException(str(e))

@cli.command()
@click.argument('service_name')
def status(service_name):
    """Get the status of a service."""
    try:
        paths = get_user_paths()
        systemd_manager = SystemdManager(paths['quadlet_dir'])
        health_checker = HealthChecker()
        
        # Get systemd status
        systemd_status = systemd_manager.get_service_status(service_name)
        
        # Get container health
        health_status = health_checker.check_container_health(service_name)
        
        click.echo(f"Service: {service_name}")
        click.echo(f"Systemd Status: {systemd_status['active']}")
        click.echo(f"Container State: {health_status['state']}")
        click.echo(f"Health Status: {health_status['status']}")
        click.echo("\nSystemd Details:")
        click.echo(systemd_status['details'])
        
    except Exception as e:
        logger.error(f"Failed to get service status: {e}")
        raise click.ClickException(str(e))

@cli.command()
def list_services():
    """List all managed services."""
    try:
        paths = get_user_paths()
        systemd_manager = SystemdManager(paths['quadlet_dir'])
        health_checker = HealthChecker()
        
        services = systemd_manager.list_services()
        if services:
            click.echo("Managed services:")
            for service in services:
                health = health_checker.check_container_health(service)
                status = "healthy" if health["healthy"] else "unhealthy"
                click.echo(f"- {service} ({status})")
        else:
            click.echo("No services found")
    except Exception as e:
        logger.error(f"Failed to list services: {e}")
        raise click.ClickException(str(e))

@cli.command()
@click.argument('service_name')
def restart(service_name):
    """Restart a service."""
    try:
        paths = get_user_paths()
        systemd_manager = SystemdManager(paths['quadlet_dir'])
        health_checker = HealthChecker()
        
        if systemd_manager.restart_service(service_name):
            # Wait for container to become healthy
            if health_checker.wait_for_healthy(service_name):
                click.echo(f"Service {service_name} restarted successfully and is healthy")
            else:
                click.echo(f"Service {service_name} restarted but failed health check")
                logs = health_checker.get_container_logs(service_name)
                if logs:
                    click.echo(f"\nContainer logs:\n{logs}")
        else:
            click.echo(f"Failed to restart service {service_name}")
    except Exception as e:
        logger.error(f"Failed to restart service: {e}")
        raise click.ClickException(str(e))

@cli.command()
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to config.toml file')
def check_quadlets(config):
    """Check the status of all files in the repository and their deployment."""
    try:
        # Load configuration
        config_path = Path(config)
        config_data = Config.from_file(config_path)
        
        # Get user paths
        paths = get_user_paths()
        
        # Initialize components
        git_ops = GitOperations(config_data.git, paths['repo_dir'])
        quadlet_handler = QuadletHandler(paths['quadlet_dir'])
        
        # Get repository path
        repo_dir = config_data.git.repo_dir or paths['repo_dir']
        quadlet_dir = config_data.git.quadlet_files_dir
        
        # Construct the path to files directory
        files_path = repo_dir / quadlet_dir if quadlet_dir else repo_dir
        
        click.echo(f"Repository directory: {repo_dir}")
        click.echo(f"Files directory: {files_path}")
        click.echo(f"Deployment directory: {paths['quadlet_dir']}")
        
        # Get deployed files
        deployed_files = quadlet_handler.get_deployed_files()
        
        # Find all files in the repository
        files = quadlet_handler.find_quadlet_files(files_path)
        
        if not files:
            click.echo("\nNo files found in repository")
            return
        
        # Group files by type
        files_by_type = {}
        for file_path in files:
            file_type = quadlet_handler._get_file_type(file_path)
            if file_type not in files_by_type:
                files_by_type[file_type] = []
            files_by_type[file_type].append(file_path)
        
        # Display files by type
        for file_type, type_files in files_by_type.items():
            click.echo(f"\n{file_type.upper()} Files:")
            click.echo("=" * 80)
            
            for file_path in type_files:
                click.echo(f"\nFile: {file_path.name}")
                click.echo(f"Path: {file_path}")
                
                # Check if file is deployed
                if file_type in quadlet_handler.QUADLET_TYPES:
                    deployed_path = paths['quadlet_dir'] / f"{file_path.stem}{quadlet_handler.QUADLET_TYPES[file_type]}"
                else:
                    deployed_path = paths['quadlet_dir'] / file_path.name
                
                if deployed_path.exists():
                    click.echo("Status: Deployed")
                    # Compare contents
                    repo_content = file_path.read_text()
                    deployed_content = deployed_path.read_text()
                    if repo_content == deployed_content:
                        click.echo("Content: Up to date")
                    else:
                        click.echo("Content: Different from repository")
                else:
                    click.echo("Status: Not deployed")
                
                # Show file contents
                click.echo("\nContent:")
                click.echo(file_path.read_text())
                click.echo("-" * 80)
        
        # Show deployment summary
        click.echo("\nDeployment Summary:")
        click.echo("=" * 80)
        for file_type, files in deployed_files.items():
            if files:
                click.echo(f"\n{file_type.upper()} files deployed:")
                for file in sorted(files):
                    click.echo(f"- {file}")
        
    except Exception as e:
        logger.error(f"Failed to check files: {e}")
        raise click.ClickException(str(e))

@cli.command()
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to config.toml file')
def list_backups(config):
    """List all available backups."""
    try:
        # Load configuration
        config_path = Path(config)
        config_data = Config.from_file(config_path)
        
        # Get user paths
        paths = get_user_paths()
        
        # Initialize rollback manager
        rollback_manager = RollbackManager(paths['backup_dir'])
        
        # Get all backups
        backups = rollback_manager.list_backups()
        
        if not backups:
            click.echo("No backups found")
            return
        
        click.echo("Available backups:")
        click.echo("=" * 80)
        
        for backup in backups:
            click.echo(f"\nFile: {backup.name}")
            click.echo(f"Path: {backup}")
            click.echo(f"Created: {datetime.fromtimestamp(backup.stat().st_mtime)}")
            click.echo("-" * 80)
        
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise click.ClickException(str(e))

@cli.command()
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to config.toml file')
@click.argument('file_name')
def restore_backup(config, file_name):
    """Restore a file from its latest backup."""
    try:
        # Load configuration
        config_path = Path(config)
        config_data = Config.from_file(config_path)
        
        # Get user paths
        paths = get_user_paths()
        
        # Initialize rollback manager
        rollback_manager = RollbackManager(paths['backup_dir'])
        
        # Get latest backup
        backup = rollback_manager.get_latest_backup(file_name)
        if not backup:
            click.echo(f"No backup found for {file_name}")
            return
        
        # Restore the backup
        target_path = paths['quadlet_dir'] / backup.name.split('_')[0]
        if rollback_manager.restore_backup(target_path, backup):
            click.echo(f"Successfully restored {file_name} from backup")
        else:
            click.echo(f"Failed to restore {file_name} from backup")
        
    except Exception as e:
        logger.error(f"Failed to restore backup: {e}")
        raise click.ClickException(str(e))

@cli.command()
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to config.toml file')
@click.option('--max-backups', '-m', type=int, default=5, help='Maximum number of backups to keep')
def cleanup_backups(config, max_backups):
    """Clean up old backups, keeping only the most recent ones."""
    try:
        # Load configuration
        config_path = Path(config)
        config_data = Config.from_file(config_path)
        
        # Get user paths
        paths = get_user_paths()
        
        # Initialize rollback manager
        rollback_manager = RollbackManager(paths['backup_dir'])
        
        # Clean up old backups
        rollback_manager.cleanup_old_backups(max_backups)
        click.echo(f"Successfully cleaned up old backups, keeping {max_backups} most recent ones")
        
    except Exception as e:
        logger.error(f"Failed to cleanup backups: {e}")
        raise click.ClickException(str(e))

if __name__ == '__main__':
    cli() 