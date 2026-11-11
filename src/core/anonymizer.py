"""PII anonymization (152-ФЗ compliance).

The anonymizer is deliberately deterministic and dependency-free.  It is a
defence-in-depth layer: the prompt builder never receives raw CRM text, and the
audit logger only receives counts of detected categories.

Placeholders are stable within one request (``[Клиент]``, ``[Телефон]``, ...).
A reversible mapping is intentionally **not** persisted anywhere.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnonymizationResult:
    """Anonymized text plus non-sensitive detection statistics."""

    text: str
    counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


# Russian first names commonly seen in B2B retail data.
_DEFAULT_NAMES = (
    "Мария Ивановна|Мария|Машей|Машенька|Маша|"
    "Иван Иванович|Иван|Ваня|Ванек|"
    "Алексей Сергеевич|Алексей|Леша|"
    "Елена Петровна|Елена|Lena|"
    "Ольга Николаевна|Ольга|Olga|"
    "Олег|Олега|Олегу|Олегом|"
    "Александр|Александра|Андрей|Анна|Артём|Артем|"
    "Борис|Вадим|Валентина|Валерий|Василий|Вера|Виктор|Виктория|"
    "Владимир|Владислав|Всеволод|Галина|Дарья|Денис|Дмитрий|"
    "Евгений|Евгения|Егор|Екатерина|Зоя|Игорь|Ирина|Кирилл|"
    "Ксения|Людмила|Максим|Маргарита|Михаил|Наталья|Наталия|"
    "Никита|Николай|Павел|Пётр|Петр|Полина|Роман|Светлана|"
    "Сергей|Станислав|Татьяна|Тимофей|Юлия|Яна"
)

_NAME_EXPLICIT_PATTERN = re.compile(rf"\b({_DEFAULT_NAMES})\b", re.IGNORECASE)
# Two or three capitalised Cyrillic words: "Мария Петрова", "Иван Иванович Петров".
_NAME_GENERIC_PATTERN = re.compile(
    r"\b[А-ЯЁ][а-яё]{1,}(?:\s+[А-ЯЁ][а-яё]{1,}){1,2}\b"
)

_PHONE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\+7\s?\(?\d{3}\)?\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}",
        r"8\s?\(?\d{3}\)?\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}",
        r"(?<!\d)\+?\d{11}(?!\d)",
        r"\d{3}[-\s]\d{3}[-\s]\d{2}[-\s]\d{2}",
        r"\(\d{3}\)\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}",
    )
)

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_SNILS_PATTERN = re.compile(r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b")
_CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Context-aware patterns keep ordinary numbers (prices, order IDs) untouched.
_INN_PATTERN = re.compile(r"(?i)(ИНН[^\d]{0,12})(\d{10}|\d{12})")
_PASSPORT_PATTERN = re.compile(
    r"(?i)(паспорт\w*[^\d]{0,20})(\d{2}\s?\d{2}\s?\d{6})"
)
_BIRTH_DATE_PATTERN = re.compile(
    r"(?i)((?:дата\s+рождения|родил(?:ся|ась)|д\.?\s*р\.)[^\d]{0,12})"
    r"(\d{2}[./-]\d{2}[./-]\d{4})"
)

_ADDRESS_PATTERN = re.compile(
    r"(?i)(?:(?:г\.|город)\s*[А-ЯЁ][а-яё-]+(?:\s*,)?\s*)?"
    r"(?:ул\.|улица|пер\.|переулок|пр-т|проспект|б-р|бульвар|ш\.|шоссе|"
    r"наб\.|набережная|д\.|дом|кв\.|квартира)"
    r"\s*[А-ЯЁа-яё0-9-]*(?:\s*,?\s*(?:д\.|дом|кв\.|квартира)?\s*\d+)?"
)


class PIIAnonymizer:
    """Mask personal data before sending to a third-party LLM.

    Stateless and thread-safe.  Substitution rules are pluggable via the
    constructor so additional PII types can be added without touching call
    sites.
    """

    PLACEHOLDER_NAME = "[Клиент]"
    PLACEHOLDER_PHONE = "[Телефон]"
    PLACEHOLDER_EMAIL = "[Email]"
    PLACEHOLDER_ADDRESS = "[Адрес]"
    PLACEHOLDER_SNILS = "[СНИЛС]"
    PLACEHOLDER_INN = "[ИНН]"
    PLACEHOLDER_PASSPORT = "[Паспорт]"
    PLACEHOLDER_BIRTH_DATE = "[Дата рождения]"
    PLACEHOLDER_CARD = "[Карта]"
    PLACEHOLDER_IP = "[IP]"

    def __init__(
        self,
        *,
        name_pattern: re.Pattern[str] | None = None,
        name_generic_pattern: re.Pattern[str] | None = None,
        phone_patterns: Iterable[re.Pattern[str]] | None = None,
        email_pattern: re.Pattern[str] | None = None,
        address_pattern: re.Pattern[str] | None = None,
        snils_pattern: re.Pattern[str] | None = None,
        card_pattern: re.Pattern[str] | None = None,
        ip_pattern: re.Pattern[str] | None = None,
    ) -> None:
        self._name_explicit = name_pattern or _NAME_EXPLICIT_PATTERN
        self._name_generic = name_generic_pattern or _NAME_GENERIC_PATTERN
        self._phones = (
            tuple(phone_patterns) if phone_patterns is not None else _PHONE_PATTERNS
        )
        self._email = email_pattern or _EMAIL_PATTERN
        self._address = address_pattern or _ADDRESS_PATTERN
        self._snils = snils_pattern or _SNILS_PATTERN
        self._card = card_pattern or _CARD_PATTERN
        self._ip = ip_pattern or _IP_PATTERN

    def anonymize(self, text: str) -> str:
        """Return text with all known PII replaced by placeholders."""
        return self.anonymize_detailed(text).text

    def anonymize_detailed(self, text: str) -> AnonymizationResult:
        """Anonymize text and report how many values of each category were found."""
        if not text:
            return AnonymizationResult(text)

        counts: dict[str, int] = {}

        def replace(
            pattern: re.Pattern[str], placeholder: str, key: str
        ) -> None:
            nonlocal text
            text, n = pattern.subn(placeholder, text)
            if n:
                counts[key] = counts.get(key, 0) + n

        # Generic full-name first (Имя Фамилия), then single names from the list.
        replace(self._name_generic, self.PLACEHOLDER_NAME, "name")
        replace(self._name_explicit, self.PLACEHOLDER_NAME, "name")
        for pattern in self._phones:
            replace(pattern, self.PLACEHOLDER_PHONE, "phone")
        replace(self._email, self.PLACEHOLDER_EMAIL, "email")
        replace(self._snils, self.PLACEHOLDER_SNILS, "snils")
        replace(self._card, self.PLACEHOLDER_CARD, "card")
        replace(self._ip, self.PLACEHOLDER_IP, "ip")

        # Context-aware substitutions keep the prefix and replace the value.
        text, n = _INN_PATTERN.subn(rf"\1{self.PLACEHOLDER_INN}", text)
        if n:
            counts["inn"] = counts.get("inn", 0) + n
        text, n = _PASSPORT_PATTERN.subn(rf"\1{self.PLACEHOLDER_PASSPORT}", text)
        if n:
            counts["passport"] = counts.get("passport", 0) + n
        text, n = _BIRTH_DATE_PATTERN.subn(
            rf"\1{self.PLACEHOLDER_BIRTH_DATE}", text
        )
        if n:
            counts["birth_date"] = counts.get("birth_date", 0) + n

        replace(self._address, self.PLACEHOLDER_ADDRESS, "address")
        return AnonymizationResult(text=text, counts=counts)


# Module-level facade — backward-compatible with the old `anonymize_text()`.
_DEFAULT_ANONYMIZER = PIIAnonymizer()


def anonymize_text(text: str) -> str:
    """Functional wrapper retained for legacy callers."""
    return _DEFAULT_ANONYMIZER.anonymize(text)
