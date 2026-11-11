"""Orchestrator fallback and streaming safety."""
from __future__ import annotations

import unittest
from collections.abc import Generator
from typing import Any

from src.ai.base import AIClient, ChatRequest, ChatResult
from src.ai.orchestrator import AIOrchestrator


def _request() -> ChatRequest:
    return ChatRequest(system_prompt="s", user_message="u", temperature=0.2, max_tokens=100)


class _Provider(AIClient):
    def __init__(
        self,
        name: str,
        *,
        chat_error: Exception | None = None,
        stream_chunks: tuple[str, ...] = ("ok",),
        stream_error: Exception | None = None,
        fail_after_chunks: int | None = None,
    ) -> None:
        self.name = name
        self._chat_error = chat_error
        self._chunks = stream_chunks
        self._stream_error = stream_error
        self._fail_after = fail_after_chunks

    def chat(self, request: ChatRequest) -> ChatResult:
        if self._chat_error:
            raise self._chat_error
        return ChatResult(content=f"{self.name} answer", provider=self.name, model="m")

    def stream(self, request: ChatRequest) -> Generator[str, None, None]:
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index >= self._fail_after:
                raise self._stream_error or RuntimeError("stream failed")
            yield chunk
        if self._stream_error:
            raise self._stream_error


class OrchestratorTests(unittest.TestCase):
    def test_complete_falls_back_to_next_provider(self) -> None:
        orch = AIOrchestrator(
            [_Provider("A", chat_error=RuntimeError("down")), _Provider("B")]
        )
        result = orch.complete(_request())
        self.assertTrue(result.success)
        self.assertIsNotNone(result.result)
        self.assertEqual(result.result.provider, "B")  # type: ignore[union-attr]

    def test_complete_reports_all_errors(self) -> None:
        orch = AIOrchestrator(
            [
                _Provider("A", chat_error=RuntimeError("down-a")),
                _Provider("B", chat_error=RuntimeError("down-b")),
            ]
        )
        result = orch.complete(_request())
        self.assertFalse(result.success)
        self.assertIn("down-a", result.error or "")
        self.assertIn("down-b", result.error or "")

    def _consume(self, gen: Any) -> tuple[list[str], Any]:
        tokens: list[str] = []
        while True:
            try:
                tokens.append(next(gen))
            except StopIteration as stop:
                return tokens, stop.value

    def test_stream_falls_back_before_first_token(self) -> None:
        first = _Provider("A", stream_chunks=(), stream_error=RuntimeError("boom"))
        second = _Provider("B", stream_chunks=("b1", "b2"))
        orch = AIOrchestrator([first, second])
        tokens, final = self._consume(orch.stream(_request()))
        self.assertEqual(tokens, ["b1", "b2"])
        provider, result, error = final
        self.assertEqual(provider, "B")
        self.assertIsNotNone(result)
        self.assertIsNone(error)

    def test_stream_does_not_mix_after_partial_output(self) -> None:
        first = _Provider(
            "A",
            stream_chunks=("a1", "a2"),
            fail_after_chunks=1,
            stream_error=RuntimeError("partial"),
        )
        second = _Provider("B", stream_chunks=("b1",))
        orch = AIOrchestrator([first, second])
        tokens, final = self._consume(orch.stream(_request()))
        self.assertEqual(tokens, ["a1"])
        provider, result, error = final
        self.assertEqual(provider, "A")
        self.assertIsNone(result)
        self.assertIn("partial response discarded", error or "")

    def test_stream_success_returns_full_text(self) -> None:
        orch = AIOrchestrator([_Provider("A", stream_chunks=("a", "b"))])
        tokens, final = self._consume(orch.stream(_request()))
        self.assertEqual(tokens, ["a", "b"])
        provider, result, error = final
        self.assertEqual(provider, "A")
        self.assertEqual(result.content, "ab")  # type: ignore[union-attr]
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
