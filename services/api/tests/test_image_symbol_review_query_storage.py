from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
    _apply_count_delta_payload,
    _count_deltas,
    _CountedCellState,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


class _ScalarSession:
    def __init__(self, result: UUID | None) -> None:
        self.result = result
        self.statement: object | None = None

    def scalar(self, statement: object) -> UUID | None:
        self.statement = statement
        return self.result


class _ExecuteSession:
    def __init__(self, driver_connection: object | None = None) -> None:
        self.calls: list[tuple[object, object | None]] = []
        self.driver_connection = driver_connection or _CancelableConnection()

    def execute(self, statement: object, parameters: object | None = None) -> None:
        self.calls.append((statement, parameters))

    def connection(self) -> _SqlAlchemyConnection:
        return _SqlAlchemyConnection(self.driver_connection)


class _CountProjectionSession:
    def __init__(self, state: object | None) -> None:
        self.state = state
        self.execute_called = False

    def get(self, _model: object, _identity: object) -> object | None:
        return self.state

    def execute(self, _statement: object) -> None:
        self.execute_called = True
        raise AssertionError("a basic V2 count must not scan symbol cells")


class _CancelableConnection:
    def __init__(self) -> None:
        self.cancel_timeouts: list[float] = []

    def cancel_safe(self, *, timeout: float = 30.0) -> None:
        self.cancel_timeouts.append(timeout)


class _ConnectionFairy:
    def __init__(self, driver_connection: object) -> None:
        self.driver_connection = driver_connection


class _SqlAlchemyConnection:
    def __init__(self, driver_connection: object) -> None:
        self.connection = _ConnectionFairy(driver_connection)


class _DatabaseFailure(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _compiled(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_active_model_cohort_uses_latest_activation_for_the_same_game() -> None:
    game_id = UUID(int=1)
    cohort_id = UUID(int=2)
    session = _ScalarSession(cohort_id)
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))

    assert repository.active_model_cohort_id(game_id) == cohort_id

    sql = _compiled(session.statement)
    assert "JOIN game_symbol_model_activations" in sql
    assert "game_symbol_model_activations.game_id" in sql
    assert "symbol_model_iterations.game_id" in sql
    assert "ORDER BY game_symbol_model_activations.activation_number DESC" in sql
    assert "LIMIT 1" in sql


def test_active_model_cohort_filter_requires_the_exact_current_crop_identity() -> None:
    cohort_id = UUID(int=3)
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT,
        include_all_symbols=True,
        model_cohort_id=cohort_id,
    )

    sql = _compiled(repository._candidate_seek_statement(review_filter=review_filter))

    assert "image_symbol_review_cells.review_state = 'approved'" in sql
    assert "JOIN verified_training_cohort_cells ON" in sql
    assert "verified_training_cohort_cells.cohort_id" in sql
    assert "verified_training_cohort_cells.cell_review_id = image_symbol_review_cells.id" in sql
    assert (
        "verified_training_cohort_cells.crop_checksum_sha256 = "
        "image_symbol_review_cells.crop_checksum_sha256" in sql
    )
    assert "verified_training_cohort_cells.asset_mode = image_symbol_review_cells.asset_mode" in sql
    assert sql.count("IS NOT DISTINCT FROM") == 3


def test_active_model_cohort_filter_without_an_activation_is_empty() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT,
        include_all_symbols=True,
        model_cohort_id=None,
    )

    sql = _compiled(repository._candidate_seek_statement(review_filter=review_filter))

    assert "false" in sql.lower()
    assert "verified_training_cohort_cells" not in sql


def test_counts_use_conditional_aggregates_without_per_cell_geometry_lookup() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=True,
    )

    sql = _compiled(repository._count_statement(review_filter=review_filter))

    assert sql.count("count(*) FILTER") == 2
    assert "image_board_search_fast_documents" in sql
    assert "recognized_boards" not in sql
    assert "GROUP BY" not in sql


def test_list_keeps_the_current_geometry_guard() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=True,
    )

    sql = _compiled(repository._list_statement(review_filter=review_filter))

    assert "JOIN recognized_boards" in sql
    assert (
        "image_symbol_review_cells.geometry_revision = recognized_boards.geometry_revision" in sql
    )


def test_v2_list_uses_only_the_current_projection_and_materialized_confidence() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=UUID(int=2),
        state=SymbolCellReviewFilterState.PENDING,
        min_confidence=0.4,
        uses_current_projection=True,
        storage_generation=2,
    )

    sql = _compiled(repository._list_statement(review_filter=review_filter))

    assert "image_board_search_fast_documents" not in sql
    assert "cell_observations" not in sql
    assert "image_symbol_prediction_revisions" not in sql
    assert "recognized_boards" not in sql
    assert "image_symbol_review_cells.prediction_confidence" in sql
    assert "JOIN image_review_items" in sql


def test_v2_seek_orders_by_the_stable_cell_projection_identity() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=True,
        uses_current_projection=True,
        storage_generation=2,
    )

    sql = _compiled(repository._candidate_seek_statement(review_filter=review_filter))

    assert "image_symbol_review_cells.id" in sql
    assert "image_board_search_fast_documents" not in sql


def test_v2_basic_counts_use_the_exact_projection_without_cell_sql() -> None:
    state = type(
        "State",
        (),
        {
            "count_projection_status": "ready",
            "count_projection": {"unknown": {"approved": 7, "pending": 3}},
        },
    )()
    session = _CountProjectionSession(state)
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        uses_current_projection=True,
        storage_generation=2,
    )

    counts = repository.counts(review_filter=review_filter)

    assert (counts.all_count, counts.approved_count, counts.pending_count) == (10, 7, 3)
    assert session.execute_called is False


def test_v2_basic_counts_are_unavailable_during_reconstruction() -> None:
    state = type(
        "State",
        (),
        {"count_projection_status": "rebuilding", "count_projection": {}},
    )()
    repository = SqlAlchemySymbolCellReviewQueryRepository(
        cast(Session, _CountProjectionSession(state))
    )
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=True,
        uses_current_projection=True,
        storage_generation=2,
    )

    with pytest.raises(SymbolCellReviewError) as raised:
        repository.counts(review_filter=review_filter)

    assert raised.value.code == "SYMBOL_CELL_REVIEW_COUNTS_UNAVAILABLE"
    assert raised.value.details == {"status": "rebuilding"}


def test_count_delta_is_aggregated_from_before_and_after_states() -> None:
    symbol_id = UUID(int=9)
    before = (
        _CountedCellState(True, None, "pending", None),
        _CountedCellState(True, symbol_id, "pending", None),
    )
    after = (
        _CountedCellState(True, symbol_id, "approved", None),
        _CountedCellState(True, symbol_id, "pending", "blurry"),
    )

    payload = _apply_count_delta_payload(
        {
            "all": {"approved": 0, "pending": 2},
            "unknown": {"approved": 0, "pending": 1},
            f"symbol:{symbol_id}": {"approved": 0, "pending": 1},
        },
        _count_deltas(before, after),
    )

    assert payload == {
        "all": {"approved": 1, "pending": 1},
        "unknown": {"approved": 0, "pending": 0},
        f"symbol:{symbol_id}": {"approved": 1, "pending": 0},
    }


def test_legacy_seek_does_not_create_a_cartesian_confidence_scan() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=UUID(int=2),
        state=SymbolCellReviewFilterState.ALL,
        min_confidence=0.4,
    )

    sql = _compiled(repository._candidate_seek_statement(review_filter=review_filter))

    assert "cell_observations" not in sql
    assert "image_symbol_prediction_revisions" not in sql


def test_count_statement_preserves_symbol_quality_and_confidence_filters() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=UUID(int=2),
        state=SymbolCellReviewFilterState.PENDING,
        min_confidence=0.4,
        max_confidence=0.8,
    )

    sql = _compiled(repository._count_statement(review_filter=review_filter))

    assert "image_symbol_review_cells.assigned_symbol_id" in sql
    assert "image_symbol_review_cells.quality_issue IS NULL" in sql
    assert "image_symbol_review_cells.review_state = 'pending'" in sql
    assert "image_symbol_prediction_revisions" in sql
    assert "cell_observations" in sql
    assert "JOIN recognized_boards" in sql
    assert ">= 0.4" in sql
    assert "<= 0.8" in sql


def test_count_statement_preserves_unknown_and_active_cohort_filters() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    unknown_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
    )
    cohort_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT,
        include_all_symbols=True,
        model_cohort_id=UUID(int=3),
    )

    unknown_sql = _compiled(repository._count_statement(review_filter=unknown_filter))
    cohort_sql = _compiled(repository._count_statement(review_filter=cohort_filter))

    assert "image_symbol_review_cells.assigned_symbol_id IS NULL" in unknown_sql
    assert "image_symbol_review_cells.quality_issue IN ('grid_issue', 'unreadable')" in unknown_sql
    assert "JOIN verified_training_cohort_cells" in cohort_sql
    assert "JOIN recognized_boards" in cohort_sql
    assert "image_symbol_review_cells.review_state = 'approved'" in cohort_sql


def test_bounded_read_sets_a_transaction_local_parameterized_timeout() -> None:
    session = _ExecuteSession()
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))

    with repository.bounded_read(timeout_ms=5_000, operation="list"):
        pass

    statement, parameters = session.calls[0]
    assert str(statement) == "SELECT set_config('statement_timeout', :timeout, true)"
    assert parameters == {"timeout": "5000ms"}


def test_active_bounded_read_can_cancel_only_its_driver_connection() -> None:
    driver_connection = _CancelableConnection()
    session = _ExecuteSession(driver_connection)
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))

    assert repository.cancel_active_read() is False
    with repository.bounded_read(timeout_ms=5_000, operation="list"):
        assert repository.cancel_active_read() is True
    assert repository.cancel_active_read() is False

    assert driver_connection.cancel_timeouts == [1.0]


def test_transport_cancel_between_statements_prevents_the_next_query() -> None:
    session = _ExecuteSession()
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=True,
    )

    with repository.bounded_read(timeout_ms=15_000, operation="counts"):
        repository.mark_active_read_cancelled()
        with pytest.raises(SymbolCellReviewError) as raised:
            repository.counts(review_filter=review_filter)

    assert raised.value.code == "SYMBOL_CELL_REVIEW_QUERY_CANCELLED"
    assert len(session.calls) == 1


def test_postgres_query_cancel_is_distinguished_from_statement_timeout() -> None:
    session = _ExecuteSession()
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))
    cancelled = DBAPIError("SELECT slow", {}, _DatabaseFailure("57014"), False)

    with (
        pytest.raises(SymbolCellReviewError) as raised,
        repository.bounded_read(timeout_ms=15_000, operation="counts"),
    ):
        repository.mark_active_read_cancelled()
        raise cancelled

    assert raised.value.code == "SYMBOL_CELL_REVIEW_QUERY_CANCELLED"
    assert raised.value.details == {"operation": "counts"}


def test_bounded_read_translates_only_postgres_query_cancellation() -> None:
    session = _ExecuteSession()
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))
    timeout = DBAPIError("SELECT slow", {}, _DatabaseFailure("57014"), False)

    with (
        pytest.raises(SymbolCellReviewError) as raised,
        repository.bounded_read(timeout_ms=15_000, operation="counts"),
    ):
        raise timeout

    assert raised.value.code == "SYMBOL_CELL_REVIEW_QUERY_TIMEOUT"
    assert raised.value.details == {"operation": "counts", "timeoutMs": 15_000}


def test_bounded_read_does_not_mask_an_unrelated_database_error() -> None:
    session = _ExecuteSession()
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))
    database_error = DBAPIError("SELECT broken", {}, _DatabaseFailure("XX000"), False)

    with (
        pytest.raises(DBAPIError) as raised,
        repository.bounded_read(timeout_ms=5_000, operation="list"),
    ):
        raise database_error

    assert raised.value is database_error
