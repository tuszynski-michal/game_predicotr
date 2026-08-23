"""Local Admin schemas for host-bound remote manual selection setup."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.remote_manual_selection_access import (
    CreatedRemoteManualSelectionAccess,
    RemoteManualSelectionAccessView,
    RemoteManualSelectionContext,
)
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionBaseCapability,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressStatus,
    is_ready_online_reviewer_ingress,
)
from game_predictor_api.schemas.catalog import ApiModel


class RemoteManualSelectionBaseCapabilityResponse(ApiModel):
    status: Literal["selected", "cancelled"]
    base_capability: str | None = None
    display_name: str | None = None
    expires_at: datetime | None = None

    @classmethod
    def selected(
        cls,
        value: RemoteManualSelectionBaseCapability,
    ) -> RemoteManualSelectionBaseCapabilityResponse:
        return cls(
            status="selected",
            base_capability=value.capability,
            display_name=value.display_name,
            expires_at=value.expires_at,
        )

    @classmethod
    def cancelled(cls) -> RemoteManualSelectionBaseCapabilityResponse:
        return cls(status="cancelled")


class RemoteManualSelectionSessionCreate(ApiModel):
    base_capability: str = Field(min_length=32, max_length=200)
    lifetime_minutes: int = Field(default=480, ge=5, le=1440)


class RemoteManualSelectionSessionResponse(ApiModel):
    session_id: UUID
    status: Literal["draft", "active", "completed", "expired", "revoked"]
    revision: int
    display_name: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    locked_at: datetime | None
    revoked_at: datetime | None
    writer_active: bool
    writer_lease_expires_at: datetime | None
    ready: bool
    review_url: str | None

    @classmethod
    def from_view(
        cls,
        value: RemoteManualSelectionAccessView,
        ingress: ReviewerIngressStatus | None,
    ) -> RemoteManualSelectionSessionResponse:
        ready = (
            value.status.value == "active"
            and ingress is not None
            and is_ready_online_reviewer_ingress(ingress)
        )
        return cls(
            session_id=value.session_id,
            status=value.status.value,
            revision=value.revision,
            display_name=value.display_name,
            created_at=value.created_at,
            updated_at=value.updated_at,
            expires_at=value.expires_at,
            locked_at=value.locked_at,
            revoked_at=value.revoked_at,
            writer_active=value.writer_active,
            writer_lease_expires_at=value.writer_lease_expires_at,
            ready=ready,
            review_url=(
                _manual_selection_url(ingress.public_origin, value.session_id)
                if ready and ingress is not None and ingress.public_origin is not None
                else None
            ),
        )


class RemoteManualSelectionSessionCreatedResponse(ApiModel):
    session: RemoteManualSelectionSessionResponse
    access_code: str

    @classmethod
    def from_created(
        cls,
        value: CreatedRemoteManualSelectionAccess,
        ingress: ReviewerIngressStatus,
    ) -> RemoteManualSelectionSessionCreatedResponse:
        return cls(
            session=RemoteManualSelectionSessionResponse.from_view(
                value.session,
                ingress,
            ),
            access_code=value.access_code,
        )


class RemoteManualSelectionSessionListResponse(ApiModel):
    sessions: list[RemoteManualSelectionSessionResponse]


class RemoteManualSelectionUnlock(ApiModel):
    access_code: str = Field(min_length=1, max_length=64)
    client_instance_id: UUID


class RemoteManualSelectionWriterLeaseCommand(ApiModel):
    client_instance_id: UUID


class RemoteManualSelectionContextResponse(ApiModel):
    session_id: UUID
    status: Literal["active"]
    revision: int
    expires_at: datetime
    is_writer: bool
    writer_active: bool
    writer_lease_expires_at: datetime | None

    @classmethod
    def from_context(
        cls,
        value: RemoteManualSelectionContext,
    ) -> RemoteManualSelectionContextResponse:
        if value.status.value != "active":
            raise ValueError("Only an active remote selection session has public context.")
        return cls(
            session_id=value.session_id,
            status="active",
            revision=value.revision,
            expires_at=value.expires_at,
            is_writer=value.is_writer,
            writer_active=value.writer_active,
            writer_lease_expires_at=value.writer_lease_expires_at,
        )


def _manual_selection_url(public_origin: str, session_id: UUID) -> str:
    parsed = urlparse(public_origin)
    return urlunparse(
        parsed._replace(
            path="/manual-selection",
            query=urlencode({"session": str(session_id)}),
        )
    )


__all__ = [
    "RemoteManualSelectionBaseCapabilityResponse",
    "RemoteManualSelectionContextResponse",
    "RemoteManualSelectionSessionCreate",
    "RemoteManualSelectionSessionCreatedResponse",
    "RemoteManualSelectionSessionListResponse",
    "RemoteManualSelectionSessionResponse",
    "RemoteManualSelectionUnlock",
    "RemoteManualSelectionWriterLeaseCommand",
]
