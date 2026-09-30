"""FastAPI webhook для интеграции с AmoCRM и другими внешними системами.

Эндпоинт принимает JSON с обращением клиента и возвращает структурированный
ответ с двумя блоками: вежливый ответ клиенту + подсказка менеджеру.

Запуск:
    uvicorn src.api.webhook:app --host 0.0.0.0 --port 8080

Тест:
    curl -X POST http://localhost:8080/consult \\
         -H "Content-Type: application/json" \\
         -d '{"crm_context":"...", "client_message":"...", "provider":"aitunnel"}'
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config.settings import get_settings
from src.core.response_parser import ResponseParser
from src.services.consultation_service import ConsultationInput, ConsultationService
from src.services.provider_factory import build_consultation_service

logger = logging.getLogger("ocx.webhook")
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ConsultRequest(BaseModel):
    """Тело входящего запроса от AmoCRM / внешнего сервиса."""

    crm_context: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Контекст сделки (карточка клиента, история заказов). ПД допустимы — анонимизируются на сервере.",
    )
    client_message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Последнее сообщение клиента в диалоге.",
    )
    provider: Literal["aitunnel", "yandex"] | None = Field(
        default=None,
        description="Переопределить AI-провайдер (по умолчанию — из settings).",
    )
    prompt_variant: Literal["standard", "expert", "warm"] | None = Field(
        default=None,
        description="Переопределить A/B-вариант промпта.",
    )
    use_cache: bool = Field(
        default=True,
        description="Использовать кэш ответов (по умолчанию — да).",
    )


class ConsultResponse(BaseModel):
    """Структурированный ответ — готов для вставки в AmoCRM-чат."""

    client_answer: str = Field(..., description="Текст для отправки клиенту.")
    manager_tip: str = Field(..., description="Подсказка по допродаже для менеджера.")
    needs_upsell: bool = Field(..., description="Требуется ли допродажа.")
    provider: str = Field(..., description="Какой AI-провайдер сгенерировал ответ.")
    model: str = Field(..., description="Имя модели.")
    cache_hit: bool = Field(..., description="Был ли ответ из кэша.")
    response_chars: int = Field(..., description="Длина сгенерированного ответа (для аудита).")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    providers: list[str]
    cache_size: int
    prompt_variants: list[str]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Health-Bot-AI Webhook",
    description=(
        "Webhook для интеграции с AmoCRM и другими CRM. "
        "Принимает обращение клиента → возвращает вежливый ответ + "
        "подсказку по допродажам для менеджера. "
        "Все ПД анонимизируются до отправки в LLM (152-ФЗ)."
    ),
    version="1.0.0",
)

# Service singleton (Streamlit rerun-safe, FastAPI — single process)
_settings = get_settings()
_service: ConsultationService | None = None


def get_service() -> ConsultationService:
    """Lazy-init ConsultationService."""
    global _service
    if _service is None:
        _service = build_consultation_service(_settings, provider_name="aitunnel")
    return _service


def _build_response_payload(outcome) -> ConsultResponse:  # type: ignore[no-untyped-def]
    if not outcome.result.success or outcome.result.result is None:
        raise HTTPException(
            status_code=502,
            detail=f"AI provider failed: {outcome.result.error or 'unknown'}",
        )
    parsed = ResponseParser().parse(outcome.result.result.content)
    return ConsultResponse(
        client_answer=parsed.client_answer,
        manager_tip=parsed.manager_tip,
        needs_upsell=parsed.needs_upsell,
        provider=outcome.result.result.provider,
        model=outcome.result.result.model,
        cache_hit=outcome.cache_hit,
        response_chars=len(outcome.result.result.content),
    )


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Health-check для load-balancer / k8s liveness probe."""
    from config.prompts import list_variants
    from src.services.provider_factory import PROVIDER_REGISTRY

    svc = get_service()
    return HealthResponse(
        status="ok",
        providers=list(PROVIDER_REGISTRY.keys()),
        cache_size=svc.cache.stats()["size"],
        prompt_variants=list_variants(),
    )


@app.post("/consult", response_model=ConsultResponse, tags=["consultation"])
def consult(req: ConsultRequest) -> ConsultResponse:
    """Главный endpoint: обработать обращение клиента.

    152-ФЗ: ПД в полях crm_context/client_message анонимизируются до отправки в LLM.
    """
    # Опциональное переопределение провайдера на один запрос.
    if req.provider:
        settings = _settings
        service = build_consultation_service(settings, provider_name=req.provider)
    else:
        service = get_service()

    outcome = service.run(
        ConsultationInput(
            crm_context=req.crm_context,
            client_message=req.client_message,
        )
    )
    return _build_response_payload(outcome)


@app.post("/consult/clear-cache", tags=["consultation"])
def clear_cache() -> dict[str, int]:
    """Сбросить кэш ответов (полезно для тестов)."""
    svc = get_service()
    before = svc.cache.stats()["size"]
    svc.cache.clear()
    return {"cleared_entries": before}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)