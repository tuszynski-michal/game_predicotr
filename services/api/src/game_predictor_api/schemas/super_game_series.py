"""OpenAPI schemas of super game series (TASK-0933, D-535)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.super_game_series import (
    DeriveRequestResult,
    SeriesBoard,
    SeriesBoards,
    SuperGameSeriesPage,
    SuperGameSeriesRecord,
)
from game_predictor_api.domain.super_game_series import (
    RunVerification,
    SeriesCompleteness,
    SuperGameState,
)
from game_predictor_api.schemas.catalog import ApiModel


class SuperGameStateResponse(ApiModel):
    """Freshness of the published series, always derived from the two versions."""

    fresh: bool
    input_version: int = Field(ge=0)
    generation_input_version: int | None = Field(default=None, ge=0)

    @classmethod
    def from_domain(cls, state: SuperGameState) -> SuperGameStateResponse:
        return cls(
            fresh=state.fresh,
            input_version=state.input_version,
            generation_input_version=state.generation_input_version,
        )


class SuperGameSeriesResponse(ApiModel):
    id: UUID
    game_id: UUID
    trigger_sequence_number: int = Field(ge=1)
    start_sequence_number: int = Field(ge=2)
    end_sequence_number: int = Field(ge=2)
    length: int = Field(ge=1)
    retrigger_sequence_numbers: list[int]
    completeness: SeriesCompleteness
    run_verification: RunVerification
    super_symbol_id: UUID | None
    defined_by: str | None
    defined_at: datetime | None
    revision: int = Field(ge=0)
    updated_at: datetime

    @classmethod
    def from_domain(cls, record: SuperGameSeriesRecord) -> SuperGameSeriesResponse:
        return cls(
            id=record.id,
            game_id=record.game_id,
            trigger_sequence_number=record.trigger_sequence_number,
            start_sequence_number=record.start_sequence_number,
            end_sequence_number=record.end_sequence_number,
            length=record.length,
            retrigger_sequence_numbers=list(record.retrigger_sequence_numbers),
            completeness=record.completeness,
            run_verification=record.run_verification,
            super_symbol_id=record.super_symbol_id,
            defined_by=record.defined_by,
            defined_at=record.defined_at,
            revision=record.revision,
            updated_at=record.updated_at,
        )


class SuperGameSeriesCountsResponse(ApiModel):
    """Exact counts of all published series of the game, independent of filters."""

    total: int = Field(ge=0)
    undefined: int = Field(ge=0)


class SuperGameSeriesListResponse(ApiModel):
    items: list[SuperGameSeriesResponse]
    next_cursor: str | None
    super_game_kind: str
    super_game_state: SuperGameStateResponse
    counts: SuperGameSeriesCountsResponse

    @classmethod
    def from_domain(cls, page: SuperGameSeriesPage) -> SuperGameSeriesListResponse:
        return cls(
            items=[SuperGameSeriesResponse.from_domain(item) for item in page.items],
            next_cursor=page.next_cursor,
            super_game_kind=page.super_game_kind,
            super_game_state=SuperGameStateResponse.from_domain(page.state),
            counts=SuperGameSeriesCountsResponse(
                total=page.counts.total, undefined=page.counts.undefined
            ),
        )


class SuperGameSeriesBoardResponse(ApiModel):
    """One position of a series in the board-search result format.

    The board fields are those of a board-search result
    (``assetMode`` … ``boardChecksumSha256``); they are ``null`` and
    ``missing`` is ``true`` when the position has no board.
    """

    sequence_number: int = Field(ge=1)
    role: Literal["trigger", "retrigger", "spin"]
    spin_index: int | None = Field(default=None, ge=1)
    missing: bool
    asset_mode: Literal["operational_review"] | None
    review_item_id: UUID | None
    recognized_board_id: UUID | None
    import_job_id: UUID | None
    status: Literal["pending", "accepted", "corrected"] | None
    board_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_domain(cls, board: SeriesBoard) -> SuperGameSeriesBoardResponse:
        document = board.document
        return cls.model_validate(
            {
                "sequence_number": board.sequence_number,
                "role": board.role.value,
                "spin_index": board.spin_index,
                "missing": board.missing,
                "asset_mode": None if document is None else document.asset_mode,
                "review_item_id": None if document is None else document.review_item_id,
                "recognized_board_id": None if document is None else document.recognized_board_id,
                "import_job_id": None if document is None else document.import_job_id,
                "status": None if document is None else document.status,
                "board_checksum_sha256": (
                    None if document is None else document.board_checksum_sha256
                ),
            }
        )


class SuperGameSeriesBoardsResponse(ApiModel):
    series: SuperGameSeriesResponse
    boards: list[SuperGameSeriesBoardResponse]
    super_game_state: SuperGameStateResponse

    @classmethod
    def from_domain(cls, result: SeriesBoards) -> SuperGameSeriesBoardsResponse:
        return cls(
            series=SuperGameSeriesResponse.from_domain(result.series),
            boards=[SuperGameSeriesBoardResponse.from_domain(board) for board in result.boards],
            super_game_state=SuperGameStateResponse.from_domain(result.state),
        )


class SuperSymbolUpdate(ApiModel):
    symbol_id: UUID | None
    expected_revision: int = Field(ge=0)


class SuperGameSeriesDeriveResponse(ApiModel):
    job_id: UUID
    deduplicated: bool
    super_game_state: SuperGameStateResponse

    @classmethod
    def from_domain(cls, result: DeriveRequestResult) -> SuperGameSeriesDeriveResponse:
        return cls(
            job_id=result.job_id,
            deduplicated=result.deduplicated,
            super_game_state=SuperGameStateResponse.from_domain(result.state),
        )


__all__ = [
    "SuperGameSeriesBoardResponse",
    "SuperGameSeriesBoardsResponse",
    "SuperGameSeriesDeriveResponse",
    "SuperGameSeriesListResponse",
    "SuperGameSeriesResponse",
    "SuperGameStateResponse",
    "SuperSymbolUpdate",
]
