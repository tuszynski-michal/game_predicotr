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
    _excluded_cell_count_sql,
)
from game_predictor_api.storage.models import (
    GameSymbolModelActivationModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
)
from sqlalchemy import Column, MetaData, Table, create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.sql import ClauseElement


class _ScalarSession:
    def __init__(self, result: UUID | None) -> None:
        self.result = result
        self.statement: object | None = None

    def scalar(self, statement: object) -> UUID | None:
        self.statement = statement
        return self.result


class _ActivationSession:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.statements: list[object] = []

    def scalar(self, statement: object) -> object:
        self.statements.append(statement)
        return self.results.pop(0)


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
        cast(ClauseElement, statement).compile(
            dialect=cast(type[Dialect], postgresql.dialect)(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_active_model_cohort_uses_latest_activation_for_the_same_game() -> None:
    game_id = UUID(int=1)
    cohort_id = UUID(int=2)
    iteration_id = UUID(int=3)
    current = GameSymbolModelActivationModel(
        game_id=game_id, model_iteration_id=iteration_id, action="activate", activation_number=5
    )
    session = _ActivationSession([current, cohort_id])
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))

    assert repository.active_model_cohort_id(game_id) == cohort_id

    assert len(session.statements) == 2
    activation_sql, cohort_sql = map(_compiled, session.statements)
    assert f"game_symbol_model_activations.game_id = '{game_id}'" in activation_sql
    assert "ORDER BY game_symbol_model_activations.activation_number DESC" in activation_sql
    assert "LIMIT 1" in activation_sql
    # Resolve the latest activation before reading its cohort. Joining first
    # would silently fall back to an older activation after a deactivation.
    assert "JOIN" not in activation_sql
    assert f"symbol_model_iterations.id = '{iteration_id}'" in cohort_sql
    assert f"symbol_model_iterations.game_id = '{game_id}'" in cohort_sql
    assert "LIMIT 1" in cohort_sql


@pytest.mark.parametrize("deactivated", [False, True])
def test_missing_or_deactivated_latest_model_never_uses_an_old_cohort(deactivated: bool) -> None:
    game_id = UUID(int=1)
    current = (
        GameSymbolModelActivationModel(
            game_id=game_id, model_iteration_id=None, action="deactivate", activation_number=6
        )
        if deactivated
        else None
    )
    session = _ActivationSession([current])
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))

    assert repository.active_model_cohort_id(game_id) is None
    assert len(session.statements) == 1
    sql = _compiled(session.statements[0])
    assert "ORDER BY game_symbol_model_activations.activation_number DESC" in sql
    assert "LIMIT 1" in sql


def test_active_lab_model_without_a_cohort_does_not_use_an_old_training_cohort() -> None:
    game_id = UUID(int=1)
    current = GameSymbolModelActivationModel(
        game_id=game_id, model_iteration_id=UUID(int=3), action="activate", activation_number=6
    )
    session = _ActivationSession([current, None])
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))

    assert repository.active_model_cohort_id(game_id) is None
    assert len(session.statements) == 2


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


def test_excluded_cell_count_sql_only_uses_fully_unavailable_for_virtual_source_v3() -> None:
    sql = _compiled(select(_excluded_cell_count_sql(RecognizedBoardModel)))

    assert "CASE WHEN" in sql
    assert "recognized_boards.asset_mode = 'virtual_source'" in sql
    assert "'manual-geometry-qualification-v3'" in sql
    assert "jsonb_array_length" in sql
    assert "fullyUnavailableCellIndices" in sql
    assert "ELSE cardinality(recognized_boards.unavailable_cell_indices) END" in sql


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
    assert "image_board_search_fast_documents" not in sql
    assert "recognized_boards" not in sql
    assert "GROUP BY" not in sql


def test_v2_list_uses_only_the_current_projection_and_materialized_confidence() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=UUID(int=2),
        state=SymbolCellReviewFilterState.PENDING,
        min_confidence=0.4,
        storage_generation=2,
    )

    sql = _compiled(repository._list_statement(review_filter=review_filter))

    assert "image_board_search_fast_documents" not in sql
    assert "cell_observations" not in sql
    assert "image_symbol_prediction_revisions" not in sql
    assert "recognized_boards" not in sql
    assert "image_symbol_review_cells.prediction_confidence" in sql
    assert "JOIN image_review_items" in sql


@pytest.mark.parametrize(
    ("min_confidence", "max_confidence"),
    [(None, 0.5999999999999999), (0.0, None), (0.0, 0.0), (0.6, 0.8), (1.0, 1.0)],
)
@pytest.mark.parametrize(
    "method", ["_candidate_seek_statement", "_list_statement", "_count_statement"]
)
def test_confidence_filters_expose_the_existing_partial_index_predicate(
    method: str, min_confidence: float | None, max_confidence: float | None
) -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=UUID(int=2),
        state=SymbolCellReviewFilterState.PENDING,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        storage_generation=2,
    )
    sql = _compiled(getattr(repository, method)(review_filter=review_filter))

    # The physical partial index uses the boolean column, not the wider
    # outside-cell OR or IS TRUE. PostgreSQL must see its exact implication.
    assert "AND image_symbol_review_cells.source_available" in sql
    assert "AND image_symbol_review_cells.source_available IS" not in sql
    assert f"image_symbol_review_cells.game_id = '{review_filter.game_id}'" in sql
    assert f"image_symbol_review_cells.assigned_symbol_id = '{review_filter.symbol_id}'" in sql
    assert "image_symbol_review_cells.review_state = 'pending'" in sql


@pytest.mark.parametrize("outside_only", [False, True])
def test_unfiltered_and_outside_reads_keep_their_original_visibility(outside_only: bool) -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=not outside_only,
        outside_only=outside_only,
        # The domain deliberately removes confidence filters for outside-only.
        min_confidence=0.0 if outside_only else None,
        max_confidence=1.0 if outside_only else None,
        storage_generation=2,
    )
    sql = _compiled(repository._candidate_seek_statement(review_filter=review_filter))

    assert (
        "source_available IS true OR image_symbol_review_cells.source_visibility = 'outside'" in sql
    )
    assert "AND image_symbol_review_cells.source_available" not in sql
    assert "prediction_confidence" not in sql


@pytest.mark.parametrize(
    ("min_confidence", "max_confidence"),
    [
        (None, None),
        (None, 0.5999999999999999),
        (0.0, None),
        (0.0, 0.0),
        (0.6, 0.8),
        (1.0, 1.0),
    ],
)
@pytest.mark.parametrize("descending", [False, True])
def test_confidence_seek_preserves_rows_counts_and_cursor_order(
    min_confidence: float | None, max_confidence: float | None, descending: bool
) -> None:
    game_id, symbol_id = UUID(int=1), UUID(int=2)
    metadata = MetaData()
    columns = (
        "id",
        "game_id",
        "assigned_symbol_id",
        "review_state",
        "prediction_confidence",
        "source_available",
        "source_visibility",
        "quality_issue",
        "sequence_number",
        "cell_index",
    )
    table = Table(
        "image_symbol_review_cells",
        metadata,
        *(Column(name, ImageSymbolReviewCellModel.__table__.c[name].type) for name in columns),
    )
    rows: list[dict[str, object]] = []
    samples: list[dict[str, object]] = [
        {"prediction_confidence": value}
        for value in (0.0, 0.3, 0.5999999999999999, 0.6, 0.8, 1.0, None)
    ]
    samples.extend(
        [
            {
                "source_available": False,
                "source_visibility": "outside",
                "prediction_confidence": None,
            },
            {"source_available": False, "prediction_confidence": 0.1},
            {"game_id": UUID(int=3), "prediction_confidence": 0.1},
            {"assigned_symbol_id": UUID(int=4), "prediction_confidence": 0.1},
            {"review_state": "approved", "prediction_confidence": 0.1},
            {"quality_issue": "grid_issue", "prediction_confidence": 0.1},
            {"quality_issue": "blurry", "prediction_confidence": 0.2},
            {"quality_issue": "unreadable", "prediction_confidence": 0.1},
            {"source_visibility": "partial", "prediction_confidence": 0.4},
        ]
    )
    for index, sample in enumerate(samples):
        rows.append(
            {
                "id": UUID(int=100 + index),
                "game_id": game_id,
                "assigned_symbol_id": symbol_id,
                "review_state": "pending",
                "source_available": True,
                "source_visibility": "full",
                "quality_issue": None,
                "sequence_number": 100 + index // 3,
                "cell_index": index % 3,
                **sample,
            }
        )
    expected: list[tuple[int, int, UUID]] = []
    for row in rows:
        confidence = cast(float | None, row["prediction_confidence"])
        if (
            row["game_id"] != game_id
            or row["assigned_symbol_id"] != symbol_id
            or row["review_state"] != "pending"
            or (not row["source_available"] and row["source_visibility"] != "outside")
            or (
                row["source_visibility"] != "outside"
                and row["quality_issue"] in ("grid_issue", "unreadable")
            )
            or (min_confidence is not None and (confidence is None or confidence < min_confidence))
            or (max_confidence is not None and (confidence is None or confidence > max_confidence))
        ):
            continue
        expected.append(
            (cast(int, row["sequence_number"]), cast(int, row["cell_index"]), cast(UUID, row["id"]))
        )
    expected.sort(reverse=descending)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(table.insert(), rows)
        with Session(engine) as session:
            repository = SqlAlchemySymbolCellReviewQueryRepository(session)
            filters = SymbolCellReviewListFilter(
                game_id=game_id,
                symbol_id=symbol_id,
                state=SymbolCellReviewFilterState.PENDING,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
                storage_generation=2,
            )
            actual = repository._seek_visible_keys(
                review_filter=filters,
                seek_key=None,
                descending=descending,
                needed_count=2501,
            )
            assert actual == expected
            assert tuple(
                session.execute(repository._count_statement(review_filter=filters)).one()
            ) == (0, len(expected))
            if expected:
                pivot = expected[len(expected) // 2]
                assert (
                    repository._seek_visible_keys(
                        review_filter=filters,
                        seek_key=pivot,
                        descending=descending,
                        needed_count=2501,
                    )
                    == expected[len(expected) // 2 + 1 :]
                )
    finally:
        engine.dispose()


def test_v2_seek_orders_by_the_stable_cell_projection_identity() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=True,
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
            "count_projection": {
                "_semantics": {"version": 2},
                "unknown": {"approved": 7, "pending": 3},
            },
        },
    )()
    session = _CountProjectionSession(state)
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
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
        # A blurry cell keeps its human-assigned symbol scope (it must stay
        # visible under that symbol's filtered tab, only excluded from
        # training), so it still counts against `symbol:{id}` here.
        f"symbol:{symbol_id}": {"approved": 1, "pending": 1},
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
    # A blurry crop keeps its human-assigned symbol and must stay counted
    # under that symbol's own tab -- only grid_issue/unreadable route to the
    # game-wide "unknown" bucket instead.
    assert "image_symbol_review_cells.quality_issue NOT IN ('grid_issue', 'unreadable')" in sql
    assert "image_symbol_review_cells.review_state = 'pending'" in sql
    assert "image_symbol_prediction_revisions" not in sql
    assert "cell_observations" not in sql
    assert "recognized_boards" not in sql
    assert "image_symbol_review_cells.prediction_confidence >= 0.4" in sql
    assert "image_symbol_review_cells.prediction_confidence <= 0.8" in sql


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
    assert "recognized_boards" not in cohort_sql
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
