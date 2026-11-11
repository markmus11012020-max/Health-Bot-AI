"""FastAPI webhook/API for CRM and external integrations.

Endpoints
---------
GET  /health                  liveness
GET  /ready                   readiness (DB, cache, providers)
POST /v1/consult              process one consultation
POST /v1/consult/stream       SSE token stream
POST /v1/feedback             manager feedback
POST /v1/admin/cache/clear    protected cache reset

Legacy aliases ``/consult`` and ``/consult/clear-cache`` are kept for
backward compatibility.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from config.prompts import list_variants
from config.settings import get_settings
from src.core.anonymizer import PIIAnonymizer
from src.core.audit_log import build_audit_logger
from src.core.db import get_database
from src.core.idempotency import IdempotencyStore
from src.core.rate_limit import RateLimiter
from src.core.response_cache import build_cache
from src.core.response_parser import ResponseParser
from src.services.consultation_service import ConsultationInput, ConsultationService
from src.services.provider_factory import (
    DEFAULT_PROVIDER,
    PROVIDER_REGISTRY,
    build_consultation_service,
)

logger = logging.getLogger("ocx.webhook")
logging.basicConfig(level=logging.INFO)

settings = get_settings()
_database = get_database(settings.database_url)
_cache = build_cache(
    redis_url=settings.redis_url,
    maxsize=settings.cache_maxsize,
    ttl_seconds=settings.cache_ttl_seconds,
)
_audit = build_audit_logger(_database)
_rate_limiter = RateLimiter(
    settings.rate_limit_requests, settings.rate_limit_window_seconds
)
_idempotency = IdempotencyStore(settings.idempotency_ttl_seconds)
_services: dict[tuple[str, str], ConsultationService] = {}
_services_lock = threading.Lock()
_anonymizer = PIIAnonymizer()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _database.init()
    yield


app = FastAPI(
    title="Health-Bot-AI API",
    description=(
        "ИИ-ассистент отдела продаж OCX: ответ клиенту + подсказка по "
        "допродажам. ПДн анонимизируются до отправки в LLM (152-ФЗ)."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------


class ConsultRequest(BaseModel):
    crm_context: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Контекст сделки. ПДн допустимы — анонимизируются на сервере.",
    )
    client_message: str = Field(
        ..., min_length=1, max_length=4000, description="Последнее сообщение клиента."
    )
    provider: Literal["aitunnel", "yandex"] | None = Field(
        default=None, description="Переопределить AI-провайдер."
    )
    prompt_variant: Literal["standard", "expert", "warm"] | None = Field(
        default=None, description="Переопределить A/B-вариант промпта."
    )
    use_cache: bool = Field(default=True, description="Использовать кэш ответов.")
    conversation_id: str | None = Field(
        default=None, max_length=128, description="Идентификатор диалога (для истории)."
    )

    @field_validator("crm_context", "client_message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be blank")
        return value


class ConsultResponse(BaseModel):
    request_id: str
    client_answer: str
    manager_tip: str
    needs_upsell: bool
    citations: list[str] = Field(default_factory=list)
    confidence: float = 0.8
    safety_flags: list[str] = Field(default_factory=list)
    provider: str
    model: str
    cache_hit: bool
    response_chars: int
    usage: dict[str, int] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=64)
    rating: int = Field(..., ge=1, le=5)
    correct: bool | None = None
    comment: str | None = Field(default=None, max_length=2000)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    providers: list[str]
    cache_size: int
    prompt_variants: list[str]


# ---------------------------------------------------------------------------
# Auth / rate limit helpers
# ---------------------------------------------------------------------------


def _check_api_key(api_key: str | None) -> None:
    configured = settings.api_key
    if configured:
        if not api_key or not secrets.compare_digest(api_key, configured):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    elif settings.is_production:
        raise HTTPException(status_code=503, detail="API_KEY is not configured")


def _check_admin_key(admin_key: str | None) -> None:
    configured = settings.admin_api_key
    if configured:
        if not admin_key or not secrets.compare_digest(admin_key, configured):
            raise HTTPException(status_code=403, detail="Invalid or missing admin key")
    elif settings.is_production:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")


def _client_id(request: Request, api_key: str | None) -> str:
    return api_key or (request.client.host if request.client else "anonymous")


def _check_rate(request: Request, api_key: str | None) -> None:
    key = _client_id(request, api_key)
    if not _rate_limiter.allow(key):
        retry_after = _rate_limiter.retry_after(key)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def _idempotency_key(api_key: str | None, header_value: str | None) -> str | None:
    if not header_value:
        return None
    raw = f"{api_key or 'anonymous'}:{header_value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or uuid.uuid4().hex)


# ---------------------------------------------------------------------------
# Service registry
# ---------------------------------------------------------------------------


def get_service(
    provider: str | None = None, prompt_variant: str | None = None
) -> ConsultationService:
    """Return a cached service instance for a provider/prompt combination."""
    provider_key = (provider or DEFAULT_PROVIDER).lower()
    variant_key = (prompt_variant or settings.prompt_variant).lower()
    key = (provider_key, variant_key)
    with _services_lock:
        service = _services.get(key)
        if service is None:
            local_settings = replace(settings, prompt_variant=variant_key)
            service = build_consultation_service(
                local_settings,
                provider_name=provider_key,
                cache=_cache,
                audit=_audit,
            )
            _services[key] = service
        return service


def _response_from_outcome(outcome: Any, request_id: str) -> ConsultResponse:
    if not outcome.result.success or outcome.result.result is None:
        raise HTTPException(
            status_code=502,
            detail=f"AI provider failed: {outcome.result.error or 'unknown error'}",
        )
    raw = outcome.result.result.content
    parsed = ResponseParser().parse(raw)
    return ConsultResponse(
        request_id=request_id,
        client_answer=parsed.client_answer,
        manager_tip=parsed.manager_tip,
        needs_upsell=parsed.needs_upsell,
        citations=list(outcome.citations or parsed.citations),
        confidence=float(outcome.confidence),
        safety_flags=list(outcome.safety_flags),
        provider=outcome.result.result.provider,
        model=outcome.result.result.model,
        cache_hit=outcome.cache_hit,
        response_chars=len(raw),
        usage={
            "prompt_tokens": int(
                getattr(outcome.result.result, "prompt_tokens", 0) or 0
            ),
            "completion_tokens": int(
                getattr(outcome.result.result, "completion_tokens", 0) or 0
            ),
        },
    )


def _execute_consult(
    req: ConsultRequest,
    request: Request,
    *,
    api_key: str | None,
    idempotency_key: str | None,
) -> ConsultResponse:
    _check_rate(request, api_key)
    request_id = _request_id(request)
    replay_key = _idempotency_key(api_key, idempotency_key)
    if replay_key:
        cached = _idempotency.get(replay_key)
        if cached is not None:
            return ConsultResponse.model_validate(cached)

    service = get_service(req.provider, req.prompt_variant)
    outcome = service.run(
        ConsultationInput(
            crm_context=req.crm_context,
            client_message=req.client_message,
            conversation_id=req.conversation_id,
        ),
        use_cache=req.use_cache,
        request_id=request_id,
    )
    response = _response_from_outcome(outcome, request_id)
    if replay_key:
        _idempotency.put(replay_key, response.model_dump())
    return response


# ---------------------------------------------------------------------------
# Middleware / error handling
# ---------------------------------------------------------------------------


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    incoming = (request.headers.get("X-Request-ID") or "").strip()
    # Keep audit/DB fields bounded and free of control characters.
    safe_incoming = "".join(ch for ch in incoming if ch.isprintable())[:64]
    request.state.request_id = safe_incoming or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    # Never log the exception message: it may contain user-provided PII.
    logger.error(
        "Unhandled error request_id=%s type=%s", request_id, type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "Health-Bot-AI", "docs": "/docs", "health": "/health"}


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        providers=list(PROVIDER_REGISTRY.keys()),
        cache_size=int(_cache.stats()["size"]),
        prompt_variants=list_variants(),
    )


@app.get("/ready", tags=["meta"])
def ready() -> JSONResponse:
    db_ok = _database.health()
    providers = {
        "aitunnel": "configured" if settings.has_aitunnel else "not_configured",
        "yandex": "configured" if settings.has_yandex else "not_configured",
    }
    ready_status = db_ok and (settings.has_aitunnel or settings.has_yandex)
    if settings.is_production and not settings.api_key:
        ready_status = False
    payload = {
        "status": "ready" if ready_status else "not_ready",
        "database": "ok" if db_ok else "unavailable",
        "cache": _cache.stats(),
        "providers": providers,
        "issues": settings.validate(),
    }
    return JSONResponse(status_code=200 if ready_status else 503, content=payload)


@app.post("/v1/consult", response_model=ConsultResponse, tags=["consultation"])
def consult(
    req: ConsultRequest,
    request: Request,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ConsultResponse:
    _check_api_key(api_key)
    return _execute_consult(
        req, request, api_key=api_key, idempotency_key=idempotency_key
    )


@app.post("/consult", response_model=ConsultResponse, include_in_schema=False)
def legacy_consult(
    req: ConsultRequest,
    request: Request,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ConsultResponse:
    _check_api_key(api_key)
    return _execute_consult(
        req, request, api_key=api_key, idempotency_key=idempotency_key
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/v1/consult/stream", tags=["consultation"])
def consult_stream(
    req: ConsultRequest,
    request: Request,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> StreamingResponse:
    _check_api_key(api_key)
    _check_rate(request, api_key)
    request_id = _request_id(request)
    service = get_service(req.provider, req.prompt_variant)
    payload = ConsultationInput(
        crm_context=req.crm_context,
        client_message=req.client_message,
        conversation_id=req.conversation_id,
    )

    def event_generator() -> Iterator[str]:
        yield _sse(
            "meta",
            {
                "request_id": request_id,
                "provider": req.provider or DEFAULT_PROVIDER,
                "prompt_variant": req.prompt_variant or settings.prompt_variant,
            },
        )
        try:
            stream = service.stream_run(
                payload, use_cache=req.use_cache, request_id=request_id
            )
            while True:
                try:
                    token = next(stream)
                except StopIteration as stop:
                    outcome = stop.value
                    break
                yield _sse("token", {"text": token})

            if outcome.result.success and outcome.result.result is not None:
                yield _sse(
                    "done",
                    {
                        "request_id": request_id,
                        "content": outcome.result.result.content,
                        "provider": outcome.result.result.provider,
                        "model": outcome.result.result.model,
                        "cache_hit": outcome.cache_hit,
                        "citations": list(outcome.citations),
                        "safety_flags": list(outcome.safety_flags),
                    },
                )
            else:
                yield _sse(
                    "error",
                    {
                        "request_id": request_id,
                        "detail": outcome.result.error or "AI provider failed",
                    },
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Streaming failed request_id=%s type=%s", request_id, type(exc).__name__
            )
            yield _sse(
                "error",
                {"request_id": request_id, "detail": "stream failed"},
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )


@app.post("/v1/feedback", tags=["feedback"])
def feedback(
    req: FeedbackRequest,
    request: Request,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> dict[str, Any]:
    _check_api_key(api_key)
    _check_rate(request, api_key)
    safe_comment = _anonymizer.anonymize(req.comment) if req.comment else None
    feedback_id = _database.record_feedback(
        request_id=req.request_id,
        rating=req.rating,
        correct=req.correct,
        comment=safe_comment,
    )
    return {"feedback_id": feedback_id, "status": "saved"}


@app.post("/v1/admin/cache/clear", tags=["admin"])
def clear_cache(
    admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> dict[str, int]:
    _check_admin_key(admin_key)
    before = int(_cache.stats()["size"])
    _cache.clear()
    _idempotency.clear()
    return {"cleared_entries": before}


@app.post("/consult/clear-cache", include_in_schema=False)
def legacy_clear_cache(
    admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> dict[str, int]:
    return clear_cache(admin_key)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
