"""Sequence searches get a usable deadline without leaking session settings."""

from unittest.mock import MagicMock

import pytest
from game_predictor_api.domain.board_search_sequence import BoardSearchSequenceError
from game_predictor_api.storage.board_search_sequence import _rank_with_timeout
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def _scalar(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


@pytest.mark.parametrize(
    ("previous", "previous_ms", "expected"),
    [("0", 0, 60000), ("5ms", 5, 5), ("15s", 15000, 15000), ("5min", 300000, 60000)],
)
def test_deadline_and_previous_setting_restored_after_success(previous, previous_ms, expected):
    session = MagicMock(spec=Session)
    ranked = MagicMock()
    ranked.mappings.return_value.all.return_value = [{"answer": 42}]
    session.execute.side_effect = [_scalar(previous), _scalar(previous_ms), None, ranked, None]
    query = text("SELECT 42 AS answer")

    assert _rank_with_timeout(session, query) == [{"answer": 42}]

    executions = session.execute.call_args_list
    assert executions[2].args[1] == {"value": str(expected)}
    assert executions[3].args[0] is query
    assert executions[4].args[1] == {"value": previous}
    session.begin_nested.return_value.__exit__.assert_called_once_with(None, None, None)


class DatabaseFailure(Exception):
    def __init__(self, sqlstate):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


@pytest.mark.parametrize("sqlstate", ["57014", "42P01"])
def test_failed_query_exits_savepoint_and_only_cancellation_becomes_sequence_timeout(sqlstate):
    session = MagicMock(spec=Session)
    failure = DBAPIError(None, None, DatabaseFailure(sqlstate))
    session.execute.side_effect = [_scalar("0"), _scalar(0), None, failure]

    with pytest.raises(BoardSearchSequenceError if sqlstate == "57014" else DBAPIError) as caught:
        _rank_with_timeout(session, text("SELECT 42 AS answer"))

    if sqlstate == "57014":
        assert caught.value.code == "BOARD_SEARCH_SEQUENCE_TIMEOUT"
        assert caught.value.__cause__ is failure
    else:
        assert caught.value is failure
    assert session.begin_nested.return_value.__exit__.call_args.args[1] is failure
    assert session.execute.call_count == 4, (
        "restoration after failure is owned by SAVEPOINT rollback"
    )
