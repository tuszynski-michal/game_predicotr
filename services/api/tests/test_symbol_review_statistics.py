from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from game_predictor_api.storage.symbol_review_statistics import (
    SYMBOL_REVIEW_QUERY_TABLES,
    SymbolReviewStatisticsRefreshError,
    refresh_symbol_review_query_statistics,
)
from sqlalchemy.exc import SQLAlchemyError


def test_refresh_analyzes_the_complete_postgresql_symbol_review_read_model() -> None:
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"

    result = refresh_symbol_review_query_statistics(session)

    assert result == SYMBOL_REVIEW_QUERY_TABLES
    statement = str(session.execute.call_args.args[0])
    assert statement == "ANALYZE " + ", ".join(SYMBOL_REVIEW_QUERY_TABLES)


def test_refresh_is_a_noop_for_non_postgresql_test_databases() -> None:
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "sqlite"

    result = refresh_symbol_review_query_statistics(session)

    assert result == ()
    session.execute.assert_not_called()


def test_refresh_fails_closed_when_postgresql_rejects_analyze() -> None:
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    session.execute.side_effect = SQLAlchemyError("maintenance unavailable")

    with pytest.raises(SymbolReviewStatisticsRefreshError) as error:
        refresh_symbol_review_query_statistics(session)

    assert error.value.code == "SYMBOL_CELL_REVIEW_STATISTICS_REFRESH_FAILED"
