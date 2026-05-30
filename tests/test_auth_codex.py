"""Tests for Anytype-Agent owned OpenAI Codex auth CLI."""

import base64
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from src.auth import __main__ as auth_cli
from src.auth.codex import (
    CODEX_DEFAULT_CLIENT_ID,
    CODEX_DEFAULT_REDIRECT_URI,
    CodexLoginError,
    build_authorization_flow,
    codex_auth_file,
    credentials_from_token_response,
    exchange_authorization_code,
    generate_pkce,
    parse_redirect_url,
    write_credentials,
)
from src.llm.base import LLMConfig, ProviderType
from src.llm.providers import OpenAICodexProvider


def _jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.sig"


def test_pkce_generation_and_challenge():
    pkce = generate_pkce()

    assert len(pkce.verifier) >= 43
    assert "=" not in pkce.verifier
    expected = base64.urlsafe_b64encode(__import__("hashlib").sha256(pkce.verifier.encode()).digest()).decode().rstrip("=")
    assert pkce.challenge == expected


def test_auth_url_contains_pi_codex_params():
    flow = build_authorization_flow(originator="anytype-agent")
    parsed = urlparse(flow.url)
    params = parse_qs(parsed.query)

    assert parsed.geturl().startswith("https://auth.openai.com/oauth/authorize?")
    assert params["response_type"] == ["code"]
    assert params["client_id"] == [CODEX_DEFAULT_CLIENT_ID]
    assert params["redirect_uri"] == [CODEX_DEFAULT_REDIRECT_URI]
    assert params["scope"] == ["openid profile email offline_access"]
    assert params["code_challenge"] == [flow.challenge]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == [flow.state]
    assert params["id_token_add_organizations"] == ["true"]
    assert params["codex_cli_simplified_flow"] == ["true"]
    assert params["originator"] == ["anytype-agent"]


def test_redirect_url_parsing_and_bad_state_rejection():
    assert parse_redirect_url(
        "http://localhost:1455/auth/callback?code=abc&state=good", expected_state="good"
    ) == "abc"

    with pytest.raises(CodexLoginError, match="State mismatch"):
        parse_redirect_url("http://localhost:1455/auth/callback?code=abc&state=bad", expected_state="good")

    with pytest.raises(CodexLoginError, match="State mismatch"):
        parse_redirect_url("code=abc", expected_state="good")


@pytest.mark.asyncio
async def test_token_exchange_request_shape():
    captured = {}

    class MockResponse:
        status_code = 200

        def json(self):
            return {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}

    class MockClient:
        def __init__(self, *args, **kwargs):
            captured["init"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers, data):
            captured["url"] = url
            captured["headers"] = headers
            captured["data"] = data
            return MockResponse()

    with patch("src.auth.codex.httpx.AsyncClient", MockClient):
        tokens = await exchange_authorization_code("code", "verifier", timeout=12)

    assert tokens["access_token"] == "access"
    assert captured["init"] == {"timeout": 12}
    assert captured["url"] == "https://auth.openai.com/oauth/token"
    assert captured["headers"] == {"Content-Type": "application/x-www-form-urlencoded"}
    assert captured["data"] == {
        "grant_type": "authorization_code",
        "client_id": CODEX_DEFAULT_CLIENT_ID,
        "code": "code",
        "code_verifier": "verifier",
        "redirect_uri": CODEX_DEFAULT_REDIRECT_URI,
    }


def test_credential_file_write_perms_and_no_token_logs(tmp_path, capsys):
    auth_file = tmp_path / "codex" / "auth.json"
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct_123"}})
    creds = credentials_from_token_response(
        {"access_token": access, "refresh_token": "secret-refresh", "expires_in": 3600}
    )

    write_credentials(auth_file, creds)

    saved = json.loads(auth_file.read_text())
    provider = saved["providers"]["openai-codex"]
    assert provider["access"] == access
    assert provider["refresh"] == "secret-refresh"
    assert provider["accountId"] == "acct_123"
    assert oct(auth_file.stat().st_mode & 0o777) == "0o600"
    output = capsys.readouterr()
    assert access not in output.out + output.err
    assert "secret-refresh" not in output.out + output.err


def test_default_auth_file_honors_anytype_state(tmp_path, monkeypatch):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.delenv("ANYTYPE_AGENT_AUTH_FILE", raising=False)
    monkeypatch.setenv("ANYTYPE_AGENT_STATE_DIR", str(tmp_path / "state"))
    assert codex_auth_file() == tmp_path / "state" / "auth.json"
    monkeypatch.setenv("ANYTYPE_AGENT_AUTH_FILE", str(tmp_path / "internal-auth.json"))
    assert codex_auth_file() == tmp_path / "internal-auth.json"


def test_cli_status_and_logout(tmp_path, capsys):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"providers": {"openai-codex": {"access": "token", "refresh": "refresh"}}}))

    with patch.dict("os.environ", {"ANYTYPE_AGENT_AUTH_FILE": str(auth_file)}, clear=False):
        assert auth_cli.main(["status", "openai-codex"]) == 0
        status_output = capsys.readouterr().out
        assert "logged in" in status_output
        assert "token" not in status_output

        assert auth_cli.main(["logout", "openai-codex"]) == 0
        assert not auth_file.exists()
        assert auth_cli.main(["status", "openai-codex"]) == 1


@pytest.mark.asyncio
async def test_provider_refreshes_from_cli_stored_credentials(tmp_path):
    auth_file = tmp_path / "auth.json"
    write_credentials(
        auth_file,
        {"type": "oauth", "access": "old", "refresh": "refresh", "expires": 946684800000},
    )

    class MockResponse:
        status_code = 200

        def json(self):
            return {"access_token": "new", "refresh_token": "new-refresh", "expires_in": 3600}

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
            extra_params={"anytype_agent_auth_file": str(auth_file)},
        )
    )
    with patch("src.llm.providers.httpx.AsyncClient", MockClient):
        assert await provider._bearer_token() == "new"
    saved = json.loads(auth_file.read_text())
    provider = saved["providers"]["openai-codex"]
    assert provider["access"] == "new"
    assert provider["refresh"] == "new-refresh"


def test_cli_rejects_other_providers():
    with pytest.raises(SystemExit):
        auth_cli.main(["status", "openai"])
