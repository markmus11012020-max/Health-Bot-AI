"""Settings: environment-driven configuration with dataclass validation."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _yandex_base_url() -> str:
    """Read YANDEX_GPT_URL, strip a trailing /completion if present.

    The native REST endpoint includes `/completion`, but the OpenAI-compatible
    client appends its own `/chat/completions`, so we must drop it here.
    """
    raw = os.getenv("YANDEX_GPT_URL", "https://llm.api.cloud.yandex.net/foundationModels/v1")
    return raw.rstrip("/").removesuffix("/completion") or raw


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment."""

    # AITunnel
    aitunnel_api_key: str = field(default_factory=lambda: os.getenv("AITUNNEL_API_KEY", ""))
    aitunnel_base_url: str = field(
        default_factory=lambda: os.getenv("AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1")
    )
    aitunnel_model: str = field(
        default_factory=lambda: os.getenv("AITUNNEL_MODEL", "minimax-m3")
    )

    # YandexGPT fallback
    yandex_api_key: str = field(default_factory=lambda: os.getenv("YANDEX_API_KEY", ""))
    yandex_iam_token: str = field(default_factory=lambda: os.getenv("YANDEX_IAM_TOKEN", ""))
    yandex_folder_id: str = field(default_factory=lambda: os.getenv("YANDEX_FOLDER_ID", ""))
    yandex_gpt_url: str = field(default_factory=_yandex_base_url)
    yandex_gpt_model: str = field(
        default_factory=lambda: os.getenv("YANDEX_GPT_MODEL", "yandexgpt-lite")
    )
    yandex_timeout_s: float = field(
        default_factory=lambda: float(os.getenv("YANDEX_TIMEOUT_S", "120"))
    )

    # Generation
    temperature: float = field(default_factory=lambda: float(os.getenv("TEMPERATURE", "0.2")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_TOKENS", "800")))
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT", "30"))
    )
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "2")))

    # UI
    app_title: str = field(
        default_factory=lambda: os.getenv("APP_TITLE", "Health-Bot-AI | OCX")
    )
    app_icon: str = field(default_factory=lambda: os.getenv("APP_ICON", "🏥"))

    # A/B-промпт: standard | expert | warm
    prompt_variant: str = field(
        default_factory=lambda: os.getenv("PROMPT_VARIANT", "standard")
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor (cached)."""
    return Settings()
