"""Base tool class with safety checks."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx

from ...config import get_settings


class BaseTool(ABC):
    """Base class for all Anytype tools."""

    name: str = ""
    description: str = ""
    required_params: list[str] = []

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.settings.anytype_base_url,
                headers={
                    "Authorization": f"Bearer {self.settings.anytype_api_key}",
                    "X-API-Version": self.settings.anytype_api_version,
                },
                timeout=30.0,
            )
        return self.client

    async def _close_client(self) -> None:
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None

    def validate_params(self, **params) -> None:
        """Validate required parameters.

        Args:
            **params: Parameters to validate

        Raises:
            ValueError: If required parameters are missing.
        """
        missing = [p for p in self.required_params if p not in params]
        if missing:
            raise ValueError(f"Missing required params: {missing}")

    @abstractmethod
    async def execute(self, **params) -> Dict[str, Any]:
        """Execute the tool.

        Args:
            **params: Tool parameters

        Returns:
            Tool result as dictionary
        """
        pass

    async def execute_with_validation(self, **params) -> Dict[str, Any]:
        """Execute with parameter validation.

        Args:
            **params: Tool parameters

        Returns:
            Tool result or error dict
        """
        try:
            self.validate_params(**params)
        except ValueError as e:
            return {"success": False, "error": str(e), "tool": self.name}

        try:
            return await self.execute(**params)
        finally:
            await self._close_client()

    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for this tool's parameters."""
        return {
            "name": self.name,
            "description": self.description,
            "required_params": self.required_params,
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }


class ToolResult:
    """Standardized tool result."""

    def __init__(
        self,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.data = data or {}
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        if self.success:
            return self.data
        return {"error": self.error}
