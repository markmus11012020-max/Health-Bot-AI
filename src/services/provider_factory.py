"""Composition root: wire services together (Dependency Injection)."""
from __future__ import annotations

from config.settings import Settings, get_settings
from src.ai.aitunnel_client import AITunnelClient
from src.ai.orchestrator import AIOrchestrator
from src.ai.yandex_client import YandexGPTClient
from src.core.anonymizer import PIIAnonymizer
from src.core.knowledge_base import KnowledgeBase
from src.services.consultation_service import ConsultationService


def build_consultation_service(settings: Settings | None = None) -> ConsultationService:
    """Construct the full service graph. Used by both app entry-point and tests."""
    settings = settings or get_settings()
    orchestrator = AIOrchestrator(
        providers=[
            AITunnelClient(settings),
            YandexGPTClient(settings),
        ]
    )
    return ConsultationService(
        settings=settings,
        orchestrator=orchestrator,
        knowledge_base=KnowledgeBase(),
        anonymizer=PIIAnonymizer(),
    )