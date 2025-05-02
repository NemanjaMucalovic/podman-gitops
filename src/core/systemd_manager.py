import logging
import subprocess
import os
from pathlib import Path
from typing import Optional, List, Dict, Set, Tuple

logger = logging.getLogger(__name__)

class SystemdManager:
    """Manages systemd services using subprocess commands."""

    def __init__(self, quadlet_dir: Path):
        """Initialize the systemd manager.

        Args:
            quadlet_dir: Directory where quadlet files are stored
        """
        self.quadlet_dir = Path(os.path.expanduser(str(quadlet_dir)))
        self._ensure_directories()

        # Cache of service to application mapping
        self._service_app_map: Dict[str, str] = {}

    def _ensure_directories(self):
        """Ensure necessary directories exist."""
        self.quadlet_dir.mkdir(parents=True, exist_ok=True)

    def _run_command(self, command: List[str]) -> Tuple[int, str, str]:
        """Run a systemd command and return the result.

        Args:
            command: Command to run as a list of strings

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        try:
            # Add --user flag for user services
            if command[0] == "systemctl":
                command.insert(1, "--user")

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to run command {' '.join(command)}: {e}")
            raise

    def reload_daemon(self) -> bool:
        """Reload the systemd daemon.

        Returns:
            Success status
        """
        code, stdout, stderr = self._run_command(["systemctl", "daemon-reload"])
        if code != 0:
            logger.error(f"Failed to reload daemon: {stderr}")
            return False
        return True

    def start_service(self, service_name: str) -> bool:
        """Start a systemd service.

        Args:
            service_name: Name of the service

        Returns:
            Success status
        """
        code, stdout, stderr = self._run_command(["systemctl", "start", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to start service {service_name}: {stderr}")
            return False
        return True

    def stop_service(self, service_name: str) -> bool:
        """Stop a systemd service.

        Args:
            service_name: Name of the service

        Returns:
            Success status
        """
        code, stdout, stderr = self._run_command(["systemctl", "stop", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to stop service {service_name}: {stderr}")
            return False
        return True

    def restart_service(self, service_name: str) -> bool:
        """Restart a systemd service.

        Args:
            service_name: Name of the service

        Returns:
            Success status
        """
        code, stdout, stderr = self._run_command(["systemctl", "restart", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to restart service {service_name}: {stderr}")
            return False
        return True

    def get_service_status(self, service_name: str) -> Dict[str, str]:
        """Get the status of a systemd service.

        Args:
            service_name: Name of the service

        Returns:
            Dictionary with status information
        """
        code, stdout, stderr = self._run_command(["systemctl", "status", f"{service_name}.service"])
        status = {
            "active": "unknown",
            "state": "unknown",
            "details": stdout or stderr
        }

        if code == 0:
            for line in stdout.splitlines():
                if "Active:" in line:
                    status["active"] = line.split("Active:")[1].strip()
                elif "State:" in line:
                    status["state"] = line.split("State:")[1].strip()

        return status

    def enable_service(self, service_name: str) -> bool:
        """Enable a systemd service to start on boot.

        Args:
            service_name: Name of the service

        Returns:
            Success status
        """
        code, stdout, stderr = self._run_command(["systemctl", "enable", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to enable service {service_name}: {stderr}")
            return False
        return True

    def disable_service(self, service_name: str) -> bool:
        """Disable a systemd service from starting on boot.

        Args:
            service_name: Name of the service

        Returns:
            Success status
        """
        code, stdout, stderr = self._run_command(["systemctl", "disable", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to disable service {service_name}: {stderr}")
            return False
        return True

    def list_services(self, app_name: Optional[str] = None) -> List[str]:
        """List all quadlet services, optionally filtered by application.

        Args:
            app_name: Optional application name to filter by

        Returns:
            List of service names
        """
        try:
            # Get all service files in the quadlet directory
            services = []
            for file in self.quadlet_dir.glob("*.container"):
                service_name = file.stem

                # If app_name is provided, only include services for that app
                if app_name:
                    if service_name.startswith(f"{app_name}-") or self._get_app_for_service(service_name) == app_name:
                        services.append(service_name)
                else:
                    services.append(service_name)

            return services
        except Exception as e:
            logger.error(f"Failed to list services: {e}")
            return []

    def _get_app_for_service(self, service_name: str) -> Optional[str]:
        """Get the application name for a service.
        This is a simple heuristic - it assumes services are prefixed with app name.

        Args:
            service_name: Name of the service

        Returns:
            Application name or None if not found
        """
        # Check cache first
        if service_name in self._service_app_map:
            return self._service_app_map[service_name]

        # Try to determine from service name (app-service convention)
        parts = service_name.split('-', 1)
        if len(parts) > 1:
            self._service_app_map[service_name] = parts[0]
            return parts[0]

        return None

    def register_service_for_app(self, app_name: str, service_name: str) -> None:
        """Register a service as belonging to an application.

        Args:
            app_name: Name of the application
            service_name: Name of the service
        """
        self._service_app_map[service_name] = app_name

    def start_app_services(self, app_name: str) -> Dict[str, bool]:
        """Start all services for an application.

        Args:
            app_name: Name of the application

        Returns:
            Dictionary of service names and their success status
        """
        services = self.list_services(app_name)
        results = {}

        for service_name in services:
            results[service_name] = self.start_service(service_name)

        return results

    def stop_app_services(self, app_name: str) -> Dict[str, bool]:
        """Stop all services for an application.

        Args:
            app_name: Name of the application

        Returns:
            Dictionary of service names and their success status
        """
        services = self.list_services(app_name)
        results = {}

        for service_name in services:
            results[service_name] = self.stop_service(service_name)

        return results

    def restart_app_services(self, app_name: str) -> Dict[str, bool]:
        """Restart all services for an application.

        Args:
            app_name: Name of the application

        Returns:
            Dictionary of service names and their success status
        """
        services = self.list_services(app_name)
        results = {}

        for service_name in services:
            results[service_name] = self.restart_service(service_name)

        return results

    def get_app_services_status(self, app_name: str) -> Dict[str, Dict[str, str]]:
        """Get status of all services for an application.

        Args:
            app_name: Name of the application

        Returns:
            Dictionary of service names and their status
        """
        services = self.list_services(app_name)
        results = {}

        for service_name in services:
            results[service_name] = self.get_service_status(service_name)

        return results