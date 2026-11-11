"""Deterministic safety guardrails for a health-related sales assistant.

The guard is intentionally simple and explainable:

* detect prompt-injection attempts in user input;
* detect medical red flags that require a doctor referral;
* soften prohibited medical claims in LLM output;
* add a disclaimer and red-flag recommendation.

It complements, but does not replace, a full moderation service.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.response_parser import ParsedResponse

DISCLAIMER = "Не является медицинской рекомендацией."

_INJECTION_STRONG = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"forget\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"(reveal|show|print|repeat)\s+(the\s+)?(system\s+)?prompt", re.I),
    re.compile(r"jailbreak|DAN\s+mode|developer\s+mode", re.I),
    re.compile(r"игнорируй\s+(все\s+)?(предыдущие\s+)?инструкции", re.I),
    re.compile(r"забудь\s+(все\s+)?(предыдущие\s+)?инструкции", re.I),
    re.compile(r"(покажи|раскрой|выведи)\s+(системный\s+)?промпт", re.I),
    re.compile(r"режим\s+DAN|режим\s+разработчика", re.I),
)

_INJECTION_SOFT = (
    re.compile(r"ты\s+теперь|представь,?\s+что\s+ты|act\s+as|pretend\s+to\s+be", re.I),
    re.compile(r"role\s*play|ролевая\s+игра", re.I),
)

_RED_FLAGS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pregnancy", re.compile(r"беременн|кормлен|грудное\s+вскармливан", re.I)),
    ("chronic", re.compile(r"хроническ|диабет|онколог|сердечн|давлен", re.I)),
    ("medication", re.compile(r"лекарств|препарат|антибиотик|гормон", re.I)),
    ("allergy", re.compile(r"аллерг", re.I)),
    ("acute", re.compile(r"остр(ая|ый|ое)\s+(боль|симптом)|кровотечен|кровь", re.I)),
    ("child", re.compile(r"реб[её]нок|детск|младен|подрост", re.I)),
)

_BANNED_CLAIMS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bлечит\b", re.I), "может поддерживать"),
    (re.compile(r"\bизлечивает\b", re.I), "может поддерживать"),
    (re.compile(r"\bгарантирует\b", re.I), "может способствовать"),
    (re.compile(r"100\s*%", re.I), "в большинстве случаев"),
    (re.compile(r"без\s+побочных\s+эффектов", re.I), "переносится индивидуально"),
    (re.compile(r"полностью\s+безопасн\w*", re.I), "требует индивидуальной оценки"),
    (re.compile(r"подходит\s+всем", re.I), "подходит не всем"),
    (re.compile(r"заменит\s+врача", re.I), "не заменяет врача"),
)


@dataclass(frozen=True)
class SafetyVerdict:
    """Result of an input/output safety check."""

    blocked: bool = False
    flags: tuple[str, ...] = ()
    red_flags: tuple[str, ...] = ()

    @property
    def has_flags(self) -> bool:
        return bool(self.flags or self.red_flags)


class SafetyGuard:
    """Deterministic, testable guardrails."""

    def check_input(self, text: str) -> SafetyVerdict:
        if not text:
            return SafetyVerdict()
        flags: list[str] = []
        if any(p.search(text) for p in _INJECTION_STRONG):
            flags.append("prompt_injection_blocked")
        elif any(p.search(text) for p in _INJECTION_SOFT):
            flags.append("prompt_injection_suspected")

        red: list[str] = [name for name, pattern in _RED_FLAGS if pattern.search(text)]
        if red:
            flags.append("medical_red_flag")

        return SafetyVerdict(
            blocked="prompt_injection_blocked" in flags,
            flags=tuple(dict.fromkeys(flags)),
            red_flags=tuple(red),
        )

    def sanitize_output(
        self,
        parsed: ParsedResponse,
        *,
        input_verdict: SafetyVerdict | None = None,
    ) -> tuple[ParsedResponse, tuple[str, ...]]:
        """Soften prohibited claims, add disclaimer and red-flag advice."""
        flags: list[str] = list(input_verdict.flags) if input_verdict else []
        client = parsed.client_answer or ""
        manager = parsed.manager_tip or ""

        for pattern, replacement in _BANNED_CLAIMS:
            client, n1 = pattern.subn(replacement, client)
            manager, n2 = pattern.subn(replacement, manager)
            if n1 or n2:
                flags.append("medical_claim_softened")

        if input_verdict and input_verdict.red_flags:
            if "врач" not in client.lower():
                client = (
                    client.rstrip()
                    + " Рекомендую согласовать приём с врачом, особенно с учётом "
                    "индивидуальных особенностей."
                )

        if DISCLAIMER.lower() not in client.lower():
            client = f"{client.rstrip()} {DISCLAIMER}".strip()

        return (
            ParsedResponse(
                client_answer=client.strip(),
                manager_tip=manager.strip(),
                raw=parsed.raw,
                citations=parsed.citations,
                confidence=parsed.confidence,
            ),
            tuple(dict.fromkeys(flags)),
        )

    @staticmethod
    def safe_refusal() -> ParsedResponse:
        return ParsedResponse(
            client_answer=(
                "Извините, я не могу выполнить этот запрос. "
                "Пожалуйста, переформулируйте вопрос о продуктах, доставке или акциях."
            ),
            manager_tip=(
                "Запрос заблокирован guardrails как попытка prompt injection. "
                "Уточните у клиента вопрос вручную."
            ),
            raw="",
            citations=(),
            confidence=0.0,
            needs_upsell_value=False,
        )
