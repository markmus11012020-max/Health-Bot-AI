"""Cross-provider orchestrator with fallback semantics."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

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