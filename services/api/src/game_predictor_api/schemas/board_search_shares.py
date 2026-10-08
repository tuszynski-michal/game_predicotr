"""Local Admin schemas for online board-search share sessions (D-471)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

from pydantic import Field, model_validator

from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareView,
    CreatedBoardSearchShare,
)
from game_predictor_api.application.board_search_share_corrections import (
    CorrectionAction,
    ShareCellCorrectionReceipt,
    ShareCorrectionBoard,
    ShareCorrectionChange,
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
from game_predictor_api.schemas.board_search_approximate_win import (
    ApproximateWinRulesResponse,
    BoardSearchBoardViewResponse,
    BoardSearchCountMatchResponse,
    BoardSearchLineMatchResponse,
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


class BoardSearchShareUnlock(ApiModel):
    access_code: str = Field(min_length=1, max_length=64)


class BoardSearchShareStakeRecordedResponse(ApiModel):
    """Acknowledges a recorded stake choice (D-487); carries no data."""

    recorded: Literal[True] = True


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
    search_context_id: UUID | None = Field(default=None)


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
    kind: Literal[
        "search", "approximate_win", "board_detail", "symbol_correction", "correction_review"
    ]
    request: dict[str, Any]
    result_summary: dict[str, Any]
    outcome_code: str
    follow_up_approximate_win: dict[str, Any] | None = Field(
        default=None,
        description=(
            "For a search: the request (`startSequenceNumber`, `spinCount`) of the "
            "newest successful range calculation made before the next search. "
            "`stakeGrosze` is present when the recipient's stake was recorded "
            "(null: the base stake)."
        ),
    )
    occurrence_times: list[datetime] = Field(
        description=(
            "When this query was made, newest first. A search listed with "
            "`groupByPattern` carries every search of the same pattern."
        ),
    )

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
            follow_up_approximate_win=None
            if value.follow_up_approximate_win is None
            else dict(value.follow_up_approximate_win),
            occurrence_times=list(value.occurrence_times or (value.occurred_at,)),
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


class BoardSearchSharePublicCellResponse(ApiModel):
    cell_index: int = Field(ge=0, le=14)
    cell_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    assigned_symbol_code: str | None
    review_state: str
    quality_issue: str | None


class BoardSearchSharePublicBoardDetailResponse(ApiModel):
    game_id: UUID
    sequence_number: int = Field(ge=1)
    board_status: str
    board_checksum_sha256: str
    data_source: str
    rules: ApproximateWinRulesResponse
    symbol_codes: tuple[str | None, ...]
    payout_credits: int
    payout_kind: Literal["exact", "confirmed_minimum", "none"]
    matches: tuple[BoardSearchLineMatchResponse, ...]
    count_matches: tuple[BoardSearchCountMatchResponse, ...]
    view: BoardSearchBoardViewResponse | None
    document_stale: bool
    cells: tuple[BoardSearchSharePublicCellResponse, ...] | None


class BoardSearchShareCellCorrectionRequest(ApiModel):
    operation_id: UUID
    expected_cell_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: CorrectionAction
    target_symbol_code: str | None = Field(default=None, min_length=1, max_length=64)
    search_context_id: UUID | None = None
    start_sequence_number: int | None = Field(default=None, ge=1)
    spin_count: int | None = Field(default=None, ge=1, le=100_000)
    stake_grosze: int | None = Field(default=None, ge=1, le=10_000_000)

    @model_validator(mode="after")
    def validate_choice(self) -> Self:
        if (self.action == "reassign") != (self.target_symbol_code is not None):
            raise ValueError("Only reassignment requires a target symbol code.")
        if self.spin_count is not None and self.start_sequence_number is None:
            raise ValueError("A range requires its starting sequence number.")
        return self


class BoardSearchShareCellCorrectionResponse(ApiModel):
    saved: Literal[True]
    changed: bool
    sequence_number: int
    cell_index: int
    cell_version: str

    @classmethod
    def from_receipt(cls, value: ShareCellCorrectionReceipt) -> Self:
        return cls.model_validate(value)


class BoardSearchShareCorrectionBoardResponse(ApiModel):
    sequence_number: int
    revision: int
    changed_cell_count: int
    pending: bool
    last_changed_at: datetime
    last_event_id: UUID
    stake_grosze: int | None
    start_sequence_number: int | None

    @classmethod
    def from_board(cls, value: ShareCorrectionBoard) -> Self:
        return cls.model_validate(value)


class BoardSearchShareCorrectionPageResponse(ApiModel):
    entries: list[BoardSearchShareCorrectionBoardResponse]
    next_cursor: str | None
    total_count: int
    pending_count: int


class BoardSearchShareCorrectionChangeResponse(ApiModel):
    id: UUID
    occurred_at: datetime
    cell_index: int
    before_symbol_code: str | None
    after_symbol_code: str | None
    before_quality_issue: str | None
    after_quality_issue: str | None
    before_review_state: str
    after_review_state: str

    @classmethod
    def from_change(cls, value: ShareCorrectionChange) -> Self:
        return cls.model_validate(value)


class BoardSearchShareCorrectionDetailResponse(ApiModel):
    board: BoardSearchShareCorrectionBoardResponse
    board_version: str
    changes: list[BoardSearchShareCorrectionChangeResponse]
    next_cursor: str | None


class BoardSearchShareCorrectionReviewRequest(ApiModel):
    expected_revision: int = Field(ge=1)
    expected_board_version: str = Field(pattern=r"^[a-f0-9]{64}$")


__all__ = [
    "BoardSearchShareCreate",
    "BoardSearchShareQueryEntryResponse",
    "BoardSearchShareQueryPageResponse",
    "BoardSearchShareQueryReplayResponse",
    "BoardSearchShareCreatedResponse",
    "BoardSearchShareSessionListResponse",
    "BoardSearchShareSessionResponse",
    "BoardSearchShareStakeRecordedResponse",
    "BoardSearchShareUnlock",
    "BoardSearchSharePublicContextResponse",
    "BoardSearchSharePublicSearchResponse",
    "BoardSearchSharePublicSearchResultResponse",
    "BoardSearchSharePublicSymbolResponse",
    "to_board_search_share_public_search_response",
    "board_search_share_url",
]
