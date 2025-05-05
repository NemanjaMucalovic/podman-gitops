# src/metrics/influx.py
import socket
import time
import logging
from datetime import datetime
from typing import Dict, Optional, Any

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from . import BaseMetricsCollector

logger = logging.getLogger(__name__)

class InfluxMetricsCollector(BaseMetricsCollector):
    """Collects and sends metrics to InfluxDB for the GitOps service."""

    def __init__(self, url: str, token: str, org: str, bucket: str):
        """Initialize the InfluxDB metrics collector.

        Args:
            url: InfluxDB server URL
            token: InfluxDB API token
            org: InfluxDB organization
            bucket: InfluxDB bucket
        """
        try:
            self.client = InfluxDBClient(url=url, token=token, org=org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.bucket = bucket
            self.org = org
            self.host = socket.gethostname()

            # Test connection
            health = self.client.health()
            if health.status == "pass":
                logger.info(f"Connected to InfluxDB at {url} (version: {health.version})")
            else:
                logger.warning(f"InfluxDB connection check returned status: {health.status}")

        except Exception as e:
            logger.error(f"Failed to initialize InfluxDB client: {e}")
            raise

        logger.info(f"InfluxDB metrics collector initialized for host {self.host}")

    def record_deployment(self, status: str, duration: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a deployment attempt.

        Args:
            status: Deployment status (success, failure)
            duration: Deployment duration in seconds
            labels: Additional labels (app, etc.)
        """
        try:
            labels = labels or {}
            app = labels.get('app', 'unknown')

            point = Point("deployment") \
                .tag("host", self.host) \
                .tag("status", status) \
                .tag("app", app) \
                .field("duration", duration) \
                .field("count", 1)

            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.debug(f"Recorded deployment metric: {status} for {app} in {duration}s")
        except Exception as e:
            logger.error(f"Failed to record deployment metric: {e}")

    def update_active_containers(self, count: int, app: Optional[str] = None) -> None:
        """Update the number of active containers.

        Args:
            count: Number of active containers
            app: Optional application name
        """
        try:
            app = app or 'all'

            point = Point("active_containers") \
                .tag("host", self.host) \
                .tag("app", app) \
                .field("count", count)

            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.debug(f"Updated active containers count: {count} for {app}")
        except Exception as e:
            logger.error(f"Failed to update active containers count: {e}")

    def record_git_operation(self, operation: str, status: str, duration: float,
                             app: Optional[str] = None) -> None:
        """Record a Git operation.

        Args:
            operation: Type of operation (clone, pull, etc.)
            status: Operation status (success, failure)
            duration: Operation duration in seconds
            app: Optional application name
        """
        try:
            app = app or 'unknown'

            point = Point("git_operation") \
                .tag("host", self.host) \
                .tag("operation", operation) \
                .tag("status", status) \
                .tag("app", app) \
                .field("duration", duration) \
                .field("count", 1)

            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.debug(f"Recorded git operation: {operation} for {app}")
        except Exception as e:
            logger.error(f"Failed to record git operation: {e}")

    def record_health_check(self, container: str, status: str, duration: float,
                            app: Optional[str] = None) -> None:
        """Record a health check result.

        Args:
            container: Container name
            status: Health check status (healthy, unhealthy)
            duration: Health check duration in seconds
            app: Optional application name
        """
        try:
            app = app or 'unknown'

            point = Point("health_check") \
                .tag("host", self.host) \
                .tag("container", container) \
                .tag("status", status) \
                .tag("app", app) \
                .field("duration", duration) \
                .field("count", 1)

            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.debug(f"Recorded health check: {status} for {container}")
        except Exception as e:
            logger.error(f"Failed to record health check: {e}")

    def update_app_metrics(self, app_name: str, service_counts: Dict[str, int],
                           error_count: int, deployment_age: Optional[float] = None) -> None:
        """Update application-specific metrics.

        Args:
            app_name: Name of the application
            service_counts: Dictionary of service states and their counts
            error_count: Number of errors in the application
            deployment_age: Time since last successful deployment in seconds
        """
        try:
            # Send service state counts
            for state, count in service_counts.items():
                point = Point("app_services") \
                    .tag("host", self.host) \
                    .tag("app", app_name) \
                    .tag("state", state) \
                    .field("count", count)

                self.write_api.write(bucket=self.bucket, org=self.org, record=point)

            # Send error count
            point = Point("app_errors") \
                .tag("host", self.host) \
                .tag("app", app_name) \
                .field("count", error_count)

            self.write_api.write(bucket=self.bucket, org=self.org, record=point)

            # Send deployment age if provided
            if deployment_age is not None:
                point = Point("app_deployment_age") \
                    .tag("host", self.host) \
                    .tag("app", app_name) \
                    .field("seconds", deployment_age)

                self.write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.debug(f"Updated app metrics for {app_name}")
        except Exception as e:
            logger.error(f"Failed to update app metrics: {e}")

    def close(self) -> None:
        """Clean up resources."""
        try:
            if self.client:
                self.client.close()
                logger.info("InfluxDB client closed")
        except Exception as e:
            logger.error(f"Error closing InfluxDB client: {e}")