"""Tests for src/llm/ module."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.llm.base import (
    BaseLLMProvider,
    LLMResponse,
    LLMConfig,
    ProviderType,
)
from src.llm.providers import OpenAIProvider, AnthropicProvider, OllamaProvider
from src.llm.router import LLMRouter, ModelRoute, get_router, _setup_default_routes


class TestProviderType:
    """Tests for ProviderType enum."""

    def test_values(self):
        assert ProviderType.OPENAI.value == "openai"
        assert ProviderType.ANTHROPIC.value == "anthropic"
        assert ProviderType.OLLAMA.value == "ollama"
        assert ProviderType.GROQ.value == "groq"
        assert ProviderType.AZURE.value == "azure"


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_defaults(self):
        cfg = LLMConfig(provider=ProviderType.OPENAI, model="gpt-4")
        assert cfg.timeout == 30.0
        assert cfg.temperature == 0.7
        assert cfg.max_tokens is None
        assert cfg.api_key is None
        assert cfg.base_url is None

    def test_custom_values(self):
        cfg = LLMConfig(
            provider=ProviderType.ANTHROPIC,
            model="claude-3",
            api_key="key",
            temperature=0.5,
            max_tokens=100,
        )
        assert cfg.api_key == "key"
        assert cfg.temperature == 0.5
        assert cfg.max_tokens == 100


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_defaults(self):
        resp = LLMResponse(
            content="hello",
            model="gpt-4",
            provider=ProviderType.OPENAI,
        )
        assert resp.content == "hello"
        assert resp.usage == {}
        assert resp.raw_response is None
        assert resp.finish_reason is None


class TestBaseLLMProvider:
    """Tests for BaseLLMProvider abstract class."""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseLLMProvider(LLMConfig(provider=ProviderType.OPENAI, model="gpt-4"))


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    @pytest.mark.asyncio
    async def test_complete(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
        mock_response.model = "gpt-4"
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_response.model_dump = MagicMock(return_value={"mock": True})
        mock_response.choices[0].finish_reason = "stop"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            provider = OpenAIProvider(
                LLMConfig(provider=ProviderType.OPENAI, model="gpt-4", api_key="test-key")
            )
            result = await provider.complete([{"role": "user", "content": "hi"}])

        assert result.content == "Hello"
        assert result.model == "gpt-4"
        assert result.provider == ProviderType.OPENAI
        assert result.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_stream(self):
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content="chunk"))]

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = MagicMock(return_value=iter([chunk]))

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            provider = OpenAIProvider(
                LLMConfig(provider=ProviderType.OPENAI, model="gpt-4")
            )
            chunks = []
            async for c in provider.stream([{"role": "user", "content": "hi"}]):
                chunks.append(c)

        assert chunks == ["chunk"]

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        mock_client = MagicMock()
        mock_client.models.list = AsyncMock()

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            provider = OpenAIProvider(
                LLMConfig(provider=ProviderType.OPENAI, model="gpt-4")
            )
            assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        mock_client = MagicMock()
        mock_client.models.list = AsyncMock(side_effect=Exception("API error"))

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client):
            provider = OpenAIProvider(
                LLMConfig(provider=ProviderType.OPENAI, model="gpt-4")
            )
            assert await provider.health_check() is False


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    @pytest.mark.asyncio
    async def test_complete(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello from Claude")]
        mock_response.model = "claude-3"
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.stop_reason = "end_turn"

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.llm.providers.AsyncAnthropic", return_value=mock_client):
            provider = AnthropicProvider(
                LLMConfig(provider=ProviderType.ANTHROPIC, model="claude-3", api_key="key")
            )
            result = await provider.complete([
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ])

        assert result.content == "Hello from Claude"
        assert result.provider == ProviderType.ANTHROPIC

    @pytest.mark.asyncio
    async def test_complete_no_system(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hi")]
        mock_response.model = "claude-3"
        mock_response.usage = MagicMock(input_tokens=5, output_tokens=2)
        mock_response.stop_reason = "end_turn"

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.llm.providers.AsyncAnthropic", return_value=mock_client):
            provider = AnthropicProvider(
                LLMConfig(provider=ProviderType.ANTHROPIC, model="claude-3")
            )
            result = await provider.complete([{"role": "user", "content": "hi"}])

        assert result.content == "Hi"

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        mock_client = MagicMock()
        mock_client.messages.list = AsyncMock()

        with patch("src.llm.providers.AsyncAnthropic", return_value=mock_client):
            provider = AnthropicProvider(
                LLMConfig(provider=ProviderType.ANTHROPIC, model="claude-3")
            )
            assert await provider.health_check() is True


class TestOllamaProvider:
    """Tests for OllamaProvider."""

    @pytest.mark.asyncio
    async def test_complete(self):
        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=AsyncMock(return_value={
                "message": {"content": "Local model response"},
                "model": "llama2",
                "prompt_eval_count": 10,
                "eval_count": 5,
                "done_reason": "stop",
            }),
        ))
        mock_post.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.post = MagicMock(return_value=mock_post)

        with patch("src.llm.providers.httpx.AsyncClient", return_value=mock_client):
            provider = OllamaProvider(
                LLMConfig(provider=ProviderType.OLLAMA, model="llama2")
            )
            result = await provider.complete([{"role": "user", "content": "hi"}])

        assert result.content == "Local model response"
        assert result.provider == ProviderType.OLLAMA

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        mock_get = AsyncMock()
        mock_get.__aenter__ = AsyncMock(return_value=MagicMock(
            status_code=200,
        ))
        mock_get.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.get = MagicMock(return_value=mock_get)

        with patch("src.llm.providers.httpx.AsyncClient", return_value=mock_client):
            provider = OllamaProvider(
                LLMConfig(provider=ProviderType.OLLAMA, model="llama2")
            )
            assert await provider.health_check() is True


class TestLLMRouter:
    """Tests for LLMRouter."""

    def test_register_route(self):
        router = LLMRouter()
        router.register_route(
            "agent",
            LLMConfig(provider=ProviderType.OPENAI, model="gpt-4", api_key="key"),
            use_cases=["agent"],
        )
        assert "agent" in router._routes

    def test_set_default(self):
        router = LLMRouter()
        router.register_route(
            "agent",
            LLMConfig(provider=ProviderType.OPENAI, model="gpt-4"),
            use_cases=["agent"],
        )
        router.set_default("agent")
        assert router._default_route == "agent"

    def test_set_default_unknown(self):
        router = LLMRouter()
        with pytest.raises(ValueError, match="Unknown route"):
            router.set_default("missing")

    def test_get_route_by_use_case(self):
        router = LLMRouter()
        router.register_route(
            "guardrail",
            LLMConfig(provider=ProviderType.OPENAI, model="gpt-4o-mini"),
            use_cases=["guardrail"],
        )
        provider = router.get_route("guardrail")
        assert provider is not None

    def test_get_route_fallback_default(self):
        router = LLMRouter()
        router.register_route(
            "agent",
            LLMConfig(provider=ProviderType.OPENAI, model="gpt-4"),
            use_cases=["agent"],
        )
        router.set_default("agent")
        provider = router.get_route("unknown_use_case")
        assert provider is not None

    def test_get_route_no_match(self):
        router = LLMRouter()
        with pytest.raises(ValueError, match="No default route"):
            router.get_route()

    def test_unknown_provider(self):
        router = LLMRouter()
        with pytest.raises(ValueError, match="Unknown provider"):
            router.register_route(
                "bad",
                LLMConfig(provider=ProviderType.GROQ, model="x"),
                use_cases=["x"],
            )


class TestGetRouter:
    """Tests for get_router singleton."""

    def test_returns_same_instance(self):
        import src.llm.router as rt
        rt._router = None
        with patch("src.llm.router._setup_default_routes"):
            r1 = get_router()
            r2 = get_router()
            assert r1 is r2
        rt._router = None


class TestSetupDefaultRoutes:
    """Tests for _setup_default_routes."""

    def test_openai_default(self):
        settings = MagicMock(
            default_provider="openai",
            model="gpt-4o",
            guardrail_model="gpt-4o-mini",
            openai_api_key="key",
            anthropic_api_key=None,
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        assert "agent" in router._routes
        assert "guardrail" in router._routes
        # Guardrail always uses OpenAI
        assert router._routes["guardrail"].provider.config.provider == ProviderType.OPENAI

    def test_anthropic_provider(self):
        settings = MagicMock(
            default_provider="anthropic",
            model="claude-3",
            guardrail_model="gpt-4o-mini",
            openai_api_key="openai-key",
            anthropic_api_key="anthro-key",
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        assert router._routes["agent"].provider.config.provider == ProviderType.ANTHROPIC
        assert router._routes["agent"].provider.config.api_key == "anthro-key"

    def test_ollama_provider(self):
        settings = MagicMock(
            default_provider="ollama",
            model="llama2",
            guardrail_model="gpt-4o-mini",
            openai_api_key="openai-key",
            anthropic_api_key=None,
            ollama_base_url="http://ollama:11434",
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        assert router._routes["agent"].provider.config.provider == ProviderType.OLLAMA
        assert router._routes["agent"].provider.config.base_url == "http://ollama:11434"
        assert router._routes["agent"].provider.config.api_key is None

    def test_invalid_provider_defaults_to_openai(self):
        settings = MagicMock(
            default_provider="invalid_provider",
            model="gpt-4",
            guardrail_model="gpt-4o-mini",
            openai_api_key="key",
            anthropic_api_key=None,
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        assert router._routes["agent"].provider.config.provider == ProviderType.OPENAI
