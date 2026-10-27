"""Guard against re-expanding per-cell evidence in the sequence ranking SQL."""

from uuid import uuid4

import pytest
from game_predictor_api.domain.board_search import BoardSearchQueryCell, BoardSearchScope
from game_predictor_api.storage.board_search_sequence import _sequence_statement
from game_predictor_api.storage.models import ImageBoardSearchFastDocumentModel
from sqlalchemy.dialects import postgresql


@pytest.mark.parametrize("count", [2, 3, 4])
def test_full_patterns_materialize_evidence_before_global_limit(count):
    pattern = tuple(BoardSearchQueryCell(index, "A") for index in range(15))
    statement = _sequence_statement(
        ImageBoardSearchFastDocumentModel,
        game_id=uuid4(),
        patterns=(pattern,) * count,
        mobile_codes={"A": 1},
        wildcard=True,
        sequence_length=300000,
        scope=BoardSearchScope.ALL_SEARCHABLE,
        limit=40,
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))
    # The former two-pattern query was ~470 KB, mostly repeated CASE trees.
    assert len(sql) < count * 65000
    assert sql.count("AS MATERIALIZED") == count + 1
    assert sql.count("LIMIT") == 1
    assert sql.index("LIMIT") > sql.index("limited_sequences AS MATERIALIZED")
    assert "JOIN evidence_1" in sql
    assert "JOIN image_board_search_fast_documents AS result_0" in sql


def test_inactive_symbol_keeps_pattern_index_error():
    from game_predictor_api.domain.board_search_sequence import BoardSearchSequenceError

    with pytest.raises(BoardSearchSequenceError) as caught:
        _sequence_statement(
            ImageBoardSearchFastDocumentModel,
            game_id=uuid4(),
            patterns=((BoardSearchQueryCell(0, "A"),), (BoardSearchQueryCell(0, "B"),)),
            mobile_codes={"A": 1},
            wildcard=False,
            sequence_length=8,
            scope=BoardSearchScope.ALL_SEARCHABLE,
            limit=40,
        )
    assert caught.value.code == "BOARD_SEARCH_SEQUENCE_INVALID"
    assert caught.value.details == {"patternIndex": 1}
