# src/metrics/__init__.py
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

class BaseMetricsCollector:
    """Base interface for metrics collection."""

    def record_deployment(self, status: str, duration: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a deployment attempt."""
        pass

    def update_active_containers(self, count: int, app: Optional[str] = None) -> None:
        """Update the number of active containers."""
        pass

    def record_git_operation(self, operation: str, status: str, duration: float, app: Optional[str] = None) -> None:
        """Record a Git operation."""
        pass

    def record_health_check(self, container: str, status: str, duration: float, app: Optional[str] = None) -> None:
        """Record a health check result."""
        pass

    def update_app_metrics(self, app_name: str, service_counts: Dict[str, int],
                           error_count: int, deployment_age: Optional[float] = None) -> None:
        """Update application-specific metrics."""
        pass

    def close(self) -> None:
        """Clean up resources."""
        pass

def get_metrics_collector(config):
    """Factory function to get the appropriate metrics collector based on configuration."""
    if not config.metrics.enabled:
        logger.info("Metrics collection is disabled")
        return None

    if config.metrics.type == "influxdb":
        try:
            from .influx import InfluxMetricsCollector
            logger.info("Using InfluxDB metrics collector")
            return InfluxMetricsCollector(
                url=config.metrics.influxdb_url,
                token=config.metrics.influxdb_token,
                org=config.metrics.influxdb_org,
                bucket=config.metrics.influxdb_bucket
            )
        except ImportError:
            logger.error("Failed to import InfluxDB metrics collector. "
                         "Is influxdb-client installed? Try: pip install 'podman-gitops[influxdb]'")
            return None
    else:  # Default to Prometheus
        try:
            from .prometheus import PrometheusMetricsCollector
            logger.info("Using Prometheus metrics collector")
            return PrometheusMetricsCollector()
        except ImportError:
            logger.error("Failed to import Prometheus metrics collector. "
                         "Is prometheus-client installed? Try: pip install 'podman-gitops[prometheus]'")
            return None