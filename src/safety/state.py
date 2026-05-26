"""Safety-related state definitions.

SandboxState is defined in sandbox_manager.py to keep the enum close to its
primary consumer and avoid circular imports.
"""
from .sandbox_manager import SandboxState

__all__ = ["SandboxState"]
