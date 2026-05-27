"""Safety module for OpenShell sandbox integration.

This module provides safety features for the anytype-agent runtime:

- SandboxManager: Lifecycle management for OpenShell sandbox (Phase 3)
- ContainerHealthChecker: Application-level health monitoring (Phase 4)
- SecurityEventLogger: Audit logging for security events (Phase 4)

OpenShell provides kernel-level security for filesystem, network, and
process isolation. This module adds application-level monitoring and
auditing capabilities on top of that foundation.
"""
from .sandbox_manager import (
    SandboxManager,
    DevSandboxManager,
    SandboxConfig,
    SandboxState,
    get_sandbox_manager,
)
from .container_health import (
    ContainerHealthChecker,
    HealthCheckResult,
    HealthStatus,
    get_health_checker,
)
from .security_events import (
    SecurityEventLogger,
    SecurityEvent,
    SecurityEventType,
    get_security_logger,
)

__all__ = [
    # Sandbox lifecycle (Phase 3)
    "SandboxManager",
    "DevSandboxManager",
    "SandboxConfig",
    "SandboxState",
    "get_sandbox_manager",
    # Health monitoring (Phase 4)
    "ContainerHealthChecker",
    "HealthCheckResult",
    "HealthStatus",
    "get_health_checker",
    # Audit logging (Phase 4)
    "SecurityEventLogger",
    "SecurityEvent",
    "SecurityEventType",
    "get_security_logger",
]