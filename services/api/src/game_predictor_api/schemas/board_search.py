"""OpenAPI schemas for the read-only partial-board search endpoint."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.board_search import BoardSearchResult, BoardSearchScope
from game_predictor_api.schemas.catalog import ApiModel


class BoardSearchScoreResponse(ApiModel):
    score: float = Field(ge=0, le=100)
    exact_match_count: int = Field(ge=0, le=15)
    alternative_match_count: int = Field(ge=0, le=15)
    weighted_alternative_score: float = Field(ge=0, le=15)
    mismatch_count: int = Field(ge=0, le=15)
    unknown_count: int = Field(ge=0, le=15)


class BoardSearchResultResponse(ApiModel):
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int = Field(ge=1)
    status: str
    board_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    score: BoardSearchScoreResponse


class BoardSearchResponse(ApiModel):
    game_id: UUID
    scope: BoardSearchScope
    query_cell_count: int = Field(ge=1, le=15)
    results: tuple[BoardSearchResultResponse, ...] = Field(max_length=100)


def to_board_search_response(
    *,
    game_id: UUID,
    scope: BoardSearchScope,
    query_cell_count: int,
    results: tuple[BoardSearchResult, ...],
) -> BoardSearchResponse:
    return BoardSearchResponse(
        game_id=game_id,
        scope=scope,
        query_cell_count=query_cell_count,
        results=tuple(
            BoardSearchResultResponse(
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
