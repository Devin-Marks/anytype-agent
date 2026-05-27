"""Security event logging for OpenShell sandbox.

Logs security-relevant events for auditing and monitoring.
Supports machine parsing via JSON output.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """Types of security events for OpenShell sandbox."""
    # Policy events
    POLICY_APPLIED = "policy_applied"
    POLICY_REJECTED = "policy_rejected"
    
    # Network security events
    NETWORK_BLOCKED = "network_blocked"
    NETWORK_ALLOWED = "network_allowed"
    
    # Filesystem security events
    FILESYSTEM_BLOCKED = "filesystem_blocked"
    FILESYSTEM_ALLOWED = "filesystem_allowed"
    
    # Process security events
    PROCESS_BLOCKED = "process_blocked"
    PROCESS_ALLOWED = "process_allowed"
    
    # Credential events
    CREDENTIAL_INJECTED = "credential_injected"
    CREDENTIAL_REJECTED = "credential_rejected"
    
    # Sandbox lifecycle events
    SANDBOX_STARTED = "sandbox_started"
    SANDBOX_STOPPED = "sandbox_stopped"
    SANDBOX_ERROR = "sandbox_error"
    
    # Health monitoring events
    HEALTH_CHECK_PASSED = "health_check_passed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    HEALTH_CHECK_DEGRADED = "health_check_degraded"
    
    # Generic security events
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"


@dataclass
class SecurityEvent:
    """A security-relevant event for audit logging.
    
    Attributes:
        timestamp: ISO 8601 timestamp of the event.
        event_type: Type of security event.
        source: Source component that generated the event.
        details: Additional event-specific details.
        blocked: Whether the event represented a blocked action.
    """
    timestamp: str
    event_type: str
    source: str
    details: dict
    blocked: bool = False

    def to_json(self) -> str:
        """Serialize to JSON string for logging.
        
        Returns:
            JSON string representation of the event.
        """
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "SecurityEvent":
        """Create a SecurityEvent from a dictionary.
        
        Args:
            data: Dictionary containing event data.
            
        Returns:
            SecurityEvent instance.
        """
        return cls(
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            event_type=data["event_type"],
            source=data["source"],
            details=data.get("details", {}),
            blocked=data.get("blocked", False),
        )


class SecurityEventLogger:
    """Logs security events for auditing and monitoring.
    
    All events are logged as structured JSON for machine parsing,
    enabling integration with SIEM systems and log aggregators.
    """

    def __init__(self, source: str = "anytype-agent"):
        """Initialize the security event logger.
        
        Args:
            source: Source identifier for events (default: "anytype-agent").
        """
        self.source = source
        self._audit_logger = logging.getLogger("security.audit")

    def log(
        self,
        event_type: SecurityEventType,
        details: Optional[dict] = None,
        blocked: bool = False,
    ) -> None:
        """Log a security event.
        
        Args:
            event_type: Type of security event.
            details: Additional event details (optional).
            blocked: Whether the event represented a blocked action (default: False).
        """
        event = SecurityEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type.value,
            source=self.source,
            details=details or {},
            blocked=blocked,
        )
        
        # Log as structured JSON for machine parsing
        self._audit_logger.info(event.to_json())
        
        # Also log human-readable version for debugging
        logger.debug(
            f"Security event: {event_type.value} "
            f"(blocked={blocked}, details={event.details})"
        )

    def log_policy_applied(self, policy_name: str, success: bool = True) -> None:
        """Log that a policy was applied.
        
        Args:
            policy_name: Name of the applied policy.
            success: Whether the policy was applied successfully.
        """
        event_type = (
            SecurityEventType.POLICY_APPLIED if success 
            else SecurityEventType.POLICY_REJECTED
        )
        self.log(event_type, {"policy": policy_name, "success": success})

    def log_network_blocked(self, destination: str, reason: str = "") -> None:
        """Log a blocked network attempt.
        
        Args:
            destination: The blocked destination (URL/host).
            reason: Reason for the block (optional).
        """
        self.log(
            SecurityEventType.NETWORK_BLOCKED,
            {"destination": destination, "reason": reason},
            blocked=True,
        )

    def log_filesystem_blocked(self, path: str, reason: str = "") -> None:
        """Log a blocked filesystem access attempt.
        
        Args:
            path: The blocked path.
            reason: Reason for the block (optional).
        """
        self.log(
            SecurityEventType.FILESYSTEM_BLOCKED,
            {"path": path, "reason": reason},
            blocked=True,
        )

    def log_process_blocked(self, operation: str, reason: str = "") -> None:
        """Log a blocked process operation.
        
        Args:
            operation: The blocked operation (e.g., "user_namespace", "mount").
            reason: Reason for the block (optional).
        """
        self.log(
            SecurityEventType.PROCESS_BLOCKED,
            {"operation": operation, "reason": reason},
            blocked=True,
        )

    def log_sandbox_started(self, sandbox_name: str) -> None:
        """Log sandbox startup.
        
        Args:
            sandbox_name: Name of the started sandbox.
        """
        self.log(
            SecurityEventType.SANDBOX_STARTED,
            {"sandbox_name": sandbox_name},
        )

    def log_sandbox_stopped(self, sandbox_name: str) -> None:
        """Log sandbox shutdown.
        
        Args:
            sandbox_name: Name of the stopped sandbox.
        """
        self.log(
            SecurityEventType.SANDBOX_STOPPED,
            {"sandbox_name": sandbox_name},
        )

    def log_health_check(
        self, 
        status: str, 
        message: str,
        details: Optional[dict] = None
    ) -> None:
        """Log health check result.
        
        Args:
            status: Health status ("healthy", "degraded", "unhealthy").
            message: Human-readable message.
            details: Check details (optional).
        """
        status_map = {
            "healthy": SecurityEventType.HEALTH_CHECK_PASSED,
            "degraded": SecurityEventType.HEALTH_CHECK_DEGRADED,
            "unhealthy": SecurityEventType.HEALTH_CHECK_FAILED,
        }
        
        event_type = status_map.get(status, SecurityEventType.HEALTH_CHECK_FAILED)
        
        self.log(
            event_type,
            {
                "status": status,
                "message": message,
                "checks": details or {},
            },
            blocked=status != "healthy",
        )

    def log_credential_injected(self, credential_type: str) -> None:
        """Log credential injection.
        
        Args:
            credential_type: Type of credential injected.
        """
        self.log(
            SecurityEventType.CREDENTIAL_INJECTED,
            {"credential_type": credential_type},
        )

    def log_unauthorized_access(self, resource: str, reason: str = "") -> None:
        """Log unauthorized access attempt.
        
        Args:
            resource: The accessed resource.
            reason: Reason for rejection (optional).
        """
        self.log(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            {"resource": resource, "reason": reason},
            blocked=True,
        )


# Singleton instance
_event_logger: Optional[SecurityEventLogger] = None


def get_security_logger() -> SecurityEventLogger:
    """Get singleton security logger instance.
    
    Returns:
        SecurityEventLogger singleton.
    """
    global _event_logger
    if _event_logger is None:
        _event_logger = SecurityEventLogger()
    return _event_logger