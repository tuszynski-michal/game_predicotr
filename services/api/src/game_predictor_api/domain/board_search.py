"""Pure contracts and deterministic ranking for partial 3 by 5 board search.

The search read path persists a compact projection, but the meaning of a query
must stay independent from SQLAlchemy and HTTP.  This module deliberately
knows neither confidence nor pixels: human resolutions are exact evidence and
pending predictions may contribute only bounded, ordered alternatives.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

BOARD_SEARCH_CELL_COUNT = 15
BOARD_SEARCH_ALTERNATIVE_WEIGHTS: tuple[float, ...] = (0.60, 0.40, 0.25, 0.15)
BOARD_SEARCH_ALGORITHM_VERSION = "partial-board-ranking-v1"
UNKNOWN_SYMBOL_CODE = "?"
_SEARCHABLE_STATUSES = frozenset({"pending", "accepted", "corrected"})
_APPROVED_STATUSES = frozenset({"accepted", "corrected"})


class BoardSearchScope(StrEnum):
    ALL_SEARCHABLE = "all_searchable"
    APPROVED_ONLY = "approved_only"


class BoardSearchError(ValueError):
    """Stable domain validation error exposed by the read-only API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class BoardSearchQueryCell:
    cell_index: int
    symbol_code: str


@dataclass(frozen=True, slots=True)
class BoardSearchCandidate:
    """One projected candidate before it is reduced to a search result."""

    review_item_id: UUID
    sequence_number: int
    status: str
    primary_symbol_codes: tuple[str | None, ...]
    alternative_symbol_codes: tuple[tuple[str | None, ...], ...]

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise ValueError("sequence_number must be positive")
        if self.status not in _SEARCHABLE_STATUSES:
            raise ValueError("candidate status is not searchable")
        if len(self.primary_symbol_codes) != BOARD_SEARCH_CELL_COUNT:
            raise ValueError("candidate must contain exactly 15 primary cells")
        if len(self.alternative_symbol_codes) != BOARD_SEARCH_CELL_COUNT:
            raise ValueError("candidate must contain exactly 15 alternative cells")
        if any(
            len(alternatives) > len(BOARD_SEARCH_ALTERNATIVE_WEIGHTS)
            for alternatives in self.alternative_symbol_codes
        ):
            raise ValueError("candidate alternatives exceed the ranking contract")


@dataclass(frozen=True, slots=True)
class BoardSearchScore:
    score: float
    exact_match_count: int
    alternative_match_count: int
    weighted_alternative_score: float
    mismatch_count: int
    unknown_count: int

    @property
    def has_positive_evidence(self) -> bool:
        return self.exact_match_count > 0 or self.alternative_match_count > 0


@dataclass(frozen=True, slots=True)
class RankedBoardSearchCandidate:
    candidate: BoardSearchCandidate
    score: BoardSearchScore


def validate_board_search_query(
    cells: Iterable[BoardSearchQueryCell],
) -> tuple[BoardSearchQueryCell, ...]:
    """Validate and normalize an intentionally partial board query.

    Empty board cells are omitted by the caller.  ``?`` is a persisted absence
    marker, not a search symbol, so accepting it would silently change its
    domain meaning.
    """

    normalized = tuple(sorted(cells, key=lambda cell: cell.cell_index))
    if not normalized:
        raise BoardSearchError(
            "BOARD_SEARCH_QUERY_EMPTY",
            "Select at least one known symbol before searching boards.",
        )
    seen_indices: set[int] = set()
    for cell in normalized:
        if not 0 <= cell.cell_index < BOARD_SEARCH_CELL_COUNT:
            raise BoardSearchError(
                "BOARD_SEARCH_CELL_INVALID",
                "A board-search cell index must be between 0 and 14.",
            )
        if cell.cell_index in seen_indices:
            raise BoardSearchError(
                "BOARD_SEARCH_CELL_DUPLICATE",
                "Each board-search cell can be selected only once.",
            )
        seen_indices.add(cell.cell_index)
        if not cell.symbol_code or cell.symbol_code == UNKNOWN_SYMBOL_CODE:
            raise BoardSearchError(
                "BOARD_SEARCH_SYMBOL_INVALID",
                "A board-search symbol must be a known catalog code.",
            )
    return normalized


def score_board_search_candidate(
    query: Sequence[BoardSearchQueryCell],
    candidate: BoardSearchCandidate,
) -> BoardSearchScore:
    """Score one candidate using the immutable partial-match contract.

    A missing value (``None`` or ``?``) neither helps nor hurts.  An accepted
    or corrected board intentionally ignores alternative predictions; its
    resolved code is the only evidence eligible for search.
    """

    exact_match_count = 0
    alternative_match_count = 0
    weighted_alternative_score = 0.0
    mismatch_count = 0
    unknown_count = 0
    accepts_alternatives = candidate.status == "pending"

    for query_cell in query:
        primary = candidate.primary_symbol_codes[query_cell.cell_index]
        if primary == query_cell.symbol_code:
            exact_match_count += 1
            continue

        alternatives = (
            candidate.alternative_symbol_codes[query_cell.cell_index]
            if accepts_alternatives
            else ()
        )
        matched_alternative_index = next(
            (
                index
                for index, alternative in enumerate(alternatives)
                if alternative == query_cell.symbol_code
            ),
            None,
        )
        if matched_alternative_index is not None:
            alternative_match_count += 1
            weighted_alternative_score += BOARD_SEARCH_ALTERNATIVE_WEIGHTS[
                matched_alternative_index
            ]
            continue

        evidence = (primary, *alternatives)
        if any(symbol not in {None, UNKNOWN_SYMBOL_CODE} for symbol in evidence):
            mismatch_count += 1
        else:
            unknown_count += 1

    normalized_score = (exact_match_count + weighted_alternative_score) / len(query) * 100.0
    return BoardSearchScore(
        score=round(normalized_score, 1),
        exact_match_count=exact_match_count,
        alternative_match_count=alternative_match_count,
        weighted_alternative_score=round(weighted_alternative_score, 6),
        mismatch_count=mismatch_count,
        unknown_count=unknown_count,
    )


def rank_board_search_candidates(
    query_cells: Iterable[BoardSearchQueryCell],
    candidates: Iterable[BoardSearchCandidate],
    *,
    scope: BoardSearchScope,
) -> tuple[RankedBoardSearchCandidate, ...]:
    """Filter and sort candidates without allowing zero-evidence noise."""

    query = validate_board_search_query(query_cells)
    ranked: list[RankedBoardSearchCandidate] = []
    for candidate in candidates:
        if scope is BoardSearchScope.APPROVED_ONLY and candidate.status not in _APPROVED_STATUSES:
            continue
        score = score_board_search_candidate(query, candidate)
        if score.has_positive_evidence:
            ranked.append(RankedBoardSearchCandidate(candidate=candidate, score=score))

    return tuple(
        sorted(
            ranked,
            key=lambda ranked_candidate: (
                -ranked_candidate.score.score,
                -ranked_candidate.score.exact_match_count,
                -ranked_candidate.score.weighted_alternative_score,
                ranked_candidate.score.mismatch_count,
                0 if ranked_candidate.candidate.status in _APPROVED_STATUSES else 1,
                ranked_candidate.candidate.sequence_number,
                str(ranked_candidate.candidate.review_item_id),
            ),
        )
    )


__all__ = [
    "BOARD_SEARCH_ALGORITHM_VERSION",
    "BOARD_SEARCH_ALTERNATIVE_WEIGHTS",
    "BOARD_SEARCH_CELL_COUNT",
    "BoardSearchCandidate",
    "BoardSearchError",
    "BoardSearchQueryCell",
    "BoardSearchScope",
    "BoardSearchScore",
    "RankedBoardSearchCandidate",
    "rank_board_search_candidates",
    "score_board_search_candidate",
    "validate_board_search_query",
]
