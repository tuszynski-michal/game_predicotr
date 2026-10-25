from uuid import UUID

import pytest
from game_predictor_api.domain.board_search import (
    BoardSearchCandidate,
    BoardSearchQueryCell,
    BoardSearchScope,
    rank_board_search_candidates,
)
from game_predictor_api.domain.board_search_sequence import (
    BoardSearchSequenceError,
    rank_board_search_sequences,
    validate_board_search_patterns,
)


def board(position: int, code: str | None, status: str = "pending") -> BoardSearchCandidate:
    return BoardSearchCandidate(UUID(int=position), position, status, (code,) * 15, ((),) * 15)


def query(code: str) -> tuple[BoardSearchQueryCell, ...]:
    return (BoardSearchQueryCell(0, code),)


def rank(patterns, boards, length=300, wildcard=False, scope=BoardSearchScope.ALL_SEARCHABLE):
    return rank_board_search_sequences(
        patterns, boards, sequence_length=length, scope=scope, unknown_matches_all=wildcard
    )


def test_sequence_finds_best_start_outside_individual_top100():
    boards = [board(i, "A") for i in range(1, 202)] + [board(202, "B")]
    assert (
        rank_board_search_candidates(query("A"), boards, scope=BoardSearchScope.ALL_SEARCHABLE)[
            100
        ].candidate.sequence_number
        == 101
    )
    results = rank([query("A"), query("B")], boards)
    assert results[0].boards[0].sequence_number == 201
    assert results[0].score.score == 100


def test_wrap_and_missing_positions_do_not_compress_sequence():
    boards = [board(1, "B"), board(3, "A")]
    assert rank([query("A"), query("B")], boards, length=3)[0].boards == (boards[1], boards[0])
    assert rank([query("A"), query("B")], [board(1, "A"), board(3, "B")], length=4) == ()


def test_denominator_is_query_evidence_not_per_board_average():
    second = (BoardSearchQueryCell(0, "B"), BoardSearchQueryCell(1, "B"))
    result = rank([query("A"), second], [board(1, "A"), board(2, "C")])[0]
    assert result.score.score == 33.3
    missing = rank([query("A"), second], [board(1, "A"), board(2, None)])[0]
    assert missing.score.score == 33.3
    assert missing.score.unknown_count == 2


def test_777a2_unknowns_add_points_but_stay_unknown():
    result = rank([query("A"), query("B")], [board(1, None), board(2, None)], wildcard=True)[0]
    assert result.score.score == 100
    assert result.score.exact_match_count == 0
    assert result.score.unknown_count == 2
    assert rank([query("A"), query("B")], [board(1, None), board(2, None)]) == ()


def test_short_sequence_scope_and_single_compatibility():
    with pytest.raises(BoardSearchSequenceError, match="at least as many"):
        rank([query("A"), query("B")], [board(1, "A")], length=1)
    boards = [board(1, "A", "accepted"), board(2, "B")]
    assert rank([query("A"), query("B")], boards, scope=BoardSearchScope.APPROVED_ONLY) == ()
    expected = rank_board_search_candidates(
        query("A"), boards, scope=BoardSearchScope.ALL_SEARCHABLE
    )
    assert [x.boards[0] for x in rank([query("A")], boards, length=0)] == [
        x.candidate for x in expected
    ]


def test_bad_patterns_report_index_and_ignore_explicit_unknown():
    with pytest.raises(BoardSearchSequenceError) as info:
        validate_board_search_patterns([query("A"), query("?")])
    assert info.value.details == {"patternIndex": 1}
    with pytest.raises(BoardSearchSequenceError):
        validate_board_search_patterns([query("A")] * 5)
    assert validate_board_search_patterns(
        [(BoardSearchQueryCell(0, "A"), BoardSearchQueryCell(1, "?"))]
    ) == (query("A"),)
