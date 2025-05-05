from prometheus_client import Counter, Gauge, Histogram
from typing import Dict, Optional, Any
import logging

from . import BaseMetricsCollector

logger = logging.getLogger(__name__)

class PrometheusMetricsCollector(BaseMetricsCollector):
    """Collects and exposes Prometheus metrics for the GitOps service."""

    def __init__(self):
        """Initialize Prometheus metrics."""
        # Deployment metrics
        self.deployment_total = Counter(
            'gitops_deployment_total',
            'Total number of deployments',
            ['status', 'app']
        )
        self.deployment_duration = Histogram(
            'gitops_deployment_duration_seconds',
            'Duration of deployments in seconds',
            ['app'],
            buckets=[1, 5, 10, 30, 60, 120, 300]
        )
        self.active_containers = Gauge(
            'gitops_active_containers',
            'Number of active containers',
            ['app']
        )
        self.active_apps = Gauge(
            'gitops_active_apps',
            'Number of active applications'
        )

        # Git operation metrics
        self.git_operations = Counter(
            'gitops_git_operations_total',
            'Total number of Git operations',
            ['operation', 'status', 'app']
        )
        self.git_operation_duration = Histogram(
            'gitops_git_operation_duration_seconds',
            'Duration of Git operations in seconds',
            ['operation', 'app'],
            buckets=[0.1, 0.5, 1, 2, 5, 10]
        )

        # Health check metrics
        self.health_checks = Counter(
            'gitops_health_checks_total',
            'Total number of health checks',
            ['container', 'status', 'app']
        )
        self.health_check_duration = Histogram(
            'gitops_health_check_duration_seconds',
            'Duration of health checks in seconds',
            ['container', 'app'],
            buckets=[0.1, 0.5, 1, 2, 5]
        )

        # Application metrics
        self.app_services = Gauge(
            'gitops_app_services',
            'Number of services in an application',
            ['app', 'state']
        )
        self.app_errors = Gauge(
            'gitops_app_errors',
            'Number of errors in an application',
            ['app']
        )
        self.app_deployment_age = Gauge(
            'gitops_app_deployment_age_seconds',
            'Time since last successful deployment in seconds',
            ['app']
        )

        logger.info("Prometheus metrics collector initialized")

    def record_deployment(self, status: str, duration: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a deployment attempt.

        Args:
            status: Deployment status (success, failure)
            duration: Deployment duration in seconds
            labels: Additional labels (app, etc.)
        """
        labels = labels or {}
        app = labels.get('app', 'unknown')

        self.deployment_total.labels(status=status, app=app).inc()
        self.deployment_duration.labels(app=app).observe(duration)
        logger.debug(f"Recorded deployment metric: {status} for {app} in {duration}s")

    def update_active_containers(self, count: int, app: Optional[str] = None) -> None:
        """Update the number of active containers.

        Args:
            count: Number of active containers
            app: Optional application name
        """
        if app:
            self.active_containers.labels(app=app).set(count)
        else:
            # Create an 'all' label value for total count
            self.active_containers.labels(app='all').set(count)
        logger.debug(f"Updated active containers count: {count} for {app or 'all'}")

    def update_active_apps(self, count: int) -> None:
        """Update the number of active applications.

        Args:
            count: Number of active applications
        """
        self.active_apps.set(count)
        logger.debug(f"Updated active apps count: {count}")

    def record_git_operation(self, operation: str, status: str, duration: float,
                             app: Optional[str] = None) -> None:
        """Record a Git operation.

        Args:
            operation: Type of operation (clone, pull, etc.)
            status: Operation status (success, failure)
            duration: Operation duration in seconds
            app: Optional application name
        """
        app = app or 'unknown'
        self.git_operations.labels(operation=operation, status=status, app=app).inc()
        self.git_operation_duration.labels(operation=operation, app=app).observe(duration)
        logger.debug(f"Recorded git operation: {operation} for {app} with status {status}")

    def record_health_check(self, container: str, status: str, duration: float,
                            app: Optional[str] = None) -> None:
        """Record a health check result.

        Args:
            container: Container name
            status: Health check status (healthy, unhealthy)
            duration: Health check duration in seconds
            app: Optional application name
        """
        app = app or 'unknown'
        self.health_checks.labels(container=container, status=status, app=app).inc()
        self.health_check_duration.labels(container=container, app=app).observe(duration)
        logger.debug(f"Recorded health check: {status} for {container} in app {app}")

    def update_app_metrics(self, app_name: str, service_counts: Dict[str, int],
                           error_count: int, deployment_age: Optional[float] = None) -> None:
        """Update application-specific metrics.

        Args:
            app_name: Name of the application
            service_counts: Dictionary of service states and their counts
            error_count: Number of errors in the application
            deployment_age: Time since last successful deployment in seconds
        """
        # Update service counts by state
        for state, count in service_counts.items():
            self.app_services.labels(app=app_name, state=state).set(count)

        # Update error count
        self.app_errors.labels(app=app_name).set(error_count)

        # Update deployment age if provided
        if deployment_age is not None:
            self.app_deployment_age.labels(app=app_name).set(deployment_age)

        logger.debug(f"Updated app metrics for {app_name}")

    def reset_app_metrics(self, app_name: str) -> None:
        """Reset metrics for an application.

        Args:
            app_name: Name of the application
        """
        # Reset service counts for all possible states
        for state in ['running', 'stopped', 'failed', 'starting', 'stopping', 'unknown']:
            self.app_services.labels(app=app_name, state=state).set(0)

        # Reset error count
        self.app_errors.labels(app=app_name).set(0)

        # Reset deployment age
        self.app_deployment_age.labels(app=app_name).set(0)

        logger.debug(f"Reset all metrics for {app_name}")

    def close(self) -> None:
        """Clean up resources."""
        # No special cleanup needed for Prometheus client
        pass