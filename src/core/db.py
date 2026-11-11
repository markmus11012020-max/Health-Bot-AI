"""SQLAlchemy persistence for audit events and manager feedback.

SQLite is the zero-dependency default for demos and tests.  PostgreSQL is
supported through ``DATABASE_URL``:

    postgresql+psycopg://user:pass@host:5432/health_bot

The schema is intentionally small; a production deployment can add Alembic
migrations and read replicas without changing the service layer.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(32), default="consultation")
    provider: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    success: Mapped[bool] = mapped_column(default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    response_chars: Mapped[int] = mapped_column(Integer, default=0)
    anonymized_input_chars: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    pii_counts: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool | None] = mapped_column(nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


def _prepare_sqlite(url: str) -> dict:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return {}
    database = parsed.database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        return {"connect_args": {"check_same_thread": False}}
    return {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }


class Database:
    """Small repository facade used by the API and service layer."""

    def __init__(self, url: str = "sqlite:///data/health_bot.db") -> None:
        self.url = url
        self._engine: Engine = create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            **_prepare_sqlite(url),
        )
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False, class_=Session
        )

    def init(self) -> None:
        Base.metadata.create_all(self._engine)

    @property
    def engine(self) -> Engine:
        return self._engine

    def record_audit(
        self,
        *,
        request_id: str,
        provider: str = "",
        model: str = "",
        success: bool = False,
        latency_ms: int = 0,
        response_chars: int = 0,
        anonymized_input_chars: int = 0,
        cache_hit: bool = False,
        pii_counts: dict[str, int] | None = None,
        error: str | None = None,
        event_type: str = "consultation",
    ) -> int:
        with self._session_factory() as session:
            event = AuditEvent(
                request_id=request_id,
                event_type=event_type,
                provider=provider,
                model=model,
                success=success,
                latency_ms=latency_ms,
                response_chars=response_chars,
                anonymized_input_chars=anonymized_input_chars,
                cache_hit=cache_hit,
                pii_counts=json.dumps(pii_counts or {}, ensure_ascii=False),
                error=error,
            )
            session.add(event)
            session.commit()
            return event.id

    def record_feedback(
        self,
        *,
        request_id: str,
        rating: int,
        correct: bool | None = None,
        comment: str | None = None,
    ) -> int:
        with self._session_factory() as session:
            item = Feedback(
                request_id=request_id,
                rating=rating,
                correct=correct,
                comment=comment,
            )
            session.add(item)
            session.commit()
            return item.id

    def get_audit(self, request_id: str) -> list[AuditEvent]:
        with self._session_factory() as session:
            stmt = (
                select(AuditEvent)
                .where(AuditEvent.request_id == request_id)
                .order_by(AuditEvent.id)
            )
            return list(session.scalars(stmt))

    def health(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Database health check failed: %s", exc)
            return False

    def close(self) -> None:
        self._engine.dispose()

    def stats(self) -> dict[str, int]:
        with self._session_factory() as session:
            audit_count = int(session.query(AuditEvent).count())
            feedback_count = int(session.query(Feedback).count())
        return {"audit_events": audit_count, "feedback": feedback_count}


_database: Database | None = None


def get_database(url: str = "sqlite:///data/health_bot.db") -> Database:
    """Process-wide database singleton keyed by URL."""
    global _database
    if _database is None or _database.url != url:
        _database = Database(url)
        _database.init()
    return _database


def reset_database() -> None:
    """Test helper: dispose and forget the singleton."""
    global _database
    if _database is not None:
        _database.close()
    _database = None
