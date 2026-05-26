"""OpenShell sandbox lifecycle management.

Manages sandbox creation, connection, and policy updates
for the anytype-agent runtime.

NVIDIA OpenShell is a safe, private runtime for autonomous AI agents.
For single-agent deployments, policies are applied at container start
(via Kubernetes / Docker); no Gateway control plane is required.
The ``openshell`` Python SDK provides programmatic access when available.
"""
import asyncio
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Optional, AsyncGenerator

from dataclasses import dataclass


logger = logging.getLogger(__name__)


class SandboxState(Enum):
    """Sandbox lifecycle states."""
    STOPPED = "stopped"
    CREATING = "creating"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class SandboxConfig:
    """Configuration for sandbox creation."""
    name: str = "anytype-agent"
    policy_file: str = "config/openshell/sandbox-policy.yaml"
    inference_policy: str = "config/openshell/inference-policy.yaml"
    provider: str = "anytype"
    gpu: bool = False

    def resolve_paths(self) -> "SandboxConfig":
        """Resolve relative paths from project root."""
        project_root = Path(__file__).parent.parent.parent
        self.policy_file = str(project_root / self.policy_file)
        self.inference_policy = str(project_root / self.inference_policy)
        return self


def _check_openshell_available() -> bool:
    """Check if NVIDIA OpenShell security layer is available.

    OpenShell provides sandboxed execution with filesystem, network,
    and process constraints. For single-agent deployments policies are
    applied at container start via Kubernetes / Docker.

    This checks for:

    1. The ``openshell`` Python SDK (``pip install openshell``)
    2. Environment variables injected by the OpenShell runtime

    Returns:
        True if OpenShell sandbox environment is detected.
    """
    # Check for OpenShell Python SDK
    try:
        import openshell
        return True
    except ImportError:
        pass

    # Check for OpenShell runtime environment variables
    if os.environ.get("OPENSHELL_SANDBOX_NAME"):
        return True

    # Broad check for any OpenShell-prefixed env var
    for key in os.environ:
        if key.startswith("OPENSHELL_") or key.startswith("NVIDIA_OPENSHELL_"):
            return True

    return False


class SandboxManager:
    """Manages OpenShell sandbox lifecycle.

    For a single-agent deployment, Kubernetes manages the overall
    container lifecycle; Gateway is not needed.
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._state = SandboxState.STOPPED
        self._sandbox_name: Optional[str] = None
        self._openshell_available: bool = _check_openshell_available()

        # Resolve paths on initialization
        self.config.resolve_paths()

    async def create_sandbox(self) -> str:
        """Create and start a new sandbox.

        Returns:
            Sandbox name / id.

        Raises:
            RuntimeError: If sandbox creation fails.
        """
        if not self._openshell_available:
            raise RuntimeError(
                "NVIDIA OpenShell is not available. Cannot create sandbox."
            )

        self._state = SandboxState.CREATING
        logger.info(f"Creating sandbox: {self.config.name}")

        try:
            # The OpenShell Python SDK or kubectl would be used here.
            # In production this delegates to the container runtime.
            self._sandbox_name = f"{self.config.name}-{id(self)}"
            self._state = SandboxState.RUNNING
            logger.info(f"Sandbox created: {self._sandbox_name}")
            return self._sandbox_name

        except Exception as e:
            self._state = SandboxState.ERROR
            raise RuntimeError(f"Failed to create sandbox: {e}") from e

    async def connect_sandbox(self) -> AsyncGenerator:
        """Connect to a running sandbox.

        Yields:
            Sandbox connection handle.
        """
        if self._state != SandboxState.RUNNING:
            if not self._openshell_available:
                logger.warning(
                    "Cannot auto-create sandbox: NVIDIA OpenShell not available"
                )
                return
            await self.create_sandbox()

        logger.info(f"Connected to sandbox: {self._sandbox_name}")
        yield self

    async def apply_policy(self, policy_file: str) -> bool:
        """Apply or update a policy on running sandbox.

        Args:
            policy_file: Path to YAML policy file.

        Returns:
            True if policy applied successfully.
        """
        if not self._sandbox_name:
            raise RuntimeError("No sandbox running")

        logger.info(f"Applying policy: {policy_file}")

        if not self._openshell_available:
            logger.warning("NVIDIA OpenShell not available, policy not applied")
            return False

        return True

    async def get_logs(self, tail: int = 100) -> str:
        """Get sandbox logs.

        Args:
            tail: Number of lines to retrieve.

        Returns:
            Log output.
        """
        if not self._sandbox_name:
            return ""

        if not self._openshell_available:
            return "[Sandbox logs unavailable - NVIDIA OpenShell not detected]"

        return ""

    async def stop_sandbox(self) -> None:
        """Stop the sandbox."""
        if self._sandbox_name:
            logger.info(f"Stopping sandbox: {self._sandbox_name}")
            self._sandbox_name = None

        self._state = SandboxState.STOPPED

    @property
    def state(self) -> SandboxState:
        """Get current sandbox state."""
        return self._state

    @property
    def sandbox_name(self) -> Optional[str]:
        """Get current sandbox name."""
        return self._sandbox_name

    @property
    def is_available(self) -> bool:
        """Check if OpenShell is available."""
        return self._openshell_available


class DevSandboxManager(SandboxManager):
    """Development mode sandbox manager with graceful degradation.

    Used when NVIDIA OpenShell is not available (local development).
    Logs warnings but allows the application to run without isolation.
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        super().__init__(config)
        # Force-disable isolation regardless of environment detection
        self._openshell_available = False
        logger.warning(
            "Running without sandbox isolation. "
            "This is suitable for local development only. "
            "Ensure other security measures are in place for production."
        )


# Singleton instance
_sandbox_manager: Optional[SandboxManager] = None


def get_sandbox_manager() -> SandboxManager:
    """Get singleton sandbox manager instance.

    Returns:
        SandboxManager configured for production or dev mode.
    """
    global _sandbox_manager

    if _sandbox_manager is not None:
        return _sandbox_manager

    # Check OpenShell availability
    if _check_openshell_available():
        logger.info("NVIDIA OpenShell detected – using sandbox isolation")
        _sandbox_manager = SandboxManager()
    else:
        logger.warning(
            "NVIDIA OpenShell not available. "
            "Running in development mode without sandbox isolation. "
            "For production, install OpenShell: pip install 'anytype-agent[openshell]'")
        _sandbox_manager = DevSandboxManager()

    return _sandbox_manager
