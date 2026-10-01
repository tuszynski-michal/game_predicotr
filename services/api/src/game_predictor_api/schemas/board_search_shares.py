"""Local Admin schemas for online board-search share sessions (D-471)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareView,
    CreatedBoardSearchShare,
)
from game_predictor_api.application.board_search_share_queries import (
    BoardSearchShareQueryEvent,
    BoardSearchShareQueryReplay,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressStatus,
    is_ready_online_reviewer_ingress,
)
from game_predictor_api.domain.board_search import BoardSearchScope
from game_predictor_api.domain.board_search_shares import (
    BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES,
    BOARD_SEARCH_SHARE_MAX_LIFETIME_MINUTES,
    BOARD_SEARCH_SHARE_MIN_LIFETIME_MINUTES,
    BOARD_SEARCH_SHARE_REVIEWER_PATH,
    BoardSearchShareStatus,
)
from game_predictor_api.schemas.board_search import BoardSearchResponse, BoardSearchScoreResponse
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


class BoardSearchShareUnlock(ApiModel):
    access_code: str = Field(min_length=1, max_length=64)


class BoardSearchSharePublicContextResponse(ApiModel):
    """What the recipient sees about their access; no internal identities."""

    session_id: UUID
    label: str | None
    game_name: str
    expires_at: datetime


class BoardSearchSharePublicSymbolResponse(ApiModel):
    id: UUID
    mobile_code: int
    code: str
    name: str
    name_pl: str | None
    name_en: str | None
    is_wildcard: bool
    display_order: int
    status: str
    image_revision: str | None = Field(
        description="Checksum of the symbol image for its immutable URL; null without an image."
    )


class BoardSearchSharePublicSearchResultResponse(ApiModel):
    sequence_number: int = Field(ge=1)
    status: str
    board_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    score: BoardSearchScoreResponse


class BoardSearchSharePublicSearchResponse(ApiModel):
    scope: BoardSearchScope
    query_cell_count: int = Field(ge=1, le=15)
    results: tuple[BoardSearchSharePublicSearchResultResponse, ...] = Field(max_length=100)


def to_board_search_share_public_search_response(
    value: BoardSearchResponse,
) -> BoardSearchSharePublicSearchResponse:
    """The Admin search response without review, board and import identities."""

    return BoardSearchSharePublicSearchResponse(
        scope=value.scope,
        query_cell_count=value.query_cell_count,
        results=tuple(
            BoardSearchSharePublicSearchResultResponse(
                sequence_number=result.sequence_number,
                status=result.status,
                board_checksum_sha256=result.board_checksum_sha256,
                score=result.score,
            )
            for result in value.results
        ),
    )


class BoardSearchShareQueryEntryResponse(ApiModel):
    """One recorded query of a share link (D-472); never an IP or header."""

    id: UUID
    session_id: UUID
    game_id: UUID
    occurred_at: datetime
    kind: Literal["search", "approximate_win", "board_detail"]
    request: dict[str, Any]
    result_summary: dict[str, Any]
    outcome_code: str

    @classmethod
    def from_event(cls, value: BoardSearchShareQueryEvent) -> BoardSearchShareQueryEntryResponse:
        return cls(
            id=value.id,
            session_id=value.session_id,
            game_id=value.game_id,
            occurred_at=value.occurred_at,
            kind=value.kind.value,
            request=dict(value.request),
            result_summary=dict(value.result_summary),
            outcome_code=value.outcome_code,
        )


class BoardSearchShareQueryPageResponse(ApiModel):
    entries: list[BoardSearchShareQueryEntryResponse]
    next_cursor: str | None = Field(
        description="Pass as `before` for the next, older page; null on the last page."
    )


class BoardSearchShareQueryReplayResponse(ApiModel):
    """The entry plus the nearest earlier successful search (and, for a
    board detail, range) of the same link, to reproduce it in the Admin."""

    event: BoardSearchShareQueryEntryResponse
    search: BoardSearchShareQueryEntryResponse | None
    approximate_win: BoardSearchShareQueryEntryResponse | None

    @classmethod
    def from_replay(cls, value: BoardSearchShareQueryReplay) -> BoardSearchShareQueryReplayResponse:
        return cls(
            event=BoardSearchShareQueryEntryResponse.from_event(value.event),
            search=None
            if value.search is None
            else BoardSearchShareQueryEntryResponse.from_event(value.search),
            approximate_win=None
            if value.approximate_win is None
            else BoardSearchShareQueryEntryResponse.from_event(value.approximate_win),
        )


__all__ = [
    "BoardSearchShareCreate",
    "BoardSearchShareQueryEntryResponse",
    "BoardSearchShareQueryPageResponse",
    "BoardSearchShareQueryReplayResponse",
    "BoardSearchShareCreatedResponse",
    "BoardSearchShareSessionListResponse",
    "BoardSearchShareSessionResponse",
    "BoardSearchShareUnlock",
    "BoardSearchSharePublicContextResponse",
    "BoardSearchSharePublicSearchResponse",
    "BoardSearchSharePublicSearchResultResponse",
    "BoardSearchSharePublicSymbolResponse",
    "to_board_search_share_public_search_response",
    "board_search_share_url",
]
