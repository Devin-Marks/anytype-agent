"""LLM provider implementations."""
import os
import json
from typing import List, Dict, Any, AsyncGenerator, Optional

from .base import (
    BaseLLMProvider,
    LLMResponse,
    LLMConfig,
    ProviderType,
)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider implementation."""

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        from openai import AsyncOpenAI

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
        from openai import AsyncOpenAI

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

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def health_check(self) -> bool:
        from openai import AsyncOpenAI
        try:
            client = AsyncOpenAI(api_key=self.config.api_key or os.getenv("OPENAI_API_KEY"))
            await client.models.list()
            return True
        except Exception:
            return False


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider implementation."""

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        from anthropic import AsyncAnthropic

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
        from anthropic import AsyncAnthropic

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
        from anthropic import AsyncAnthropic
        try:
            client = AsyncAnthropic(api_key=self.config.api_key or os.getenv("ANTHROPIC_API_KEY"))
            await client.messages.list(limit=1)
            return True
        except Exception:
            return False


class OllamaProvider(BaseLLMProvider):
    """Ollama local provider implementation."""

    async def complete(self, messages: List[Dict[str, str]]) -> LLMResponse:
        import httpx

        base_url = self.config.base_url or "http://localhost:11434"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": self.config.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": self.config.temperature},
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()

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
        import httpx

        base_url = self.config.base_url or "http://localhost:11434"
        async with httpx.AsyncClient() as client:
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

    async def health_check(self) -> bool:
        import httpx
        try:
            base_url = self.config.base_url or "http://localhost:11434"
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False