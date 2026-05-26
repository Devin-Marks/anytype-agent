"""Safety module for OpenShell sandbox integration.

Exports:
- SandboxManager for lifecycle management
- SandboxState enum for state tracking
- get_sandbox_manager() singleton getter
"""
from .sandbox_manager import (
    SandboxManager,
    DevSandboxManager,
    SandboxConfig,
    SandboxState,
    get_sandbox_manager,
)

__all__ = [
    "SandboxManager",
    "DevSandboxManager",
    "SandboxConfig",
    "SandboxState",
    "get_sandbox_manager",
]