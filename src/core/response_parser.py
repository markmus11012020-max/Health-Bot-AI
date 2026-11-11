"""Parse the structured LLM response.

Primary contract is JSON.  The legacy two-block format is still supported so
existing prompts, cached responses and integrations keep working.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

CLIENT_BLOCK_START = "=== БЛОК ДЛЯ КЛИЕНТА ==="
MANAGER_BLOCK_START = "=== БЛОК ДЛЯ МЕНЕДЖЕРА (ВНУТРЕННИЙ) ==="
NO_UPSELL_HINT = "Допродажа не требуется"

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_PARTIAL_NEEDS_RE = re.compile(r'"needs_upsell"\s*:\s*(true|false)', re.IGNORECASE)
_PARTIAL_CITATIONS_RE = re.compile(r'"citations"\s*:\s*\[(.*?)\]', re.DOTALL)


@dataclass(frozen=True)
class ParsedResponse:
    """Structured LLM response."""

    client_answer: str
    manager_tip: str
    raw: str
    citations: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.8
    needs_upsell_value: bool | None = None

    @property
    def needs_upsell(self) -> bool:
        if self.needs_upsell_value is not None:
            return self.needs_upsell_value
        return NO_UPSELL_HINT.lower() not in self.manager_tip.lower()

    def to_text(self) -> str:
        """Serialise back to the legacy two-block format (cache/DB/UI safe)."""
        return (
            f"{CLIENT_BLOCK_START}\n{self.client_answer.strip()}\n\n"
            f"{MANAGER_BLOCK_START}\n{self.manager_tip.strip()}"
        )


class ResponseParser:
    """Stateless parser for JSON and legacy two-block responses."""

    def parse(self, raw: str) -> ParsedResponse:
        if not raw or not raw.strip():
            return ParsedResponse("", "", "")

        text = raw.strip()
        if text.startswith("```"):
            text = _JSON_FENCE.sub("", text).strip()

        parsed_json = self._try_json(text)
        if parsed_json is not None:
            return parsed_json

        # A reasoning model may hit max_tokens in the middle of JSON.  Extract
        # the fields we already have instead of showing raw JSON to the user.
        partial_json = self._try_partial_json(text)
        if partial_json is not None:
            return partial_json

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
        return self.parse(raw).client_answer

    @staticmethod
    def _try_json(text: str) -> ParsedResponse | None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        candidate = text[start : end + 1]
        try:
            payload: Any = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None

        client = payload.get("client_answer")
        manager = payload.get("manager_tip")
        if not isinstance(client, str) or not isinstance(manager, str):
            return None

        citations_raw = payload.get("citations", [])
        citations: tuple[str, ...]
        if isinstance(citations_raw, list):
            citations = tuple(str(item).strip() for item in citations_raw if str(item).strip())
        else:
            citations = ()

        try:
            confidence = float(payload.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        confidence = min(1.0, max(0.0, confidence))

        needs_upsell_raw = payload.get("needs_upsell")
        needs_upsell_value = (
            needs_upsell_raw if isinstance(needs_upsell_raw, bool) else None
        )

        return ParsedResponse(
            client_answer=client.strip(),
            manager_tip=manager.strip(),
            raw=text,
            citations=citations,
            confidence=confidence,
            needs_upsell_value=needs_upsell_value,
        )

    def _try_partial_json(self, text: str) -> ParsedResponse | None:
        """Salvage a JSON object truncated by max_tokens or malformed quotes."""
        if '"client_answer"' not in text:
            return None
        client = self._extract_string(text, "client_answer")
        if not client:
            return None

        manager = self._extract_string(text, "manager_tip") or ""
        needs_match = _PARTIAL_NEEDS_RE.search(text)
        needs_value = (
            needs_match.group(1).lower() == "true" if needs_match else None
        )

        citations: tuple[str, ...] = ()
        citations_match = _PARTIAL_CITATIONS_RE.search(text)
        if citations_match:
            citations = tuple(
                item.strip()
                for item in re.findall(r'"([^"]+)"', citations_match.group(1))
                if item.strip()
            )

        return ParsedResponse(
            client_answer=client.strip(),
            manager_tip=(
                manager.strip()
                or "Подсказка по допродажам не сформирована."
            ),
            raw=text,
            citations=citations,
            needs_upsell_value=needs_value,
        )

    @staticmethod
    def _extract_string(text: str, field: str) -> str | None:
        # Proper JSON string, including escaped quotes and newlines.
        proper = re.compile(
            rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', re.DOTALL
        )
        match = proper.search(text)
        if match:
            raw = match.group(1)
            try:
                return str(json.loads('"' + raw + '"'))
            except json.JSONDecodeError:
                return (
                    raw.replace('\\"', '"')
                    .replace("\\n", "\n")
                    .replace("\\r", "\r")
                    .replace("\\t", "\t")
                )

        # Truncated string without a closing quote: take the rest of the text.
        truncated = re.compile(
            rf'"{re.escape(field)}"\s*:\s*"([^"]*)', re.DOTALL
        )
        match = truncated.search(text)
        if match:
            return match.group(1).strip()
        return None


# Module-level facade.
_DEFAULT_PARSER = ResponseParser()


def parse_ai_response(response: str) -> ParsedResponse:
    return _DEFAULT_PARSER.parse(response)


def extract_copy_text(response: str) -> str:
    return _DEFAULT_PARSER.extract_copy_text(response)
