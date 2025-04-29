import logging
import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class DeploymentState:
    """Represents the state of a deployment."""
    id: int
    commit_hash: str
    timestamp: datetime
    status: str
    error_message: Optional[str] = None

class StateManager:
    """Manages the state of deployments using SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        # Create parent directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database with required tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create deployments table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS deployments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        commit_hash TEXT NOT NULL,
                        timestamp DATETIME NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT
                    )
                """)
                
                # Create service_states table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS service_states (
                        service_name TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        last_updated DATETIME NOT NULL
                    )
                """)
                
                # Create service_dependencies table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS service_dependencies (
                        service_name TEXT NOT NULL,
                        dependency TEXT NOT NULL,
                        PRIMARY KEY (service_name, dependency)
                    )
                """)
                
                # Create service_configurations table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS service_configurations (
                        service_name TEXT PRIMARY KEY,
                        configuration TEXT NOT NULL,
                        last_updated DATETIME NOT NULL
                    )
                """)
                
                # Create health_history table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS health_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                        service_name TEXT NOT NULL,
                        version TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        timestamp DATETIME NOT NULL
                    )
                """)
                
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def set_service_state(self, service_name: str, state: str) -> None:
        """Set the state of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO service_states (service_name, state, last_updated)
                    VALUES (?, ?, ?)
                    """,
                    (service_name, state, datetime.now())
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to set service state: {e}")
            raise

    def get_service_state(self, service_name: str) -> Optional[str]:
        """Get the state of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT state FROM service_states WHERE service_name = ?",
                    (service_name,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get service state: {e}")
            raise

    def remove_service_state(self, service_name: str) -> None:
        """Remove the state of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM service_states WHERE service_name = ?",
                    (service_name,)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to remove service state: {e}")
            raise

    def set_service_dependencies(self, service_name: str, dependencies: List[str]) -> None:
        """Set the dependencies of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Remove existing dependencies
                cursor.execute(
                    "DELETE FROM service_dependencies WHERE service_name = ?",
                    (service_name,)
                )
                # Add new dependencies
                for dep in dependencies:
                    cursor.execute(
                        """
                        INSERT INTO service_dependencies (service_name, dependency)
                        VALUES (?, ?)
                        """,
                        (service_name, dep)
                    )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to set service dependencies: {e}")
            raise

    def get_service_dependencies(self, service_name: str) -> List[str]:
        """Get the dependencies of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT dependency FROM service_dependencies WHERE service_name = ?",
                    (service_name,)
                )
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get service dependencies: {e}")
            raise

    def set_service_configuration(self, service_name: str, configuration: Dict[str, Any]) -> None:
        """Set the configuration of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO service_configurations (service_name, configuration, last_updated)
                    VALUES (?, ?, ?)
                    """,
                    (service_name, json.dumps(configuration), datetime.now())
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to set service configuration: {e}")
            raise

    def get_service_configuration(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get the configuration of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT configuration FROM service_configurations WHERE service_name = ?",
                    (service_name,)
                )
                result = cursor.fetchone()
                return json.loads(result[0]) if result else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get service configuration: {e}")
            raise

    def add_health_check(self, service_name: str, health_data: Dict[str, Any]) -> None:
        """Add a health check result."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO health_history (service_name, status, details, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (service_name, health_data["status"], json.dumps(health_data), datetime.now())
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to add health check: {e}")
            raise

    def get_service_health_history(self, service_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the health check history of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT details FROM health_history
                    WHERE service_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (service_name, limit)
                )
                return [json.loads(row[0]) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get health history: {e}")
            raise

    def add_rollback(self, service_name: str, rollback_data: Dict[str, Any]) -> None:
        """Add a rollback record."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO rollback_history (service_name, version, reason, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (service_name, rollback_data["version"], rollback_data["reason"], datetime.now())
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to add rollback: {e}")
            raise

    def get_service_rollback_history(self, service_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the rollback history of a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT version, reason, timestamp FROM rollback_history
                    WHERE service_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (service_name, limit)
                )
                return [
                    {
                        "version": row[0],
                        "reason": row[1],
                        "timestamp": row[2]
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get rollback history: {e}")
            raise

    def record_deployment(self, commit_hash: str, status: str, error_message: Optional[str] = None) -> int:
        """Record a new deployment in the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO deployments (commit_hash, timestamp, status, error_message)
                    VALUES (?, ?, ?, ?)
                    """,
                    (commit_hash, datetime.now(), status, error_message)
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to record deployment: {e}")
            raise

    def get_deployment_history(self, limit: int = 10) -> List[DeploymentState]:
        """Get the deployment history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, commit_hash, timestamp, status, error_message
                    FROM deployments
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
                return [
                    DeploymentState(
                        id=row[0],
                        commit_hash=row[1],
                        timestamp=datetime.fromisoformat(row[2]),
                        status=row[3],
                        error_message=row[4]
                    )
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get deployment history: {e}")
            raise

    def get_last_successful_deployment(self) -> Optional[DeploymentState]:
        """Get the last successful deployment."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, commit_hash, timestamp, status, error_message
                    FROM deployments
                    WHERE status = 'success'
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()
                if row:
                    return DeploymentState(
                        id=row[0],
                        commit_hash=row[1],
                        timestamp=datetime.fromisoformat(row[2]),
                        status=row[3],
                        error_message=row[4]
                    )
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to get last successful deployment: {e}")
            raise

    def set_last_error(self, service_name: str, error_message: str) -> None:
        """Set the last error for a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO service_states (service_name, state, last_updated)
                    VALUES (?, ?, ?)
                    """,
                    (service_name, "error", datetime.now())
                )
                # Store error message in service_configurations
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO service_configurations (service_name, configuration, last_updated)
                    VALUES (?, ?, ?)
                    """,
                    (service_name, json.dumps({"error": error_message}), datetime.now())
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to set last error: {e}")
            raise

    def get_last_error(self, service_name: str) -> Optional[str]:
        """Get the last error for a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT configuration FROM service_configurations WHERE service_name = ?",
                    (service_name,)
                )
                result = cursor.fetchone()
                if result:
                    config = json.loads(result[0])
                    return config.get("error")
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to get last error: {e}")
            raise

    def clear_last_error(self, service_name: str) -> None:
        """Clear the last error for a service."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM service_configurations WHERE service_name = ?",
                    (service_name,)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to clear last error: {e}")
            raise 