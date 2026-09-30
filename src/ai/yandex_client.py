"""YandexGPT provider — OpenAI-compatible endpoint, used as fallback."""
from __future__ import annotations

import logging
from typing import Generator

from openai import OpenAI

from config.settings import Settings
from src.ai.base import AIClient, ChatRequest, ChatResult

logger = logging.getLogger(__name__)


class YandexGPTClient(AIClient):
    """Fallback provider. Implements the same contract as AITunnelClient.

    Yandex's OpenAI-compatible API requires:
      * auth via either API-key or IAM-token (IAM wins if both are set);
      * a model URI in the form ``gpt://<folder_id>/<model_name>``.
    Passing a bare ``yandexgpt-lite`` (without the ``gpt://`` prefix) yields
    a 404 Not Found, which is the most common integration pitfall.
    """

    name = "YandexGPT"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model_uri = self._build_model_uri(settings)
        self._client = OpenAI(
            api_key=self._resolve_auth(settings),
            base_url=settings.yandex_gpt_url,
            timeout=settings.yandex_timeout_s,
            max_retries=settings.max_retries,
        )

    @staticmethod
    def _resolve_auth(settings: Settings) -> str:
        """IAM-token has priority over API-key when both are configured."""
        iam = (settings.yandex_iam_token or "").strip()
        if iam:
            logger.debug("YandexGPT: authenticating with IAM token")
            return iam
        logger.debug("YandexGPT: authenticating with API key")
        return settings.yandex_api_key or ""

    @staticmethod
    def _build_model_uri(settings: Settings) -> str:
        """Compose ``gpt://<folder_id>/<model>`` from config parts."""
        model = settings.yandex_gpt_model or "yandexgpt-lite"
        if model.startswith("gpt://"):
            return model  # already a fully-qualified URI
        folder = (settings.yandex_folder_id or "").strip()
        if not folder:
            logger.warning(
                "YANDEX_FOLDER_ID is empty — request will likely fail with 404"
            )
            return model
        return f"gpt://{folder}/{model}"

    def chat(self, request: ChatRequest) -> ChatResult:
        messages = [{"role": m.role, "content": m.content} for m in request.to_messages()]
        response = self._client.chat.completions.create(
            model=self._model_uri,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return ChatResult(
            content=response.choices[0].message.content or "",
            provider=self.name,
            model=self._model_uri,
        )

    def stream(self, request: ChatRequest) -> Generator[str, None, None]:
        messages = [{"role": m.role, "content": m.content} for m in request.to_messages()]
        stream = self._client.chat.completions.create(
            model=self._model_uri,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content
            except (AttributeError, IndexError):
                delta = None
            if delta:
                yield delta
