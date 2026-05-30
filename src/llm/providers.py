"""LLM provider implementations."""
import asyncio
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import subprocess
from typing import Any, AsyncGenerator, Dict, List

import httpx
from openai import AsyncOpenAI

from .base import (
    BaseLLMProvider,
    LLMResponse,
    ProviderType,
)

try:  # Anthropic is optional unless that provider is configured.
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - exercised only without optional dependency
    AsyncAnthropic = None


CODEX_DEFAULT_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"


class CodexAuthError(RuntimeError):
    """Raised when OpenAI Codex subscription auth cannot provide a bearer token."""


def _expand_auth_path(path: str) -> Path:
    """Expand env/user vars in a Codex auth file path."""
    return Path(os.path.expandvars(os.path.expanduser(path)))


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


def _find_codex_access_token(data: Any) -> tuple[str | None, datetime | None]:
    """Find a Codex-compatible access token and optional expiry in auth.json data."""
    expiry_keys = ("expires_at", "expiresAt", "expires", "expiry", "expiration")

    def walk(node: Any, inherited_expiry: datetime | None = None) -> tuple[str | None, datetime | None]:
        if isinstance(node, dict):
            local_expiry = inherited_expiry
            for key in expiry_keys:
                if key in node:
                    parsed = _parse_expiry(node[key])
                    if parsed is not None:
                        local_expiry = parsed
                        break
            for key in ("access_token", "accessToken", "token", "bearer_token", "bearerToken"):
                token = node.get(key)
                if isinstance(token, str) and token.strip():
                    return token.strip(), local_expiry
            for value in node.values():
                found_token, found_expiry = walk(value, local_expiry)
                if found_token:
                    return found_token, found_expiry
        elif isinstance(node, list):
            for value in node:
                found_token, found_expiry = walk(value, inherited_expiry)
                if found_token:
                    return found_token, found_expiry
        return None, inherited_expiry

    return walk(data)


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
        client = AsyncOpenAI(
            api_key=self._api_key(),
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
        client = AsyncOpenAI(
            api_key=self._api_key(),
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
            client = AsyncOpenAI(
                api_key=self._api_key(),
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
        configured = (
            self.config.extra_params.get("codex_auth_file")
            or os.getenv("CODEX_AUTH_FILE")
            or "/var/lib/anytype-agent/codex/auth.json"
        )
        return _expand_auth_path(configured)

    def _token_command(self) -> str | None:
        return self.config.extra_params.get("codex_token_command") or os.getenv("CODEX_TOKEN_COMMAND")

    async def _token_from_command(self, command: str) -> str:
        def run_command() -> str:
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if completed.returncode != 0:
                stderr = completed.stderr.strip()
                raise CodexAuthError(
                    f"CODEX_TOKEN_COMMAND failed with exit code {completed.returncode}"
                    + (f": {stderr}" if stderr else "")
                )
            token = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
            if not token:
                raise CodexAuthError("CODEX_TOKEN_COMMAND did not print a bearer token")
            return token

        return await asyncio.to_thread(run_command)

    async def _bearer_token(self) -> str:
        token_command = self._token_command()
        if token_command:
            return await self._token_from_command(token_command)

        auth_file = self._auth_file()
        if not auth_file.exists():
            raise CodexAuthError(
                f"Codex auth file not found: {auth_file}. Run `codex login --device-auth` "
                "or mount a Codex auth.json, or configure CODEX_TOKEN_COMMAND."
            )
        try:
            data = json.loads(auth_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CodexAuthError(f"Codex auth file is malformed JSON: {auth_file}") from exc
        except OSError as exc:
            raise CodexAuthError(f"Could not read Codex auth file {auth_file}: {exc}") from exc

        token, expiry = _find_codex_access_token(data)
        if not token:
            raise CodexAuthError(f"Codex auth file does not contain an access token: {auth_file}")
        if expiry is not None and expiry <= datetime.now(timezone.utc):
            raise CodexAuthError(
                f"Codex access token in {auth_file} expired at {expiry.isoformat()}. "
                "Refresh with Codex CLI or configure CODEX_TOKEN_COMMAND."
            )
        return token

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
            raise ImportError("anthropic package is not installed")

        client = AsyncAnthropic(api_key=self._api_key())

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
            raise ImportError("anthropic package is not installed")

        client = AsyncAnthropic(api_key=self._api_key())

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
            client = AsyncAnthropic(api_key=self._api_key())
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
