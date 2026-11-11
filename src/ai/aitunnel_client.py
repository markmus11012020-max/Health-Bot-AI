"""AITunnel provider — OpenAI-compatible API."""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

from openai import OpenAI

from config.settings import Settings
from src.ai.base import AIClient, ChatRequest, ChatResult


class AITunnelClient(AIClient):
    """Primary provider. Uses AITunnel's OpenAI-compatible endpoint."""

    name = "AITunnel"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = OpenAI(
            api_key=settings.aitunnel_api_key,
            base_url=settings.aitunnel_base_url,
            timeout=settings.request_timeout,
            max_retries=settings.max_retries,
        )

    @property
    def model_name(self) -> str:
        return self._settings.aitunnel_model

    def chat(self, request: ChatRequest) -> ChatResult:
        messages: Any = [
            {"role": m.role, "content": m.content} for m in request.to_messages()
        ]
        response = self._client.chat.completions.create(
            model=self._settings.aitunnel_model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        usage = getattr(response, "usage", None)
        return ChatResult(
            content=response.choices[0].message.content or "",
            provider=self.name,
            model=self._settings.aitunnel_model,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    def stream(self, request: ChatRequest) -> Generator[str, None, None]:
        messages: Any = [
            {"role": m.role, "content": m.content} for m in request.to_messages()
        ]
        stream = self._client.chat.completions.create(
            model=self._settings.aitunnel_model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )
        for chunk in stream:
            try:
                chunk_any: Any = chunk
                delta = chunk_any.choices[0].delta.content
            except (AttributeError, IndexError):
                delta = None
            if delta:
                yield delta