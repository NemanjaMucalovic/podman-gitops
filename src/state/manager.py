# src/state/manager.py
import logging
import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Tuple

logger = logging.getLogger(__name__)

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
    """Manages the state of GitOps deployments using SQLite."""

    def __init__(self, db_path: Path):
        """Initialize the state manager with a database path.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(str(db_path))

        # Create parent directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database with required tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Create applications table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS applications (
                        app_name TEXT PRIMARY KEY,
                        description TEXT,
                        last_updated DATETIME NOT NULL,
                        enabled BOOLEAN DEFAULT 1,
                        config_hash TEXT
                    )
                """)

                # Create deployments table with app_name
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS deployments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        app_name TEXT NOT NULL,
                        commit_hash TEXT NOT NULL,
                        timestamp DATETIME NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        FOREIGN KEY (app_name) REFERENCES applications(app_name)
                    )
                """)

                # Create services table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS services (
                        app_name TEXT NOT NULL,
                        service_name TEXT NOT NULL,
                        state TEXT NOT NULL,
                        container_id TEXT,
                        deployment_id INTEGER,
                        last_updated DATETIME NOT NULL,
                        PRIMARY KEY (app_name, service_name),
                        FOREIGN KEY (app_name) REFERENCES applications(app_name),
                        FOREIGN KEY (deployment_id) REFERENCES deployments(id)
                    )
                """)

                # Create health_checks table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS health_checks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        app_name TEXT NOT NULL,
                        service_name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        timestamp DATETIME NOT NULL,
                        details TEXT,
                        FOREIGN KEY (app_name, service_name) REFERENCES services(app_name, service_name)
                    )
                """)

                # Create error_log table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS error_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        app_name TEXT NOT NULL,
                        service_name TEXT,
                        error_message TEXT NOT NULL,
                        timestamp DATETIME NOT NULL,
                        resolved BOOLEAN DEFAULT 0,
                        FOREIGN KEY (app_name) REFERENCES applications(app_name)
                    )
                """)

                # Create indexes for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_deployments_timestamp ON deployments(timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_deployments_app ON deployments(app_name, timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_state ON services(state, app_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_timestamp ON health_checks(timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_service ON health_checks(app_name, service_name, timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_errors_unresolved ON error_log(resolved, timestamp DESC)")

                conn.commit()
                logger.info("Database initialized successfully")
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check if application already exists
                cursor.execute("SELECT 1 FROM applications WHERE app_name = ?", (app_name,))
                exists = cursor.fetchone() is not None

                if exists:
                    # Update existing application
                    cursor.execute(
                        """
                        UPDATE applications 
                        SET description = ?, last_updated = ?, config_hash = ?
                        WHERE app_name = ?
                        """,
                        (description, datetime.now(), config_hash, app_name)
                    )
                else:
                    # Insert new application
                    cursor.execute(
                        """
                        INSERT INTO applications (app_name, description, last_updated, enabled, config_hash)
                        VALUES (?, ?, ?, 1, ?)
                        """,
                        (app_name, description, datetime.now(), config_hash)
                    )

                conn.commit()
                logger.info(f"Registered application: {app_name}")
                return True
        except sqlite3.Error as e:
            logger.error(f"Failed to register application {app_name}: {e}")
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Ensure application exists
                self.register_application(app_name)

                # Record deployment as in_progress
                cursor.execute(
                    """
                    INSERT INTO deployments (app_name, commit_hash, timestamp, status, error_message)
                    VALUES (?, ?, ?, 'in_progress', NULL)
                    """,
                    (app_name, commit_hash, datetime.now())
                )

                deployment_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Started deployment {deployment_id} for {app_name} at commit {commit_hash}")
                return deployment_id
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Update deployment status
                cursor.execute(
                    """
                    UPDATE deployments 
                    SET status = ?, error_message = ?, timestamp = ?
                    WHERE id = ?
                    """,
                    (status, error_message, datetime.now(), deployment_id)
                )

                if cursor.rowcount == 0:
                    logger.warning(f"Deployment {deployment_id} not found")
                    return False

                conn.commit()
                logger.info(f"Finished deployment {deployment_id} with status {status}")
                return True
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Ensure application exists
                self.register_application(app_name)

                # Record deployment
                cursor.execute(
                    """
                    INSERT INTO deployments (app_name, commit_hash, timestamp, status, error_message)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (app_name, commit_hash, datetime.now(), status, error_message)
                )

                deployment_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Recorded deployment for {app_name} with status {status}")
                return deployment_id
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check if service exists
                cursor.execute(
                    "SELECT 1 FROM services WHERE app_name = ? AND service_name = ?",
                    (app_name, service_name)
                )
                exists = cursor.fetchone() is not None

                if exists:
                    # Update existing service
                    query = """
                        UPDATE services 
                        SET state = ?, last_updated = ?
                    """
                    params = [state, datetime.now()]

                    if deployment_id is not None:
                        query += ", deployment_id = ?"
                        params.append(deployment_id)

                    if container_id is not None:
                        query += ", container_id = ?"
                        params.append(container_id)

                    query += " WHERE app_name = ? AND service_name = ?"
                    params.extend([app_name, service_name])

                    cursor.execute(query, params)
                else:
                    # Insert new service
                    cursor.execute(
                        """
                        INSERT INTO services (app_name, service_name, state, container_id, deployment_id, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (app_name, service_name, state, container_id, deployment_id, datetime.now())
                    )

                conn.commit()
                logger.debug(f"Updated service {service_name} in app {app_name} to state {state}")
                return True
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT state FROM services WHERE app_name = ? AND service_name = ?",
                    (app_name, service_name)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT service_name, state FROM services WHERE app_name = ?",
                    (app_name,)
                )
                return {row[0]: row[1] for row in cursor.fetchall()}
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Ensure service exists (attempt to fetch it first)
                cursor.execute(
                    "SELECT 1 FROM services WHERE app_name = ? AND service_name = ?",
                    (app_name, service_name)
                )
                if not cursor.fetchone():
                    logger.warning(f"Adding health check for unknown service {service_name} in app {app_name}")
                    # Create service record with unknown state
                    self.update_service(app_name, service_name, "unknown")

                # Extract status from health data
                status = health_data.get("status", "unknown")

                # Record health check
                cursor.execute(
                    """
                    INSERT INTO health_checks (app_name, service_name, status, timestamp, details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (app_name, service_name, status, datetime.now(), json.dumps(health_data))
                )

                conn.commit()
                logger.debug(f"Added health check for {service_name} in app {app_name}: {status}")
                return True
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, status, timestamp, details FROM health_checks
                    WHERE app_name = ? AND service_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (app_name, service_name, limit)
                )

                return [
                    {
                        "id": row[0],
                        "status": row[1],
                        "timestamp": row[2],
                        "details": json.loads(row[3]) if row[3] else {}
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Log error
                cursor.execute(
                    """
                    INSERT INTO error_log (app_name, service_name, error_message, timestamp, resolved)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (app_name, service_name, error_message, datetime.now())
                )

                # If service-level error, update service state
                if service_name:
                    self.update_service(app_name, service_name, "error")

                conn.commit()
                logger.info(f"Recorded error for {app_name}{f'/{service_name}' if service_name else ''}: {error_message}")
                return True
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if service_name:
                    # Get service-level error
                    cursor.execute(
                        """
                        SELECT id, error_message, timestamp, resolved FROM error_log
                        WHERE app_name = ? AND service_name = ?
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """,
                        (app_name, service_name)
                    )
                else:
                    # Get app-level error
                    cursor.execute(
                        """
                        SELECT id, error_message, timestamp, resolved FROM error_log
                        WHERE app_name = ? AND service_name IS NULL
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """,
                        (app_name,)
                    )

                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "error_message": row[1],
                        "timestamp": row[2],
                        "resolved": bool(row[3])
                    }
                return None
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE error_log
                    SET resolved = 1
                    WHERE id = ?
                    """,
                    (error_id,)
                )

                success = cursor.rowcount > 0
                conn.commit()

                if success:
                    logger.info(f"Resolved error {error_id}")
                else:
                    logger.warning(f"Error {error_id} not found")

                return success
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if app_name:
                    cursor.execute(
                        """
                        SELECT id, app_name, commit_hash, timestamp, status, error_message
                        FROM deployments
                        WHERE app_name = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (app_name, limit)
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, app_name, commit_hash, timestamp, status, error_message
                        FROM deployments
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (limit,)
                    )

                return [
                    DeploymentState(
                        id=row[0],
                        app_name=row[1],
                        commit_hash=row[2],
                        timestamp=datetime.fromisoformat(row[3]) if isinstance(row[3], str) else row[3],
                        status=row[4],
                        error_message=row[5]
                    )
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, app_name, commit_hash, timestamp, status, error_message
                    FROM deployments
                    WHERE app_name = ? AND status = 'success'
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (app_name,)
                )
                row = cursor.fetchone()
                if row:
                    return DeploymentState(
                        id=row[0],
                        app_name=row[1],
                        commit_hash=row[2],
                        timestamp=datetime.fromisoformat(row[3]) if isinstance(row[3], str) else row[3],
                        status=row[4],
                        error_message=row[5]
                    )
                return None
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                query = """
                    SELECT s.app_name, s.service_name, s.state, s.container_id, s.last_updated
                    FROM services s
                """

                params = []
                where_clauses = []

                if app_name:
                    where_clauses.append("s.app_name = ?")
                    params.append(app_name)

                if state:
                    where_clauses.append("s.state = ?")
                    params.append(state)

                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)

                query += " ORDER BY s.last_updated DESC"

                cursor.execute(query, params)

                return [
                    {
                        "app_name": row[0],
                        "service_name": row[1],
                        "state": row[2],
                        "container_id": row[3],
                        "last_updated": row[4]
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
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
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Get application info
                cursor.execute(
                    "SELECT * FROM applications WHERE app_name = ?",
                    (app_name,)
                )
                app_info = cursor.fetchone()
                if not app_info:
                    return {"status": "not_found", "app_name": app_name}

                # Get services and their states
                cursor.execute(
                    "SELECT service_name, state FROM services WHERE app_name = ?",
                    (app_name,)
                )
                services = {row[0]: row[1] for row in cursor.fetchall()}

                # Get last deployment
                cursor.execute(
                    """
                    SELECT id, commit_hash, timestamp, status, error_message 
                    FROM deployments 
                    WHERE app_name = ? 
                    ORDER BY timestamp DESC LIMIT 1
                    """,
                    (app_name,)
                )
                last_deployment_row = cursor.fetchone()
                last_deployment = None
                if last_deployment_row:
                    last_deployment = {
                        "id": last_deployment_row["id"],
                        "commit_hash": last_deployment_row["commit_hash"],
                        "timestamp": last_deployment_row["timestamp"],
                        "status": last_deployment_row["status"],
                        "error_message": last_deployment_row["error_message"]
                    }

                # Count services by state
                cursor.execute(
                    """
                    SELECT state, COUNT(*) as count
                    FROM services 
                    WHERE app_name = ? 
                    GROUP BY state
                    """,
                    (app_name,)
                )
                state_counts = {row["state"]: row["count"] for row in cursor.fetchall()}

                # Count active errors
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM error_log 
                    WHERE app_name = ? AND resolved = 0
                    """,
                    (app_name,)
                )
                error_count = cursor.fetchone()["count"]

                # Determine overall status
                overall_status = "healthy"  # Default
                if error_count > 0:
                    overall_status = "error"
                elif "error" in state_counts or "failed" in state_counts:
                    overall_status = "error"
                elif "unhealthy" in state_counts:
                    overall_status = "unhealthy"
                elif last_deployment and last_deployment["status"] == "failed":
                    overall_status = "deployment_failed"
                elif not services:
                    overall_status = "no_services"

                # Prepare summary
                summary = {
                    "app_name": app_name,
                    "description": app_info["description"],
                    "last_updated": app_info["last_updated"],
                    "services": services,
                    "service_count": len(services),
                    "state_counts": state_counts,
                    "error_count": error_count,
                    "overall_status": overall_status
                }

                # Add last deployment info if available
                if last_deployment:
                    summary["last_deployment"] = last_deployment

                return summary

        except sqlite3.Error as e:
            logger.error(f"Failed to get app status summary: {e}")
            return {"status": "error", "app_name": app_name, "error": str(e)}

    def get_status_all_applications(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all applications.

        Returns:
            Dictionary of application names and their status
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get all application names
                cursor.execute("SELECT app_name FROM applications WHERE enabled = 1")
                app_names = [row[0] for row in cursor.fetchall()]

                # Get status for each application
                return {
                    app_name: self.get_app_status_summary(app_name)
                    for app_name in app_names
                }
        except sqlite3.Error as e:
            logger.error(f"Failed to get status of all applications: {e}")
            raise