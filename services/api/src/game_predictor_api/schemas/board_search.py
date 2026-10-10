"""OpenAPI schemas for the read-only partial-board search endpoint."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.board_search import (
    BoardSearchAssetMode,
    BoardSearchResult,
    BoardSearchScope,
)
from game_predictor_api.domain.super_game_markers import SuperGameMarkers
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.super_game_markers import (
    SuperGameMarkerResponse,
    marker_response_at,
)
from game_predictor_api.schemas.super_game_series import SuperGameStateResponse


class BoardSearchScoreResponse(ApiModel):
    score: float = Field(ge=0, le=100)
    exact_match_count: int = Field(ge=0, le=15)
    alternative_match_count: int = Field(ge=0, le=15)
    weighted_alternative_score: float = Field(ge=0, le=15)
    mismatch_count: int = Field(ge=0, le=15)
    unknown_count: int = Field(ge=0, le=15)


class BoardSearchResultResponse(ApiModel):
    asset_mode: BoardSearchAssetMode
    review_item_id: UUID | None
    recognized_board_id: UUID | None
    import_job_id: UUID | None
    sequence_number: int = Field(ge=1)
    status: str
    board_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    score: BoardSearchScoreResponse
    super_game: SuperGameMarkerResponse | None = Field(
        default=None,
        description=(
            "Super game role of this board in the published series generation "
            "(trigger or spin of a series); absent: base mode according to that "
            "generation. Never present for a game without a super game kind."
        ),
    )


class BoardSearchResponse(ApiModel):
    game_id: UUID
    scope: BoardSearchScope
    query_cell_count: int = Field(ge=1, le=15)
    results: tuple[BoardSearchResultResponse, ...] = Field(max_length=100)
    super_game_state: SuperGameStateResponse | None = Field(
        default=None,
        description=(
            "Freshness of the series generation behind the per-board markers, "
            "read in the same snapshot; present on every live response (null only "
            "in a stored management receipt written before the field existed). "
            "`fresh = false`: the series are being recalculated, so even boards "
            "without a marker may be part of a series."
        ),
    )


def to_board_search_response(
    *,
    game_id: UUID,
    scope: BoardSearchScope,
    query_cell_count: int,
    results: tuple[BoardSearchResult, ...],
    super_game: SuperGameMarkers | None = None,
) -> BoardSearchResponse:
    return BoardSearchResponse(
        game_id=game_id,
        scope=scope,
        query_cell_count=query_cell_count,
        super_game_state=(
            None if super_game is None else SuperGameStateResponse.from_domain(super_game.state)
        ),
        results=tuple(
            BoardSearchResultResponse(
                asset_mode=result.asset_mode,
                review_item_id=result.review_item_id,
                recognized_board_id=result.recognized_board_id,
                import_job_id=result.import_job_id,
                sequence_number=result.sequence_number,
                status=result.status,
                board_checksum_sha256=result.board_checksum_sha256,
                score=BoardSearchScoreResponse(
                    score=result.score.score,
                    exact_match_count=result.score.exact_match_count,
                    alternative_match_count=result.score.alternative_match_count,
                    weighted_alternative_score=result.score.weighted_alternative_score,
                    mismatch_count=result.score.mismatch_count,
                    unknown_count=result.score.unknown_count,
                ),
                super_game=marker_response_at(super_game, result.sequence_number),
            )
            for result in results
        ),
    )


__all__ = [
    "BoardSearchResponse",
    "BoardSearchResultResponse",
    "BoardSearchScoreResponse",
    "to_board_search_response",
]
