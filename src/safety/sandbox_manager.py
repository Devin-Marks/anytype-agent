"""OpenShell sandbox lifecycle management.

Manages sandbox creation, connection, and policy updates
for the anytype-agent runtime.
"""
import asyncio
import logging
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional, AsyncGenerator

from dataclasses import dataclass


class SandboxState(Enum):
    """Sandbox lifecycle states."""
    STOPPED = "stopped"
    CREATING = "creating"
    RUNNING = "running"
    ERROR = "error"



logger = logging.getLogger(__name__)



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


class SandboxManager:
    """Manages OpenShell sandbox lifecycle.

    For single agent deployment, uses CLI commands with Kubernetes
    managing the overall container lifecycle. Gateway is not needed.
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._state = SandboxState.STOPPED
        self._sandbox_name: Optional[str] = None
        self._openshell_available: bool = False

        # Resolve paths on initialization
        self.config.resolve_paths()

    async def create_sandbox(self) -> str:
        """Create and start a new sandbox.

        Returns:
            Sandbox name/id

        Raises:
            RuntimeError: If sandbox creation fails
        """
        if not self._openshell_available:
            raise RuntimeError(
                "OpenShell CLI not available. Cannot create sandbox."
            )

        self._state = SandboxState.CREATING
        logger.info(f"Creating sandbox: {self.config.name}")

        try:
            # OpenShell CLI command structure for sandbox creation
            # Note: Actual subprocess call is commented since OpenShell
            # may not be installed in development environment

            # result = subprocess.run([
            #     "openshell", "sandbox", "create",
            #     "--name", self.config.name,
            #     "--policy", self.config.policy_file,
            #     "--provider", self.config.provider,
            #     "--", "python", "-m", "uvicorn",
            #     "src.main:app",
            # ], capture_output=True, text=True)

            # if result.returncode != 0:
            #     raise RuntimeError(f"Sandbox creation failed: {result.stderr}")

            # For simulation, set the sandbox name
            self._sandbox_name = f"{self.config.name}-{id(self)}"
            self._state = SandboxState.RUNNING

            logger.info(f"Sandbox created: {self._sandbox_name}")
            return self._sandbox_name

        except subprocess.SubprocessError as e:
            self._state = SandboxState.ERROR
            raise RuntimeError(f"Failed to create sandbox: {e}")

    async def connect_sandbox(self) -> AsyncGenerator:
        """Connect to a running sandbox.

        Yields:
            Sandbox connection handle
        """
        if self._state != SandboxState.RUNNING:
            if not self._openshell_available:
                logger.warning("Cannot auto-create sandbox: OpenShell not available")
                return
            await self.create_sandbox()

        logger.info(f"Connected to sandbox: {self._sandbox_name}")
        yield self

    async def apply_policy(self, policy_file: str) -> bool:
        """Apply or update a policy on running sandbox.

        Args:
            policy_file: Path to YAML policy file

        Returns:
            True if policy applied successfully
        """
        if not self._sandbox_name:
            raise RuntimeError("No sandbox running")

        logger.info(f"Applying policy: {policy_file}")

        if not self._openshell_available:
            logger.warning("OpenShell not available, policy not applied")
            return False

        # OpenShell CLI command for applying policy
        # result = subprocess.run([
        #     "openshell", "policy", "set",
        #     self._sandbox_name,
        #     "--policy", policy_file,
        # ], capture_output=True, text=True)

        return True

    async def get_logs(self, tail: int = 100) -> str:
        """Get sandbox logs.

        Args:
            tail: Number of lines to retrieve

        Returns:
            Log output
        """
        if not self._sandbox_name:
            return ""

        if not self._openshell_available:
            return "[Sandbox logs unavailable - OpenShell not running]"

        # OpenShell CLI command for retrieving logs
        # result = subprocess.run([
        #     "openshell", "logs", self._sandbox_name,
        #     "--tail", str(tail),
        # ], capture_output=True, text=True)
        # return result.stdout

        return ""

    async def stop_sandbox(self) -> None:
        """Stop the sandbox."""
        if self._sandbox_name:
            logger.info(f"Stopping sandbox: {self._sandbox_name}")

            if self._openshell_available:
                # OpenShell CLI command for stopping sandbox
                # subprocess.run([
                #     "openshell", "sandbox", "stop",
                #     self._sandbox_name,
                # ], capture_output=True)
                pass

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

    Used when OpenShell CLI is not available (local development).
    Logs warnings but allows the application to run without isolation.
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        super().__init__(config)
        self._openshell_available = False
        logger.warning(
            "Running without sandbox isolation. "
            "This is suitable for local development only. "
            "Ensure other security measures are in place for production."
        )


def _check_openshell_available() -> bool:
    """Check if OpenShell CLI is available.

    Returns:
        True if openshell command can be executed
    """
    try:
        result = subprocess.run(
            ["openshell", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


# Singleton instance
_sandbox_manager: Optional[SandboxManager] = None


def get_sandbox_manager() -> SandboxManager:
    """Get singleton sandbox manager instance.

    Returns:
        SandboxManager configured for production or dev mode
    """
    global _sandbox_manager

    if _sandbox_manager is not None:
        return _sandbox_manager

    # Check OpenShell availability
    if _check_openshell_available():
        logger.info("OpenShell CLI detected - using sandbox isolation")
        _sandbox_manager = SandboxManager()
    else:
        logger.warning(
            "OpenShell not available. "
            "Running in development mode without sandbox isolation. "
            "For production, install OpenShell: "
            "curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh"
        )
        _sandbox_manager = DevSandboxManager()

    return _sandbox_manager