"""Local Admin schemas for online board-search share sessions (D-471)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareView,
    CreatedBoardSearchShare,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressStatus,
    is_ready_online_reviewer_ingress,
)
from game_predictor_api.domain.board_search_shares import (
    BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES,
    BOARD_SEARCH_SHARE_MAX_LIFETIME_MINUTES,
    BOARD_SEARCH_SHARE_MIN_LIFETIME_MINUTES,
    BOARD_SEARCH_SHARE_REVIEWER_PATH,
    BoardSearchShareStatus,
)
from game_predictor_api.schemas.catalog import ApiModel


class BoardSearchShareCreate(ApiModel):
    game_id: UUID
    label: str | None = Field(default=None, max_length=200)
    lifetime_minutes: int = Field(
        default=BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES,
        ge=BOARD_SEARCH_SHARE_MIN_LIFETIME_MINUTES,
        le=BOARD_SEARCH_SHARE_MAX_LIFETIME_MINUTES,
    )


class BoardSearchShareSessionResponse(ApiModel):
    """One share session as the owner sees it; never contains secrets."""

    session_id: UUID
    game_id: UUID
    label: str | None
    status: Literal["active", "locked", "expired", "revoked"]
    failed_attempts: int
    created_at: datetime
    expires_at: datetime
    locked_at: datetime | None
    revoked_at: datetime | None
    last_unlocked_at: datetime | None
    ready: bool = Field(
        description="The session is active and the public Reviewer ingress is online."
    )
    share_url: str | None = Field(
        description="The link for the recipient (without the code) while `ready`."
    )

    @classmethod
    def from_view(
        cls,
        value: BoardSearchShareView,
        ingress: ReviewerIngressStatus | None,
    ) -> BoardSearchShareSessionResponse:
        ready = (
            value.status is BoardSearchShareStatus.ACTIVE
            and ingress is not None
            and is_ready_online_reviewer_ingress(ingress)
        )
        return cls(
            session_id=value.session_id,
            game_id=value.game_id,
            label=value.label,
            status=value.status.value,
            failed_attempts=value.failed_attempts,
            created_at=value.created_at,
            expires_at=value.expires_at,
            locked_at=value.locked_at,
            revoked_at=value.revoked_at,
            last_unlocked_at=value.last_unlocked_at,
            ready=ready,
            share_url=(
                board_search_share_url(ingress.public_origin, value.session_id)
                if ready and ingress is not None and ingress.public_origin is not None
                else None
            ),
        )


class BoardSearchShareCreatedResponse(ApiModel):
    session: BoardSearchShareSessionResponse
    access_code: str = Field(description="Shown once; only its hash is stored.")

    @classmethod
    def from_created(
        cls,
        value: CreatedBoardSearchShare,
        ingress: ReviewerIngressStatus,
    ) -> BoardSearchShareCreatedResponse:
        return cls(
            session=BoardSearchShareSessionResponse.from_view(value.session, ingress),
            access_code=value.access_code,
        )


class BoardSearchShareSessionListResponse(ApiModel):
    sessions: list[BoardSearchShareSessionResponse]


def board_search_share_url(public_origin: str, session_id: UUID) -> str:
    parsed = urlparse(public_origin)
    return urlunparse(
        parsed._replace(
            path=BOARD_SEARCH_SHARE_REVIEWER_PATH,
            query=urlencode({"share": str(session_id)}),
        )
    )


__all__ = [
    "BoardSearchShareCreate",
    "BoardSearchShareCreatedResponse",
    "BoardSearchShareSessionListResponse",
    "BoardSearchShareSessionResponse",
    "board_search_share_url",
]
