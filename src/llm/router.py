"""LLM router for multi-model routing."""
from typing import Optional, Dict, List
from dataclasses import dataclass

from .base import BaseLLMProvider, LLMConfig, ProviderType


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
    - "agent": Main agent model (OpenAI)
    - "guardrail": Guardrail model (OpenAI mini)

    Usage:
        from src.llm import get_router

        router = get_router()
        provider = router.get_route("agent")  # or router.get_route("guardrail")
        response = await provider.complete(messages)
    """
    global _router
    if _router is None:
        _router = LLMRouter()
        _setup_default_routes(_router)
    return _router


def _setup_default_routes(router: LLMRouter) -> None:
    """Setup default routes from environment/config.
    
    Respects ``settings.default_provider`` to choose the primary LLM provider.
    Currently supports: openai, anthropic, ollama.
    """
    from ..config import get_settings
    settings = get_settings()

    provider_map = {
        "openai": ProviderType.OPENAI,
        "anthropic": ProviderType.ANTHROPIC,
        "ollama": ProviderType.OLLAMA,
    }
    default_provider = provider_map.get(
        settings.default_provider.lower(),
        ProviderType.OPENAI,
    )

    # Determine the right API key / base_url for the chosen provider
    if default_provider == ProviderType.OPENAI:
        api_key = settings.openai_api_key
        base_url = None
    elif default_provider == ProviderType.ANTHROPIC:
        api_key = settings.anthropic_api_key or settings.openai_api_key
        base_url = None
    elif default_provider == ProviderType.OLLAMA:
        api_key = None
        base_url = settings.ollama_base_url
    else:
        api_key = settings.openai_api_key
        base_url = None

    # Main agent model (expensive)
    router.register_route(
        "agent",
        LLMConfig(
            provider=default_provider,
            model=settings.model,
            api_key=api_key,
            base_url=base_url,
        ),
        use_cases=["agent", "intent", "response"],
    )

    # Guardrail model (cheap/fast) – always use OpenAI for reliability
    router.register_route(
        "guardrail",
        LLMConfig(
            provider=ProviderType.OPENAI,
            model=settings.guardrail_model,
            api_key=settings.openai_api_key,
        ),
        use_cases=["guardrail", "input_check", "output_check"],
    )


# Import providers for factory
from .providers import OpenAIProvider, AnthropicProvider, OllamaProvider