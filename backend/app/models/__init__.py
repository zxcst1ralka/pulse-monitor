from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
    Uuid, false, text, true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), UUID: Uuid}


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(default=now, server_default=text("now()"))


class Updated:
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now, server_default=text("now()"))


class User(Record, Updated, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class RefreshSession(Record, Base):
    __tablename__ = "refresh_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[UUID] = mapped_column(index=True)
    expires_at: Mapped[datetime] = mapped_column(index=True)
    revoked_at: Mapped[datetime | None]


class Monitor(Record, Updated, Base):
    __tablename__ = "monitors"
    __table_args__ = (Index("ix_monitor_due", "next_check_at", postgresql_where=text("is_active AND NOT is_synthetic")),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    type: Mapped[str] = mapped_column(String(16))
    interval_seconds: Mapped[int]
    timeout_seconds: Mapped[int]
    expected_status_code: Mapped[int]
    keyword: Mapped[str | None] = mapped_column(String(200))
    response_threshold_ms: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime | None]
    next_check_at: Mapped[datetime] = mapped_column(default=now)
    last_response_time_ms: Mapped[int | None]
    ssl_expires_at: Mapped[datetime | None]
    ssl_valid: Mapped[bool | None]
    ssl_hostname_valid: Mapped[bool | None]
    dispatch_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None]
    check_started: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class MonitorCheck(Record, Base):
    __tablename__ = "monitor_checks"
    __table_args__ = (
        UniqueConstraint("monitor_id", "scheduled_at", name="uq_check_slot"),
        Index("ix_checks_monitor_time", "monitor_id", "checked_at"),
    )

    monitor_id: Mapped[UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))
    http_status_code: Mapped[int | None]
    response_time_ms: Mapped[int | None]
    error_message: Mapped[str | None] = mapped_column(String(240))
    scheduled_at: Mapped[datetime]
    checked_at: Mapped[datetime] = mapped_column(default=now, index=True)


class Incident(Record, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("uq_open_incident", "monitor_id", unique=True, postgresql_where=text("status = 'ongoing'")),
        Index("ix_incidents_monitor_time", "monitor_id", "started_at"),
    )

    monitor_id: Mapped[UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="ongoing")
    reason: Mapped[str] = mapped_column(String(240))
    http_status_code: Mapped[int | None]
    started_at: Mapped[datetime] = mapped_column(default=now)
    resolved_at: Mapped[datetime | None]
    duration_seconds: Mapped[int | None]


class NotificationChannel(Record, Base):
    __tablename__ = "notification_channels"
    __table_args__ = (UniqueConstraint("user_id", "type", name="uq_user_channel"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16))
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationLog(Record, Base):
    __tablename__ = "notification_logs"

    channel_id: Mapped[UUID] = mapped_column(ForeignKey("notification_channels.id", ondelete="CASCADE"), index=True)
    monitor_id: Mapped[UUID | None] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(24))
    deduplication_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    message: Mapped[str] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(String(240))
    sent_at: Mapped[datetime | None]


class TelegramLink(Record, Base):
    __tablename__ = "telegram_links"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(index=True)


class StatusPage(Record, Updated, Base):
    __tablename__ = "status_pages"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)


class StatusPageMonitor(Base):
    __tablename__ = "status_page_monitors"

    status_page_id: Mapped[UUID] = mapped_column(ForeignKey("status_pages.id", ondelete="CASCADE"), primary_key=True)
    monitor_id: Mapped[UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True, index=True)
    display_order: Mapped[int]
