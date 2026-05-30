"""Pi-style manual OAuth login for OpenAI Codex/ChatGPT subscription auth."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx

CODEX_DEFAULT_AUTH_ISSUER = "https://auth.openai.com"
CODEX_DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_DEFAULT_REDIRECT_URI = "http://localhost:1455/auth/callback"
CODEX_DEFAULT_SCOPE = "openid profile email offline_access api.connectors.read api.connectors.invoke"
CODEX_AUTHORIZE_PATH = "/oauth/authorize"
CODEX_TOKEN_PATH = "/oauth/token"
APP_STATE_ENV = "ANYTYPE_AGENT_STATE_DIR"
APP_CONTAINER_STATE_DIR = Path("/var/lib/anytype-agent")
APP_AUTH_RELATIVE_PATH = Path("auth.json")
PROVIDER_KEY = "openai-codex"
JWT_AUTH_CLAIM = "https://api.openai.com/auth"


class CodexLoginError(RuntimeError):
    """Raised when the OpenAI Codex OAuth flow fails."""


@dataclass(frozen=True)
class PKCEPair:
    verifier: str
    challenge: str


@dataclass(frozen=True)
class AuthorizationFlow:
    verifier: str
    challenge: str
    state: str
    url: str


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def generate_pkce() -> PKCEPair:
    """Generate a PKCE S256 verifier/challenge pair like pi's Codex login flow."""
    verifier = _base64url(secrets.token_bytes(32))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return PKCEPair(verifier=verifier, challenge=_base64url(digest))


def generate_state() -> str:
    """Generate an OAuth state token."""
    return secrets.token_hex(16)


def default_app_state_dir() -> Path:
    """Return Anytype-Agent's persistent app-state root.

    Containers/Kubernetes use /var/lib/anytype-agent by default. Local executions use the
    XDG state directory (or ~/.local/state) unless ANYTYPE_AGENT_STATE_DIR is set.
    """
    configured = os.getenv(APP_STATE_ENV)
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured)))
    if os.getenv("KUBERNETES_SERVICE_HOST") or Path("/.dockerenv").exists():
        return APP_CONTAINER_STATE_DIR
    xdg_state = os.getenv("XDG_STATE_HOME")
    if xdg_state:
        return Path(os.path.expandvars(os.path.expanduser(xdg_state))) / "anytype-agent"
    return Path.home() / ".local" / "state" / "anytype-agent"


def app_auth_file() -> Path:
    """Return Anytype-Agent's unified auth file path under Anytype-owned state."""
    return default_app_state_dir() / APP_AUTH_RELATIVE_PATH


def codex_auth_file() -> Path:
    """Return Anytype-Agent's unified auth file path for Codex credentials."""
    return app_auth_file()


def build_authorization_flow(
    *,
    issuer: str = CODEX_DEFAULT_AUTH_ISSUER,
    client_id: str = CODEX_DEFAULT_CLIENT_ID,
    redirect_uri: str = CODEX_DEFAULT_REDIRECT_URI,
    scope: str = CODEX_DEFAULT_SCOPE,
    originator: str = "codex_cli_rs",
) -> AuthorizationFlow:
    pkce = generate_pkce()
    state = generate_state()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": originator,
        },
        quote_via=quote,
    )
    return AuthorizationFlow(
        verifier=pkce.verifier,
        challenge=pkce.challenge,
        state=state,
        url=f"{issuer.rstrip('/')}{CODEX_AUTHORIZE_PATH}?{query}",
    )


def parse_redirect_url(
    value: str,
    *,
    expected_state: str,
    expected_redirect_uri: str = CODEX_DEFAULT_REDIRECT_URI,
) -> str:
    """Extract the authorization code and require matching OAuth state/callback."""
    text = value.strip()
    if not text:
        raise CodexLoginError("Missing redirect URL")

    parsed = urlparse(text)
    expected = urlparse(expected_redirect_uri)
    if parsed.scheme or parsed.netloc:
        if (parsed.scheme, parsed.netloc, parsed.path) != (expected.scheme, expected.netloc, expected.path):
            raise CodexLoginError("Redirect URL did not match the expected localhost callback")
        params = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=False)
    else:
        params = parse_qs(text, keep_blank_values=True, strict_parsing=False)

    error = params.get("error", [None])[0]
    if error:
        raise CodexLoginError(f"OpenAI authorization failed: {error}")
    states = params.get("state", [])
    if len(states) != 1 or states[0] != expected_state:
        raise CodexLoginError("State mismatch in redirect URL")
    codes = params.get("code", [])
    if len(codes) != 1 or not codes[0]:
        raise CodexLoginError("Redirect URL did not contain exactly one authorization code")
    return codes[0]


def _token_url(issuer: str) -> str:
    return f"{issuer.rstrip('/')}{CODEX_TOKEN_PATH}"


async def exchange_authorization_code(
    code: str,
    verifier: str,
    *,
    issuer: str = CODEX_DEFAULT_AUTH_ISSUER,
    client_id: str = CODEX_DEFAULT_CLIENT_ID,
    redirect_uri: str = CODEX_DEFAULT_REDIRECT_URI,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Exchange an OAuth authorization code for Codex tokens."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            _token_url(issuer),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
            },
        )
    if response.status_code >= 400:
        raise CodexLoginError(f"OpenAI Codex token exchange failed with HTTP {response.status_code}")
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise CodexLoginError("OpenAI Codex token exchange returned malformed JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
        raise CodexLoginError("OpenAI Codex token exchange did not return an access token")
    if not isinstance(data.get("refresh_token"), str):
        raise CodexLoginError("OpenAI Codex token exchange did not return a refresh token")
    return data


def account_id_from_token(access_token: str) -> str | None:
    """Extract ChatGPT account id from an access-token JWT without logging token contents."""
    parts = access_token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode((parts[1] + "=" * (-len(parts[1]) % 4)).encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return None
    auth_claim = payload.get(JWT_AUTH_CLAIM)
    if isinstance(auth_claim, dict) and isinstance(auth_claim.get("chatgpt_account_id"), str):
        return auth_claim["chatgpt_account_id"]
    return None


def credentials_from_token_response(token_response: dict[str, Any]) -> dict[str, Any]:
    """Convert OAuth token response into Anytype-Agent's Codex auth file schema."""
    expires_in = token_response.get("expires_in")
    expires = None
    if isinstance(expires_in, (int, float)):
        expires = int((datetime.now(timezone.utc) + timedelta(seconds=float(expires_in))).timestamp() * 1000)
    credentials: dict[str, Any] = {
        "type": "oauth",
        "provider": "openai-codex",
        "access": token_response["access_token"].strip(),
        "refresh": token_response["refresh_token"].strip(),
        "expires": expires,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if isinstance(token_response.get("id_token"), str) and token_response["id_token"].strip():
        credentials["id_token"] = token_response["id_token"].strip()
    account_id = account_id_from_token(credentials["access"])
    if account_id:
        credentials["accountId"] = account_id
    return credentials


def _with_provider_credentials(existing: dict[str, Any] | None, credentials: dict[str, Any]) -> dict[str, Any]:
    data = existing if isinstance(existing, dict) else {}
    providers = data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    providers[PROVIDER_KEY] = credentials
    data["providers"] = providers
    data["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return data


def _atomic_write_auth_file(path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON auth data with 0600 file permissions where supported."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        try:
            dir_fd = os.open(path.parent, os.O_DIRECTORY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


def write_credentials(path: Path, credentials: dict[str, Any]) -> None:
    """Atomically write provider credentials with 0600 permissions where supported."""
    existing = read_credentials(path)
    _atomic_write_auth_file(path, _with_provider_credentials(existing, credentials))


def read_credentials(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def read_provider_credentials(path: Path) -> dict[str, Any] | None:
    data = read_credentials(path)
    if not isinstance(data, dict):
        return None
    providers = data.get("providers")
    if not isinstance(providers, dict):
        return None
    record = providers.get(PROVIDER_KEY)
    return record if isinstance(record, dict) else None


def remove_provider_credentials(path: Path) -> bool:
    data = read_credentials(path)
    if not isinstance(data, dict):
        return False
    providers = data.get("providers")
    if not isinstance(providers, dict) or PROVIDER_KEY not in providers:
        return False
    providers.pop(PROVIDER_KEY, None)
    if providers:
        write_credentials_file(path, data)
    else:
        path.unlink(missing_ok=True)
    return True


def write_credentials_file(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_auth_file(path, data)


async def login_with_manual_redirect(
    *,
    auth_file: Path | None = None,
    issuer: str = CODEX_DEFAULT_AUTH_ISSUER,
    client_id: str = CODEX_DEFAULT_CLIENT_ID,
    redirect_uri: str = CODEX_DEFAULT_REDIRECT_URI,
    input_func=input,
    output_func=print,
) -> Path:
    """Run the manual browser redirect login flow and persist credentials."""
    target = auth_file or codex_auth_file()
    flow = build_authorization_flow(issuer=issuer, client_id=client_id, redirect_uri=redirect_uri)
    output_func("Open this URL in your browser to sign in with ChatGPT Plus/Pro (Codex):")
    output_func(flow.url)
    redirect = input_func("Paste the final redirect URL here: ")
    code = parse_redirect_url(redirect, expected_state=flow.state, expected_redirect_uri=redirect_uri)
    token_response = await exchange_authorization_code(
        code,
        flow.verifier,
        issuer=issuer,
        client_id=client_id,
        redirect_uri=redirect_uri,
    )
    write_credentials(target, credentials_from_token_response(token_response))
    return target
