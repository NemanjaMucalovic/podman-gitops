import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

class SystemdManager:
    """Manages systemd services using subprocess commands."""

    def __init__(self, quadlet_dir: Path):
        self.quadlet_dir = quadlet_dir
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure necessary directories exist."""
        self.quadlet_dir.mkdir(parents=True, exist_ok=True)

    def _run_command(self, command: List[str]) -> tuple[int, str, str]:
        """Run a systemd command and return the result."""
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
        """Reload the systemd daemon."""
        code, stdout, stderr = self._run_command(["systemctl", "daemon-reload"])
        if code != 0:
            logger.error(f"Failed to reload daemon: {stderr}")
            return False
        return True

    def start_service(self, service_name: str) -> bool:
        """Start a systemd service."""
        code, stdout, stderr = self._run_command(["systemctl", "start", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to start service {service_name}: {stderr}")
            return False
        return True

    def stop_service(self, service_name: str) -> bool:
        """Stop a systemd service."""
        code, stdout, stderr = self._run_command(["systemctl", "stop", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to stop service {service_name}: {stderr}")
            return False
        return True

    def restart_service(self, service_name: str) -> bool:
        """Restart a systemd service."""
        code, stdout, stderr = self._run_command(["systemctl", "restart", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to restart service {service_name}: {stderr}")
            return False
        return True

    def get_service_status(self, service_name: str) -> Dict[str, str]:
        """Get the status of a systemd service."""
        code, stdout, stderr = self._run_command(["systemctl", "status", f"{service_name}.service"])
        status = {
            "active": "unknown",
            "state": "unknown",
            "details": stdout
        }
        
        if code == 0:
            for line in stdout.splitlines():
                if "Active:" in line:
                    status["active"] = line.split("Active:")[1].strip()
                elif "State:" in line:
                    status["state"] = line.split("State:")[1].strip()
        
        return status

    def enable_service(self, service_name: str) -> bool:
        """Enable a systemd service to start on boot."""
        code, stdout, stderr = self._run_command(["systemctl", "enable", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to enable service {service_name}: {stderr}")
            return False
        return True

    def disable_service(self, service_name: str) -> bool:
        """Disable a systemd service from starting on boot."""
        code, stdout, stderr = self._run_command(["systemctl", "disable", f"{service_name}.service"])
        if code != 0:
            logger.error(f"Failed to disable service {service_name}: {stderr}")
            return False
        return True

    def list_services(self) -> List[str]:
        """List all quadlet services."""
        try:
            services = []
            for file in self.quadlet_dir.glob("*.container"):
                service_name = file.stem
                code, stdout, stderr = self._run_command(["systemctl", "is-active", f"{service_name}.service"])
                if code == 0:
                    services.append(service_name)
            return services
        except Exception as e:
            logger.error(f"Failed to list services: {e}")
            return [] 