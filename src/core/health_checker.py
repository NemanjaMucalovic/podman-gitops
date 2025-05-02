import logging
import socket
import subprocess
import time
import httpx
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any

logger = logging.getLogger(__name__)

class HealthChecker:
    """Basic health checker for containers."""

    def __init__(self):
        """Initialize the health checker."""
        self._ensure_podman()
        self._client = httpx.Client(timeout=1.0)
        logger.info("Health checker initialized")

    def _ensure_podman(self):
        """Ensure Podman is available."""
        try:
            result = subprocess.run(["podman", "--version"], capture_output=True, check=True, text=True)
            logger.info(f"Podman available: {result.stdout.strip()}")
        except subprocess.SubprocessError as e:
            logger.error("Podman is not available: %s", e)
            raise RuntimeError("Podman is not installed or not accessible")

    def _get_container_ports(self, container_name: str) -> Dict[str, int]:
        """Get the exposed ports of a container."""
        try:
            logger.debug(f"Getting ports for container {container_name}")

            # Try a different format string that directly gives us the port mappings
            result = subprocess.run(
                ["podman", "inspect", "--format", "{{json .HostConfig.PortBindings}}", container_name],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0 and result.stdout.strip():
                try:
                    # Parse the JSON output
                    import json
                    port_bindings = json.loads(result.stdout.strip())

                    ports = {}
                    for port_key, bindings in port_bindings.items():
                        # Format is usually like "8080/tcp"
                        port_str = port_key.split('/')[0]

                        # Each binding is a list of objects with HostIP and HostPort
                        for binding in bindings:
                            host_port = binding.get('HostPort')
                            if host_port and host_port.isdigit():
                                ports[port_str] = int(host_port)

                    logger.debug(f"Parsed ports for {container_name} from JSON: {ports}")
                    return ports
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON port bindings: {result.stdout}")
                    # Fall back to the original method

            # If JSON approach failed, try an alternative method by getting exposed ports
            result = subprocess.run(
                ["podman", "container", "port", container_name],
                capture_output=True,
                text=True,
                check=False
            )

            ports = {}
            if result.returncode == 0 and result.stdout.strip():
                # Output format: 8080/tcp -> 0.0.0.0:8080
                for line in result.stdout.strip().split('\n'):
                    parts = line.split(' -> ')
                    if len(parts) == 2:
                        container_port = parts[0].split('/')[0]  # Get "8080" from "8080/tcp"
                        host_part = parts[1]  # Get "0.0.0.0:8080"

                        if ':' in host_part:
                            host_port = host_part.split(':')[1]
                            if host_port.isdigit():
                                ports[container_port] = int(host_port)

                logger.debug(f"Parsed ports for {container_name} using port command: {ports}")
                return ports

            logger.warning(f"No port bindings found for container {container_name}")
            return {}
        except Exception as e:
            logger.error(f"Failed to get container ports: {e}")
            return {}

    def _check_tcp_port(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """Check if a TCP port is open."""
        try:
            logger.debug(f"Checking TCP port {port} on {host}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            is_open = result == 0
            logger.debug(f"TCP port {port} on {host} is {'open' if is_open else 'closed'}")
            return is_open
        except Exception as e:
            logger.error(f"Failed to check TCP port {port}: {e}")
            return False

    def _check_http_status(self, url: str, timeout: float = 1.0) -> bool:
        """Check if an HTTP endpoint returns 200."""
        try:
            logger.debug(f"Checking HTTP status for {url}")
            response = self._client.get(url, timeout=timeout)
            is_ok = response.status_code == 200
            logger.debug(f"HTTP status for {url}: {response.status_code} (ok: {is_ok})")
            return is_ok
        except Exception as e:
            logger.error(f"Failed to check HTTP status for {url}: {e}")
            return False

    def check_container_health(self, container_name: str) -> Dict[str, Any]:
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

            if state_result.returncode != 0:
                logger.warning(f"Failed to inspect container {container_name}: {state_result.stderr}")
                return {
                    "status": "not_found",
                    "state": "unknown",
                    "healthy": False
                }

            state = state_result.stdout.strip()
            logger.info(f"Container {container_name} state: {state}")

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

                # Check if the container has any exposed ports in its configuration
                exposed_ports_result = subprocess.run(
                    ["podman", "inspect", "--format", "{{.Config.ExposedPorts}}", container_name],
                    capture_output=True,
                    text=True,
                    check=False
                )

                exposed_ports = exposed_ports_result.stdout.strip()
                logger.info(f"Container {container_name} exposed ports: {exposed_ports}")

                if exposed_ports == "map[]" or not exposed_ports:
                    logger.info(f"Container {container_name} has no exposed ports, assuming it's healthy")
                    return {
                        "status": "running_no_ports",
                        "state": state,
                        "healthy": True  # Consider it healthy if it's not meant to expose ports
                    }
                else:
                    logger.warning(f"Container {container_name} has exposed ports but none are mapped")
                    return {
                        "status": "no_mapped_ports",
                        "state": state,
                        "healthy": False
                    }

            # Check TCP ports
            port_checks = {}
            for port in ports.values():
                port_checks[port] = self._check_tcp_port("localhost", port)

            logger.info(f"TCP port checks for {container_name}: {port_checks}")

            if not any(port_checks.values()):
                logger.warning(f"No open TCP ports found for container {container_name}")
                return {
                    "status": "no_open_ports",
                    "state": state,
                    "ports": {str(p): "closed" for p in ports.values()},
                    "healthy": False
                }

            # If any port is open, consider it healthy
            # Optionally try HTTP check
            http_healthy = False
            for port in ports.values():
                if port_checks.get(port, False):
                    try:
                        logger.debug(f"Attempting HTTP check on port {port}")
                        http_healthy = self._check_http_status(f"http://localhost:{port}")
                        if http_healthy:
                            logger.info(f"HTTP check successful on port {port}")
                            break
                    except Exception as e:
                        logger.debug(f"HTTP check error on port {port}: {e}")

            # Determine overall health based on port checks
            # If any port is open, consider it healthy even if HTTP check fails
            healthy = state == "running" and any(port_checks.values())

            health_status = {
                "status": "healthy" if healthy else "unhealthy",
                "state": state,
                "ports": {str(p): "open" if port_checks.get(p, False) else "closed" for p in ports.values()},
                "http": "ok" if http_healthy else "failed" if any(port_checks.values()) else "not_attempted",
                "healthy": healthy
            }

            logger.info(f"Health check result for {container_name}: {health_status}")
            return health_status

        except Exception as e:
            logger.error(f"Failed to check container health: {e}", exc_info=True)
            return {
                "status": "error",
                "state": "error",
                "error": str(e),
                "healthy": False
            }

    def wait_for_healthy(self, container_name: str, timeout: int = 30) -> bool:
        """Wait for a container to become healthy."""
        logger.info(f"Waiting for container {container_name} to become healthy (timeout: {timeout}s)")
        start_time = time.time()
        while time.time() - start_time < timeout:
            health = self.check_container_health(container_name)
            if health["healthy"]:
                logger.info(f"Container {container_name} is healthy after {int(time.time() - start_time)}s")
                return True

            # Log progress
            elapsed = int(time.time() - start_time)
            logger.debug(f"Container {container_name} is not yet healthy after {elapsed}s, current state: {health['state']}")

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
                logger.debug(f"Successfully retrieved {lines} lines of logs for {container_name}")
                return result.stdout
            else:
                logger.error(f"Failed to get logs for {container_name}: {result.stderr}")
                return None
        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
            return None

    def get_container_id(self, container_name: str) -> Optional[str]:
        """Get the container ID for a given container name."""
        try:
            logger.debug(f"Getting container ID for {container_name}")
            result = subprocess.run(
                ["podman", "inspect", "--format", "{{.Id}}", container_name],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                container_id = result.stdout.strip()
                logger.debug(f"Container ID for {container_name}: {container_id}")
                return container_id
            else:
                logger.warning(f"Failed to get container ID for {container_name}: {result.stderr}")
                return None
        except Exception as e:
            logger.error(f"Error getting container ID: {e}")
            return None

    def get_all_containers(self) -> List[Dict[str, str]]:
        """Get a list of all containers with their health status."""
        try:
            logger.info("Getting all containers")
            result = subprocess.run(
                ["podman", "ps", "-a", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                logger.error(f"Failed to list containers: {result.stderr}")
                return []

            containers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            logger.info(f"Found {len(containers)} containers")

            container_status = []
            for container in containers:
                health = self.check_container_health(container)
                container_status.append({
                    "name": container,
                    "state": health.get("state", "unknown"),
                    "status": health.get("status", "unknown"),
                    "healthy": health.get("healthy", False)
                })

            return container_status

        except Exception as e:
            logger.error(f"Failed to get all containers: {e}")
            return []

    def __del__(self):
        """Clean up httpx client."""
        try:
            self._client.close()
        except Exception:
            pass