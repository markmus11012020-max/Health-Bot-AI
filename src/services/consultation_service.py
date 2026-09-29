"""Consultation use-case: combines anonymization, prompt building, AI call."""
from __future__ import annotations

from dataclasses import dataclass

from config.prompts import build_system_prompt
from config.settings import Settings
from src.ai.base import ChatRequest
from src.ai.orchestrator import AIOrchestrator, OrchestrationResult
from src.core.anonymizer import PIIAnonymizer
from src.core.knowledge_base import KnowledgeBase


@dataclass(frozen=True)
class ConsultationInput:
    crm_context: str
    client_message: str


@dataclass(frozen=True)
class ConsultationOutcome:
    result: OrchestrationResult
    anonymized_input: str


class ConsultationService:
    """High-level use-case: produce AI guidance for a sales conversation."""

    def __init__(
        self,
        *,
        settings: Settings,
        orchestrator: AIOrchestrator,
        knowledge_base: KnowledgeBase,
        anonymizer: PIIAnonymizer,
    ) -> None:
        self._settings = settings
        self._orchestrator = orchestrator
        self._kb = knowledge_base
        self._anonymizer = anonymizer

    def run(self, payload: ConsultationInput) -> ConsultationOutcome:
        combined = f"{payload.crm_context}\n\nСообщение клиента: {payload.client_message}"
        anonymized = self._anonymizer.anonymize(combined)
        kb_text = self._kb.read()

        system_prompt = build_system_prompt(
            crm_context=payload.crm_context,
            knowledge_base=kb_text,
            anonymized_context=anonymized,
        )
        user_prompt = f"Клиент написал:\n{payload.client_message}"

        request = ChatRequest(
            system_prompt=system_prompt,
            user_message=user_prompt,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
        )
        outcome = self._orchestrator.complete(request, anonymized=anonymized)
        return ConsultationOutcome(result=outcome, anonymized_input=anonymized)