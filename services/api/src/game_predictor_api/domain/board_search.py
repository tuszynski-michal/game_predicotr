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
BOARD_SEARCH_ALGORITHM_VERSION = "partial-board-ranking-v2-unknown-missing-evidence"
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
    symbol_code: str | None


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


@dataclass(frozen=True, slots=True)
class BoardSearchResult:
    """One ranked logical board returned by the read-only search API."""

    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int
    status: str
    board_checksum_sha256: str
    score: BoardSearchScore


@dataclass(frozen=True, slots=True)
class BoardSearchProjectionPayload:
    """Persistable evidence for one review item without any image bytes."""

    game_id: UUID
    import_job_id: UUID
    recognized_board_id: UUID
    candidate: BoardSearchCandidate
    board_checksum_sha256: str
    board_confidence: float
    sequence_confidence: float
    source_pixel_count: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.board_confidence <= 1.0:
            raise ValueError("board_confidence must be between 0 and 1")
        if not 0.0 <= self.sequence_confidence <= 1.0:
            raise ValueError("sequence_confidence must be between 0 and 1")
        if self.source_pixel_count <= 0:
            raise ValueError("source_pixel_count must be positive")
        if len(self.board_checksum_sha256) != 64:
            raise ValueError("board_checksum_sha256 must be a SHA-256 digest")

    @property
    def known_evidence_positions(self) -> tuple[str, ...]:
        """Return cells with any permissible evidence for mismatch accounting.

        The read path needs to distinguish a known contradictory value from
        ``?`` without evaluating JSON for every ranked candidate.  Pending
        alternatives are evidence; resolved boards deliberately use only the
        human primary value, matching the ranking invariant.
        """

        positions: list[str] = []
        accepts_alternatives = self.candidate.status == "pending"
        for index, primary in enumerate(self.candidate.primary_symbol_codes):
            alternatives = (
                self.candidate.alternative_symbol_codes[index] if accepts_alternatives else ()
            )
            if any(_is_known_symbol(symbol) for symbol in (primary, *alternatives)):
                positions.append(str(index))
        return tuple(positions)


@dataclass(frozen=True, slots=True)
class BoardSearchDocumentSelection:
    review_item_id: UUID
    sequence_number: int
    selection_kind: str


def validate_board_search_query(
    cells: Iterable[BoardSearchQueryCell],
) -> tuple[BoardSearchQueryCell, ...]:
    """Validate and normalize an intentionally partial board query.

    Empty cells and logical ``?`` values carry no evidence.  They may be
    supplied by a client so the complete editor state remains representable,
    but are removed before scoring and therefore never enter the denominator.
    """

    supplied = tuple(sorted(cells, key=lambda cell: cell.cell_index))
    seen_indices: set[int] = set()
    normalized: list[BoardSearchQueryCell] = []
    for cell in supplied:
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
        symbol_code = cell.symbol_code.strip() if cell.symbol_code is not None else None
        if symbol_code in {None, UNKNOWN_SYMBOL_CODE}:
            continue
        if not symbol_code:
            raise BoardSearchError(
                "BOARD_SEARCH_SYMBOL_INVALID",
                "A board-search symbol must be a known catalog code.",
            )
        normalized.append(BoardSearchQueryCell(cell_index=cell.cell_index, symbol_code=symbol_code))
    if not normalized:
        raise BoardSearchError(
            "BOARD_SEARCH_QUERY_EMPTY",
            "Select at least one known symbol before searching boards.",
        )
    return tuple(normalized)


def score_board_search_candidate(
    query: Sequence[BoardSearchQueryCell],
    candidate: BoardSearchCandidate,
) -> BoardSearchScore:
    """Score one candidate using the immutable partial-match contract.

    A missing value (``None`` or ``?``) neither helps nor hurts.  An accepted
    or corrected board intentionally ignores alternative predictions; its
    resolved code is the only evidence eligible for search.
    """

    normalized_query = validate_board_search_query(query)
    return _score_validated_board_search_candidate(normalized_query, candidate)


def _score_validated_board_search_candidate(
    query: Sequence[BoardSearchQueryCell],
    candidate: BoardSearchCandidate,
) -> BoardSearchScore:
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
        score = _score_validated_board_search_candidate(query, candidate)
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


def select_board_search_document(
    *,
    sequence_number: int,
    candidates: Iterable[BoardSearchProjectionPayload],
    canonical_review_item_id: UUID | None,
    waiting_pending_review_item_ids: Iterable[UUID],
) -> BoardSearchDocumentSelection | None:
    """Choose the single visible candidate for a logical sequence.

    The caller owns persistence and job-state lookups.  Keeping this resolver
    pure means the backfill and every incremental writer apply identical source
    precedence.
    """

    if sequence_number < 1:
        raise ValueError("sequence_number must be positive")
    same_sequence = tuple(
        candidate
        for candidate in candidates
        if candidate.candidate.sequence_number == sequence_number
    )
    by_review_item = {candidate.candidate.review_item_id: candidate for candidate in same_sequence}
    if canonical_review_item_id is not None and canonical_review_item_id in by_review_item:
        return BoardSearchDocumentSelection(
            review_item_id=canonical_review_item_id,
            sequence_number=sequence_number,
            selection_kind="canonical",
        )

    resolved = tuple(
        candidate for candidate in same_sequence if candidate.candidate.status in _APPROVED_STATUSES
    )
    if resolved:
        return BoardSearchDocumentSelection(
            review_item_id=_selection_sort_key(resolved)[0].candidate.review_item_id,
            sequence_number=sequence_number,
            selection_kind="canonical",
        )

    waiting_ids = set(waiting_pending_review_item_ids)
    pending = tuple(
        candidate
        for candidate in same_sequence
        if candidate.candidate.status == "pending"
        and candidate.candidate.review_item_id in waiting_ids
    )
    if not pending:
        return None
    return BoardSearchDocumentSelection(
        review_item_id=_selection_sort_key(pending)[0].candidate.review_item_id,
        sequence_number=sequence_number,
        selection_kind="pending",
    )


def _selection_sort_key(
    candidates: Iterable[BoardSearchProjectionPayload],
) -> tuple[BoardSearchProjectionPayload, ...]:
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.board_confidence,
                -candidate.sequence_confidence,
                -candidate.source_pixel_count,
                str(candidate.candidate.review_item_id),
            ),
        )
    )


def _is_known_symbol(symbol: str | None) -> bool:
    return symbol not in {None, UNKNOWN_SYMBOL_CODE}


__all__ = [
    "BOARD_SEARCH_ALGORITHM_VERSION",
    "BOARD_SEARCH_ALTERNATIVE_WEIGHTS",
    "BOARD_SEARCH_CELL_COUNT",
    "BoardSearchCandidate",
    "BoardSearchError",
    "BoardSearchDocumentSelection",
    "BoardSearchProjectionPayload",
    "BoardSearchQueryCell",
    "BoardSearchResult",
    "BoardSearchScope",
    "BoardSearchScore",
    "RankedBoardSearchCandidate",
    "rank_board_search_candidates",
    "select_board_search_document",
    "score_board_search_candidate",
    "validate_board_search_query",
]
