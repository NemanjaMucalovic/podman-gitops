import logging
import os
from pathlib import Path
from typing import Optional
from git import Repo, GitCommandError
from .config import GitConfig

logger = logging.getLogger(__name__)

class GitOperations:
    """Handles Git operations for the GitOps workflow."""

    def __init__(self, config: GitConfig, work_dir: Path):
        self.config = config
        self.work_dir = work_dir
        self.repo: Optional[Repo] = None
        self._setup_ssh()

    def _setup_ssh(self):
        """Set up SSH key for Git operations."""
        if self.config.ssh_key_path:
            # Ensure SSH key exists
            if not self.config.ssh_key_path.exists():
                raise ValueError(f"SSH key not found at {self.config.ssh_key_path}")
            
            # Set up SSH environment
            os.environ['GIT_SSH_COMMAND'] = f'ssh -i {self.config.ssh_key_path} -o StrictHostKeyChecking=no'
            
            # If key has password, set up ssh-agent
            if self.config.ssh_key_password:
                import subprocess
                try:
                    # Start ssh-agent
                    subprocess.run(['ssh-agent', '-s'], check=True)
                    # Add key to ssh-agent
                    subprocess.run(
                        ['ssh-add', str(self.config.ssh_key_path)],
                        input=self.config.ssh_key_password.encode(),
                        check=True
                    )
                except subprocess.SubprocessError as e:
                    logger.error(f"Failed to set up ssh-agent: {e}")
                    raise

    def clone_repository(self) -> bool:
        """Clone the repository if it doesn't exist."""
        try:
            # Use custom repo directory if specified
            repo_dir = self.config.repo_dir or self.work_dir
            
            if not repo_dir.exists():
                repo_dir.mkdir(parents=True)
            
            if not (repo_dir / '.git').exists():
                logger.info(f"Cloning repository {self.config.repository_url}")
                self.repo = Repo.clone_from(
                    self.config.repository_url,
                    repo_dir,
                    branch=self.config.branch
                )
                return True
            return False
        except GitCommandError as e:
            logger.error(f"Failed to clone repository: {e}")
            raise

    def pull_changes(self) -> bool:
        """Pull latest changes from the repository."""
        try:
            if not self.repo:
                repo_dir = self.config.repo_dir or self.work_dir
                self.repo = Repo(repo_dir)
            
            logger.info("Pulling latest changes")
            self.repo.remotes.origin.pull()
            return True
        except GitCommandError as e:
            logger.error(f"Failed to pull changes: {e}")
            raise

    def get_current_commit(self) -> str:
        """Get the current commit hash."""
        if not self.repo:
            repo_dir = self.config.repo_dir or self.work_dir
            self.repo = Repo(repo_dir)
        return self.repo.head.commit.hexsha

    def checkout_branch(self, branch: str) -> bool:
        """Checkout a specific branch."""
        try:
            if not self.repo:
                repo_dir = self.config.repo_dir or self.work_dir
                self.repo = Repo(repo_dir)
            
            logger.info(f"Checking out branch {branch}")
            self.repo.git.checkout(branch)
            return True
        except GitCommandError as e:
            logger.error(f"Failed to checkout branch: {e}")
            raise 