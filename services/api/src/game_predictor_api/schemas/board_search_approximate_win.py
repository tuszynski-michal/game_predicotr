"""OpenAPI schemas for the read-only "Przybliżona wygrana" range endpoint."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.board_search_approximate_win import ApproximateWinCalculation
from game_predictor_api.application.board_search_board_detail import BoardSearchBoardDetail
from game_predictor_api.domain.board_search import BoardSearchAssetMode
from game_predictor_api.schemas.catalog import ApiModel


class ApproximateWinRulesResponse(ApiModel):
    rules_version_id: UUID
    rules_version: int = Field(ge=1)
    spin_cost: int = Field(ge=0)
    algorithm_version: str


class ApproximateWinSummaryResponse(ApiModel):
    recognized_payout_credits: int = Field(ge=0)
    spin_cost_credits: int = Field(ge=0)
    balance_credits: int


class ApproximateWinCompletenessResponse(ApiModel):
    complete_board_count: int = Field(ge=0)
    partial_board_count: int = Field(ge=0)
    missing_board_count: int = Field(ge=0)


class ApproximateWinRowResponse(ApiModel):
    spin_number: int = Field(ge=1)
    sequence_number: int = Field(ge=1)
    payout_credits: int = Field(gt=0)
    cumulative_payout_credits: int = Field(ge=0)
    cumulative_cost_credits: int = Field(ge=0)
    cumulative_balance_credits: int
    payout_kind: Literal["exact", "confirmed_minimum"]
    board_status: str


class ApproximateWinResponse(ApiModel):
    game_id: UUID
    start_sequence_number: int = Field(ge=1)
    start_board_status: str | None
    requested_spin_count: int = Field(ge=1)
    evaluated_spin_count: int = Field(ge=0)
    sequence_length: int = Field(ge=1)
    wrapped_at_sequence_end: bool
    data_source: BoardSearchAssetMode
    data_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rules: ApproximateWinRulesResponse
    summary: ApproximateWinSummaryResponse
    completeness: ApproximateWinCompletenessResponse
    rows: tuple[ApproximateWinRowResponse, ...]


def to_approximate_win_response(
    calculation: ApproximateWinCalculation,
) -> ApproximateWinResponse:
    result = calculation.result
    return ApproximateWinResponse(
        game_id=calculation.game_id,
        start_sequence_number=result.start_sequence_number,
        start_board_status=calculation.start_board_status,
        requested_spin_count=result.requested_spin_count,
        evaluated_spin_count=result.evaluated_spin_count,
        sequence_length=result.sequence_length,
        wrapped_at_sequence_end=result.wrapped_at_sequence_end,
        data_source=calculation.data_source,
        data_fingerprint_sha256=result.data_fingerprint_sha256,
        rules=ApproximateWinRulesResponse(
            rules_version_id=calculation.rules_version_id,
            rules_version=calculation.rules_version,
            spin_cost=calculation.spin_cost,
            algorithm_version=calculation.algorithm_version,
        ),
        summary=ApproximateWinSummaryResponse(
            recognized_payout_credits=result.summary.recognized_payout_credits,
            spin_cost_credits=result.summary.spin_cost_credits,
            balance_credits=result.summary.balance_credits,
        ),
        completeness=ApproximateWinCompletenessResponse(
            complete_board_count=result.completeness.complete_board_count,
            partial_board_count=result.completeness.partial_board_count,
            missing_board_count=result.completeness.missing_board_count,
        ),
        rows=tuple(
            ApproximateWinRowResponse(
                spin_number=row.spin_number,
                sequence_number=row.sequence_number,
                payout_credits=row.payout_credits,
                cumulative_payout_credits=row.cumulative_payout_credits,
                cumulative_cost_credits=row.cumulative_cost_credits,
                cumulative_balance_credits=row.cumulative_balance_credits,
                payout_kind=row.payout_kind,  # type: ignore[arg-type]
                board_status=row.board_status,
            )
            for row in result.rows
        ),
    )


class BoardSearchLineMatchResponse(ApiModel):
    payline_id: str
    payline_code: str
    payline_name: str
    payline_display_order: int = Field(ge=0)
    row_path: tuple[int, ...]
    symbol_code: str
    matched_length: int = Field(ge=1)
    matched_cells: tuple[int, ...]
    joker_cells: tuple[int, ...]
    payout_credits: int = Field(gt=0)


class BoardSearchViewPointResponse(ApiModel):
    x: float
    y: float


class BoardSearchBoardViewResponse(ApiModel):
    """Size of the cropped view and cell polygons in its 0–1 coordinates."""

    width: int = Field(ge=1)
    height: int = Field(ge=1)
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    cell_polygons: tuple[tuple[BoardSearchViewPointResponse, ...], ...] | None = Field(
        min_length=15, max_length=15
    )


class BoardSearchBoardDetailResponse(ApiModel):
    game_id: UUID
    sequence_number: int = Field(ge=1)
    board_status: str
    board_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    data_source: BoardSearchAssetMode
    rules: ApproximateWinRulesResponse
    symbol_codes: tuple[str | None, ...]
    payout_credits: int = Field(ge=0)
    payout_kind: Literal["exact", "confirmed_minimum", "none"]
    matches: tuple[BoardSearchLineMatchResponse, ...]
    view: BoardSearchBoardViewResponse | None


def to_board_search_board_detail_response(
    detail: BoardSearchBoardDetail,
) -> BoardSearchBoardDetailResponse:
    return BoardSearchBoardDetailResponse(
        game_id=detail.game_id,
        sequence_number=detail.sequence_number,
        board_status=detail.board_status,
        board_checksum_sha256=detail.board_checksum_sha256,
        data_source=detail.data_source,
        rules=ApproximateWinRulesResponse(
            rules_version_id=detail.rules_version_id,
            rules_version=detail.rules_version,
            spin_cost=detail.spin_cost,
            algorithm_version=detail.algorithm_version,
        ),
        symbol_codes=detail.symbol_codes,
        payout_credits=detail.payout_credits,
        payout_kind=detail.payout_kind,
        matches=tuple(
            BoardSearchLineMatchResponse(
                payline_id=match.payline_id,
                payline_code=match.payline_code,
                payline_name=match.payline_name,
                payline_display_order=match.payline_display_order,
                row_path=match.row_path,
                symbol_code=match.symbol_code,
                matched_length=match.matched_length,
                matched_cells=match.matched_cells,
                joker_cells=match.joker_cells,
                payout_credits=match.payout_credits,
            )
            for match in detail.matches
        ),
        view=None
        if detail.view is None
        else BoardSearchBoardViewResponse(
            width=detail.view.width,
            height=detail.view.height,
            revision=detail.view.revision,
            cell_polygons=None
            if detail.view.cell_polygons is None
            else tuple(
                tuple(BoardSearchViewPointResponse(x=x, y=y) for x, y in polygon)
                for polygon in detail.view.cell_polygons
            ),
        ),
    )


__all__ = [
    "ApproximateWinCompletenessResponse",
    "BoardSearchBoardDetailResponse",
    "BoardSearchBoardViewResponse",
    "BoardSearchLineMatchResponse",
    "BoardSearchViewPointResponse",
    "ApproximateWinResponse",
    "ApproximateWinRowResponse",
    "ApproximateWinRulesResponse",
    "ApproximateWinSummaryResponse",
    "to_approximate_win_response",
    "to_board_search_board_detail_response",
]
