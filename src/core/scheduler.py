from datetime import datetime
from croniter import croniter
import logging

logger = logging.getLogger(__name__)

class CronScheduler:
    """Manages cron-based schedules for application operations."""

    def __init__(self):
        """Initialize the scheduler."""
        # Map of app names to their next scheduled run time
        self.next_runs = {}
        # Map of app names to their cron expressions
        self.schedules = {}

    def set_schedule(self, app_name: str, cron_expression: str) -> bool:
        """Set a cron schedule for an application.

        Args:
            app_name: Name of the application
            cron_expression: Cron expression defining the schedule

        Returns:
            Success status
        """
        try:
            # Validate the cron expression by creating a croniter object
            base = datetime.now()
            cron = croniter(cron_expression, base)

            # Set the next run time
            self.next_runs[app_name] = cron.get_next(datetime)
            self.schedules[app_name] = cron_expression

            logger.info(f"Set schedule for {app_name}: {cron_expression}, next run at {self.next_runs[app_name]}")
            return True
        except Exception as e:
            logger.error(f"Invalid cron expression for {app_name}: {cron_expression} - {e}")
            return False

    def get_next_run(self, app_name: str) -> datetime:
        """Get the next scheduled run time for an application.

        Args:
            app_name: Name of the application

        Returns:
            Next run time as datetime
        """
        return self.next_runs.get(app_name)

    def is_due(self, app_name: str) -> bool:
        """Check if an application is due to run.

        Args:
            app_name: Name of the application

        Returns:
            True if the application is due to run, False otherwise
        """
        if app_name not in self.next_runs:
            return False

        now = datetime.now()
        return now >= self.next_runs[app_name]

    def update_next_run(self, app_name: str) -> None:
        """Update the next run time for an application after it has run.

        Args:
            app_name: Name of the application
        """
        if app_name in self.schedules:
            cron = croniter(self.schedules[app_name], datetime.now())
            self.next_runs[app_name] = cron.get_next(datetime)
            logger.debug(f"Updated next run for {app_name} to {self.next_runs[app_name]}")