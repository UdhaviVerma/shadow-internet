from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (UniqueConstraint("owner", "request_key", name="uq_owner_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner: Mapped[str] = mapped_column(String(200), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    domain: Mapped[str] = mapped_column(String(253), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSON)
    changes: Mapped[list] = mapped_column(JSON, default=list)


class Monitor(Base):
    __tablename__ = "monitors"
    __table_args__ = (UniqueConstraint("owner", "domain", name="uq_monitor_owner_domain"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner: Mapped[str] = mapped_column(String(200), index=True)
    domain: Mapped[str] = mapped_column(String(253))
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
