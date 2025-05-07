import logging
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

import peewee as pw

logger = logging.getLogger(__name__)

# Database instance
db = pw.SqliteDatabase(None)  # Initialized with None, set actual path later

# Base model class
class BaseModel(pw.Model):
    class Meta:
        database = db

# Models
class Application(BaseModel):
    app_name = pw.CharField(primary_key=True)
    description = pw.TextField(null=True)
    last_updated = pw.DateTimeField(default=datetime.now)
    enabled = pw.BooleanField(default=True)
    config_hash = pw.CharField(null=True)

class Deployment(BaseModel):
    id = pw.AutoField()
    app_name = pw.ForeignKeyField(Application, backref='deployments')
    commit_hash = pw.CharField()
    timestamp = pw.DateTimeField(default=datetime.now)
    status = pw.CharField()  # 'success', 'failed', 'in_progress'
    error_message = pw.TextField(null=True)

class Service(BaseModel):
    app_name = pw.ForeignKeyField(Application, backref='services')
    service_name = pw.CharField()
    state = pw.CharField()  # 'running', 'stopped', 'failed', etc.
    container_id = pw.CharField(null=True)
    deployment = pw.ForeignKeyField(Deployment, backref='services', null=True)
    last_updated = pw.DateTimeField(default=datetime.now)

    class Meta:
        primary_key = pw.CompositeKey('app_name', 'service_name')

class HealthCheck(BaseModel):
    id = pw.AutoField()
    app_name = pw.CharField()
    service_name = pw.CharField()
    status = pw.CharField()
    timestamp = pw.DateTimeField(default=datetime.now)
    details = pw.TextField(null=True)

    class Meta:
        indexes = (
            (('app_name', 'service_name'), False),
        )

class ErrorLog(BaseModel):
    id = pw.AutoField()
    app_name = pw.CharField()
    service_name = pw.CharField(null=True)  # null for app-level errors
    error_message = pw.TextField()
    timestamp = pw.DateTimeField(default=datetime.now)
    resolved = pw.BooleanField(default=False)

    class Meta:
        indexes = (
            (('app_name', 'service_name'), False),
        )

@dataclass
class DeploymentState:
    """Represents the state of a deployment."""
    id: int
    app_name: str
    commit_hash: str
    timestamp: datetime
    status: str
    error_message: Optional[str] = None

class StateManager:
    """Manages the state of GitOps deployments using Peewee ORM."""

    def __init__(self, db_path: Path):
        """Initialize the state manager with a database path.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(str(db_path))

        # Create parent directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize the database
        db.init(str(self.db_path))
        self._init_db()

    def _init_db(self):
        """Initialize the database with required tables."""
        try:
            # Create tables if they don't exist
            db.create_tables([
                Application,
                Deployment,
                Service,
                HealthCheck,
                ErrorLog
            ])
            logger.info("Database initialized successfully")
        except pw.DatabaseError as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def register_application(self, app_name: str, description: Optional[str] = None, config_hash: Optional[str] = None) -> bool:
        """Register an application in the state database.

        Args:
            app_name: Name of the application
            description: Optional description of the application
            config_hash: Optional hash of the configuration

        Returns:
            Success status
        """
        try:
            with db.atomic():
                app, created = Application.get_or_create(
                    app_name=app_name,
                    defaults={
                        'description': description,
                        'config_hash': config_hash,
                        'last_updated': datetime.now()
                    }
                )

                if not created:
                    # Update existing application
                    app.description = description
                    app.config_hash = config_hash
                    app.last_updated = datetime.now()
                    app.save()

                logger.info(f"{'Registered' if created else 'Updated'} application: {app_name}")
                return True
        except pw.DatabaseError as e:
            logger.error(f"Failed to register application {app_name}: {e}")
            return False

    def deregister_application(self, app_name: str) -> bool:
        """Remove an application and all its related data from the state database.

        Args:
            app_name: Name of the application to remove

        Returns:
            Success status
        """
        try:
            with db.atomic():
                # Delete all health checks for this application's services
                HealthCheck.delete().where(HealthCheck.app_name == app_name).execute()

                # Delete all error logs for this application
                ErrorLog.delete().where(ErrorLog.app_name == app_name).execute()

                # Delete all services for this application
                Service.delete().where(Service.app_name == app_name).execute()

                # Delete all deployments for this application
                Deployment.delete().where(Deployment.app_name == app_name).execute()

                # Finally, delete the application itself
                deleted = Application.delete().where(Application.app_name == app_name).execute()

                if deleted:
                    logger.info(f"Application {app_name} has been deregistered and all its data removed")
                    return True
                else:
                    logger.warning(f"Application {app_name} not found")
                    return False

        except pw.DatabaseError as e:
            logger.error(f"Database error while deregistering application {app_name}: {e}")
            return False

    def start_deployment(self, app_name: str, commit_hash: str) -> int:
        """Record the start of a deployment.

        Args:
            app_name: Name of the application
            commit_hash: Git commit hash being deployed

        Returns:
            ID of the deployment record
        """
        try:
            with db.atomic():
                # Ensure application exists
                self.register_application(app_name)

                # Record deployment as in_progress
                deployment = Deployment.create(
                    app_name=app_name,
                    commit_hash=commit_hash,
                    status='in_progress'
                )

                logger.info(f"Started deployment {deployment.id} for {app_name} at commit {commit_hash}")
                return deployment.id
        except pw.DatabaseError as e:
            logger.error(f"Failed to start deployment for {app_name}: {e}")
            raise

    def finish_deployment(self, deployment_id: int, status: str, error_message: Optional[str] = None) -> bool:
        """Record the completion of a deployment.

        Args:
            deployment_id: ID of the deployment
            status: Status of the deployment ('success' or 'failed')
            error_message: Optional error message

        Returns:
            Success status
        """
        try:
            with db.atomic():
                try:
                    deployment = Deployment.get_by_id(deployment_id)
                    deployment.status = status
                    deployment.error_message = error_message
                    deployment.timestamp = datetime.now()
                    deployment.save()

                    logger.info(f"Finished deployment {deployment_id} with status {status}")
                    return True
                except Deployment.DoesNotExist:
                    logger.warning(f"Deployment {deployment_id} not found")
                    return False
        except pw.DatabaseError as e:
            logger.error(f"Failed to finish deployment {deployment_id}: {e}")
            return False

    def record_deployment(self, app_name: str, commit_hash: str, status: str, error_message: Optional[str] = None) -> int:
        """Record a complete deployment (combines start_deployment and finish_deployment).

        Args:
            app_name: Name of the application
            commit_hash: Git commit hash
            status: Status of the deployment ('success' or 'failed')
            error_message: Optional error message

        Returns:
            ID of the deployment record
        """
        try:
            with db.atomic():
                # Ensure application exists
                self.register_application(app_name)

                # Record deployment
                deployment = Deployment.create(
                    app_name=app_name,
                    commit_hash=commit_hash,
                    status=status,
                    error_message=error_message
                )

                logger.info(f"Recorded deployment for {app_name} with status {status}")
                return deployment.id
        except pw.DatabaseError as e:
            logger.error(f"Failed to record deployment for {app_name}: {e}")
            raise

    def update_service(self, app_name: str, service_name: str, state: str,
                       deployment_id: Optional[int] = None, container_id: Optional[str] = None) -> bool:
        """Update the state of a service.

        Args:
            app_name: Name of the application
            service_name: Name of the service
            state: Current state of the service
            deployment_id: Optional ID of the deployment that updated this service
            container_id: Optional container ID

        Returns:
            Success status
        """
        try:
            with db.atomic():
                # Ensure application exists
                self.register_application(app_name)

                service, created = Service.get_or_create(
                    app_name=app_name,
                    service_name=service_name,
                    defaults={
                        'state': state,
                        'container_id': container_id,
                        'deployment': deployment_id
                    }
                )

                if not created:
                    # Update existing service
                    service.state = state
                    service.last_updated = datetime.now()

                    if deployment_id is not None:
                        service.deployment = deployment_id

                    if container_id is not None:
                        service.container_id = container_id

                    service.save()

                logger.debug(f"{'Created' if created else 'Updated'} service {service_name} in app {app_name} to state {state}")
                return True
        except pw.DatabaseError as e:
            logger.error(f"Failed to update service {service_name} in app {app_name}: {e}")
            return False

    def get_service_state(self, app_name: str, service_name: str) -> Optional[str]:
        """Get the state of a service.

        Args:
            app_name: Name of the application
            service_name: Name of the service

        Returns:
            Current state of the service or None if not found
        """
        try:
            service = Service.get_or_none(Service.app_name == app_name, Service.service_name == service_name)
            return service.state if service else None
        except pw.DatabaseError as e:
            logger.error(f"Failed to get service state: {e}")
            raise

    def get_app_services(self, app_name: str) -> Dict[str, str]:
        """Get all services and their states for an application.

        Args:
            app_name: Name of the application

        Returns:
            Dictionary of service names and their states
        """
        try:
            query = Service.select().where(Service.app_name == app_name)
            return {service.service_name: service.state for service in query}
        except pw.DatabaseError as e:
            logger.error(f"Failed to get application services: {e}")
            raise

    def add_health_check(self, app_name: str, service_name: str, health_data: Dict[str, Any]) -> bool:
        """Add a health check result.

        Args:
            app_name: Name of the application
            service_name: Name of the service
            health_data: Health check data

        Returns:
            Success status
        """
        try:
            with db.atomic():
                # Ensure service exists
                service = Service.get_or_none(Service.app_name == app_name, Service.service_name == service_name)
                if not service:
                    logger.warning(f"Adding health check for unknown service {service_name} in app {app_name}")
                    # Create service record with unknown state
                    self.update_service(app_name, service_name, "unknown")

                # Extract status from health data
                status = health_data.get("status", "unknown")

                # Record health check
                HealthCheck.create(
                    app_name=app_name,
                    service_name=service_name,
                    status=status,
                    details=json.dumps(health_data)
                )

                logger.debug(f"Added health check for {service_name} in app {app_name}: {status}")
                return True
        except pw.DatabaseError as e:
            logger.error(f"Failed to add health check: {e}")
            return False

    def get_service_health_history(self, app_name: str, service_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the health check history of a service.

        Args:
            app_name: Name of the application
            service_name: Name of the service
            limit: Maximum number of records to return

        Returns:
            List of health check records
        """
        try:
            query = (HealthCheck
                     .select()
                     .where(HealthCheck.app_name == app_name, HealthCheck.service_name == service_name)
                     .order_by(HealthCheck.timestamp.desc())
                     .limit(limit))

            return [
                {
                    "id": health.id,
                    "status": health.status,
                    "timestamp": health.timestamp,
                    "details": json.loads(health.details) if health.details else {}
                }
                for health in query
            ]
        except pw.DatabaseError as e:
            logger.error(f"Failed to get health history: {e}")
            raise

    def set_last_error(self, app_name: str, service_name: Optional[str], error_message: str) -> bool:
        """Set an error for an application or service.

        Args:
            app_name: Name of the application
            service_name: Name of the service (None for app-level errors)
            error_message: Error message

        Returns:
            Success status
        """
        try:
            with db.atomic():
                # Log error
                ErrorLog.create(
                    app_name=app_name,
                    service_name=service_name,
                    error_message=error_message
                )

                # If service-level error, update service state
                if service_name:
                    self.update_service(app_name, service_name, "error")

                logger.info(f"Recorded error for {app_name}{f'/{service_name}' if service_name else ''}: {error_message}")
                return True
        except pw.DatabaseError as e:
            logger.error(f"Failed to set error: {e}")
            return False

    def get_last_error(self, app_name: str, service_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the last error for an application or service.

        Args:
            app_name: Name of the application
            service_name: Name of the service (None for app-level errors)

        Returns:
            Error details or None if not found
        """
        try:
            query = ErrorLog.select().where(ErrorLog.app_name == app_name)

            if service_name:
                query = query.where(ErrorLog.service_name == service_name)
            else:
                query = query.where(ErrorLog.service_name.is_null())

            error = query.order_by(ErrorLog.timestamp.desc()).first()

            if error:
                return {
                    "id": error.id,
                    "error_message": error.error_message,
                    "timestamp": error.timestamp,
                    "resolved": error.resolved
                }
            return None
        except pw.DatabaseError as e:
            logger.error(f"Failed to get last error: {e}")
            return None

    def resolve_error(self, error_id: int) -> bool:
        """Mark an error as resolved.

        Args:
            error_id: ID of the error

        Returns:
            Success status
        """
        try:
            with db.atomic():
                try:
                    error = ErrorLog.get_by_id(error_id)
                    error.resolved = True
                    error.save()

                    logger.info(f"Resolved error {error_id}")
                    return True
                except ErrorLog.DoesNotExist:
                    logger.warning(f"Error {error_id} not found")
                    return False
        except pw.DatabaseError as e:
            logger.error(f"Failed to resolve error: {e}")
            return False

    def get_deployment_history(self, app_name: Optional[str] = None, limit: int = 10) -> List[DeploymentState]:
        """Get the deployment history.

        Args:
            app_name: Name of the application (None for all applications)
            limit: Maximum number of records to return

        Returns:
            List of deployment records
        """
        try:
            query = Deployment.select()

            if app_name:
                query = query.where(Deployment.app_name == app_name)

            query = query.order_by(Deployment.timestamp.desc()).limit(limit)

            return [
                DeploymentState(
                    id=deployment.id,
                    app_name=deployment.app_name.app_name if isinstance(deployment.app_name, Application) else deployment.app_name,
                    commit_hash=deployment.commit_hash,
                    timestamp=deployment.timestamp,
                    status=deployment.status,
                    error_message=deployment.error_message
                )
                for deployment in query
            ]
        except pw.DatabaseError as e:
            logger.error(f"Failed to get deployment history: {e}")
            raise

    def get_last_successful_deployment(self, app_name: str) -> Optional[DeploymentState]:
        """Get the last successful deployment for an application.

        Args:
            app_name: Name of the application

        Returns:
            Last successful deployment record or None if not found
        """
        try:
            deployment = (Deployment
                          .select()
                          .where(Deployment.app_name == app_name, Deployment.status == 'success')
                          .order_by(Deployment.timestamp.desc())
                          .first())

            if deployment:
                return DeploymentState(
                    id=deployment.id,
                    app_name=deployment.app_name.app_name if isinstance(deployment.app_name, Application) else deployment.app_name,
                    commit_hash=deployment.commit_hash,
                    timestamp=deployment.timestamp,
                    status=deployment.status,
                    error_message=deployment.error_message
                )
            return None
        except pw.DatabaseError as e:
            logger.error(f"Failed to get last successful deployment: {e}")
            raise

    def get_active_services(self, app_name: Optional[str] = None, state: Optional[str] = "running") -> List[Dict[str, Any]]:
        """Get all active services.

        Args:
            app_name: Optional application filter
            state: State to filter by (default: "running")

        Returns:
            List of active services with their details
        """
        try:
            query = Service.select()

            if app_name:
                query = query.where(Service.app_name == app_name)

            if state:
                query = query.where(Service.state == state)

            query = query.order_by(Service.last_updated.desc())

            return [
                {
                    "app_name": service.app_name.app_name if isinstance(service.app_name, Application) else service.app_name,
                    "service_name": service.service_name,
                    "state": service.state,
                    "container_id": service.container_id,
                    "last_updated": service.last_updated
                }
                for service in query
            ]
        except pw.DatabaseError as e:
            logger.error(f"Failed to get active services: {e}")
            raise

    def get_app_status_summary(self, app_name: str) -> Dict[str, Any]:
        """Get a summary of the status for an application.

        Args:
            app_name: Name of the application

        Returns:
            Dictionary with application status summary
        """
        try:
            with db.atomic():
                # Get application info
                app = Application.get_or_none(Application.app_name == app_name)
                if not app:
                    return {"status": "not_found", "app_name": app_name}

                # Get services and their states
                services_query = Service.select().where(Service.app_name == app_name)
                services = {service.service_name: service.state for service in services_query}

                # Get last deployment
                last_deployment = (Deployment
                                   .select()
                                   .where(Deployment.app_name == app_name)
                                   .order_by(Deployment.timestamp.desc())
                                   .first())

                last_deployment_dict = None
                if last_deployment:
                    last_deployment_dict = {
                        "id": last_deployment.id,
                        "commit_hash": last_deployment.commit_hash,
                        "timestamp": last_deployment.timestamp,
                        "status": last_deployment.status,
                        "error_message": last_deployment.error_message
                    }

                # Count services by state
                state_counts = {}
                for service in services_query:
                    if service.state not in state_counts:
                        state_counts[service.state] = 0
                    state_counts[service.state] += 1

                # Count active errors
                error_count = (ErrorLog
                               .select()
                               .where(ErrorLog.app_name == app_name, ErrorLog.resolved == False)
                               .count())

                # Determine overall status
                overall_status = "healthy"  # Default
                if error_count > 0:
                    overall_status = "error"
                elif "error" in state_counts or "failed" in state_counts:
                    overall_status = "error"
                elif "unhealthy" in state_counts:
                    overall_status = "unhealthy"
                elif last_deployment and last_deployment.status == "failed":
                    overall_status = "deployment_failed"
                elif not services:
                    overall_status = "no_services"

                # Prepare summary
                summary = {
                    "app_name": app_name,
                    "description": app.description,
                    "last_updated": app.last_updated,
                    "services": services,
                    "service_count": len(services),
                    "state_counts": state_counts,
                    "error_count": error_count,
                    "overall_status": overall_status
                }

                # Add last deployment info if available
                if last_deployment_dict:
                    summary["last_deployment"] = last_deployment_dict

                return summary

        except pw.DatabaseError as e:
            logger.error(f"Failed to get app status summary: {e}")
            return {"status": "error", "app_name": app_name, "error": str(e)}

    def get_status_all_applications(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all applications.

        Returns:
            Dictionary of application names and their status
        """
        try:
            # Get all application names
            applications = Application.select().where(Application.enabled == True)

            # Get status for each application
            return {
                app.app_name: self.get_app_status_summary(app.app_name)
                for app in applications
            }
        except pw.DatabaseError as e:
            logger.error(f"Failed to get status of all applications: {e}")
            raise