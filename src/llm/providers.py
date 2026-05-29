"""LLM provider implementations."""
import inspect
import json
import os
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


async def _read_ollama_response(response: Any) -> dict:
    """Read an Ollama HTTP response from real httpx or test doubles."""
    response.raise_for_status()
    data = response.json()
    if inspect.isawaitable(data):
        data = await data
    return data


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider implementation."""

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        client = AsyncOpenAI(
            api_key=self.config.api_key or os.getenv("OPENAI_API_KEY"),
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
            api_key=self.config.api_key or os.getenv("OPENAI_API_KEY"),
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
            client = AsyncOpenAI(api_key=self.config.api_key or os.getenv("OPENAI_API_KEY"))
            await client.models.list()
            return True
        except Exception:
            return False


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider implementation."""

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        if AsyncAnthropic is None:
            raise ImportError("anthropic package is not installed")

        client = AsyncAnthropic(
            api_key=self.config.api_key or os.getenv("ANTHROPIC_API_KEY"),
        )

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

        client = AsyncAnthropic(
            api_key=self.config.api_key or os.getenv("ANTHROPIC_API_KEY"),
        )

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
            client = AsyncAnthropic(api_key=self.config.api_key or os.getenv("ANTHROPIC_API_KEY"))
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
