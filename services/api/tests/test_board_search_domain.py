from __future__ import annotations

from uuid import UUID

import pytest
from game_predictor_api.domain.board_search import (
    BoardSearchCandidate,
    BoardSearchError,
    BoardSearchQueryCell,
    BoardSearchScope,
    rank_board_search_candidates,
    score_board_search_candidate,
)


def _candidate(
    *,
    identifier: int,
    sequence_number: int,
    status: str = "pending",
    primary: tuple[str | None, ...] | None = None,
    alternatives: tuple[tuple[str | None, ...], ...] | None = None,
) -> BoardSearchCandidate:
    return BoardSearchCandidate(
        review_item_id=UUID(int=identifier),
        sequence_number=sequence_number,
        status=status,
        primary_symbol_codes=primary or ("lemon",) * 15,
        alternative_symbol_codes=alternatives or ((),) * 15,
    )


def test_exact_evidence_beats_pending_alternative_and_mismatch() -> None:
    query = (BoardSearchQueryCell(cell_index=0, symbol_code="seven"),)
    exact = _candidate(
        identifier=1,
        sequence_number=3,
        status="accepted",
        primary=("seven",) + ("lemon",) * 14,
    )
    alternative = _candidate(
        identifier=2,
        sequence_number=1,
        primary=("lemon",) * 15,
        alternatives=(("seven",),) + ((),) * 14,
    )
    mismatch = _candidate(identifier=3, sequence_number=2)

    ranked = rank_board_search_candidates(
        query,
        (alternative, mismatch, exact),
        scope=BoardSearchScope.ALL_SEARCHABLE,
    )

    assert [entry.candidate.review_item_id for entry in ranked] == [
        exact.review_item_id,
        alternative.review_item_id,
    ]
    assert ranked[0].score.score == 100.0
    assert ranked[1].score.score == 60.0


def test_unknown_is_neither_a_match_nor_a_mismatch() -> None:
    query = (
        BoardSearchQueryCell(cell_index=0, symbol_code="seven"),
        BoardSearchQueryCell(cell_index=1, symbol_code="bell"),
    )
    candidate = _candidate(
        identifier=1,
        sequence_number=1,
        primary=("seven", "?", *(["lemon"] * 13)),
    )

    score = score_board_search_candidate(query, candidate)

    assert score.score == 50.0
    assert score.exact_match_count == 1
    assert score.mismatch_count == 0
    assert score.unknown_count == 1


def test_approved_scope_excludes_pending_and_approved_ignores_alternatives() -> None:
    query = (BoardSearchQueryCell(cell_index=0, symbol_code="seven"),)
    pending = _candidate(
        identifier=1,
        sequence_number=1,
        alternatives=(("seven",),) + ((),) * 14,
    )
    approved_with_stale_alternative = _candidate(
        identifier=2,
        sequence_number=2,
        status="corrected",
        alternatives=(("seven",),) + ((),) * 14,
    )

    ranked = rank_board_search_candidates(
        query,
        (pending, approved_with_stale_alternative),
        scope=BoardSearchScope.APPROVED_ONLY,
    )

    assert ranked == ()


def test_ties_are_deterministic_and_prefer_approved_before_pending() -> None:
    query = (BoardSearchQueryCell(cell_index=0, symbol_code="seven"),)
    approved = _candidate(
        identifier=9,
        sequence_number=20,
        status="accepted",
        primary=("seven",) + ("lemon",) * 14,
    )
    pending_first = _candidate(
        identifier=1,
        sequence_number=1,
        primary=("seven",) + ("lemon",) * 14,
    )
    pending_second = _candidate(
        identifier=2,
        sequence_number=2,
        primary=("seven",) + ("lemon",) * 14,
    )

    ranked = rank_board_search_candidates(
        query,
        (pending_second, pending_first, approved),
        scope=BoardSearchScope.ALL_SEARCHABLE,
    )

    assert [entry.candidate.review_item_id for entry in ranked] == [
        approved.review_item_id,
        pending_first.review_item_id,
        pending_second.review_item_id,
    ]


@pytest.mark.parametrize(
    ("query", "code"),
    [
        ((), "BOARD_SEARCH_QUERY_EMPTY"),
        (
            (
                BoardSearchQueryCell(cell_index=0, symbol_code="seven"),
                BoardSearchQueryCell(cell_index=0, symbol_code="bell"),
            ),
            "BOARD_SEARCH_CELL_DUPLICATE",
        ),
        ((BoardSearchQueryCell(cell_index=15, symbol_code="seven"),), "BOARD_SEARCH_CELL_INVALID"),
        ((BoardSearchQueryCell(cell_index=0, symbol_code="?"),), "BOARD_SEARCH_SYMBOL_INVALID"),
    ],
)
def test_partial_query_validation_is_fail_closed(
    query: tuple[BoardSearchQueryCell, ...],
    code: str,
) -> None:
    with pytest.raises(BoardSearchError, match=".") as error:
        rank_board_search_candidates(
            query,
            (),
            scope=BoardSearchScope.ALL_SEARCHABLE,
        )

    assert error.value.code == code
