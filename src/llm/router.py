"""LLM router for multi-model routing."""
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..config import get_settings
from .base import BaseLLMProvider, LLMConfig, ProviderType
from .providers import AnthropicProvider, OllamaProvider, OpenAICodexProvider, OpenAIProvider


@dataclass
class ModelRoute:
    """Route configuration for a model."""

    name: str
    provider: BaseLLMProvider
    use_cases: List[str]


class LLMRouter:
    """Routes LLM requests to appropriate provider/model."""

    def __init__(self):
        self._routes: Dict[str, ModelRoute] = {}
        self._default_route: Optional[str] = None

    def register_route(
        self,
        route_name: str,
        config: LLMConfig,
        use_cases: List[str],
    ) -> None:
        """Register a model route.

        Args:
            route_name: Unique name for this route
            config: LLM configuration
            use_cases: List of use cases this model is good for
        """
        provider = self._create_provider(config)
        self._routes[route_name] = ModelRoute(
            name=route_name,
            provider=provider,
            use_cases=use_cases,
        )

    def set_default(self, route_name: str) -> None:
        """Set default route for unclassified requests."""
        if route_name not in self._routes:
            raise ValueError(f"Unknown route: {route_name}")
        self._default_route = route_name

    def get_route(self, use_case: Optional[str] = None) -> BaseLLMProvider:
        """Get provider for use case.

        Args:
            use_case: Specific use case (e.g., "guardrail", "agent")

        Returns:
            Configured provider
        """
        if use_case:
            for route in self._routes.values():
                if use_case in route.use_cases:
                    return route.provider

        if self._default_route:
            return self._routes[self._default_route].provider

        raise ValueError("No default route configured")

    def _create_provider(self, config: LLMConfig) -> BaseLLMProvider:
        """Factory to create provider from config."""
        providers = {
            ProviderType.OPENAI: OpenAIProvider,
            ProviderType.OPENAI_CODEX: OpenAICodexProvider,
            ProviderType.ANTHROPIC: AnthropicProvider,
            ProviderType.OLLAMA: OllamaProvider,
        }

        provider_class = providers.get(config.provider)
        if not provider_class:
            raise ValueError(f"Unknown provider: {config.provider}")

        return provider_class(config)


# Global router instance
_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """Get global LLM router.

    Returns a pre-configured router with default routes:
    - "agent": Main agent model
    - "guardrail": Guardrail model
    """
    global _router
    if _router is None:
        _router = LLMRouter()
        _setup_default_routes(_router)
    return _router


def _provider_type(provider: Optional[str]) -> ProviderType:
    """Map provider name to ProviderType, defaulting to OpenAI-compatible."""
    provider_map = {
        "openai": ProviderType.OPENAI,
        "openai-compatible": ProviderType.OPENAI,
        "openai-codex": ProviderType.OPENAI_CODEX,
        "anthropic": ProviderType.ANTHROPIC,
        "ollama": ProviderType.OLLAMA,
    }
    return provider_map.get((provider or "openai").lower(), ProviderType.OPENAI)


def _api_key_for_provider(provider: ProviderType, settings, explicit_key: Optional[str]) -> Optional[str]:
    """Resolve API key from generic config first, then legacy provider keys."""
    if provider in (ProviderType.OLLAMA, ProviderType.OPENAI_CODEX):
        return None
    if explicit_key:
        return explicit_key
    if provider == ProviderType.ANTHROPIC:
        return settings.anthropic_api_key
    return settings.openai_api_key


def _base_url_for_provider(provider: ProviderType, settings, explicit_base_url: Optional[str]) -> Optional[str]:
    """Resolve base URL from generic config first, then legacy provider URLs."""
    if explicit_base_url:
        return explicit_base_url
    if provider == ProviderType.OPENAI_CODEX:
        return settings.codex_base_url
    if provider == ProviderType.OLLAMA:
        return settings.ollama_base_url
    return None


def _setup_default_routes(router: LLMRouter) -> None:
    """Setup default routes from generic and legacy environment/config.

    New deployments should use LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY,
    LLM_MODEL and optional GUARDRAIL_LLM_* overrides. Legacy DEFAULT_PROVIDER,
    MODEL, OPENAI_API_KEY, ANTHROPIC_API_KEY, and OLLAMA_BASE_URL remain
    supported where practical.
    """
    settings = get_settings()

    default_provider = _provider_type(settings.llm_provider)
    api_key = _api_key_for_provider(default_provider, settings, settings.llm_api_key)
    base_url = _base_url_for_provider(default_provider, settings, settings.llm_base_url)

    router.register_route(
        "agent",
        LLMConfig(
            provider=default_provider,
            model=settings.llm_model,
            api_key=api_key,
            base_url=base_url,
            extra_params=(
                {
                    "codex_auth_file": settings.codex_auth_file,
                    "codex_token_command": settings.codex_token_command,
                    "codex_base_url": settings.codex_base_url,
                    "codex_auth_issuer": settings.codex_auth_issuer,
                    "codex_client_id": settings.codex_client_id,
                    "codex_refresh_skew_seconds": settings.codex_refresh_skew_seconds,
                }
                if default_provider == ProviderType.OPENAI_CODEX
                else {}
            ),
        ),
        use_cases=["agent", "intent", "response"],
    )

    guardrail_provider = _provider_type(settings.guardrail_llm_provider or settings.llm_provider)
    guardrail_key = _api_key_for_provider(
        guardrail_provider,
        settings,
        settings.guardrail_llm_api_key or settings.llm_api_key,
    )
    guardrail_base_url = _base_url_for_provider(
        guardrail_provider,
        settings,
        settings.guardrail_llm_base_url or settings.llm_base_url,
    )

    router.register_route(
        "guardrail",
        LLMConfig(
            provider=guardrail_provider,
            model=settings.guardrail_model or settings.llm_model,
            api_key=guardrail_key,
            base_url=guardrail_base_url,
            extra_params=(
                {
                    "codex_auth_file": settings.codex_auth_file,
                    "codex_token_command": settings.codex_token_command,
                    "codex_base_url": settings.codex_base_url,
                    "codex_auth_issuer": settings.codex_auth_issuer,
                    "codex_client_id": settings.codex_client_id,
                    "codex_refresh_skew_seconds": settings.codex_refresh_skew_seconds,
                }
                if guardrail_provider == ProviderType.OPENAI_CODEX
                else {}
            ),
        ),
        use_cases=["guardrail", "input_check", "output_check"],
    )
    router.set_default("agent")
