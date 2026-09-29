"""Composition root: wire services together (Dependency Injection).

Test variant: a single provider is selected via UI. No fallback chain.
"""
from __future__ import annotations

from config.settings import Settings, get_settings
from src.ai.aitunnel_client import AITunnelClient
from src.ai.base import AIClient
from src.ai.orchestrator import AIOrchestrator
from src.ai.yandex_client import YandexGPTClient
from src.core.anonymizer import PIIAnonymizer
from src.core.knowledge_base import KnowledgeBase
from src.services.consultation_service import ConsultationService

# Registry of available providers (test mode — only one is active at a time).
PROVIDER_REGISTRY: dict[str, type[AIClient]] = {
    "aitunnel": AITunnelClient,
    "yandex": YandexGPTClient,
}

DEFAULT_PROVIDER = "aitunnel"


def build_consultation_service(
    settings: Settings | None = None,
    *,
    provider_name: str = DEFAULT_PROVIDER,
) -> ConsultationService:
    """Construct the service graph with a single selected provider.

    Parameters
    ----------
    settings : Settings | None
        App configuration. Loaded from env if omitted.
    provider_name : str
        Key from ``PROVIDER_REGISTRY``. Unknown values fall back to AITunnel.
    """
    settings = settings or get_settings()
    provider_cls = PROVIDER_REGISTRY.get(provider_name.lower(), AITunnelClient)
    orchestrator = AIOrchestrator(providers=[provider_cls(settings)])
    return ConsultationService(
        settings=settings,
        orchestrator=orchestrator,
        knowledge_base=KnowledgeBase(),
        anonymizer=PIIAnonymizer(),
    )