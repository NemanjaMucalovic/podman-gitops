import logging
import socket
import subprocess
import time
import httpx
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class HealthChecker:
    """Basic health checker for containers."""

    def __init__(self):
        self._ensure_podman()
        self._client = httpx.Client(timeout=1.0)

    def _ensure_podman(self):
        """Ensure Podman is available."""
        try:
            subprocess.run(["podman", "--version"], capture_output=True, check=True)
        except subprocess.SubprocessError as e:
            logger.error("Podman is not available: %s", e)
            raise RuntimeError("Podman is not installed or not accessible")

    def _get_container_ports(self, container_name: str) -> Dict[str, int]:
        """Get the exposed ports of a container."""
        try:
            result = subprocess.run(
                ["podman", "inspect", "--format", "{{.HostConfig.PortBindings}}", container_name],
                capture_output=True,
                text=True,
                check=False
            )
            
            ports = {}
            if result.returncode == 0 and result.stdout.strip():
                logger.info(f"Container {container_name} port bindings: {result.stdout.strip()}")
                # The output will be in format like: map[8080/tcp:[{HostIP: HostPort:8080}]]
                # We need to parse this to get the host ports
                output = result.stdout.strip()
                if output != "map[]" and output != "<nil>":
                    # Remove the map[] wrapper
                    port_mappings = output[4:-1]  # Remove "map[" and "]"
                    if port_mappings:
                        # Split by port mappings
                        for mapping in port_mappings.split(" "):
                            if mapping:
                                try:
                                    # Extract port number from format like "8080/tcp:[{HostIP: HostPort:8080}]"
                                    port_str = mapping.split("/")[0]
                                    port_num = int(port_str)
                                    ports[port_str] = port_num
                                except (ValueError, IndexError) as e:
                                    logger.warning(f"Failed to parse port mapping {mapping}: {e}")
            else:
                logger.warning(f"No port bindings found for container {container_name}")
            
            logger.info(f"Parsed ports for {container_name}: {ports}")
            return ports
        except Exception as e:
            logger.error(f"Failed to get container ports: {e}")
            return {}

    def _check_tcp_port(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """Check if a TCP port is open."""
        try:
            logger.info(f"Checking TCP port {port} on {host}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            is_open = result == 0
            logger.info(f"TCP port {port} on {host} is {'open' if is_open else 'closed'}")
            return is_open
        except Exception as e:
            logger.error(f"Failed to check TCP port {port}: {e}")
            return False

    def _check_http_status(self, url: str, timeout: float = 1.0) -> bool:
        """Check if an HTTP endpoint returns 200."""
        try:
            logger.info(f"Checking HTTP status for {url}")
            response = self._client.get(url, timeout=timeout)
            is_ok = response.status_code == 200
            logger.info(f"HTTP status for {url}: {response.status_code} (ok: {is_ok})")
            return is_ok
        except Exception as e:
            logger.error(f"Failed to check HTTP status for {url}: {e}")
            return False

    def check_container_health(self, container_name: str) -> Dict[str, str]:
        """Check the health of a container."""
        try:
            logger.info(f"Checking health for container: {container_name}")
            
            # Get container state
            state_result = subprocess.run(
                ["podman", "inspect", "--format", "{{.State.Status}}", container_name],
                capture_output=True,
                text=True,
                check=False
            )
            logger.info(f"Container {container_name} state: {state_result.stdout.strip()}")
            
            state = state_result.stdout.strip() if state_result.returncode == 0 else "unknown"
            
            # Check if container is running
            if state != "running":
                logger.warning(f"Container {container_name} is not running (state: {state})")
                return {
                    "status": "not_running",
                    "state": state,
                    "healthy": False
                }
            
            # Get container ports
            ports = self._get_container_ports(container_name)
            if not ports:
                logger.warning(f"No TCP ports found for container {container_name}")
                return {
                    "status": "no_ports",
                    "state": state,
                    "healthy": False
                }
            
            # Check TCP ports
            port_checks = {}
            for port in ports.values():
                port_checks[port] = self._check_tcp_port("localhost", port)
            
            if not any(port_checks.values()):
                logger.warning(f"No open TCP ports found for container {container_name}")
                return {
                    "status": "no_open_ports",
                    "state": state,
                    "ports": {str(p): "closed" for p in ports.values()},
                    "healthy": False
                }
            
            # If any port is open, try HTTP check
            http_healthy = False
            for port in ports.values():
                if port_checks[port]:
                    logger.info(f"Attempting HTTP check on port {port}")
                    http_healthy = self._check_http_status(f"http://localhost:{port}")
                    if http_healthy:
                        logger.info(f"HTTP check successful on port {port}")
                        break
            
            # Determine overall health
            healthy = state == "running" and any(port_checks.values()) and http_healthy
            
            health_status = {
                "status": "healthy" if healthy else "unhealthy",
                "state": state,
                "ports": {str(p): "open" if v else "closed" for p, v in port_checks.items()},
                "http": "ok" if http_healthy else "failed",
                "healthy": healthy
            }
            
            logger.info(f"Health check result for {container_name}: {health_status}")
            return health_status
            
        except Exception as e:
            logger.error(f"Failed to check container health: {e}")
            return {
                "status": "error",
                "state": "error",
                "healthy": False
            }

    def wait_for_healthy(self, container_name: str, timeout: int = 30) -> bool:
        """Wait for a container to become healthy."""
        logger.info(f"Waiting for container {container_name} to become healthy (timeout: {timeout}s)")
        start_time = time.time()
        while time.time() - start_time < timeout:
            health = self.check_container_health(container_name)
            if health["healthy"]:
                logger.info(f"Container {container_name} is healthy")
                return True
            time.sleep(1)
        
        logger.warning(f"Container {container_name} did not become healthy within {timeout}s")
        return False

    def get_container_logs(self, container_name: str, lines: int = 50) -> Optional[str]:
        """Get recent logs from a container."""
        try:
            logger.info(f"Getting logs for container {container_name}")
            result = subprocess.run(
                ["podman", "logs", "--tail", str(lines), container_name],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                logger.info(f"Successfully retrieved logs for {container_name}")
                return result.stdout
            else:
                logger.error(f"Failed to get logs for {container_name}: {result.stderr}")
                return None
        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
            return None

    def __del__(self):
        """Clean up httpx client."""
        try:
            self._client.close()
        except Exception:
            pass 