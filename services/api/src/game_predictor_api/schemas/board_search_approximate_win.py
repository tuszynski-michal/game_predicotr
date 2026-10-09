"""OpenAPI schemas for the read-only "Przybliżona wygrana" range endpoint."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.board_search_approximate_win import ApproximateWinCalculation
from game_predictor_api.application.board_search_board_detail import BoardSearchBoardDetail
from game_predictor_api.domain.board_search import BoardSearchAssetMode
from game_predictor_api.domain.board_search_board_detail import BoardCountMatch, BoardExpansion
from game_predictor_api.domain.super_game_markers import SuperGameMarkers
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.super_game_markers import (
    SuperGameMarkerResponse,
    marker_response_at,
)
from game_predictor_api.schemas.super_game_series import SuperGameStateResponse


class ApproximateWinRulesResponse(ApiModel):
    rules_version_id: UUID
    rules_version: int = Field(ge=1)
    spin_cost: int = Field(ge=0)
    algorithm_version: str


SequenceModeValue = Literal["base", "super"]

ApproximateWinPayoutKind = Literal["exact", "confirmed_minimum", "provisional"]


class ApproximateWinSpinRangeResponse(ApiModel):
    """Inclusive range of spin numbers (1-based within the evaluated range)."""

    start_spin: int = Field(ge=1)
    end_spin: int = Field(ge=1)


class ApproximateWinSummaryResponse(ApiModel):
    recognized_payout_credits: int = Field(
        ge=0,
        description=(
            "Sum of exact and confirmed_minimum payouts; provisional payouts are "
            "summed apart in provisionalPayoutCredits and never enter the balance."
        ),
    )
    spin_cost_credits: int = Field(
        ge=0,
        description=(
            "Sum of the cost of every evaluated spin: the rules' spin cost in base "
            "mode, the free spin cost (0) inside a super game series."
        ),
    )
    balance_credits: int
    provisional_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Evaluated super game series boards whose result is provisional (super "
            "symbol undefined, stale series generation or any unknown cell)."
        ),
    )
    provisional_payout_credits: int = Field(
        default=0,
        ge=0,
        description=(
            "Sum of provisional payouts; after the super symbol is defined or the "
            "board completed it may grow or shrink, so it is not a lower bound."
        ),
    )
    super_spin_ranges: tuple[ApproximateWinSpinRangeResponse, ...] = Field(
        default=(),
        description=(
            "Spins evaluated in super mode (free spins of a published super game "
            "series), as inclusive spin-number ranges; every other spin costs "
            "rules.spinCost. Empty for a game without a super game kind. Lets a "
            "client compute the exact cost and balance at any spin."
        ),
    )
    super_spin_cost: int = Field(
        default=0,
        ge=0,
        description="Cost of one spin inside superSpinRanges (0 for wild_super_spins).",
    )


class ApproximateWinCompletenessResponse(ApiModel):
    complete_board_count: int = Field(ge=0)
    partial_board_count: int = Field(ge=0)
    missing_board_count: int = Field(ge=0)


class BoardSearchCountMatchResponse(ApiModel):
    """A super game trigger symbol paid per count of its cells anywhere on
    the board (`payout-v4-wild-count`); unknown cells are never counted."""

    symbol_code: str
    count: int = Field(ge=1)
    cells: tuple[int, ...]
    payout_credits: int = Field(ge=0)


def _count_match_responses(
    count_matches: tuple[BoardCountMatch, ...],
) -> tuple[BoardSearchCountMatchResponse, ...]:
    return tuple(
        BoardSearchCountMatchResponse(
            symbol_code=match.symbol_code,
            count=match.count,
            cells=match.cells,
            payout_credits=match.payout_credits,
        )
        for match in count_matches
    )


class ApproximateWinRowResponse(ApiModel):
    spin_number: int = Field(ge=1)
    sequence_number: int = Field(ge=1)
    payout_credits: int = Field(gt=0)
    cumulative_payout_credits: int = Field(ge=0)
    cumulative_cost_credits: int = Field(ge=0)
    cumulative_balance_credits: int
    payout_kind: ApproximateWinPayoutKind = Field(
        description=(
            "exact: complete board; confirmed_minimum: partial board whose visible "
            "prefix guarantees the payout; provisional: super game series board "
            "whose payout can still grow or shrink (not in the cumulative payout)."
        )
    )
    board_status: str
    mode: SequenceModeValue | None = Field(
        default=None,
        description=(
            "Game mode of the position: base, or super inside a published super "
            "game series. Null only in frozen management result history."
        ),
    )
    spin_cost_credits: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Cost of this spin (0 inside a super game series). Null only in frozen "
            "management result history."
        ),
    )
    count_matches: tuple[BoardSearchCountMatchResponse, ...] = Field(
        default=(),
        description=(
            "Count payouts of super game trigger symbols, already included in "
            "payoutCredits. Empty for games without a trigger symbol and in "
            "frozen management result history."
        ),
    )
    super_game: SuperGameMarkerResponse | None = Field(
        default=None,
        description=(
            "Super game role of this board in the published series generation "
            "(trigger or spin of a series); absent: base mode according to that "
            "generation. Never present for a game without a super game kind or "
            "in frozen management result history."
        ),
    )


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
    super_game_state: SuperGameStateResponse | None = Field(
        default=None,
        description=(
            "Freshness of the series generation behind the per-row markers, read "
            "in the same snapshot; present on every live response, null only in "
            "frozen management result history. `fresh = false`: the series are "
            "being recalculated, so even rows without a marker may be part of a "
            "series."
        ),
    )


def apply_super_game_markers(
    response: ApproximateWinResponse, markers: SuperGameMarkers
) -> ApproximateWinResponse:
    """A copy of ``response`` carrying the row markers and the generation state
    (management preview: the frozen snapshot itself never holds markers)."""

    return response.model_copy(
        update={
            "super_game_state": SuperGameStateResponse.from_domain(markers.state),
            "rows": tuple(
                row.model_copy(
                    update={"super_game": marker_response_at(markers, row.sequence_number)}
                )
                for row in response.rows
            ),
        }
    )


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
            provisional_count=result.summary.provisional_count,
            provisional_payout_credits=result.summary.provisional_payout_credits,
            super_spin_ranges=tuple(
                ApproximateWinSpinRangeResponse(start_spin=first, end_spin=last)
                for first, last in result.super_spin_ranges
            ),
            super_spin_cost=result.super_spin_cost if result.super_spin_ranges else 0,
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
                mode=row.mode.value,
                spin_cost_credits=row.spin_cost_credits,
                count_matches=_count_match_responses(row.count_matches),
                super_game=marker_response_at(calculation.super_game, row.sequence_number),
            )
            for row in result.rows
        ),
        super_game_state=(
            None
            if calculation.super_game is None
            else SuperGameStateResponse.from_domain(calculation.super_game.state)
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


class BoardSearchExpansionResponse(ApiModel):
    """The super symbol expanded over whole columns of a super game series
    board (`wild_super_spins`): `payoutCredits = linePayoutCredits ×
    paylineCount`; it replaces the super symbol's own line wins."""

    symbol_code: str
    columns: tuple[int, ...] = Field(description="0-based columns filled with the super symbol.")
    column_count: int = Field(ge=1)
    line_payout_credits: int = Field(ge=0)
    payline_count: int = Field(ge=1)
    payout_credits: int = Field(ge=0)


def _expansion_response(expansion: BoardExpansion | None) -> BoardSearchExpansionResponse | None:
    if expansion is None:
        return None
    return BoardSearchExpansionResponse(
        symbol_code=expansion.symbol_code,
        columns=expansion.columns,
        column_count=expansion.column_count,
        line_payout_credits=expansion.line_payout_credits,
        payline_count=expansion.payline_count,
        payout_credits=expansion.payout_credits,
    )


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


class BoardSearchBoardCellResponse(ApiModel):
    """One cell's review record: the checksum-bound target of
    `applySymbolCellReviewDecision` (D-473)."""

    cell_index: int = Field(ge=0, le=14)
    cell_review_id: UUID
    revision: int = Field(ge=0)
    geometry_revision: int = Field(ge=0)
    crop_sample_id: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    crop_checksum_sha256: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    review_state: str
    quality_issue: str | None
    assigned_symbol_code: str | None


class BoardSearchBoardDetailResponse(ApiModel):
    game_id: UUID
    sequence_number: int = Field(ge=1)
    board_status: str
    board_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    data_source: BoardSearchAssetMode
    rules: ApproximateWinRulesResponse
    symbol_codes: tuple[str | None, ...]
    payout_credits: int = Field(ge=0)
    payout_kind: Literal["exact", "confirmed_minimum", "provisional", "none"]
    matches: tuple[BoardSearchLineMatchResponse, ...]
    count_matches: tuple[BoardSearchCountMatchResponse, ...] = Field(
        description=(
            "Count payouts of super game trigger symbols, counted on the original "
            "board; payoutCredits is the sum of matches, countMatches and expansion."
        )
    )
    mode: SequenceModeValue = Field(
        default="base",
        description="base, or super for a spin of a published super game series.",
    )
    spin_cost_credits: int | None = Field(
        default=None, ge=0, description="Cost of this spin (0 inside a super game series)."
    )
    expanded_symbol_codes: tuple[str | None, ...] | None = Field(
        default=None,
        description=(
            "The board the lines were evaluated on when the super symbol expanded "
            "(its columns filled with the super symbol); null without an expansion. "
            "symbolCodes stays the original board."
        ),
    )
    expansion: BoardSearchExpansionResponse | None = None
    view: BoardSearchBoardViewResponse | None
    document_stale: bool = Field(
        description=(
            "True when the board changed after its search document was written; "
            "lines then come from the older reading and no view or cells are given."
        )
    )
    cells: tuple[BoardSearchBoardCellResponse, ...] | None = Field(
        description=(
            "Editable cell review records of a pending operational board; "
            "null for resolved and archive boards."
        )
    )


class BoardSearchBoardRefreshResponse(ApiModel):
    """Outcome of rebuilding one board's search document (TASK-0773)."""

    document_removed: bool = Field(
        description="The rebuild left no search document at this sequence position."
    )
    detail: BoardSearchBoardDetailResponse | None


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
        count_matches=_count_match_responses(detail.count_matches),
        mode=detail.mode.value,
        spin_cost_credits=detail.spin_cost_credits,
        expanded_symbol_codes=detail.expanded_symbol_codes,
        expansion=_expansion_response(detail.expansion),
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
        document_stale=detail.document_stale,
        cells=None
        if detail.cells is None
        else tuple(
            BoardSearchBoardCellResponse(
                cell_index=cell.cell_index,
                cell_review_id=cell.cell_review_id,
                revision=cell.revision,
                geometry_revision=cell.geometry_revision,
                crop_sample_id=cell.crop_sample_id,
                crop_checksum_sha256=cell.crop_checksum_sha256,
                review_state=cell.review_state,
                quality_issue=cell.quality_issue,
                assigned_symbol_code=cell.assigned_symbol_code,
            )
            for cell in detail.cells
        ),
    )


__all__ = [
    "ApproximateWinCompletenessResponse",
    "BoardSearchBoardCellResponse",
    "BoardSearchBoardDetailResponse",
    "BoardSearchBoardRefreshResponse",
    "BoardSearchBoardViewResponse",
    "BoardSearchCountMatchResponse",
    "BoardSearchExpansionResponse",
    "BoardSearchLineMatchResponse",
    "BoardSearchViewPointResponse",
    "ApproximateWinResponse",
    "ApproximateWinRowResponse",
    "ApproximateWinRulesResponse",
    "ApproximateWinSpinRangeResponse",
    "ApproximateWinSummaryResponse",
    "apply_super_game_markers",
    "to_approximate_win_response",
    "to_board_search_board_detail_response",
]
