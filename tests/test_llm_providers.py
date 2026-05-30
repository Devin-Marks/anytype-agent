"""Tests for src/llm/ module."""
import base64
import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.llm.base import (
    BaseLLMProvider,
    LLMResponse,
    LLMConfig,
    ProviderType,
)
from src.llm.providers import (
    AnthropicProvider,
    CodexAuthError,
    OpenAICodexProvider,
    OpenAIProvider,
    OllamaProvider,
    _parse_expiry,
)
from src.llm.router import LLMRouter, get_router, _setup_default_routes


def _jwt_with_exp(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


class TestProviderType:
    """Tests for ProviderType enum."""

    def test_values(self):
        assert ProviderType.OPENAI.value == "openai"
        assert ProviderType.OPENAI_CODEX.value == "openai-codex"
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

        with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client) as mock_openai:
            provider = OpenAIProvider(
                LLMConfig(provider=ProviderType.OPENAI, model="gpt-4", api_key="test-key")
            )
            result = await provider.complete([{"role": "user", "content": "hi"}])

        mock_openai.assert_called_once_with(api_key="test-key", base_url=None)
        assert result.content == "Hello"
        assert result.model == "gpt-4"
        assert result.provider == ProviderType.OPENAI
        assert result.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_local_openai_compatible_endpoint_can_be_keyless(self):
        mock_client = MagicMock()
        mock_client.models.list = AsyncMock()

        with patch.dict("os.environ", {}, clear=True):
            with patch("src.llm.providers.AsyncOpenAI", return_value=mock_client) as mock_openai:
                provider = OpenAIProvider(
                    LLMConfig(
                        provider=ProviderType.OPENAI,
                        model="local-model",
                        base_url="http://vllm:8000/v1",
                    )
                )
                assert await provider.health_check() is True

        mock_openai.assert_called_once_with(
            api_key="not-needed",
            base_url="http://vllm:8000/v1",
        )

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


class TestOpenAICodexProvider:
    """Tests for OpenAICodexProvider."""

    @pytest.mark.asyncio
    async def test_reads_token_from_auth_file(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text('{"tokens":{"access_token":"codex-token"}}')
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        assert await provider._bearer_token() == "codex-token"

    @pytest.mark.asyncio
    async def test_missing_auth_file_error(self, tmp_path):
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(tmp_path / "missing.json")},
            )
        )

        with pytest.raises(CodexAuthError, match="Codex auth file not found"):
            await provider._bearer_token()

    @pytest.mark.asyncio
    async def test_malformed_auth_file_error(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text("not json")
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        with pytest.raises(CodexAuthError, match="malformed JSON"):
            await provider._bearer_token()

    @pytest.mark.asyncio
    async def test_missing_token_error(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text('{"tokens":{"refresh_token":"refresh-only"}}')
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        with pytest.raises(CodexAuthError, match="does not contain an access token"):
            await provider._bearer_token()

    @pytest.mark.asyncio
    async def test_ignores_generic_token_field(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text('{"tokens":{"token":"generic-secret"}}')
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        with pytest.raises(CodexAuthError, match="does not contain an access token"):
            await provider._bearer_token()

    @pytest.mark.asyncio
    async def test_reads_realistic_nested_access_token(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            '{"accounts":{"chatgpt":{"tokens":{'
            '"accessToken":"nested-token","expiresAt":"2999-01-01T00:00:00Z"}}}}'
        )
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        assert await provider._bearer_token() == "nested-token"

    def test_parse_expiry_treats_naive_iso_as_utc(self):
        expiry = _parse_expiry("2999-01-01T00:00:00")

        assert expiry is not None
        assert expiry.tzinfo is not None
        assert expiry.isoformat() == "2999-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_expired_token_error(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text('{"tokens":{"access_token":"old","expires_at":"2000-01-01T00:00:00Z"}}')
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        with pytest.raises(CodexAuthError, match="expired or near expiry"):
            await provider._bearer_token()

    @pytest.mark.asyncio
    async def test_expired_token_refresh_success(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {
                        "access_token": "old-access",
                        "refresh_token": "old-refresh",
                        "account_id": "acct",
                        "expires_at": "2000-01-01T00:00:00Z",
                    },
                    "other": {"preserved": True},
                }
            )
        )
        captured = {}

        class MockResponse:
            status_code = 200

            def json(self):
                return {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}

        class MockClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, headers, json):
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json
                return MockResponse()

        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        with patch("src.llm.providers.httpx.AsyncClient", MockClient):
            assert await provider._bearer_token() == "new-access"

        saved = json.loads(auth_file.read_text())
        assert saved["tokens"]["access_token"] == "new-access"
        assert saved["tokens"]["refresh_token"] == "new-refresh"
        assert saved["tokens"]["account_id"] == "acct"
        assert saved["other"] == {"preserved": True}
        assert saved["last_refresh"]
        assert oct(auth_file.stat().st_mode & 0o777) == "0o600"
        assert captured["url"] == "https://auth.openai.com/oauth/token"
        assert captured["headers"] == {"Content-Type": "application/json"}
        assert captured["json"] == {
            "grant_type": "refresh_token",
            "refresh_token": "old-refresh",
            "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        }

    @pytest.mark.asyncio
    async def test_near_expiry_token_refreshes(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps(
                {
                    "tokens": {
                        "access_token": _jwt_with_exp(4102444800),
                        "refresh_token": "refresh",
                        "expires_at": "2999-01-01T00:03:00Z",
                    }
                }
            )
        )

        class MockResponse:
            status_code = 200

            def json(self):
                return {"access_token": "near-new"}

        class MockClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, *args, **kwargs):
                return MockResponse()

        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file), "codex_refresh_skew_seconds": 40000000000},
            )
        )

        with patch("src.llm.providers.httpx.AsyncClient", MockClient):
            assert await provider._bearer_token() == "near-new"

    @pytest.mark.asyncio
    async def test_refresh_failure_does_not_leak_tokens(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            '{"tokens":{"access_token":"old-secret","refresh_token":"refresh-secret","expires_at":"2000-01-01T00:00:00Z"}}'
        )

        class MockResponse:
            status_code = 401
            text = '{"error":"refresh-secret"}'

            def json(self):
                return {"error": "refresh-secret"}

        class MockClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, *args, **kwargs):
                return MockResponse()

        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        with patch("src.llm.providers.httpx.AsyncClient", MockClient), pytest.raises(CodexAuthError) as exc_info:
            await provider._bearer_token()

        message = str(exc_info.value)
        assert "HTTP 401" in message
        assert "old-secret" not in message
        assert "refresh-secret" not in message

    @pytest.mark.asyncio
    async def test_read_only_auth_directory_error_mentions_writable_volume(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            '{"tokens":{"access_token":"old","refresh_token":"refresh","expires_at":"2000-01-01T00:00:00Z"}}'
        )

        class MockResponse:
            status_code = 200

            def json(self):
                return {"access_token": "new"}

        class MockClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, *args, **kwargs):
                return MockResponse()

        def raise_read_only(*args, **kwargs):
            raise PermissionError("read-only file system")

        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        with (
            patch("src.llm.providers.httpx.AsyncClient", MockClient),
            patch("src.llm.providers.tempfile.mkstemp", raise_read_only),
            pytest.raises(CodexAuthError) as exc_info,
        ):
            await provider._bearer_token()
        assert "writable volume" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_command_takes_precedence(self, tmp_path):
        missing_auth = tmp_path / "missing.json"
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={
                    "codex_auth_file": str(missing_auth),
                    "codex_token_command": "printf command-token",
                },
            )
        )

        assert await provider._bearer_token() == "command-token"

    @pytest.mark.asyncio
    async def test_token_command_does_not_use_shell(self, tmp_path):
        marker = tmp_path / "shell-injection-marker"
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_token_command": f"printf safe-token; touch {marker}"},
            )
        )

        assert await provider._bearer_token() == "safe-token;"
        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_token_command_error_does_not_echo_stderr_secret(self):
        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                extra_params={"codex_token_command": "sh -c 'echo secret-token >&2; exit 2'"},
            )
        )

        with pytest.raises(CodexAuthError) as exc_info:
            await provider._bearer_token()

        message = str(exc_info.value)
        assert "exit code 2" in message
        assert "wrote to stderr" in message
        assert "secret-token" not in message

    @pytest.mark.asyncio
    async def test_complete_request_format_and_headers(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text('{"access_token":"codex-token"}')
        captured = {}

        class MockResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"output_text": "Hello", "model": "gpt-5-codex", "usage": {"total_tokens": 3}}

        class MockClient:
            def __init__(self, *args, **kwargs):
                captured["client_kwargs"] = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, headers, json):
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json
                return MockResponse()

        provider = OpenAICodexProvider(
            LLMConfig(
                provider=ProviderType.OPENAI_CODEX,
                model="gpt-5-codex",
                base_url="https://codex.example/responses",
                extra_params={"codex_auth_file": str(auth_file)},
            )
        )

        with patch("src.llm.providers.httpx.AsyncClient", MockClient):
            result = await provider.complete([{"role": "user", "content": "hi"}])

        assert captured["url"] == "https://codex.example/responses"
        assert captured["headers"]["Authorization"] == "Bearer codex-token"
        assert captured["json"] == {
            "model": "gpt-5-codex",
            "input": [{"role": "user", "content": "hi"}],
            "stream": False,
        }
        assert result.content == "Hello"
        assert result.provider == ProviderType.OPENAI_CODEX
        assert result.usage["total_tokens"] == 3


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

    def test_generic_openai_compatible_endpoint(self):
        settings = MagicMock(
            llm_provider="openai",
            llm_base_url="https://llm.example/v1",
            llm_api_key="generic-key",
            llm_model="custom-model",
            guardrail_llm_provider=None,
            guardrail_llm_base_url=None,
            guardrail_llm_api_key=None,
            guardrail_model="guard-model",
            openai_api_key=None,
            anthropic_api_key=None,
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        agent = router._routes["agent"].provider.config
        guardrail = router._routes["guardrail"].provider.config
        assert agent.provider == ProviderType.OPENAI
        assert agent.base_url == "https://llm.example/v1"
        assert agent.api_key == "generic-key"
        assert agent.model == "custom-model"
        assert guardrail.provider == ProviderType.OPENAI
        assert guardrail.base_url == "https://llm.example/v1"
        assert guardrail.api_key == "generic-key"
        assert guardrail.model == "guard-model"

    def test_openai_codex_provider_selection(self):
        settings = MagicMock(
            llm_provider="openai-codex",
            llm_base_url=None,
            llm_api_key="ignored-platform-key",
            llm_model="gpt-5-codex",
            guardrail_llm_provider=None,
            guardrail_llm_base_url=None,
            guardrail_llm_api_key=None,
            guardrail_model="gpt-5-codex",
            openai_api_key="legacy-openai",
            anthropic_api_key=None,
            ollama_base_url=None,
            codex_auth_file="/var/lib/anytype-agent/codex/auth.json",
            codex_token_command="print-token",
            codex_base_url="https://codex.example/responses",
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        agent = router._routes["agent"].provider.config
        assert agent.provider == ProviderType.OPENAI_CODEX
        assert agent.api_key is None
        assert agent.base_url == "https://codex.example/responses"
        assert agent.extra_params["codex_auth_file"] == "/var/lib/anytype-agent/codex/auth.json"
        assert agent.extra_params["codex_token_command"] == "print-token"

    def test_guardrail_generic_override(self):
        settings = MagicMock(
            llm_provider="ollama",
            llm_base_url="http://ollama:11434",
            llm_api_key=None,
            llm_model="llama3",
            guardrail_llm_provider="openai",
            guardrail_llm_base_url="https://guard.example/v1",
            guardrail_llm_api_key="guard-key",
            guardrail_model="guard-model",
            openai_api_key=None,
            anthropic_api_key=None,
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        agent = router._routes["agent"].provider.config
        guardrail = router._routes["guardrail"].provider.config
        assert agent.provider == ProviderType.OLLAMA
        assert agent.api_key is None
        assert guardrail.provider == ProviderType.OPENAI
        assert guardrail.base_url == "https://guard.example/v1"
        assert guardrail.api_key == "guard-key"

    def test_anthropic_provider_uses_generic_key(self):
        settings = MagicMock(
            llm_provider="anthropic",
            llm_base_url=None,
            llm_api_key="generic-anthro",
            llm_model="claude-3",
            guardrail_llm_provider=None,
            guardrail_llm_base_url=None,
            guardrail_llm_api_key=None,
            guardrail_model="claude-3-haiku",
            openai_api_key=None,
            anthropic_api_key="legacy-anthro",
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        assert router._routes["agent"].provider.config.provider == ProviderType.ANTHROPIC
        assert router._routes["agent"].provider.config.api_key == "generic-anthro"

    def test_ollama_provider_does_not_require_openai_key(self):
        settings = MagicMock(
            llm_provider="ollama",
            llm_base_url="http://ollama:11434",
            llm_api_key=None,
            llm_model="llama2",
            guardrail_llm_provider=None,
            guardrail_llm_base_url=None,
            guardrail_llm_api_key=None,
            guardrail_model="llama2",
            openai_api_key=None,
            anthropic_api_key=None,
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        assert router._routes["agent"].provider.config.provider == ProviderType.OLLAMA
        assert router._routes["agent"].provider.config.base_url == "http://ollama:11434"
        assert router._routes["agent"].provider.config.api_key is None

    def test_guardrail_model_falls_back_to_llm_model(self):
        settings = MagicMock(
            llm_provider="ollama",
            llm_base_url="http://ollama:11434",
            llm_api_key=None,
            llm_model="llama3",
            guardrail_llm_provider=None,
            guardrail_llm_base_url=None,
            guardrail_llm_api_key=None,
            guardrail_model=None,
            openai_api_key=None,
            anthropic_api_key=None,
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        guardrail = router._routes["guardrail"].provider.config
        assert guardrail.provider == ProviderType.OLLAMA
        assert guardrail.base_url == "http://ollama:11434"
        assert guardrail.api_key is None
        assert guardrail.model == "llama3"

    def test_legacy_openai_model_default_provider(self):
        settings = MagicMock(
            llm_provider="openai",
            llm_base_url=None,
            llm_api_key=None,
            llm_model="gpt-4",
            guardrail_llm_provider=None,
            guardrail_llm_base_url=None,
            guardrail_llm_api_key=None,
            guardrail_model="gpt-4o-mini",
            openai_api_key="legacy-openai",
            anthropic_api_key=None,
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        assert router._routes["agent"].provider.config.provider == ProviderType.OPENAI
        assert router._routes["agent"].provider.config.model == "gpt-4"
        assert router._routes["agent"].provider.config.api_key == "legacy-openai"

    def test_invalid_provider_defaults_to_openai_compatible(self):
        settings = MagicMock(
            llm_provider="invalid_provider",
            llm_base_url="https://llm.example/v1",
            llm_api_key="key",
            llm_model="model",
            guardrail_llm_provider=None,
            guardrail_llm_base_url=None,
            guardrail_llm_api_key=None,
            guardrail_model="guard",
            openai_api_key=None,
            anthropic_api_key=None,
            ollama_base_url=None,
        )
        router = LLMRouter()

        with patch("src.llm.router.get_settings", return_value=settings):
            _setup_default_routes(router)

        assert router._routes["agent"].provider.config.provider == ProviderType.OPENAI
