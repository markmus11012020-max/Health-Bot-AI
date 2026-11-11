"""Consultation use-case: anonymize, retrieve, generate, guard, cache, audit.

Pipeline:

1. Anonymize ``crm_context`` and ``client_message`` (152-ФЗ).
2. Run deterministic guardrails on the input.
3. Retrieve relevant knowledge-base chunks.
4. Look up a versioned cache entry.
5. Call the AI orchestrator (with fallback).
6. Parse and sanitize the answer.
7. Persist metadata-only audit and cache the safe answer.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Generator, Mapping
from dataclasses import dataclass, field, replace

from config.prompts import build_system_prompt, prompt_fingerprint
from config.settings import Settings
from src.ai.base import ChatRequest as ChatRequestDTO
from src.ai.base import ChatResult
from src.ai.orchestrator import AIOrchestrator, OrchestrationResult
from src.core.anonymizer import PIIAnonymizer
from src.core.audit_log import AuditLogger, NullAuditLogger
from src.core.business_rules import UpsellAdvisor, UpsellRecommendation
from src.core.knowledge_base import KnowledgeBase
from src.core.response_cache import CacheBackend, CacheEntry, ResponseCache
from src.core.response_parser import ParsedResponse, ResponseParser
from src.core.safety import SafetyGuard, SafetyVerdict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsultationInput:
    crm_context: str
    client_message: str
    conversation_id: str | None = None


@dataclass(frozen=True)
class ConsultationOutcome:
    """Result plus diagnostics for UI, API and audit."""

    result: OrchestrationResult
    anonymized_input: str
    cache_hit: bool = False
    request_id: str = ""
    citations: tuple[str, ...] = field(default_factory=tuple)
    safety_flags: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.8
    latency_ms: int = 0
    pii_counts: Mapping[str, int] = field(default_factory=dict)


class ConsultationService:
    """High-level use-case: produce AI guidance for a sales conversation."""

    def __init__(
        self,
        *,
        settings: Settings,
        orchestrator: AIOrchestrator,
        knowledge_base: KnowledgeBase,
        anonymizer: PIIAnonymizer,
        cache: CacheBackend | None = None,
        safety: SafetyGuard | None = None,
        audit: AuditLogger | None = None,
        parser: ResponseParser | None = None,
        upsell: UpsellAdvisor | None = None,
    ) -> None:
        self._settings = settings
        self._orchestrator = orchestrator
        self._kb = knowledge_base
        self._anonymizer = anonymizer
        self._upsell = upsell or UpsellAdvisor()
        self._cache = cache or ResponseCache(
            maxsize=self._int_setting("cache_maxsize", 256),
            ttl_seconds=self._int_setting("cache_ttl_seconds", 86400),
        )
        self._safety = safety or SafetyGuard()
        self._audit = audit or NullAuditLogger()
        self._parser = parser or ResponseParser()

    @property
    def cache(self) -> CacheBackend:
        return self._cache

    # ------------------------------------------------------------------
    # Settings helpers (keep service testable with lightweight fakes)
    # ------------------------------------------------------------------
    def _str_setting(self, name: str, default: str) -> str:
        value = getattr(self._settings, name, default)
        return value if isinstance(value, str) and value else default

    def _int_setting(self, name: str, default: int) -> int:
        value = getattr(self._settings, name, default)
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    def _bool_setting(self, name: str, default: bool) -> bool:
        value = getattr(self._settings, name, default)
        return value if isinstance(value, bool) else default

    def _float_setting(self, name: str, default: float) -> float:
        value = getattr(self._settings, name, default)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default

    @property
    def prompt_variant(self) -> str:
        return self._str_setting("prompt_variant", "standard")

    @property
    def temperature(self) -> float:
        return self._float_setting("temperature", 0.2)

    @property
    def max_tokens(self) -> int:
        return self._int_setting("max_tokens", 800)

    # ------------------------------------------------------------------
    # Pipeline helpers
    # ------------------------------------------------------------------
    def _prepare_inputs(
        self, payload: ConsultationInput
    ) -> tuple[str, str, str, dict[str, int]]:
        """Anonymize both fields and return combined text plus counts."""
        crm_result = self._anonymizer.anonymize_detailed(payload.crm_context)
        msg_result = self._anonymizer.anonymize_detailed(payload.client_message)
        counts: dict[str, int] = {}
        for source in (crm_result.counts, msg_result.counts):
            for key, value in source.items():
                counts[key] = counts.get(key, 0) + int(value)

        anonymized = (
            f"CRM-контекст (анонимизировано): {crm_result.text}\n"
            f"Сообщение клиента (анонимизировано): {msg_result.text}"
        )
        return anonymized, crm_result.text, msg_result.text, counts

    def _provider_signature(self) -> tuple[str, str]:
        providers = getattr(self._orchestrator, "providers", []) or []
        if providers:
            provider = providers[0]
            model = getattr(provider, "model_name", "") or "unknown"
            return str(getattr(provider, "name", "unknown")), str(model)
        return "unknown", "unknown"

    def _build_request(
        self, anonymized: str, anonymized_crm: str, anonymized_msg: str
    ) -> tuple[ChatRequestDTO, tuple[str, ...]]:
        query = f"{anonymized_crm}\n{anonymized_msg}"
        context, citations = self._kb.context_for(query)
        system_prompt = build_system_prompt(
            anonymized_context=anonymized,
            knowledge_base=context,
            variant=self.prompt_variant,
        )
        user_prompt = (
            "Контекст сделки (анонимизировано):\n"
            f"{anonymized_crm}\n\n"
            "Сообщение клиента (анонимизировано):\n"
            f"{anonymized_msg}"
        )
        request = ChatRequestDTO(
            system_prompt=system_prompt,
            user_message=user_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return request, citations

    def _cache_key(
        self, anonymized: str, *, provider_name: str, model_name: str
    ) -> str:
        return ResponseCache.make_key(
            anonymized_input=anonymized,
            prompt_variant=self.prompt_variant,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            provider_name=provider_name,
            model_name=model_name,
            kb_version=str(getattr(self._kb, "version", "")),
            prompt_version=prompt_fingerprint(self.prompt_variant),
        )

    def _finalize(
        self,
        raw: str,
        input_verdict: SafetyVerdict,
        *,
        fallback_citations: tuple[str, ...] = (),
        fallback_upsell: UpsellRecommendation | None = None,
    ) -> tuple[ParsedResponse, str, tuple[str, ...]]:
        parsed = self._parser.parse(raw)
        manager_lower = (parsed.manager_tip or "").lower()
        if (
            fallback_upsell is not None
            and fallback_upsell.needs_upsell
            and (
                not parsed.manager_tip
                or "не сформирована" in manager_lower
                or "допродажа не требуется" in manager_lower
            )
        ):
            parsed = replace(
                parsed,
                manager_tip=fallback_upsell.text,
                needs_upsell_value=fallback_upsell.needs_upsell,
            )
        if self._bool_setting("guardrails_enabled", True):
            parsed, output_flags = self._safety.sanitize_output(
                parsed, input_verdict=input_verdict
            )
        else:
            output_flags = ()
        if not parsed.citations and fallback_citations:
            parsed = ParsedResponse(
                client_answer=parsed.client_answer,
                manager_tip=parsed.manager_tip,
                raw=parsed.raw,
                citations=fallback_citations,
                confidence=parsed.confidence,
                needs_upsell_value=parsed.needs_upsell_value,
            )
        flags = tuple(dict.fromkeys((*input_verdict.flags, *output_flags)))
        return parsed, parsed.to_text(), flags

    def _blocked_outcome(
        self,
        *,
        request_id: str,
        anonymized: str,
        verdict: SafetyVerdict,
        pii_counts: Mapping[str, int],
    ) -> ConsultationOutcome:
        parsed = self._safety.safe_refusal()
        result = OrchestrationResult(
            success=True,
            result=ChatResult(
                content=parsed.to_text(),
                provider="guardrails",
                model="deterministic",
            ),
            error=None,
            anonymized=anonymized,
        )
        self._audit.log_consultation(
            request_id=request_id,
            anonymized_input=anonymized,
            provider="guardrails",
            model="deterministic",
            success=True,
            latency_ms=0,
            response_chars=len(parsed.client_answer),
            cache_hit=False,
            pii_counts=dict(pii_counts),
            error=None,
        )
        return ConsultationOutcome(
            result=result,
            anonymized_input=anonymized,
            request_id=request_id,
            safety_flags=verdict.flags,
            confidence=0.0,
            pii_counts=pii_counts,
        )

    def _cached_outcome(
        self,
        *,
        entry: CacheEntry,
        request_id: str,
        anonymized: str,
        pii_counts: Mapping[str, int],
    ) -> ConsultationOutcome:
        result = OrchestrationResult(
            success=True,
            result=ChatResult(
                content=entry.content,
                provider=entry.provider,
                model=entry.model,
            ),
            error=None,
            anonymized=anonymized,
        )
        self._audit.log_consultation(
            request_id=request_id,
            anonymized_input=anonymized,
            provider=entry.provider,
            model=entry.model,
            success=True,
            latency_ms=0,
            response_chars=len(entry.content),
            cache_hit=True,
            pii_counts=dict(pii_counts),
        )
        return ConsultationOutcome(
            result=result,
            anonymized_input=anonymized,
            cache_hit=True,
            request_id=request_id,
            citations=entry.citations,
            safety_flags=entry.safety_flags,
            confidence=entry.confidence,
            pii_counts=pii_counts,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(
        self,
        payload: ConsultationInput,
        *,
        use_cache: bool = True,
        request_id: str | None = None,
    ) -> ConsultationOutcome:
        request_id = request_id or uuid.uuid4().hex
        anonymized, anonymized_crm, anonymized_msg, pii_counts = self._prepare_inputs(
            payload
        )
        verdict = self._safety.check_input(
            f"{payload.crm_context}\n{payload.client_message}"
        )
        if verdict.blocked:
            return self._blocked_outcome(
                request_id=request_id,
                anonymized=anonymized,
                verdict=verdict,
                pii_counts=pii_counts,
            )

        request, kb_citations = self._build_request(
            anonymized, anonymized_crm, anonymized_msg
        )
        fallback_upsell = self._upsell.recommend(
            crm_context=anonymized_crm, client_message=anonymized_msg
        )
        provider_name, model_name = self._provider_signature()
        cache_key = self._cache_key(
            anonymized, provider_name=provider_name, model_name=model_name
        )

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return self._cached_outcome(
                    entry=cached,
                    request_id=request_id,
                    anonymized=anonymized,
                    pii_counts=pii_counts,
                )

        started = time.perf_counter()
        outcome = self._orchestrator.complete(request, anonymized=anonymized)
        latency_ms = int((time.perf_counter() - started) * 1000)

        if outcome.success and outcome.result is not None:
            parsed, safe_content, safety_flags = self._finalize(
                outcome.result.content,
                verdict,
                fallback_citations=kb_citations,
                fallback_upsell=fallback_upsell,
            )
            result = ChatResult(
                content=safe_content,
                provider=outcome.result.provider,
                model=outcome.result.model,
                prompt_tokens=outcome.result.prompt_tokens,
                completion_tokens=outcome.result.completion_tokens,
            )
            final_outcome = OrchestrationResult(
                success=True,
                result=result,
                error=None,
                anonymized=anonymized,
            )
            self._audit.log_consultation(
                request_id=request_id,
                anonymized_input=anonymized,
                provider=result.provider,
                model=result.model,
                success=True,
                latency_ms=latency_ms,
                response_chars=len(safe_content),
                cache_hit=False,
                pii_counts=pii_counts,
            )
            if use_cache:
                self._cache.put(
                    cache_key,
                    CacheEntry(
                        content=safe_content,
                        provider=result.provider,
                        model=result.model,
                        citations=parsed.citations or kb_citations,
                        confidence=parsed.confidence,
                        safety_flags=safety_flags,
                    ),
                )
            return ConsultationOutcome(
                result=final_outcome,
                anonymized_input=anonymized,
                request_id=request_id,
                citations=parsed.citations or kb_citations,
                safety_flags=safety_flags,
                confidence=parsed.confidence,
                latency_ms=latency_ms,
                pii_counts=pii_counts,
            )

        self._audit.log_consultation(
            request_id=request_id,
            anonymized_input=anonymized,
            provider=provider_name,
            model=model_name,
            success=False,
            latency_ms=latency_ms,
            response_chars=0,
            cache_hit=False,
            pii_counts=pii_counts,
            error=outcome.error,
        )
        return ConsultationOutcome(
            result=outcome,
            anonymized_input=anonymized,
            request_id=request_id,
            safety_flags=verdict.flags,
            latency_ms=latency_ms,
            pii_counts=pii_counts,
        )

    def stream_run(
        self,
        payload: ConsultationInput,
        *,
        use_cache: bool = True,
        request_id: str | None = None,
    ) -> Generator[str, None, ConsultationOutcome]:
        """Stream tokens, then return the final (sanitized) outcome.

        Note: tokens are emitted as they arrive.  The final outcome contains the
        sanitized canonical text; clients should replace the preview with it.
        """
        request_id = request_id or uuid.uuid4().hex
        anonymized, anonymized_crm, anonymized_msg, pii_counts = self._prepare_inputs(
            payload
        )
        verdict = self._safety.check_input(
            f"{payload.crm_context}\n{payload.client_message}"
        )
        if verdict.blocked:
            blocked = self._blocked_outcome(
                request_id=request_id,
                anonymized=anonymized,
                verdict=verdict,
                pii_counts=pii_counts,
            )
            yield blocked.result.result.content if blocked.result.result else ""
            return blocked

        request, kb_citations = self._build_request(
            anonymized, anonymized_crm, anonymized_msg
        )
        fallback_upsell = self._upsell.recommend(
            crm_context=anonymized_crm, client_message=anonymized_msg
        )
        provider_name, model_name = self._provider_signature()
        cache_key = self._cache_key(
            anonymized, provider_name=provider_name, model_name=model_name
        )

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                yield cached.content
                return self._cached_outcome(
                    entry=cached,
                    request_id=request_id,
                    anonymized=anonymized,
                    pii_counts=pii_counts,
                )

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
                parsed, safe_content, safety_flags = self._finalize(
                    chat_result.content,
                    verdict,
                    fallback_citations=kb_citations,
                    fallback_upsell=fallback_upsell,
                )
                result = ChatResult(
                    content=safe_content,
                    provider=provider or chat_result.provider,
                    model=chat_result.model or model_name,
                )
                outcome = OrchestrationResult(
                    success=True, result=result, error=None, anonymized=anonymized
                )
                self._audit.log_consultation(
                    request_id=request_id,
                    anonymized_input=anonymized,
                    provider=result.provider,
                    model=result.model,
                    success=True,
                    latency_ms=latency_ms,
                    response_chars=len(safe_content),
                    cache_hit=False,
                    pii_counts=pii_counts,
                )
                if use_cache:
                    self._cache.put(
                        cache_key,
                        CacheEntry(
                            content=safe_content,
                            provider=result.provider,
                            model=result.model,
                            citations=parsed.citations or kb_citations,
                            confidence=parsed.confidence,
                            safety_flags=safety_flags,
                        ),
                    )
                return ConsultationOutcome(
                    result=outcome,
                    anonymized_input=anonymized,
                    request_id=request_id,
                    citations=parsed.citations or kb_citations,
                    safety_flags=safety_flags,
                    confidence=parsed.confidence,
                    latency_ms=latency_ms,
                    pii_counts=pii_counts,
                )

            failure = OrchestrationResult(
                success=False, result=None, error=error, anonymized=anonymized
            )
            self._audit.log_consultation(
                request_id=request_id,
                anonymized_input=anonymized,
                provider=provider_name,
                model=model_name,
                success=False,
                latency_ms=latency_ms,
                response_chars=0,
                cache_hit=False,
                pii_counts=pii_counts,
                error=error,
            )
            return ConsultationOutcome(
                result=failure,
                anonymized_input=anonymized,
                request_id=request_id,
                safety_flags=verdict.flags,
                latency_ms=latency_ms,
                pii_counts=pii_counts,
            )
