from prometheus_client import Counter, Gauge, Histogram
from typing import Dict

class MetricsCollector:
    """Collects and exposes Prometheus metrics for the GitOps service."""

    def __init__(self):
        # Deployment metrics
        self.deployment_total = Counter(
            'gitops_deployment_total',
            'Total number of deployments',
            ['status']
        )
        self.deployment_duration = Histogram(
            'gitops_deployment_duration_seconds',
            'Duration of deployments in seconds',
            buckets=[1, 5, 10, 30, 60, 120, 300]
        )
        self.active_containers = Gauge(
            'gitops_active_containers',
            'Number of active containers'
        )

        # Git operation metrics
        self.git_operations = Counter(
            'gitops_git_operations_total',
            'Total number of Git operations',
            ['operation', 'status']
        )
        self.git_operation_duration = Histogram(
            'gitops_git_operation_duration_seconds',
            'Duration of Git operations in seconds',
            buckets=[0.1, 0.5, 1, 2, 5, 10]
        )

        # Health check metrics
        self.health_checks = Counter(
            'gitops_health_checks_total',
            'Total number of health checks',
            ['container', 'status']
        )
        self.health_check_duration = Histogram(
            'gitops_health_check_duration_seconds',
            'Duration of health checks in seconds',
            buckets=[0.1, 0.5, 1, 2, 5]
        )

    def record_deployment(self, status: str, duration: float):
        """Record a deployment attempt."""
        self.deployment_total.labels(status=status).inc()
        self.deployment_duration.observe(duration)

    def update_active_containers(self, count: int):
        """Update the number of active containers."""
        self.active_containers.set(count)

    def record_git_operation(self, operation: str, status: str, duration: float):
        """Record a Git operation."""
        self.git_operations.labels(operation=operation, status=status).inc()
        self.git_operation_duration.observe(duration)

    def record_health_check(self, container: str, status: str, duration: float):
        """Record a health check result."""
        self.health_checks.labels(container=container, status=status).inc()
        self.health_check_duration.observe(duration) 