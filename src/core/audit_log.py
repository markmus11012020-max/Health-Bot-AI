"""Audit logging interfaces and legacy file fallback.

Production path: ``DatabaseAuditLogger`` writes structured metadata to
SQLite/PostgreSQL.  The legacy rotating-file logger is retained for scripts and
backward compatibility, but the service layer uses the injected logger.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

from src.core.db import Database

LOG_FILE = Path("audit.log")
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 5
_AUDIT_LOGGER_NAME = "ocx.audit"


class AuditLogger(Protocol):
    def log_consultation(
        self,
        *,
        request_id: str,
        anonymized_input: str,
        provider: str,
        model: str,
        success: bool,
        latency_ms: int,
        response_chars: int,
        cache_hit: bool,
        pii_counts: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None: ...


class NullAuditLogger:
    """No-op logger used by unit tests and local scripts."""

    def log_consultation(self, **_: object) -> None:
        return None


class DatabaseAuditLogger:
    """Persist audit events without storing raw PII."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def log_consultation(
        self,
        *,
        request_id: str,
        anonymized_input: str,
        provider: str,
        model: str,
        success: bool,
        latency_ms: int,
        response_chars: int,
        cache_hit: bool,
        pii_counts: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        self._db.record_audit(
            request_id=request_id,
            provider=provider,
            model=model,
            success=success,
            latency_ms=latency_ms,
            response_chars=response_chars,
            anonymized_input_chars=len(anonymized_input),
            cache_hit=cache_hit,
            pii_counts=pii_counts,
            error=error,
        )


def build_audit_logger(database: Database | None) -> AuditLogger:
    return DatabaseAuditLogger(database) if database is not None else NullAuditLogger()


def _build_file_logger() -> logging.Logger:
    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    if logger.handlers:  # idempotent — не дублируем хэндлеры при rerun Streamlit
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    except OSError:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


_FILE_LOGGER = _build_file_logger()


def log_consultation_event(
    *,
    anonymized_input: str,
    provider: str,
    model: str,
    success: bool,
    latency_ms: int,
    response_chars: int,
    error: str | None = None,
    request_id: str = "",
    cache_hit: bool = False,
    pii_counts: dict[str, int] | None = None,
) -> None:
    """Legacy JSONL audit event.  Never writes raw input text."""
    payload = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": "consultation",
        "request_id": request_id,
        "provider": provider,
        "model": model,
        "success": success,
        "latency_ms": latency_ms,
        "response_chars": response_chars,
        "anonymized_input_chars": len(anonymized_input),
        "cache_hit": cache_hit,
        "pii_counts": pii_counts or {},
        "error": error,
    }
    _FILE_LOGGER.info(json.dumps(payload, ensure_ascii=False))


def log_audit_trail(*, action: str, details: dict | None = None) -> None:
    payload = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": action,
        "details": details or {},
    }
    _FILE_LOGGER.info(json.dumps(payload, ensure_ascii=False))
