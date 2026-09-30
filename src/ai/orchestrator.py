"""Cross-provider orchestrator with fallback semantics."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Generator, Sequence

from src.ai.base import AIClient, ChatRequest, ChatResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestrationResult:
    """Outcome of an orchestrated request."""

    success: bool
    result: ChatResult | None
    error: str | None
    anonymized: str


class AIOrchestrator:
    """Tries providers in order, returns the first successful response.

    Failures from earlier providers are logged and surfaced in `error`
    so the UI can show diagnostic information.
    """

    def __init__(self, providers: Sequence[AIClient]) -> None:
        if not providers:
            raise ValueError("At least one AI provider is required")
        self._providers = list(providers)

    @property
    def providers(self) -> Sequence[AIClient]:
        return tuple(self._providers)

    def complete(self, request: ChatRequest, *, anonymized: str = "") -> OrchestrationResult:
        errors: list[str] = []
        for provider in self._providers:
            try:
                logger.info("Trying provider: %s", provider.name)
                result = provider.chat(request)
                return OrchestrationResult(
                    success=True,
                    result=result,
                    error=None,
                    anonymized=anonymized,
                )
            except Exception as exc:  # noqa: BLE001 — orchestration needs broad catch
                msg = f"{provider.name}: {type(exc).__name__}: {exc}"
                logger.warning("Provider failed — %s", msg)
                errors.append(msg)
                continue

        return OrchestrationResult(
            success=False,
            result=None,
            error="\n".join(errors),
            anonymized=anonymized,
        )

    def stream(
        self, request: ChatRequest, *, anonymized: str = ""
    ) -> Generator[str, None, tuple[str, ChatResult | None, str | None]]:
        """Стриминг с fallback по провайдерам.

        Yields строки-токены. После исчерпания генератора вызов next() вернёт
        кортеж ``(provider_name, chat_result_or_none, error_or_none)``.
        Схема 'finally-result' позволяет UI собрать полный текст из токенов
        и получить метаданные для логирования/кэша.
        """
        errors: list[str] = []
        for provider in self._providers:
            try:
                logger.info("Streaming via provider: %s", provider.name)
                buffer: list[str] = []
                for token in provider.stream(request):
                    buffer.append(token)
                    yield token
                full = "".join(buffer)
                return (
                    provider.name,
                    ChatResult(content=full, provider=provider.name, model=""),
                    None,
                )
            except Exception as exc:  # noqa: BLE001
                msg = f"{provider.name}: {type(exc).__name__}: {exc}"
                logger.warning("Stream provider failed — %s", msg)
                errors.append(msg)
                continue

        return ("", None, "\n".join(errors))