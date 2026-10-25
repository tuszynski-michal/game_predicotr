"""Deterministic reference ranking for consecutive partial board patterns."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from game_predictor_api.domain.board_search import (
    BoardSearchCandidate,
    BoardSearchError,
    BoardSearchQueryCell,
    BoardSearchResult,
    BoardSearchScope,
    BoardSearchScore,
    rank_board_search_candidates,
    score_board_search_candidate,
    validate_board_search_query,
)

SEQUENCE_PATTERN_MAX = 4
SEQUENCE_REQUEST_MAX_BYTES = 32768


class BoardSearchSequenceError(BoardSearchError):
    def __init__(self, code: str, message: str, *, pattern_index: int | None = None) -> None:
        super().__init__(code, message)
        self.details: dict[str, object] = (
            {} if pattern_index is None else {"patternIndex": pattern_index}
        )


@dataclass(frozen=True, slots=True)
class BoardSearchSequenceResult:
    boards: tuple[BoardSearchResult, ...]
    score: BoardSearchScore

    @property
    def start_sequence_number(self) -> int:
        return self.boards[0].sequence_number

    @property
    def end_sequence_number(self) -> int:
        return self.boards[-1].sequence_number


@dataclass(frozen=True, slots=True)
class RankedBoardSearchSequence:
    boards: tuple[BoardSearchCandidate, ...]
    scores: tuple[BoardSearchScore, ...]
    score: BoardSearchScore


def validate_board_search_patterns(
    patterns: Sequence[Iterable[BoardSearchQueryCell]],
) -> tuple[tuple[BoardSearchQueryCell, ...], ...]:
    if not 1 <= len(patterns) <= SEQUENCE_PATTERN_MAX:
        raise BoardSearchSequenceError(
            "BOARD_SEARCH_SEQUENCE_INVALID", "Provide between one and four board patterns."
        )
    queries = []
    for index, pattern in enumerate(patterns):
        supplied = tuple(pattern)
        try:
            if len(supplied) > 15:
                raise BoardSearchError(
                    "BOARD_SEARCH_CELL_INVALID", "A pattern has at most 15 cells."
                )
            queries.append(validate_board_search_query(supplied))
        except BoardSearchError as error:
            raise BoardSearchSequenceError(
                "BOARD_SEARCH_SEQUENCE_INVALID", error.message, pattern_index=index
            ) from error
    return tuple(queries)


def validate_sequence_length(sequence_length: int, pattern_count: int) -> None:
    if sequence_length < 1 or pattern_count > sequence_length:
        raise BoardSearchSequenceError(
            "BOARD_SEARCH_SEQUENCE_LENGTH_INVALID",
            "The sequence must contain at least as many positions as the search patterns.",
        )


def aggregate_board_search_scores(
    scores: Sequence[BoardSearchScore], query_cell_count: int
) -> BoardSearchScore:
    """Use raw evidence, never the rounded per-board percentages."""
    exact = sum(score.exact_match_count for score in scores)
    alternative = sum(score.alternative_match_count for score in scores)
    weighted = sum(Decimal(str(score.weighted_alternative_score)) for score in scores)
    unknown = sum(score.unknown_count for score in scores)
    wildcard = any(score.unknown_matches_all for score in scores)
    points = Decimal(exact) + weighted + (Decimal(unknown) if wildcard else Decimal(0))
    # Match the SQL float multiplier -> Numeric(10,6) -> round(..., 1) contract.
    raw = Decimal(str(float(points) * (100.0 / query_cell_count)))
    percent = raw.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    return BoardSearchScore(
        score=float(percent),
        exact_match_count=exact,
        alternative_match_count=alternative,
        weighted_alternative_score=float(weighted),
        mismatch_count=sum(score.mismatch_count for score in scores),
        unknown_count=unknown,
        unknown_matches_all=wildcard,
    )


def rank_board_search_sequences(
    patterns: Sequence[Iterable[BoardSearchQueryCell]],
    candidates: Iterable[BoardSearchCandidate],
    *,
    sequence_length: int,
    scope: BoardSearchScope,
    unknown_matches_all: bool = False,
) -> tuple[RankedBoardSearchSequence, ...]:
    queries = validate_board_search_patterns(patterns)
    documents = tuple(candidates)
    if len(queries) == 1:
        return tuple(
            RankedBoardSearchSequence((item.candidate,), (item.score,), item.score)
            for item in rank_board_search_candidates(
                queries[0], documents, scope=scope, unknown_matches_all=unknown_matches_all
            )
        )
    validate_sequence_length(sequence_length, len(queries))
    by_position: dict[int, BoardSearchCandidate] = {}
    for board in documents:
        if board.sequence_number in by_position:
            raise ValueError("The search projection must have one document per sequence position.")
        by_position[board.sequence_number] = board
    ranked = []
    for start in sorted(position for position in by_position if 1 <= position <= sequence_length):
        positions = tuple(
            (start - 1 + index) % sequence_length + 1 for index in range(len(queries))
        )
        if any(position not in by_position for position in positions):
            continue
        boards = tuple(by_position[position] for position in positions)
        if scope is BoardSearchScope.APPROVED_ONLY and any(
            board.status not in {"accepted", "corrected"} for board in boards
        ):
            continue
        scores = tuple(
            score_board_search_candidate(query, board, unknown_matches_all=unknown_matches_all)
            for query, board in zip(queries, boards, strict=True)
        )
        total = aggregate_board_search_scores(scores, sum(map(len, queries)))
        if total.has_positive_evidence:
            ranked.append(RankedBoardSearchSequence(boards, scores, total))
    return tuple(
        sorted(
            ranked,
            key=lambda item: (
                -item.score.score,
                -item.score.exact_match_count,
                -item.score.weighted_alternative_score,
                item.score.mismatch_count,
                -sum(board.status in {"accepted", "corrected"} for board in item.boards),
                item.boards[0].sequence_number,
                str(item.boards[0].review_item_id),
            ),
        )
    )
