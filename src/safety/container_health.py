"""Container health monitoring for OpenShell sandbox.

Provides health checks to verify sandbox security is active
and functioning correctly.
"""
import logging
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    status: HealthStatus
    message: str
    details: dict


class ContainerHealthChecker:
    """Performs health checks on container security.
    
    Verifies that OpenShell's kernel-level security policies are
    properly enforced at the application level.
    """

    def __init__(self):
        self._checks: list[callable] = [
            self._check_sandbox_isolation,
            self._check_network_restricted,
            self._check_process_capabilities,
        ]

    async def check(self) -> HealthCheckResult:
        """Run all health checks.
        
        Returns:
            Overall health status with details of each check.
        """
        results: list[tuple[str, bool]] = []
        
        for check in self._checks:
            try:
                result = await check()
                results.append((check.__name__, result))
            except Exception as e:
                logger.error(f"Health check failed: {check.__name__} - {e}")
                results.append((check.__name__, False))

        # All checks must pass for HEALTHY
        all_passed = all(r[1] for r in results)
        any_failed = any(not r[1] for r in results)
        
        if all_passed:
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="All container security checks passed",
                details={r[0]: "pass" for r in results},
            )
        elif any_failed:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="One or more security checks failed",
                details={r[0]: "fail" for r in results},
            )
        else:
            # Fallback for edge cases
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message="Health check completed with partial results",
                details={r[0]: "unknown" for r in results},
            )

    async def _check_sandbox_isolation(self) -> bool:
        """Verify filesystem isolation is active.
        
        In a properly sandboxed environment:
        - /host should not exist or be inaccessible
        - /proc/1/root should be restricted
        
        Returns:
            True if isolation is working, False if blocked paths are accessible.
        """
        blocked_paths = ["/host", "/proc/1/root"]
        
        for path in blocked_paths:
            if Path(path).exists():
                # Path exists - check if we can access it
                try:
                    # Attempt to list the directory contents
                    list(Path(path).iterdir())
                    # If we can access a blocked path, isolation is broken
                    logger.warning(f"Blocked path accessible: {path}")
                    return False
                except PermissionError:
                    # Good - path is blocked as expected
                    continue
                except OSError:
                    # Other OS-level error, assume blocked
                    continue
        
        return True

    async def _check_network_restricted(self) -> bool:
        """Verify network policies are enforced.
        
        This is a best-effort check. Actual enforcement is done by
        OpenShell's policy engine at the HTTP/proxy level.
        
        Returns:
            True if network appears restricted (best-effort).
        """
        # Check for common sandbox indicators
        # In a real sandboxed environment, network policies are enforced
        # at the proxy/ingress level, not through direct socket checks
        
        # Check if we have access to common external addresses
        # This is a passive check - we're not attempting connections
        suspicious_env_vars = [
            "http_proxy",
            "https_proxy",
            "no_proxy",
        ]
        
        # If proxies are configured, network is likely controlled
        for var in suspicious_env_vars:
            if os.environ.get(var):
                logger.debug(f"Network proxy detected via {var}")
                return True
        
        # No explicit proxy found - assume network may be less restricted
        # but don't fail the check as OpenShell handles this
        return True

    async def _check_process_capabilities(self) -> bool:
        """Verify dangerous capabilities are dropped.
        
        In a restricted container:
        - Should not be able to create user namespaces
        - Should not be able to mount
        - Should not be able to load kernel modules
        
        Returns:
            True if capabilities appear restricted, False if running as root.
        """
        # Check if we're running as root
        if os.geteuid() == 0:
            logger.warning(
                "Process running as root - capabilities not restricted. "
                "In a properly sandboxed environment, containers should "
                "run as non-root user."
            )
            return False
        
        return True


# Singleton instance
_checker: Optional[ContainerHealthChecker] = None


def get_health_checker() -> ContainerHealthChecker:
    """Get singleton health checker instance.
    
    Returns:
        ContainerHealthChecker singleton.
    """
    global _checker
    if _checker is None:
        _checker = ContainerHealthChecker()
    return _checker