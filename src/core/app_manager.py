# src/core/app_manager.py - Update imports and class
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any
import time

from .config import Config, ApplicationConfig
from .quadlet_handler import QuadletHandler
from .systemd_manager import SystemdManager
from .git_operations import GitOperations
from .git_manager import GitManager
from .health_checker import HealthChecker
from ..state.manager import StateManager

logger = logging.getLogger(__name__)

class ApplicationManager:
    """Manages the lifecycle and operations of multiple applications."""

    def __init__(self,
                 config: Config,
                 state_manager: StateManager,
                 quadlet_handler: QuadletHandler,
                 systemd_manager: SystemdManager,
                 git_ops: Optional[GitOperations] = None):
        """Initialize the application manager.

        Args:
            config: Main configuration
            state_manager: State manager for tracking application states
            quadlet_handler: Handler for quadlet files
            systemd_manager: Manager for systemd services
            git_ops: Optional Git operations handler (legacy parameter, kept for compatibility)
        """
        self.config = config
        self.state_manager = state_manager
        self.quadlet_handler = quadlet_handler
        self.systemd_manager = systemd_manager
        self.health_checker = HealthChecker()  # Initialize health checker

        # Initialize the Git manager
        self.git_manager = GitManager()

        # Legacy support - add the provided git_ops to our manager if given
        if git_ops and hasattr(git_ops, 'config') and hasattr(git_ops, 'work_dir'):
            self.git_manager.repositories[git_ops.config.repository_url] = git_ops

        # Track processed applications to avoid duplicate processing
        self.processed_apps: Set[str] = set()

    def get_app_list(self) -> List[str]:
        """Get a list of enabled applications.

        Returns:
            List of enabled application names
        """
        return self.config.applications.enabled

    def get_app_config(self, app_name: str) -> Optional[ApplicationConfig]:
        """Get configuration for an application.

        Args:
            app_name: Name of the application

        Returns:
            Application configuration or None if not found
        """
        return self.config.app_configs.get(app_name)

    def get_application_status(self, app_name: str) -> Dict[str, Any]:
        """Get detailed status of an application.

        Args:
            app_name: Name of the application

        Returns:
            Dictionary with application status details
        """
        try:
            # Get application configuration
            app_config = self.get_app_config(app_name)
            if not app_config:
                return {"status": "not_configured", "error": "Application not configured"}

            # Get application status from state manager
            app_status = self.state_manager.get_app_status_summary(app_name)

            # Add configuration info if not already included
            if "config" not in app_status:
                app_status["config"] = {
                    "description": app_config.description,
                    "quadlet_dir": str(app_config.quadlet_dir),
                    "env_var_count": len(app_config.env or {})
                }

            return app_status

        except Exception as e:
            logger.error(f"Failed to get status for application {app_name}: {e}")
            return {"status": "error", "error": str(e)}

    def process_application(self, app_name: str) -> bool:
        """Process an application for deployment.

        Args:
            app_name: Name of the application

        Returns:
            Success status
        """
        try:
            logger.info(f"Processing application: {app_name}")

            # Check if application is configured
            app_config = self.get_app_config(app_name)
            if not app_config:
                logger.error(f"Configuration for application {app_name} not found")
                return False

            # Register application in state manager with description
            self.state_manager.register_application(
                app_name=app_name,
                description=app_config.description
            )

            # Initialize default values
            quadlet_dir = app_config.quadlet_dir
            commit_hash = "local"  # Default for non-Git deployments
            git_ops = None
            deployment_id = None

            # Check if we need to use Git
            if self.config.git:
                # Get appropriate Git operations for this application
                git_config = self.config.git  # Use default Git config

                # Apps can override Git configuration in their app-specific config
                if hasattr(app_config, 'git') and app_config.git:
                    git_config = app_config.git  # Use app-specific Git config

                # Validate Git config
                if git_config is None:
                    logger.error(f"Git configuration is None for application {app_name}")
                    return False

                # Create a proper work directory path
                work_dir = Path(str(self.config.system.config_dir)) / "repos" / app_name
                logger.debug(f"Git work directory for {app_name}: {work_dir}")

                # Get or create GitOperations instance
                git_ops = self.git_manager.get_git_ops(git_config, work_dir)

                # Validate the repository worktree directory exists
                repo_dir = git_ops.work_dir
                if not repo_dir.exists():
                    logger.info(f"Creating repository directory: {repo_dir}")
                    repo_dir.mkdir(parents=True, exist_ok=True)

                    # Initial clone if repository doesn't exist
                    if not (repo_dir / ".git").exists():
                        if not git_ops.clone_repository():
                            logger.error(f"Failed to clone repository for {app_name}")
                            self.state_manager.record_deployment(
                                app_name=app_name,
                                commit_hash="none",
                                status="failed",
                                error_message="Git clone failed"
                            )
                            return False

                # Check for changes (uses cached result if already checked)
                if not self.git_manager.check_for_changes(git_ops):
                    # No changes detected, get the last successful deployment
                    last_deployment = self.state_manager.get_last_successful_deployment(app_name)
                    if last_deployment and last_deployment.status == "success":
                        logger.info(f"No changes detected and last deployment was successful - skipping deployment for {app_name}")
                        return True
                    else:
                        logger.info(f"No changes detected but last deployment wasn't successful - proceeding with deployment for {app_name}")

                # Update repository
                if git_ops.config.repository_url in self.git_manager.repos_with_changes:
                    if not git_ops.pull_changes():
                        logger.error(f"Failed to pull changes from Git repository")
                        # Record failed deployment
                        self.state_manager.record_deployment(
                            app_name=app_name,
                            commit_hash=git_ops.get_current_commit(),
                            status="failed",
                            error_message="Git pull failed"
                        )
                        return False

                # Get current commit hash
                commit_hash = git_ops.get_current_commit()

                # Construct a valid quadlet directory path from the repository
                if app_config.quadlet_dir:
                    # If app_config.quadlet_dir is a relative path, combine with repo directory
                    if not app_config.quadlet_dir.is_absolute():
                        quadlet_dir = git_ops.work_dir / str(app_config.quadlet_dir)
                        logger.debug(f"Using relative quadlet path: {quadlet_dir}")
                    else:
                        # Use absolute path directly
                        quadlet_dir = app_config.quadlet_dir
                        logger.debug(f"Using absolute quadlet path: {quadlet_dir}")
                else:
                    logger.error(f"quadlet_dir is None for application {app_name}")
                    return False

            # Validate that quadlet_dir exists
            if not quadlet_dir.exists():
                logger.error(f"Quadlet directory does not exist: {quadlet_dir}")
                os.makedirs(quadlet_dir, exist_ok=True)
                logger.info(f"Created quadlet directory: {quadlet_dir}")

            # Start a new deployment in the state manager
            deployment_id = self.state_manager.start_deployment(
                app_name=app_name,
                commit_hash=commit_hash
            )

            # Process and deploy quadlet files
            logger.info(f"Processing quadlet files for {app_name} from {quadlet_dir}")
            success, deployed_services = self.quadlet_handler.process_and_deploy_app_quadlets(
                app_name=app_name,
                quadlet_dir=quadlet_dir,
                env_vars=app_config.env
            )

            if not success:
                logger.error(f"Failed to process quadlet files for application {app_name}")
                # Finish deployment as failed
                self.state_manager.finish_deployment(
                    deployment_id=deployment_id,
                    status="failed",
                    error_message="Failed to process quadlet files"
                )
                return False

            # Reload systemd daemon
            if not self.systemd_manager.reload_daemon():
                logger.error("Failed to reload systemd daemon")
                self.state_manager.finish_deployment(
                    deployment_id=deployment_id,
                    status="failed",
                    error_message="Failed to reload systemd daemon"
                )
                return False

            # Start services
            logger.info(f"Starting services for application {app_name}: {deployed_services}")
            all_started = True
            for service_name in deployed_services:
                logger.info(f"Starting service: {service_name}")

                # Update service state to starting
                self.state_manager.update_service(
                    app_name=app_name,
                    service_name=service_name,
                    state="starting",
                    deployment_id=deployment_id
                )

                # Start the service
                if not self.systemd_manager.start_service(service_name):
                    logger.error(f"Failed to start service {service_name}")
                    self.state_manager.update_service(
                        app_name=app_name,
                        service_name=service_name,
                        state="failed",
                        deployment_id=deployment_id
                    )
                    self.state_manager.set_last_error(
                        app_name=app_name,
                        service_name=service_name,
                        error_message="Failed to start service"
                    )
                    all_started = False
                else:
                    logger.info(f"Service {service_name} started successfully")
                    self.state_manager.update_service(
                        app_name=app_name,
                        service_name=service_name,
                        state="running",
                        deployment_id=deployment_id
                    )

            if not all_started:
                logger.error(f"Some services failed to start for application {app_name}")
                self.state_manager.finish_deployment(
                    deployment_id=deployment_id,
                    status="failed",
                    error_message="Some services failed to start"
                )
                return False

            # Perform health checks
            logger.info(f"Performing health checks for application {app_name}")
            all_healthy = True

            for service_name in deployed_services:
                try:
                    # Log before health check
                    logger.info(f"Checking health of service {service_name} in app {app_name}")

                    # Use the existing HealthChecker to check container health
                    health_data = self.health_checker.check_container_health(service_name)

                    # Log health check result
                    logger.info(f"Health check result for {service_name}: {health_data}")

                    # Update state based on health
                    if health_data.get("healthy", False):
                        logger.info(f"Service {service_name} is healthy")
                        self.state_manager.update_service(
                            app_name=app_name,
                            service_name=service_name,
                            state="running",
                            deployment_id=deployment_id
                        )

                        # Add health check to state manager
                        self.state_manager.add_health_check(
                            app_name=app_name,
                            service_name=service_name,
                            health_data=health_data
                        )
                    else:
                        logger.warning(f"Service {service_name} is unhealthy: {health_data}")
                        self.state_manager.update_service(
                            app_name=app_name,
                            service_name=service_name,
                            state="unhealthy",
                            deployment_id=deployment_id
                        )
                        self.state_manager.set_last_error(
                            app_name=app_name,
                            service_name=service_name,
                            error_message=f"Health check failed: {health_data.get('status', 'unknown')}"
                        )
                        all_healthy = False

                        # Get container logs for debugging
                        logs = self.health_checker.get_container_logs(service_name)
                        if logs:
                            logger.info(f"Container logs for {service_name}:\n{logs[:500]}...")

                except Exception as e:
                    logger.error(f"Error checking health for service {service_name}: {e}")
                    self.state_manager.update_service(
                        app_name=app_name,
                        service_name=service_name,
                        state="unknown",
                        deployment_id=deployment_id
                    )
                    self.state_manager.set_last_error(
                        app_name=app_name,
                        service_name=service_name,
                        error_message=f"Health check error: {str(e)}"
                    )
                    all_healthy = False

            # Wait for containers to become healthy
            if all_healthy:
                logger.info(f"All services for application {app_name} are initially healthy")

                # Optional: Wait for containers to become fully stable
                logger.info(f"Waiting for all services in {app_name} to stabilize...")
                for service_name in deployed_services:
                    if not self.health_checker.wait_for_healthy(service_name, timeout=30):
                        logger.warning(f"Service {service_name} did not stabilize within timeout period")
                        all_healthy = False
                        self.state_manager.update_service(
                            app_name=app_name,
                            service_name=service_name,
                            state="unstable",
                            deployment_id=deployment_id
                        )
                        self.state_manager.set_last_error(
                            app_name=app_name,
                            service_name=service_name,
                            error_message="Service did not stabilize within timeout period"
                        )

            # Record final deployment status
            if all_healthy:
                self.state_manager.finish_deployment(
                    deployment_id=deployment_id,
                    status="success"
                )
                logger.info(f"Application {app_name} deployed successfully with all services healthy")
                self.processed_apps.add(app_name)
                return True
            else:
                self.state_manager.finish_deployment(
                    deployment_id=deployment_id,
                    status="failed",
                    error_message="Some services are unhealthy or unstable"
                )
                logger.error(f"Application {app_name} deployment completed but some services are unhealthy")
                return False

        except Exception as e:
            logger.error(f"Error processing application {app_name}: {e}", exc_info=True)
            # Record error if deployment was started
            try:
                if deployment_id:
                    self.state_manager.finish_deployment(
                        deployment_id=deployment_id,
                        status="failed",
                        error_message=str(e)
                    )
                else:
                    commit = "local"
                    if git_ops:
                        try:
                            commit = git_ops.get_current_commit()
                        except:
                            pass

                    self.state_manager.record_deployment(
                        app_name=app_name,
                        commit_hash=commit,
                        status="failed",
                        error_message=str(e)
                    )
            except Exception as record_error:
                logger.error(f"Failed to record deployment failure: {record_error}")
            return False

    def process_all_applications(self) -> Dict[str, bool]:
        """Process all enabled applications.

        Returns:
            Dictionary of application names and their success status
        """
        # Reset the Git manager cycle
        self.git_manager.reset_cycle()

        results = {}
        for app_name in self.get_app_list():
            results[app_name] = self.process_application(app_name)

        return results