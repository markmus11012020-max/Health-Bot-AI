"""Consultation use-case: combines anonymization, prompt building, AI call.

Pipeline:
  1. Анонимизация crm_context и client_message (152-ФЗ).
  2. Поиск в локальном LRU-кэше (на ключе SHA-256 от анонимизированного ввода).
  3. Если cache miss — запрос к AI-провайдеру, логирование результата.
  4. Запись успешного ответа в кэш.

Поддерживает два режима:
  - run()         — обычный (возвращает ConsultationOutcome целиком).
  - stream_run()  — стриминг (для UX с мгновенным откликом).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generator

from config.prompts import build_system_prompt
from config.settings import Settings
from src.ai.base import ChatRequest as ChatRequestDTO, ChatResult
from src.ai.orchestrator import AIOrchestrator, OrchestrationResult
from src.core.anonymizer import PIIAnonymizer
from src.core.audit_log import log_consultation_event
from src.core.response_cache import CacheEntry, ResponseCache
from src.core.knowledge_base import KnowledgeBase


@dataclass(frozen=True)
class ConsultationInput:
    crm_context: str
    client_message: str


@dataclass(frozen=True)
class ConsultationOutcome:
    """Результат + диагностика (для UI и аудита)."""

    result: OrchestrationResult
    anonymized_input: str
    cache_hit: bool = False


class ConsultationService:
    """High-level use-case: produce AI guidance for a sales conversation."""

    def __init__(
        self,
        *,
        settings: Settings,
        orchestrator: AIOrchestrator,
        knowledge_base: KnowledgeBase,
        anonymizer: PIIAnonymizer,
        cache: ResponseCache | None = None,
    ) -> None:
        self._settings = settings
        self._orchestrator = orchestrator
        self._kb = knowledge_base
        self._anonymizer = anonymizer
        self._cache = cache or ResponseCache()

    @property
    def cache(self) -> ResponseCache:
        return self._cache

    def _build_provider_signature(self) -> tuple[str, str]:
        providers = getattr(self._orchestrator, "providers", []) or []
        if providers:
            p = providers[0]
            model = getattr(
                p._settings, "aitunnel_model", getattr(p._settings, "yandex_gpt_model", "?")
            )
            return p.name, model
        return "unknown", "unknown"

    def _prepare_inputs(self, payload: ConsultationInput) -> tuple[str, str, str]:
        """Анонимизация обоих полей. Возвращает (anonymized_full, crm_part, msg_part)."""
        anonymized_crm = self._anonymizer.anonymize(payload.crm_context)
        anonymized_msg = self._anonymizer.anonymize(payload.client_message)
        anonymized = (
            f"CRM-контекст (анонимизировано): {anonymized_crm}\n"
            f"Сообщение клиента (анонимизировано): {anonymized_msg}"
        )
        return anonymized, anonymized_crm, anonymized_msg

    def _build_request(
        self, anonymized: str, anonymized_crm: str, anonymized_msg: str
    ) -> ChatRequestDTO:
        kb_text = self._kb.read()
        system_prompt = build_system_prompt(
            anonymized_context=anonymized,
            knowledge_base=kb_text,
            variant=self._settings.prompt_variant,
        )
        user_prompt = (
            "Контекст сделки (анонимизировано):\n"
            f"{anonymized_crm}\n\n"
            "Сообщение клиента (анонимизировано):\n"
            f"{anonymized_msg}"
        )
        return ChatRequestDTO(
            system_prompt=system_prompt,
            user_message=user_prompt,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
        )

    def run(self, payload: ConsultationInput) -> ConsultationOutcome:
        anonymized, anonymized_crm, anonymized_msg = self._prepare_inputs(payload)
        provider_name, model_name = self._build_provider_signature()
        cache_key = ResponseCache.make_key(
            anonymized_input=anonymized,
            prompt_variant=self._settings.prompt_variant,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
            provider_name=provider_name,
            model_name=model_name,
        )

        # 1. Cache lookup
        cached = self._cache.get(cache_key)
        if cached is not None:
            outcome = OrchestrationResult(
                success=True,
                result=ChatResult(
                    content=cached.content, provider=cached.provider, model=cached.model
                ),
                error=None,
                anonymized=anonymized,
            )
            log_consultation_event(
                anonymized_input=anonymized,
                provider=cached.provider,
                model=cached.model,
                success=True,
                latency_ms=0,
                response_chars=len(cached.content),
                error="cache_hit",
            )
            return ConsultationOutcome(
                result=outcome, anonymized_input=anonymized, cache_hit=True
            )

        # 2. Cache miss → AI
        request = self._build_request(anonymized, anonymized_crm, anonymized_msg)

        started = time.perf_counter()
        outcome = self._orchestrator.complete(request, anonymized=anonymized)
        latency_ms = int((time.perf_counter() - started) * 1000)

        if outcome.success and outcome.result is not None:
            log_consultation_event(
                anonymized_input=anonymized,
                provider=outcome.result.provider,
                model=outcome.result.model,
                success=True,
                latency_ms=latency_ms,
                response_chars=len(outcome.result.content),
            )
            self._cache.put(
                cache_key,
                CacheEntry(
                    content=outcome.result.content,
                    provider=outcome.result.provider,
                    model=outcome.result.model,
                ),
            )
        else:
            log_consultation_event(
                anonymized_input=anonymized,
                provider=provider_name,
                model=model_name,
                success=False,
                latency_ms=latency_ms,
                response_chars=0,
                error=outcome.error,
            )

        return ConsultationOutcome(
            result=outcome, anonymized_input=anonymized, cache_hit=False
        )

    def stream_run(
        self, payload: ConsultationInput
    ) -> Generator[str, None, ConsultationOutcome]:
        """Стриминг ответа с fallback между провайдерами.

        Yields токены текста. Возвращаемое значение (после последнего yield) —
        ``ConsultationOutcome`` для логирования и кэширования.
        """
        anonymized, anonymized_crm, anonymized_msg = self._prepare_inputs(payload)
        provider_name, model_name = self._build_provider_signature()
        cache_key = ResponseCache.make_key(
            anonymized_input=anonymized,
            prompt_variant=self._settings.prompt_variant,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
            provider_name=provider_name,
            model_name=model_name,
        )

        # Cache hit → возвращаем целиком одним куском.
        cached = self._cache.get(cache_key)
        if cached is not None:
            yield cached.content
            outcome = OrchestrationResult(
                success=True,
                result=ChatResult(
                    content=cached.content, provider=cached.provider, model=cached.model
                ),
                error=None,
                anonymized=anonymized,
            )
            log_consultation_event(
                anonymized_input=anonymized,
                provider=cached.provider,
                model=cached.model,
                success=True,
                latency_ms=0,
                response_chars=len(cached.content),
                error="cache_hit",
            )
            return ConsultationOutcome(
                result=outcome, anonymized_input=anonymized, cache_hit=True
            )

        request = self._build_request(anonymized, anonymized_crm, anonymized_msg)
        started = time.perf_counter()
        gen = self._orchestrator.stream(request, anonymized=anonymized)
        buffer: list[str] = []
        try:
            while True:
                token = next(gen)
                buffer.append(token)
                yield token
        except StopIteration as stop:
            latency_ms = int((time.perf_counter() - started) * 1000)
            provider, chat_result, error = stop.value
            if chat_result is not None:
                outcome = OrchestrationResult(
                    success=True,
                    result=chat_result,
                    error=None,
                    anonymized=anonymized,
                )
                log_consultation_event(
                    anonymized_input=anonymized,
                    provider=provider,
                    model=model_name,
                    success=True,
                    latency_ms=latency_ms,
                    response_chars=len(chat_result.content),
                )
                self._cache.put(
                    cache_key,
                    CacheEntry(
                        content=chat_result.content,
                        provider=provider,
                        model=model_name,
                    ),
                )
                return ConsultationOutcome(
                    result=outcome, anonymized_input=anonymized, cache_hit=False
                )
            else:
                outcome = OrchestrationResult(
                    success=False, result=None, error=error, anonymized=anonymized
                )
                log_consultation_event(
                    anonymized_input=anonymized,
                    provider=provider_name,
                    model=model_name,
                    success=False,
                    latency_ms=latency_ms,
                    response_chars=0,
                    error=error,
                )
                return ConsultationOutcome(
                    result=outcome, anonymized_input=anonymized, cache_hit=False
                )