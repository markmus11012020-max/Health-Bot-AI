"""Settings: environment-driven configuration with validation.

The module is intentionally dependency-light: dataclass + os.getenv.  This keeps
the demo runnable without pydantic-settings while still failing fast on invalid
values.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

_ALLOWED_ENVIRONMENTS = frozenset({"development", "test", "production"})
_ALLOWED_PROMPT_VARIANTS = frozenset({"standard", "expert", "warm"})
_YANDEX_OPENAI_BASE = "https://llm.api.cloud.yandex.net/v1"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def _yandex_base_url() -> str:
    """Return an OpenAI-compatible YandexGPT base URL.

    Yandex supports two different APIs:

    * native REST: ``.../foundationModels/v1/completion``;
    * OpenAI-compatible: ``https://llm.api.cloud.yandex.net/v1``.

    The provider uses the OpenAI SDK, so a native URL must be normalised.
    """
    raw = os.getenv("YANDEX_GPT_URL", _YANDEX_OPENAI_BASE).strip()
    if not raw:
        return _YANDEX_OPENAI_BASE
    if "foundationModels" in raw:
        return _YANDEX_OPENAI_BASE
    return raw.rstrip("/").removesuffix("/completion") or _YANDEX_OPENAI_BASE


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment."""

    # General
    environment: str = field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development").strip().lower()
    )
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    # AITunnel
    aitunnel_api_key: str = field(default_factory=lambda: os.getenv("AITUNNEL_API_KEY", ""))
    aitunnel_base_url: str = field(
        default_factory=lambda: os.getenv("AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1")
    )
    aitunnel_model: str = field(
        default_factory=lambda: os.getenv("AITUNNEL_MODEL", "minimax-m3")
    )

    # YandexGPT
    yandex_api_key: str = field(default_factory=lambda: os.getenv("YANDEX_API_KEY", ""))
    yandex_iam_token: str = field(default_factory=lambda: os.getenv("YANDEX_IAM_TOKEN", ""))
    yandex_folder_id: str = field(default_factory=lambda: os.getenv("YANDEX_FOLDER_ID", ""))
    yandex_gpt_url: str = field(default_factory=_yandex_base_url)
    yandex_gpt_model: str = field(
        default_factory=lambda: os.getenv("YANDEX_GPT_MODEL", "yandexgpt-lite")
    )
    yandex_timeout_s: float = field(
        default_factory=lambda: _env_float("YANDEX_TIMEOUT_S", 120.0)
    )

    # Generation
    temperature: float = field(default_factory=lambda: _env_float("TEMPERATURE", 0.2))
    max_tokens: int = field(default_factory=lambda: _env_int("MAX_TOKENS", 800))
    request_timeout: float = field(
        default_factory=lambda: _env_float("REQUEST_TIMEOUT", 30.0)
    )
    max_retries: int = field(default_factory=lambda: _env_int("MAX_RETRIES", 2))
    enable_fallback: bool = field(default_factory=lambda: _env_bool("ENABLE_FALLBACK", True))

    # UI
    app_title: str = field(
        default_factory=lambda: os.getenv("APP_TITLE", "Health-Bot-AI | OCX")
    )
    app_icon: str = field(default_factory=lambda: os.getenv("APP_ICON", "🏥"))

    # Prompt / knowledge base
    prompt_variant: str = field(
        default_factory=lambda: os.getenv("PROMPT_VARIANT", "standard").strip().lower()
    )
    kb_path: str = field(
        default_factory=lambda: os.getenv("KB_PATH", "knowledge_base.txt")
    )
    kb_top_k: int = field(default_factory=lambda: _env_int("KB_TOP_K", 3))
    kb_max_chars: int = field(default_factory=lambda: _env_int("KB_MAX_CHARS", 6000))

    # Cache
    cache_maxsize: int = field(default_factory=lambda: _env_int("CACHE_MAXSIZE", 256))
    cache_ttl_seconds: int = field(
        default_factory=lambda: _env_int("CACHE_TTL_SECONDS", 86400)
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "").strip())

    # Persistence
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "sqlite:///data/health_bot.db"
        ).strip()
    )

    # API security
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", "").strip())
    admin_api_key: str = field(
        default_factory=lambda: os.getenv("ADMIN_API_KEY", "").strip()
    )
    rate_limit_requests: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_REQUESTS", 60)
    )
    rate_limit_window_seconds: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
    )
    idempotency_ttl_seconds: int = field(
        default_factory=lambda: _env_int("IDEMPOTENCY_TTL_SECONDS", 3600)
    )

    # Guardrails
    guardrails_enabled: bool = field(
        default_factory=lambda: _env_bool("GUARDRAILS_ENABLED", True)
    )

    def __post_init__(self) -> None:
        # Normalise and validate user-provided values early.
        object.__setattr__(self, "environment", (self.environment or "development").lower())
        object.__setattr__(self, "prompt_variant", (self.prompt_variant or "standard").lower())
        object.__setattr__(self, "log_level", (self.log_level or "INFO").upper())
        if "foundationModels" in self.yandex_gpt_url:
            object.__setattr__(self, "yandex_gpt_url", _YANDEX_OPENAI_BASE)
        else:
            object.__setattr__(
                self,
                "yandex_gpt_url",
                (self.yandex_gpt_url or _YANDEX_OPENAI_BASE).rstrip("/"),
            )

        if self.environment not in _ALLOWED_ENVIRONMENTS:
            raise ValueError(
                f"ENVIRONMENT must be one of {sorted(_ALLOWED_ENVIRONMENTS)}, "
                f"got {self.environment!r}"
            )
        if self.prompt_variant not in _ALLOWED_PROMPT_VARIANTS:
            raise ValueError(
                f"PROMPT_VARIANT must be one of {sorted(_ALLOWED_PROMPT_VARIANTS)}, "
                f"got {self.prompt_variant!r}"
            )
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("TEMPERATURE must be between 0.0 and 2.0")
        if not 64 <= self.max_tokens <= 8192:
            raise ValueError("MAX_TOKENS must be between 64 and 8192")
        if self.request_timeout <= 0:
            raise ValueError("REQUEST_TIMEOUT must be positive")
        if self.max_retries < 0:
            raise ValueError("MAX_RETRIES must be non-negative")
        if self.cache_maxsize < 1:
            raise ValueError("CACHE_MAXSIZE must be positive")
        if self.cache_ttl_seconds < 0:
            raise ValueError("CACHE_TTL_SECONDS must be non-negative")
        if self.rate_limit_requests < 0 or self.rate_limit_window_seconds < 1:
            raise ValueError("RATE_LIMIT values are invalid")
        if self.kb_top_k < 1 or self.kb_max_chars < 500:
            raise ValueError("KB_TOP_K / KB_MAX_CHARS values are invalid")
        if not self.database_url:
            raise ValueError("DATABASE_URL must not be empty")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def has_aitunnel(self) -> bool:
        return bool(self.aitunnel_api_key)

    @property
    def has_yandex(self) -> bool:
        return bool(self.yandex_api_key or self.yandex_iam_token)

    def validate(self) -> list[str]:
        """Return human-readable configuration issues (empty list = OK)."""
        issues: list[str] = []
        if self.is_production and not self.api_key:
            issues.append("API_KEY is required in production")
        if self.is_production and not self.admin_api_key:
            issues.append("ADMIN_API_KEY is required in production")
        if self.is_production and self.database_url.startswith("sqlite"):
            issues.append("SQLite is not recommended for production; use PostgreSQL")
        if not self.has_aitunnel and not self.has_yandex:
            issues.append("No LLM provider credentials configured")
        if not self.has_yandex:
            issues.append("YandexGPT credentials are not configured (fallback disabled)")
        if self.redis_url == "":
            issues.append("REDIS_URL is empty; using in-process cache (single worker)")
        return issues


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor (cached)."""
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache and re-read environment variables (used by tests)."""
    get_settings.cache_clear()
    return get_settings()
