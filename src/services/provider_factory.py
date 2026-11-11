"""Composition root: wire the service graph (Dependency Injection)."""
from __future__ import annotations

import logging
from collections.abc import Callable

from config.settings import Settings, get_settings
from src.ai.aitunnel_client import AITunnelClient
from src.ai.base import AIClient
from src.ai.orchestrator import AIOrchestrator
from src.ai.yandex_client import YandexGPTClient
from src.core.anonymizer import PIIAnonymizer
from src.core.audit_log import AuditLogger, build_audit_logger
from src.core.db import get_database
from src.core.knowledge_base import KnowledgeBase
from src.core.response_cache import CacheBackend, build_cache
from src.core.safety import SafetyGuard
from src.services.consultation_service import ConsultationService

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY: dict[str, Callable[[Settings], AIClient]] = {
    "aitunnel": AITunnelClient,
    "yandex": YandexGPTClient,
}

DEFAULT_PROVIDER = "aitunnel"


def _build_providers(settings: Settings, provider_name: str) -> list[AIClient]:
    """Build the selected provider and optional fallback chain."""
    selected_key = provider_name.lower()
    selected_cls = PROVIDER_REGISTRY.get(selected_key, AITunnelClient)
    providers: list[AIClient] = [selected_cls(settings)]

    if not getattr(settings, "enable_fallback", True):
        return providers

    for key, cls in PROVIDER_REGISTRY.items():
        if key == selected_key:
            continue
        # Avoid instantiating a provider that has no credentials at all.
        if key == "yandex" and not (
            getattr(settings, "yandex_api_key", "")
            or getattr(settings, "yandex_iam_token", "")
        ):
            continue
        if key == "aitunnel" and not getattr(settings, "aitunnel_api_key", ""):
            continue
        providers.append(cls(settings))
    return providers


def build_consultation_service(
    settings: Settings | None = None,
    *,
    provider_name: str = DEFAULT_PROVIDER,
    cache: CacheBackend | None = None,
    audit: AuditLogger | None = None,
    knowledge_base: KnowledgeBase | None = None,
) -> ConsultationService:
    """Construct the service graph with a selected provider and fallback chain."""
    settings = settings or get_settings()

    providers = _build_providers(settings, provider_name)
    orchestrator = AIOrchestrator(providers=providers)

    if cache is None:
        cache = build_cache(
            redis_url=getattr(settings, "redis_url", ""),
            maxsize=getattr(settings, "cache_maxsize", 256),
            ttl_seconds=getattr(settings, "cache_ttl_seconds", 86400),
        )
    if audit is None:
        try:
            database = get_database(getattr(settings, "database_url", "sqlite:///data/health_bot.db"))
            audit = build_audit_logger(database)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Audit database unavailable, using null logger: %s", exc)
            audit = build_audit_logger(None)

    kb = knowledge_base or KnowledgeBase(
        getattr(settings, "kb_path", KnowledgeBase.DEFAULT_PATH),
        top_k=getattr(settings, "kb_top_k", 3),
        max_chars=getattr(settings, "kb_max_chars", 6000),
    )

    return ConsultationService(
        settings=settings,
        orchestrator=orchestrator,
        knowledge_base=kb,
        anonymizer=PIIAnonymizer(),
        cache=cache,
        safety=SafetyGuard(),
        audit=audit,
    )
