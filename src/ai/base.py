"""Abstract AI client contract used by all providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
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


class AIClient(ABC):
    """Provider-agnostic chat interface."""

    name: str = "abstract"

    @abstractmethod
    def chat(self, request: ChatRequest) -> ChatResult:  # pragma: no cover - contract
        """Send a chat request and return the model's text reply."""
        raise NotImplementedError