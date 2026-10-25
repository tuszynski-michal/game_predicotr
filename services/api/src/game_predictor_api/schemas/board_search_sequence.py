"""Additive OpenAPI contract for consecutive board searches."""

from collections.abc import Sequence
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.board_search import BoardSearchSequenceOutcome
from game_predictor_api.domain.board_search import BoardSearchQueryCell, BoardSearchScope
from game_predictor_api.domain.board_search_sequence import validate_board_search_patterns
from game_predictor_api.schemas.board_search import (
    BoardSearchResultResponse,
    BoardSearchScoreResponse,
    to_board_search_response,
)
from game_predictor_api.schemas.board_search_shares import (
    BoardSearchSharePublicSearchResultResponse,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.super_game_series import SuperGameStateResponse


class BoardSearchPatternCell(ApiModel):
    cell_index: int = Field(ge=0, le=14)
    symbol_code: str | None = Field(max_length=64)


class BoardSearchPattern(ApiModel):
    cells: tuple[BoardSearchPatternCell, ...] = Field(min_length=1, max_length=15)


class BoardSearchSequenceRequest(ApiModel):
    patterns: tuple[BoardSearchPattern, ...] = Field(min_length=1, max_length=4)
    scope: BoardSearchScope = BoardSearchScope.ALL_SEARCHABLE
    limit: int = Field(default=100, ge=1, le=100)

    def queries(self) -> tuple[tuple[BoardSearchQueryCell, ...], ...]:
        return validate_board_search_patterns(
            tuple(
                tuple(
                    BoardSearchQueryCell(cell.cell_index, cell.symbol_code)
                    for cell in pattern.cells
                )
                for pattern in self.patterns
            )
        )


class BoardSearchSequenceScoreResponse(BoardSearchScoreResponse):
    exact_match_count: int = Field(ge=0, le=60)
    alternative_match_count: int = Field(ge=0, le=60)
    weighted_alternative_score: float = Field(ge=0, le=60)
    mismatch_count: int = Field(ge=0, le=60)
    unknown_count: int = Field(ge=0, le=60)


class BoardSearchSequenceResultResponse(ApiModel):
    start_sequence_number: int = Field(ge=1)
    end_sequence_number: int = Field(ge=1)
    score: BoardSearchSequenceScoreResponse
    boards: tuple[BoardSearchResultResponse, ...] = Field(min_length=1, max_length=4)


class BoardSearchSequenceResponse(ApiModel):
    game_id: UUID
    scope: BoardSearchScope
    pattern_count: int = Field(ge=1, le=4)
    query_cell_count: int = Field(ge=1, le=60)
    results: tuple[BoardSearchSequenceResultResponse, ...] = Field(max_length=100)
    super_game_state: SuperGameStateResponse


class BoardSearchSharePublicSequenceResultResponse(ApiModel):
    start_sequence_number: int = Field(ge=1)
    end_sequence_number: int = Field(ge=1)
    score: BoardSearchSequenceScoreResponse
    boards: tuple[BoardSearchSharePublicSearchResultResponse, ...] = Field(
        min_length=1, max_length=4
    )


class BoardSearchSharePublicSequenceResponse(ApiModel):
    scope: BoardSearchScope
    pattern_count: int = Field(ge=1, le=4)
    query_cell_count: int = Field(ge=1, le=60)
    results: tuple[BoardSearchSharePublicSequenceResultResponse, ...] = Field(max_length=100)
    super_game_state: SuperGameStateResponse
    search_context_id: UUID | None = None


def to_board_search_sequence_response(
    *,
    game_id: UUID,
    scope: BoardSearchScope,
    query_cell_counts: Sequence[int],
    outcome: BoardSearchSequenceOutcome,
) -> BoardSearchSequenceResponse:
    return BoardSearchSequenceResponse(
        game_id=game_id,
        scope=scope,
        pattern_count=len(query_cell_counts),
        query_cell_count=sum(query_cell_counts),
        super_game_state=SuperGameStateResponse.from_domain(outcome.super_game.state),
        results=tuple(
            BoardSearchSequenceResultResponse(
                start_sequence_number=result.start_sequence_number,
                end_sequence_number=result.end_sequence_number,
                score=BoardSearchSequenceScoreResponse.model_validate(result.score),
                boards=tuple(
                    to_board_search_response(
                        game_id=game_id,
                        scope=scope,
                        query_cell_count=count,
                        results=(board,),
                        super_game=outcome.super_game,
                    ).results[0]
                    for board, count in zip(result.boards, query_cell_counts, strict=True)
                ),
            )
            for result in outcome.results
        ),
    )


def to_public_sequence_response(
    value: BoardSearchSequenceResponse,
    search_context_id: UUID | None,
) -> BoardSearchSharePublicSequenceResponse:
    return BoardSearchSharePublicSequenceResponse(
        scope=value.scope,
        pattern_count=value.pattern_count,
        query_cell_count=value.query_cell_count,
        super_game_state=value.super_game_state,
        search_context_id=search_context_id,
        results=tuple(
            BoardSearchSharePublicSequenceResultResponse(
                start_sequence_number=result.start_sequence_number,
                end_sequence_number=result.end_sequence_number,
                score=result.score,
                boards=tuple(
                    BoardSearchSharePublicSearchResultResponse(
                        sequence_number=board.sequence_number,
                        status=board.status,
                        board_checksum_sha256=board.board_checksum_sha256,
                        score=board.score,
                        super_game=board.super_game,
                    )
                    for board in result.boards
                ),
            )
            for result in value.results
        ),
    )
