"""YandexGPT provider — OpenAI-compatible endpoint, used as fallback."""
from __future__ import annotations

from openai import OpenAI

from config.settings import Settings
from src.ai.base import AIClient, ChatRequest, ChatResult


class YandexGPTClient(AIClient):
    """Fallback provider. Implements the same contract as AITunnelClient."""

    name = "YandexGPT"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = OpenAI(
            api_key=settings.yandex_api_key,
            base_url="https://llm.api.cloud.yandex.net/foundationModels/v1",
            timeout=settings.request_timeout,
            max_retries=settings.max_retries,
        )

    def chat(self, request: ChatRequest) -> ChatResult:
        messages = [{"role": m.role, "content": m.content} for m in request.to_messages()]
        response = self._client.chat.completions.create(
            model=self._settings.yandex_model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return ChatResult(
            content=response.choices[0].message.content or "",
            provider=f"{self.name} (fallback)",
            model=self._settings.yandex_model,
        )