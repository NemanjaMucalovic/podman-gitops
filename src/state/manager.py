import logging
import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

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
    """Manages the state of deployments using SQLite."""

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

                # Create deployments table with app_name
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS deployments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        app_name TEXT NOT NULL,
                        commit_hash TEXT NOT NULL,
                        timestamp DATETIME NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT
                    )
                """)

                # Create service_states table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS service_states (
                        app_name TEXT NOT NULL,
                        service_name TEXT NOT NULL,
                        state TEXT NOT NULL,
                        last_updated DATETIME NOT NULL,
                        PRIMARY KEY (app_name, service_name)
                    )
                """)

                # Create error_messages table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS error_messages (
                        app_name TEXT NOT NULL,
                        service_name TEXT NOT NULL,
                        error_message TEXT NOT NULL,
                        last_updated DATETIME NOT NULL,
                        PRIMARY KEY (app_name, service_name)
                    )
                """)

                # Create health_history table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS health_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        app_name TEXT NOT NULL,
                        service_name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        details TEXT,
                        timestamp DATETIME NOT NULL
                    )
                """)

                # Create rollback_history table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rollback_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        app_name TEXT NOT NULL,
                        service_name TEXT NOT NULL,
                        version TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        timestamp DATETIME NOT NULL
                    )
                """)

                # Create app_configs table to store application configurations
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS app_configs (
                        app_name TEXT PRIMARY KEY,
                        config TEXT NOT NULL,
                        last_updated DATETIME NOT NULL
                    )
                """)

                conn.commit()
                logger.info("Database initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def set_service_state(self, app_name: str, service_name: str, state: str) -> None:
        """Set the state of a service.

        Args:
            app_name: Name of the application
            service_name: Name of the service
            state: Current state of the service
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO service_states (app_name, service_name, state, last_updated)
                    VALUES (?, ?, ?, ?)
                    """,
                    (app_name, service_name, state, datetime.now())
                )
                conn.commit()
                logger.debug(f"Set state of service {service_name} in app {app_name} to {state}")
        except sqlite3.Error as e:
            logger.error(f"Failed to set service state: {e}")
            raise

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
                    "SELECT state FROM service_states WHERE app_name = ? AND service_name = ?",
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
                    "SELECT service_name, state FROM service_states WHERE app_name = ?",
                    (app_name,)
                )
                return {row[0]: row[1] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            logger.error(f"Failed to get application services: {e}")
            raise

    def remove_service_state(self, app_name: str, service_name: str) -> None:
        """Remove the state of a service.

        Args:
            app_name: Name of the application
            service_name: Name of the service
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM service_states WHERE app_name = ? AND service_name = ?",
                    (app_name, service_name)
                )
                conn.commit()
                logger.debug(f"Removed state of service {service_name} in app {app_name}")
        except sqlite3.Error as e:
            logger.error(f"Failed to remove service state: {e}")
            raise

    def add_health_check(self, app_name: str, service_name: str, health_data: Dict[str, Any]) -> None:
        """Add a health check result.

        Args:
            app_name: Name of the application
            service_name: Name of the service
            health_data: Health check data
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO health_history (app_name, service_name, status, details, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (app_name, service_name, health_data.get("status", "unknown"),
                     json.dumps(health_data), datetime.now())
                )
                conn.commit()
                logger.debug(f"Added health check for service {service_name} in app {app_name}")
        except sqlite3.Error as e:
            logger.error(f"Failed to add health check: {e}")
            raise

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
                    SELECT details, timestamp FROM health_history
                    WHERE app_name = ? AND service_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (app_name, service_name, limit)
                )
                return [
                    {
                        **json.loads(row[0]),
                        "timestamp": row[1]
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get health history: {e}")
            raise

    def add_rollback(self, app_name: str, service_name: str, rollback_data: Dict[str, str]) -> None:
        """Add a rollback record.

        Args:
            app_name: Name of the application
            service_name: Name of the service
            rollback_data: Rollback data
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO rollback_history (app_name, service_name, version, reason, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (app_name, service_name, rollback_data.get("version", "unknown"),
                     rollback_data.get("reason", "unknown"), datetime.now())
                )
                conn.commit()
                logger.debug(f"Added rollback for service {service_name} in app {app_name}")
        except sqlite3.Error as e:
            logger.error(f"Failed to add rollback: {e}")
            raise

    def record_deployment(self, app_name: str, commit_hash: str, status: str, error_message: Optional[str] = None) -> int:
        """Record a new deployment in the database.

        Args:
            app_name: Name of the application
            commit_hash: Git commit hash
            status: Deployment status
            error_message: Optional error message

        Returns:
            ID of the new deployment record
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO deployments (app_name, commit_hash, timestamp, status, error_message)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (app_name, commit_hash, datetime.now(), status, error_message)
                )
                conn.commit()
                logger.info(f"Recorded deployment for app {app_name} with status {status}")
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to record deployment: {e}")
            raise

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
                        timestamp=datetime.fromisoformat(row[3]),
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
                        timestamp=datetime.fromisoformat(row[3]),
                        status=row[4],
                        error_message=row[5]
                    )
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to get last successful deployment: {e}")
            raise

    def set_last_error(self, app_name: str, service_name: str, error_message: str) -> None:
        """Set the last error for a service.

        Args:
            app_name: Name of the application
            service_name: Name of the service
            error_message: Error message
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO error_messages (app_name, service_name, error_message, last_updated)
                    VALUES (?, ?, ?, ?)
                    """,
                    (app_name, service_name, error_message, datetime.now())
                )
                conn.commit()
                logger.debug(f"Set error for service {service_name} in app {app_name}")

                # Also update service state
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO service_states (app_name, service_name, state, last_updated)
                    VALUES (?, ?, ?, ?)
                    """,
                    (app_name, service_name, "error", datetime.now())
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to set last error: {e}")
            raise

    def get_last_error(self, app_name: str, service_name: str) -> Optional[str]:
        """Get the last error for a service.

        Args:
            app_name: Name of the application
            service_name: Name of the service

        Returns:
            Last error message or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT error_message FROM error_messages WHERE app_name = ? AND service_name = ?",
                    (app_name, service_name)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get last error: {e}")
            raise

    def clear_last_error(self, app_name: str, service_name: str) -> None:
        """Clear the last error for a service.

        Args:
            app_name: Name of the application
            service_name: Name of the service
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM error_messages WHERE app_name = ? AND service_name = ?",
                    (app_name, service_name)
                )
                conn.commit()
                logger.debug(f"Cleared error for service {service_name} in app {app_name}")
        except sqlite3.Error as e:
            logger.error(f"Failed to clear last error: {e}")
            raise

    def store_app_config(self, app_name: str, config: Dict[str, Any]) -> None:
        """Store the configuration for an application.

        Args:
            app_name: Name of the application
            config: Application configuration
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO app_configs (app_name, config, last_updated)
                    VALUES (?, ?, ?)
                    """,
                    (app_name, json.dumps(config), datetime.now())
                )
                conn.commit()
                logger.debug(f"Stored configuration for app {app_name}")
        except sqlite3.Error as e:
            logger.error(f"Failed to store app configuration: {e}")
            raise

    def get_app_config(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Get the configuration for an application.

        Args:
            app_name: Name of the application

        Returns:
            Application configuration or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT config FROM app_configs WHERE app_name = ?",
                    (app_name,)
                )
                result = cursor.fetchone()
                return json.loads(result[0]) if result else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get app configuration: {e}")
            raise

    def get_all_apps(self) -> List[str]:
        """Get a list of all applications in the database.

        Returns:
            List of application names
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT app_name FROM app_configs")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get all apps: {e}")
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
                cursor = conn.cursor()

                # Get services and their states
                cursor.execute(
                    "SELECT service_name, state FROM service_states WHERE app_name = ?",
                    (app_name,)
                )
                services = {row[0]: row[1] for row in cursor.fetchall()}

                # Get last deployment
                cursor.execute(
                    """
                    SELECT commit_hash, timestamp, status, error_message 
                    FROM deployments 
                    WHERE app_name = ? 
                    ORDER BY timestamp DESC LIMIT 1
                    """,
                    (app_name,)
                )
                last_deployment = cursor.fetchone()

                # Get count of services by state
                cursor.execute(
                    """
                    SELECT state, COUNT(*) 
                    FROM service_states 
                    WHERE app_name = ? 
                    GROUP BY state
                    """,
                    (app_name,)
                )
                state_counts = {row[0]: row[1] for row in cursor.fetchall()}

                # Get count of errors
                cursor.execute(
                    "SELECT COUNT(*) FROM error_messages WHERE app_name = ?",
                    (app_name,)
                )
                error_count = cursor.fetchone()[0]

                # Prepare summary
                summary = {
                    "app_name": app_name,
                    "services": services,
                    "service_count": len(services),
                    "state_counts": state_counts,
                    "error_count": error_count,
                    "overall_status": "healthy"  # Default
                }

                # Add last deployment info if available
                if last_deployment:
                    summary["last_deployment"] = {
                        "commit_hash": last_deployment[0],
                        "timestamp": last_deployment[1],
                        "status": last_deployment[2],
                        "error_message": last_deployment[3]
                    }

                # Determine overall status
                if error_count > 0 or "error" in state_counts:
                    summary["overall_status"] = "error"
                elif "unhealthy" in state_counts:
                    summary["overall_status"] = "unhealthy"

                return summary

        except sqlite3.Error as e:
            logger.error(f"Failed to get app status summary: {e}")
            raise