"""Base LLM provider interface.

Provides abstraction layer for multiple LLM providers,
enabling provider portability and multi-model routing.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum


class ProviderType(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    OPENAI_CODEX = "openai-codex"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    GROQ = "groq"
    AZURE = "azure"


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    model: str
    provider: ProviderType
    usage: Dict[str, int] = field(default_factory=dict)
    raw_response: Optional[dict] = None
    finish_reason: Optional[str] = None


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: ProviderType
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 30.0
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        """Generate completion from messages.

        Args:
            messages: List of message dicts with role/content

        Returns:
            LLMResponse with standardized response
        """
        pass

    @abstractmethod
    async def stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """Stream completion from messages.

        Args:
            messages: List of message dicts with role/content

        Yields:
            Text chunks as they are generated
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is accessible.

        Returns:
            True if provider is healthy
        """
        pass