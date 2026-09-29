"""PII anonymization (152-ФЗ compliance)."""
from __future__ import annotations

import re
from typing import Iterable

# Russian first names commonly seen in B2B retail data.
_DEFAULT_NAMES = (
    "Мария|Машей|Машенька|Мария Ивановна|Маша|"
    "Иван Иванович|Ваня|Ванек|"
    "Алексей|Алексей Сергеевич|Леша|"
    "Елена|Елена Петровна|Lena|"
    "Ольга|Ольга Николаевна|Olga"
)

# Built once at import time — regex compilation is expensive.
# Two patterns so we can keep case-insensitive matching for the explicit name
# list while requiring capitalized initials for the generic "Firstname Lastname" rule.
_NAME_EXPLICIT_PATTERN = re.compile(rf"\b({_DEFAULT_NAMES})\b", re.IGNORECASE)
_NAME_GENERIC_PATTERN = re.compile(r"\b[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+\b")

_PHONE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\+7\s?\(?\d{3}\)?\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}",
        r"8\s?\(?\d{3}\)?\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}",
        r"\+?\d{11}",
        r"\d{3}[-\s]\d{3}[-\s]\d{2}[-\s]\d{2}",
        r"\(\d{3}\)\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}",
    )
)

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_ADDRESS_PATTERN = re.compile(
    r"(?:\d+\s+)?[А-ЯЁа-яё][А-ЯЁа-яё\s]+(?:улица|ул\.|переулок|пер\.|"
    r"проспект|пр-т|бульвар|б-р|шоссе|область|регион)\s*,?\s*"
    r"(?:дом|д\.|квартира|кв\.)?\s*\d*",
    re.IGNORECASE,
)


class PIIAnonymizer:
    """Mask personal data before sending to a third-party LLM.

    Stateless and thread-safe. Substitution rules are pluggable via
    the constructor so additional PII types can be added without touching
    the call sites.
    """

    PLACEHOLDER_NAME = "[Клиент]"
    PLACEHOLDER_PHONE = "[Телефон]"
    PLACEHOLDER_EMAIL = "[Email]"
    PLACEHOLDER_ADDRESS = "[Адрес]"

    def __init__(
        self,
        *,
        name_pattern: re.Pattern[str] | None = None,
        name_generic_pattern: re.Pattern[str] | None = None,
        phone_patterns: Iterable[re.Pattern[str]] | None = None,
        email_pattern: re.Pattern[str] | None = None,
        address_pattern: re.Pattern[str] | None = None,
    ) -> None:
        self._name_explicit = name_pattern or _NAME_EXPLICIT_PATTERN
        self._name_generic = name_generic_pattern or _NAME_GENERIC_PATTERN
        self._phones = tuple(phone_patterns) if phone_patterns is not None else _PHONE_PATTERNS
        self._email = email_pattern or _EMAIL_PATTERN
        self._address = address_pattern or _ADDRESS_PATTERN

    def anonymize(self, text: str) -> str:
        """Return text with all known PII replaced by placeholders."""
        if not text:
            return text
        text = self._name_explicit.sub(self.PLACEHOLDER_NAME, text)
        text = self._name_generic.sub(self.PLACEHOLDER_NAME, text)
        for pattern in self._phones:
            text = pattern.sub(self.PLACEHOLDER_PHONE, text)
        text = self._email.sub(self.PLACEHOLDER_EMAIL, text)
        text = self._address.sub(self.PLACEHOLDER_ADDRESS, text)
        return text


# Module-level facade — backward-compatible with the old `anonymize_text()`.
_DEFAULT_ANONYMIZER = PIIAnonymizer()


def anonymize_text(text: str) -> str:
    """Functional wrapper retained for legacy callers."""
    return _DEFAULT_ANONYMIZER.anonymize(text)