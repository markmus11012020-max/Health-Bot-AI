"""Settings: environment-driven configuration with dataclass validation."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment."""

    # AITunnel
    aitunnel_api_key: str = field(default_factory=lambda: os.getenv("AITUNNEL_API_KEY", ""))
    aitunnel_base_url: str = field(
        default_factory=lambda: os.getenv("AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1")
    )
    aitunnel_model: str = field(
        default_factory=lambda: os.getenv("AITUNNEL_MODEL", "gpt-3.5-turbo")
    )

    # YandexGPT fallback
    yandex_api_key: str = field(default_factory=lambda: os.getenv("YANDEX_API_KEY", ""))
    yandex_folder_id: str = field(default_factory=lambda: os.getenv("YANDEX_FOLDER_ID", ""))
    yandex_model: str = field(
        default_factory=lambda: os.getenv("YANDEX_MODEL", "yandexgpt-lite")
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor (cached)."""
    return Settings()