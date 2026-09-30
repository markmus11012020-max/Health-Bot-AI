"""Аудит-логирование: фиксирует анонимизированные обращения для compliance.

ВАЖНО: в лог пишется ТОЛЬКО анонимизированный ввод и метаданные ответа.
Сырые ПД (имена, телефоны, email, адреса) **никогда** не попадают в лог.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Лог-файл лежит в корне проекта рядом с .env (не коммитится — см. .gitignore).
LOG_FILE = Path("audit.log")
_MAX_BYTES = 2 * 1024 * 1024  # 2 МБ
_BACKUP_COUNT = 5

_AUDIT_LOGGER_NAME = "ocx.audit"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    if logger.handlers:  # idempotent — не дублируем хэндлеры при rerun Streamlit
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    except OSError:
        # Если файловая система read-only — fallback в stderr.
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(sh)
    return logger


_LOGGER = _build_logger()


def log_consultation_event(
    *,
    anonymized_input: str,
    provider: str,
    model: str,
    success: bool,
    latency_ms: int,
    response_chars: int,
    error: str | None = None,
) -> None:
    """Записать событие 'обращение обработано'.

    Параметры берутся ПОСЛЕ анонимизации: в логе гарантированно нет ПД.
    """
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": "consultation",
        "provider": provider,
        "model": model,
        "success": success,
        "latency_ms": latency_ms,
        "response_chars": response_chars,
        "anonymized_input_chars": len(anonymized_input),
        "error": error,
    }
    _LOGGER.info(json.dumps(payload, ensure_ascii=False))


def log_audit_trail(
    *,
    action: str,
    details: dict | None = None,
) -> None:
    """Универсальный аудит-событийный логгер (для будущих интеграций)."""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": action,
        "details": details or {},
    }
    _LOGGER.info(json.dumps(payload, ensure_ascii=False))