"""Sandbox state definitions."""
from enum import Enum


class SandboxState(Enum):
    """Sandbox lifecycle states."""
    STOPPED = "stopped"
    CREATING = "creating"
    RUNNING = "running"
    ERROR = "error"