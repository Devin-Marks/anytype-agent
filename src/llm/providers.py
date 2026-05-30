"""LLM provider implementations."""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import inspect
import json
import os
from pathlib import Path
import tempfile
from typing import Any, AsyncGenerator, Dict, List

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None

import httpx
from openai import AsyncOpenAI

from .base import (
    BaseLLMProvider,
    LLMConfigurationError,
    LLMResponse,
    ProviderType,
)

try:  # Anthropic is optional unless that provider is configured.
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - exercised only without optional dependency
    AsyncAnthropic = None


CODEX_DEFAULT_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"
CODEX_DEFAULT_AUTH_ISSUER = "https://auth.openai.com"
CODEX_DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_DEFAULT_REFRESH_SKEW_SECONDS = 300
CODEX_DEFAULT_AUTH_RELATIVE_PATH = Path("auth.json")
CODEX_CONTAINER_STATE_DIR = Path("/var/lib/anytype-agent")
CODEX_PROVIDER_KEY = "openai-codex"
_CODEX_REFRESH_LOCKS: dict[str, asyncio.Lock] = {}


class CodexAuthError(LLMConfigurationError):
    """Raised when OpenAI Codex subscription auth cannot provide a bearer token."""


def _expand_auth_path(path: str) -> Path:
    """Expand env/user vars in a Codex auth file path."""
    return Path(os.path.expandvars(os.path.expanduser(path)))


def _default_app_state_dir() -> Path:
    """Return Anytype-Agent's persistent app-state root."""
    configured = os.getenv("ANYTYPE_AGENT_STATE_DIR")
    if configured:
        return _expand_auth_path(configured)
    if os.getenv("KUBERNETES_SERVICE_HOST") or Path("/.dockerenv").exists():
        return CODEX_CONTAINER_STATE_DIR
    xdg_state = os.getenv("XDG_STATE_HOME")
    if xdg_state:
        return _expand_auth_path(xdg_state) / "anytype-agent"
    return Path.home() / ".local" / "state" / "anytype-agent"


def _default_codex_auth_file() -> Path:
    return _default_app_state_dir() / CODEX_DEFAULT_AUTH_RELATIVE_PATH


def _parse_expiry(value: Any) -> datetime | None:
    """Parse common Codex/OAuth expiry shapes."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return _parse_expiry(int(stripped))
        if stripped.endswith("Z"):
            stripped = stripped[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(stripped)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _jwt_expiry(token: str) -> datetime | None:
    """Parse a JWT exp claim without verifying the token."""
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return None
    return _parse_expiry(claims.get("exp"))


def _codex_token_record(data: Any) -> tuple[dict[str, Any] | None, str | None, str | None, datetime | None]:
    """Find a Codex-compatible token record with access/refresh tokens."""
    expiry_keys = ("expires_at", "expiresAt", "expires", "expiry", "expiration")
    access_keys = ("access_token", "accessToken", "access", "bearer_token", "bearerToken")
    refresh_keys = ("refresh_token", "refreshToken", "refresh")

    best: tuple[dict[str, Any] | None, str | None, str | None, datetime | None] = (None, None, None, None)

    def walk(node: Any, inherited_expiry: datetime | None = None) -> None:
        nonlocal best
        if isinstance(node, dict):
            local_expiry = inherited_expiry
            for key in expiry_keys:
                if key in node:
                    parsed = _parse_expiry(node[key])
                    if parsed is not None:
                        local_expiry = parsed
                        break
            access_token = next(
                (node[key].strip() for key in access_keys if isinstance(node.get(key), str) and node[key].strip()),
                None,
            )
            refresh_token = next(
                (node[key].strip() for key in refresh_keys if isinstance(node.get(key), str) and node[key].strip()),
                None,
            )
            if access_token:
                token_expiry = local_expiry or _jwt_expiry(access_token)
                if refresh_token:
                    best = (node, access_token, refresh_token, token_expiry)
                    return
                if best[1] is None:
                    best = (node, access_token, None, token_expiry)
            for value in node.values():
                walk(value, local_expiry)
                if best[2]:
                    return
        elif isinstance(node, list):
            for value in node:
                walk(value, inherited_expiry)
                if best[2]:
                    return

    walk(data)
    return best


def _find_codex_access_token(data: Any) -> tuple[str | None, datetime | None]:
    """Find a Codex-compatible access token and optional expiry in auth.json data."""
    _, token, _, expiry = _codex_token_record(data)
    return token, expiry


async def _read_ollama_response(response: Any) -> dict:
    """Read an Ollama HTTP response from real httpx or test doubles."""
    response.raise_for_status()
    data = response.json()
    if inspect.isawaitable(data):
        data = await data
    return data


class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible chat completions provider implementation."""

    def _api_key(self) -> str | None:
        """Return configured API key, allowing local endpoints without real keys."""
        key = self.config.api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if key:
            return key
        if self.config.base_url:
            return "not-needed"
        return None

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        api_key = self._api_key()
        if not api_key:
            raise LLMConfigurationError(
                "LLM provider is not configured/authenticated. Set LLM_PROVIDER=openai and LLM_API_KEY, "
                "or set LLM_BASE_URL for a local/OpenAI-compatible endpoint."
            )
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
        )

        response = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            **(self.config.extra_params or {}),
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            provider=ProviderType.OPENAI,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            raw_response=response.model_dump(),
            finish_reason=response.choices[0].finish_reason,
        )

    async def stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        api_key = self._api_key()
        if not api_key:
            raise LLMConfigurationError(
                "LLM provider is not configured/authenticated. Set LLM_PROVIDER=openai and LLM_API_KEY, "
                "or set LLM_BASE_URL for a local/OpenAI-compatible endpoint."
            )
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
        )

        stream = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=True,
        )

        iterator = stream.__aiter__()
        if hasattr(iterator, "__anext__"):
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        else:
            for chunk in iterator:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    async def health_check(self) -> bool:
        try:
            api_key = self._api_key()
            if not api_key:
                raise LLMConfigurationError(
                    "LLM provider is not configured/authenticated. Set LLM_PROVIDER=openai and LLM_API_KEY, "
                    "or set LLM_BASE_URL for a local/OpenAI-compatible endpoint."
                )
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.config.base_url,
            )
            await client.models.list()
            return True
        except Exception:
            return False


class OpenAICodexProvider(BaseLLMProvider):
    """OpenAI Codex/ChatGPT subscription backend provider.

    This provider intentionally uses explicit opt-in subscription auth
    (LLM_PROVIDER=openai-codex). It is not OpenAI Platform API-key auth.
    """

    def _endpoint(self) -> str:
        return (
            self.config.base_url
            or self.config.extra_params.get("codex_base_url")
            or os.getenv("CODEX_BASE_URL")
            or CODEX_DEFAULT_ENDPOINT
        )

    def _auth_file(self) -> Path:
        return _default_codex_auth_file()

    def _auth_issuer(self) -> str:
        return (
            self.config.extra_params.get("codex_auth_issuer")
            or os.getenv("CODEX_AUTH_ISSUER")
            or CODEX_DEFAULT_AUTH_ISSUER
        ).rstrip("/")

    def _client_id(self) -> str:
        return (
            self.config.extra_params.get("codex_client_id")
            or os.getenv("CODEX_CLIENT_ID")
            or CODEX_DEFAULT_CLIENT_ID
        )

    def _refresh_skew(self) -> int:
        configured = self.config.extra_params.get("codex_refresh_skew_seconds") or os.getenv(
            "CODEX_REFRESH_SKEW_SECONDS"
        )
        if configured in (None, ""):
            return CODEX_DEFAULT_REFRESH_SKEW_SECONDS
        try:
            return max(0, int(configured))
        except (TypeError, ValueError):
            return CODEX_DEFAULT_REFRESH_SKEW_SECONDS

    def _read_auth_data(self, auth_file: Path) -> Any:
        if not auth_file.exists():
            raise CodexAuthError(
                f"Anytype-Agent auth file not found: {auth_file}. Run "
                "`python -m src.auth login openai-codex` with persistent storage mounted."
            )
        try:
            return json.loads(auth_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CodexAuthError(f"Codex auth file is malformed JSON: {auth_file}") from exc
        except OSError as exc:
            raise CodexAuthError(f"Could not read Codex auth file {auth_file}: {exc}") from exc

    def _needs_refresh(self, expiry: datetime | None) -> bool:
        if expiry is None:
            return False
        return expiry <= datetime.now(timezone.utc) + timedelta(seconds=self._refresh_skew())

    async def _refresh_codex_tokens(self, refresh_token: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self._auth_issuer()}/oauth/token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": self._client_id(),
                    },
                )
        except httpx.HTTPError as exc:
            raise CodexAuthError(f"Codex OAuth token refresh request failed: {exc.__class__.__name__}") from exc

        if response.status_code >= 400:
            raise CodexAuthError(f"Codex OAuth token refresh failed with HTTP {response.status_code}")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise CodexAuthError("Codex OAuth token refresh returned malformed JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
            raise CodexAuthError("Codex OAuth token refresh response did not contain an access token")
        return data

    @staticmethod
    def _existing_key(record: dict[str, Any], candidates: tuple[str, ...], default: str) -> str:
        """Return the first existing key from candidates to preserve auth.json schema style."""
        return next((key for key in candidates if key in record), default)

    def _persist_refreshed_auth(self, auth_file: Path, data: Any, record: dict[str, Any], refreshed: dict[str, Any]) -> None:
        access_key = self._existing_key(record, ("access_token", "accessToken", "access"), "access_token")
        refresh_key = self._existing_key(record, ("refresh_token", "refreshToken", "refresh"), "refresh_token")
        id_key = self._existing_key(record, ("id_token", "idToken"), "id_token")
        expiry_key = self._existing_key(
            record,
            ("expires_at", "expiresAt", "expires", "expiry", "expiration"),
            "expires_at",
        )

        record[access_key] = refreshed["access_token"].strip()
        if isinstance(refreshed.get("refresh_token"), str) and refreshed["refresh_token"].strip():
            record[refresh_key] = refreshed["refresh_token"].strip()
        if isinstance(refreshed.get("id_token"), str) and refreshed["id_token"].strip():
            record[id_key] = refreshed["id_token"].strip()
        if isinstance(refreshed.get("expires_in"), (int, float)) and any(
            key in record for key in ("expires_at", "expiresAt", "expires", "expiry", "expiration")
        ):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=float(refreshed["expires_in"]))
            if expiry_key == "expires":
                record[expiry_key] = int(expires_at.timestamp() * 1000)
            else:
                record[expiry_key] = expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")

        if isinstance(data, dict):
            data["last_refresh"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        auth_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_name = ""
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=f".{auth_file.name}.", suffix=".tmp", dir=str(auth_file.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(data, tmp, indent=2, sort_keys=True)
                tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, auth_file)
            try:
                dir_fd = os.open(auth_file.parent, os.O_DIRECTORY)
            except OSError:
                dir_fd = None
            if dir_fd is not None:
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        except OSError as exc:
            raise CodexAuthError(
                f"Could not persist refreshed Codex auth file {auth_file}: {exc}. "
                "Mount /var/lib/anytype-agent from a writable PVC and re-run Anytype-Agent login."
            ) from exc
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass

    def _token_status_from_auth_file(
        self,
        auth_file: Path,
    ) -> tuple[Any, dict[str, Any] | None, str, str | None, datetime | None, bool]:
        """Read auth data and return token state without exposing token values in errors."""
        data = self._read_auth_data(auth_file)
        provider_data = data.get("providers", {}).get(CODEX_PROVIDER_KEY) if isinstance(data, dict) else None
        if not isinstance(provider_data, dict):
            raise CodexAuthError(
                f"Anytype-Agent auth file does not contain {CODEX_PROVIDER_KEY} credentials: {auth_file}. "
                "Run `python -m src.auth login openai-codex`."
            )
        record, token, refresh_token, expiry = _codex_token_record(provider_data)
        if not token:
            raise CodexAuthError(f"Codex credential file does not contain an access token: {auth_file}")
        return data, record, token, refresh_token, expiry, self._needs_refresh(expiry)

    async def _token_from_auth_file(self, auth_file: Path) -> str:
        data, record, token, refresh_token, _expiry, needs_refresh = self._token_status_from_auth_file(auth_file)
        if not needs_refresh:
            return token

        lock = _CODEX_REFRESH_LOCKS.setdefault(str(auth_file), asyncio.Lock())
        async with lock:
            lock_file = auth_file.with_suffix(auth_file.suffix + ".lock")
            file_handle = None
            try:
                try:
                    lock_file.parent.mkdir(parents=True, exist_ok=True)
                    file_handle = lock_file.open("a+")
                except OSError as exc:
                    raise CodexAuthError(
                        f"Could not create Codex auth lock file {lock_file}: {exc}. "
                        "Mount /var/lib/anytype-agent from a writable PVC and re-run Anytype-Agent login."
                    ) from exc
                if fcntl is not None:
                    await asyncio.to_thread(fcntl.flock, file_handle.fileno(), fcntl.LOCK_EX)

                data, record, token, refresh_token, _expiry, needs_refresh = self._token_status_from_auth_file(auth_file)
                if not needs_refresh:
                    return token
                if not refresh_token:
                    raise CodexAuthError(
                        f"Codex access token in {auth_file} is expired or near expiry, "
                        "but no refresh token is available. Re-run `python -m src.auth login openai-codex`."
                    )
                if record is None:
                    raise CodexAuthError(f"Codex auth file does not contain refreshable token data: {auth_file}")
                refreshed = await self._refresh_codex_tokens(refresh_token)
                self._persist_refreshed_auth(auth_file, data, record, refreshed)
                return refreshed["access_token"].strip()
            finally:
                if file_handle is not None:
                    try:
                        if fcntl is not None:
                            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
                    finally:
                        file_handle.close()

    async def _bearer_token(self) -> str:
        return await self._token_from_auth_file(self._auth_file())

    def _request_payload(self, messages: List[Dict[str, str]], stream: bool = False) -> dict:
        payload = {
            "model": self.config.model,
            "input": messages,
            "stream": stream,
        }
        payload.update(self.config.extra_params.get("codex_request_params", {}))
        return payload

    @staticmethod
    def _content_from_response(data: dict) -> str:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        output = data.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                content = item.get("content") if isinstance(item, dict) else None
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append(part["text"])
                elif isinstance(content, str):
                    parts.append(content)
            if parts:
                return "".join(parts)
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            if isinstance(message.get("content"), str):
                return message["content"]
        return ""

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        token = await self._bearer_token()
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                self._endpoint(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=self._request_payload(messages),
            )
            response.raise_for_status()
            data = response.json()

        if inspect.isawaitable(data):
            data = await data

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return LLMResponse(
            content=self._content_from_response(data),
            model=data.get("model", self.config.model),
            provider=ProviderType.OPENAI_CODEX,
            usage={k: v for k, v in usage.items() if isinstance(v, int)},
            raw_response=data,
            finish_reason=data.get("finish_reason") or data.get("status"),
        )

    async def stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        # The Codex backend is intentionally isolated and less stable than the
        # public OpenAI API. Use a non-streaming response here until its server
        # streaming contract is documented for this application use case.
        response = await self.complete(messages)
        if response.content:
            yield response.content

    async def health_check(self) -> bool:
        try:
            return bool(await self._bearer_token())
        except Exception:
            return False


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider implementation."""

    def _api_key(self) -> str | None:
        """Return configured API key with generic and legacy env fallback."""
        return self.config.api_key or os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        if AsyncAnthropic is None:
            raise LLMConfigurationError(
                "LLM provider is not configured/authenticated. Install the anthropic package or choose another LLM_PROVIDER."
            )
        api_key = self._api_key()
        if not api_key:
            raise LLMConfigurationError(
                "LLM provider is not configured/authenticated. Set LLM_PROVIDER=anthropic and LLM_API_KEY."
            )

        client = AsyncAnthropic(api_key=api_key)

        system = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        response = await client.messages.create(
            model=self.config.model,
            system=system,
            messages=anthropic_messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens or 1024,
        )

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            provider=ProviderType.ANTHROPIC,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            finish_reason=response.stop_reason,
        )

    async def stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        if AsyncAnthropic is None:
            raise LLMConfigurationError(
                "LLM provider is not configured/authenticated. Install the anthropic package or choose another LLM_PROVIDER."
            )
        api_key = self._api_key()
        if not api_key:
            raise LLMConfigurationError(
                "LLM provider is not configured/authenticated. Set LLM_PROVIDER=anthropic and LLM_API_KEY."
            )

        client = AsyncAnthropic(api_key=api_key)

        system = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        async with client.messages.stream(
            model=self.config.model,
            system=system,
            messages=anthropic_messages,
            max_tokens=self.config.max_tokens or 1024,
        ) as stream:
            async for text_stream in stream.text_stream:
                yield text_stream

    async def health_check(self) -> bool:
        if AsyncAnthropic is None:
            return False

        try:
            api_key = self._api_key()
            if not api_key:
                raise LLMConfigurationError(
                    "LLM provider is not configured/authenticated. Set LLM_PROVIDER=anthropic and LLM_API_KEY."
                )
            client = AsyncAnthropic(api_key=api_key)
            await client.messages.list(limit=1)
            return True
        except Exception:
            return False


class OllamaProvider(BaseLLMProvider):
    """Ollama local provider implementation."""

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        base_url = self.config.base_url or "http://localhost:11434"
        client = httpx.AsyncClient()
        try:
            response_or_cm = client.post(
                f"{base_url}/api/chat",
                json={
                    "model": self.config.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": self.config.temperature},
                },
                timeout=self.config.timeout,
            )
            if hasattr(response_or_cm, "__aenter__"):
                async with response_or_cm as response:
                    data = await _read_ollama_response(response)
            else:
                response = await response_or_cm
                data = await _read_ollama_response(response)
        finally:
            close_result = client.aclose()
            if inspect.isawaitable(close_result):
                await close_result

        return LLMResponse(
            content=data["message"]["content"],
            model=data["model"],
            provider=ProviderType.OLLAMA,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            finish_reason=data.get("done_reason"),
        )

    async def stream(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        base_url = self.config.base_url or "http://localhost:11434"
        client = httpx.AsyncClient()
        try:
            async with client.stream(
                "POST",
                f"{base_url}/api/chat",
                json={
                    "model": self.config.model,
                    "messages": messages,
                    "stream": True,
                },
                timeout=self.config.timeout,
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
        finally:
            close_result = client.aclose()
            if inspect.isawaitable(close_result):
                await close_result

    async def health_check(self) -> bool:
        try:
            base_url = self.config.base_url or "http://localhost:11434"
            client = httpx.AsyncClient()
            try:
                response_or_cm = client.get(f"{base_url}/api/tags")
                if hasattr(response_or_cm, "__aenter__"):
                    async with response_or_cm as response:
                        return response.status_code == 200
                response = await response_or_cm
                return response.status_code == 200
            finally:
                close_result = client.aclose()
                if inspect.isawaitable(close_result):
                    await close_result
        except Exception:
            return False
