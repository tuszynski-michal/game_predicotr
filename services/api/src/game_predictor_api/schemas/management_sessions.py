"""Credential-free panel context; one-time code exists only in local create."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.management_access import ManagementSessionRecord, session_status
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressStatus,
    is_ready_online_reviewer_ingress,
)
from game_predictor_api.schemas.catalog import ApiModel


class ManagementSessionCreate(ApiModel):
    label: str = Field(min_length=1, max_length=200)
    lifetime_minutes: Literal[60, 240, 480, 1440, 2880, 4320] = 480


class ManagementSessionContext(ApiModel):
    session_id: UUID
    label: str
    expires_at: datetime

    @classmethod
    def from_record(cls, record: ManagementSessionRecord) -> "ManagementSessionContext":
        return cls(session_id=record.id, label=record.label, expires_at=record.expires_at)


class ManagementSessionResponse(ManagementSessionContext):
    status: Literal["active", "locked", "expired", "revoked"]
    failed_attempts: int
    created_at: datetime
    last_unlocked_at: datetime | None
    revoked_at: datetime | None
    locked_at: datetime | None
    ready: bool
    share_url: str | None

    @classmethod
    def view(
        cls, record: ManagementSessionRecord, ingress: ReviewerIngressStatus | None = None
    ) -> "ManagementSessionResponse":
        status = session_status(record, datetime.now(UTC))
        ready = (
            status == "active" and ingress is not None and is_ready_online_reviewer_ingress(ingress)
        )
        return cls(
            **ManagementSessionContext.from_record(record).model_dump(),
            status=status,
            failed_attempts=record.failed_attempts,
            created_at=record.created_at,
            last_unlocked_at=record.last_unlocked_at,
            revoked_at=record.revoked_at,
            locked_at=record.locked_at,
            ready=ready,
            share_url=f"{ingress.public_origin}/management?share={record.id}"
            if ready and ingress
            else None,
        )


class ManagementSessionCreated(ApiModel):
    session: ManagementSessionResponse
    access_code: str


class ManagementSessionList(ApiModel):
    sessions: tuple[ManagementSessionResponse, ...]


class ManagementSessionUnlock(ApiModel):
    access_code: str = Field(min_length=1, max_length=64)
