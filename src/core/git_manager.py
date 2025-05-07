import logging
from typing import Dict, Optional, Set
from pathlib import Path

from .git_operations import GitOperations
from .config import GitConfig

logger = logging.getLogger(__name__)

class GitManager:
    """Manages multiple Git repositories for different applications."""

    def __init__(self):
        """Initialize the Git manager."""
        # Map of repository URLs to GitOperations instances
        self.repositories: Dict[str, GitOperations] = {}

        # Track which repositories have been checked this cycle
        self.checked_repos: Set[str] = set()

        # Track which repositories have changes
        self.repos_with_changes: Set[str] = set()

    def get_git_ops(self, git_config: GitConfig, work_dir: Path) -> GitOperations:
        """Get or create a GitOperations instance for a repository.

        Args:
            git_config: Git configuration
            work_dir: Working directory

        Returns:
            GitOperations instance
        """
        repo_url = git_config.repository_url

        # Create a new GitOperations instance if one doesn't exist
        if repo_url not in self.repositories:
            logger.info(f"Creating new GitOperations for repository: {repo_url}")
            self.repositories[repo_url] = GitOperations(git_config, work_dir)

        return self.repositories[repo_url]

    def check_for_changes(self, git_ops: GitOperations) -> bool:
        """Check if a repository has changes (only once per cycle).

        Args:
            git_ops: GitOperations instance

        Returns:
            True if there are changes, False otherwise
        """
        repo_url = git_ops.config.repository_url

        # If we've already checked this repository, return the cached result
        if repo_url in self.checked_repos:
            has_changes = repo_url in self.repos_with_changes
            logger.debug(f"Using cached change status for {repo_url}: {has_changes}")
            return has_changes

        # Check for changes and cache the result
        has_changes = git_ops.has_changes()
        self.checked_repos.add(repo_url)

        if has_changes:
            self.repos_with_changes.add(repo_url)

        return has_changes

    def reset_cycle(self):
        """Reset the cycle tracking."""
        self.checked_repos.clear()
        self.repos_with_changes.clear()