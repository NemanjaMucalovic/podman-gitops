"""
State management for Podman GitOps.
"""

from .manager import StateManager, DeploymentState

__all__ = [
    'StateManager',
    'DeploymentState',
]