"""Parse the two-block structured response emitted by the LLM."""
from __future__ import annotations

from dataclasses import dataclass

CLIENT_BLOCK_START = "=== БЛОК ДЛЯ КЛИЕНТА ==="
MANAGER_BLOCK_START = "=== БЛОК ДЛЯ МЕНЕДЖЕРА (ВНУТРЕННИЙ) ==="
NO_UPSELL_HINT = "Допродажа не требуется"


@dataclass(frozen=True)
class ParsedResponse:
    """Structured LLM response."""

    client_answer: str
    manager_tip: str
    raw: str

    @property
    def needs_upsell(self) -> bool:
        return NO_UPSELL_HINT not in self.manager_tip


class ResponseParser:
    """Stateless parser for the two-block LLM contract."""

    def parse(self, raw: str) -> ParsedResponse:
        if not raw:
            return ParsedResponse("", "", "")

        if CLIENT_BLOCK_START in raw and MANAGER_BLOCK_START in raw:
            client_answer = (
                raw.split(CLIENT_BLOCK_START, 1)[1]
                .split(MANAGER_BLOCK_START, 1)[0]
                .strip()
            )
            manager_tip = raw.split(MANAGER_BLOCK_START, 1)[1].strip()
            return ParsedResponse(client_answer, manager_tip, raw)

        # Fallback: whole response treated as the client-facing answer.
        return ParsedResponse(
            client_answer=raw.strip(),
            manager_tip="Подсказка по допродажам не сформирована.",
            raw=raw,
        )

    def extract_copy_text(self, raw: str) -> str:
        """Pull just the client block — used for clipboard copy."""
        if CLIENT_BLOCK_START not in raw:
            return raw.strip()
        try:
            return raw.split(CLIENT_BLOCK_START, 1)[1].split(MANAGER_BLOCK_START, 1)[0].strip()
        except IndexError:
            return raw.strip()


# Module-level facade.
_DEFAULT_PARSER = ResponseParser()


def parse_ai_response(response: str) -> ParsedResponse:
    return _DEFAULT_PARSER.parse(response)


def extract_copy_text(response: str) -> str:
    return _DEFAULT_PARSER.extract_copy_text(response)