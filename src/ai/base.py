"""Abstract AI client contract used by all providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatRequest:
    system_prompt: str
    user_message: str
    temperature: float
    max_tokens: int

    def to_messages(self) -> list[ChatMessage]:
        return [
            ChatMessage("system", self.system_prompt),
            ChatMessage("user", self.user_message),
        ]


@dataclass(frozen=True)
class ChatResult:
    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class AIClient(ABC):
    """Provider-agnostic chat interface."""

    name: str = "abstract"

    @property
    def model_name(self) -> str:
        """Human-readable model identifier for cache/audit metadata."""
        return ""

    @abstractmethod
    def chat(self, request: ChatRequest) -> ChatResult:  # pragma: no cover - contract
        """Send a chat request and return the model's text reply."""
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Generator[str, None, None]:  # noqa: D401
        """Optional streaming variant. Default falls back to non-streaming chat.

        Providers are encouraged to override this for better UX on slow models.
        """
        result = self.chat(request)
        yield result.content
