"""Shared capability credentials and immutable security events."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class ManagementSessionModel(Base):
    __tablename__ = "management_sessions"
    __table_args__ = {"schema": "public"}
    id: Mapped[UUID] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    code_salt: Mapped[bytes] = mapped_column(LargeBinary(16))
    code_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    failed_attempts: Mapped[int] = mapped_column(Integer)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ManagementSessionAuditModel(Base):
    __tablename__ = "management_session_audit"
    __table_args__ = {"schema": "public"}
    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("public.management_sessions.id"))
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
