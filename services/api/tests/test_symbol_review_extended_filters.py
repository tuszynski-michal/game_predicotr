from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

import pytest
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkFilterSelection,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.domain.image_symbol_reviews import (
    REFERENCE_LIBRARY_PREDICTION_MODEL_VERSION,
    RGB_V2_PREDICTION_MODEL_VERSION,
    SymbolCellReviewAction,
    SymbolCellReviewCursorDirection,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
    SymbolCellReviewPredictionSource,
    decode_symbol_cell_review_cursor,
    encode_symbol_cell_review_cursor,
)
from game_predictor_api.storage.image_symbol_review_bulk_operation_repository import (
    _visible_cells_statement,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
    extended_symbol_cell_review_filter_clauses,
)
from game_predictor_worker.symbols.reference_library_writer import MODEL_VERSION
from sqlalchemy.dialects import postgresql

GAME = uuid4()
MIDNIGHT = datetime(2026, 9, 30, tzinfo=timezone(timedelta(hours=2)))


def _filter(**changes: object) -> SymbolCellReviewListFilter:
    values: dict[str, object] = {
        "game_id": GAME,
        "symbol_id": uuid4(),
        "state": SymbolCellReviewFilterState.PENDING,
    }
    values.update(changes)
    return SymbolCellReviewListFilter(**values)  # type: ignore[arg-type]


def _sql(review_filter: SymbolCellReviewListFilter) -> list[str]:
    dialect: Any = cast(Any, postgresql).dialect()
    return [
        str(clause.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
        for clause in extended_symbol_cell_review_filter_clauses(review_filter)
    ]


def test_writer_and_filter_share_the_library_model_version() -> None:
    assert MODEL_VERSION == REFERENCE_LIBRARY_PREDICTION_MODEL_VERSION


def test_no_extended_filter_adds_no_clause() -> None:
    review_filter = _filter()

    assert review_filter.has_extended_filters is False
    assert _sql(review_filter) == []


def test_reference_library_source_matches_the_cells_own_library_entry() -> None:
    (clause,) = _sql(_filter(prediction_source=SymbolCellReviewPredictionSource.REFERENCE_LIBRARY))

    assert clause.startswith("EXISTS")
    assert REFERENCE_LIBRARY_PREDICTION_MODEL_VERSION in clause
    assert "library_revision.id = image_symbol_review_cells.prediction_revision_id" in clause
    # A library revision copies the whole board, so the cell's own entry must carry the marker.
    assert "predictions @> jsonb_build_array(jsonb_build_object('rowIndex'" in clause
    assert "'referenceLibrary', jsonb_build_object()" in clause


def test_rgb_v2_source_matches_the_cells_own_rgb_entry() -> None:
    (clause,) = _sql(_filter(prediction_source=SymbolCellReviewPredictionSource.RGB_V2))

    assert RGB_V2_PREDICTION_MODEL_VERSION == "symbol-rgb-v2"
    assert clause.startswith("EXISTS")
    assert "rgb_revision.model_version = 'symbol-rgb-v2'" in clause
    assert "rgb_revision.id = image_symbol_review_cells.prediction_revision_id" in clause
    assert "rgb_revision.game_id = image_symbol_review_cells.game_id" in clause
    # The cell's own entry (rowIndex/columnIndex) must carry an ``rgbV2`` object of any status.
    assert "predictions @> jsonb_build_array(jsonb_build_object('rowIndex'" in clause
    assert "'rgbV2', jsonb_build_object())" in clause
    assert "referenceLibrary" not in clause
    assert "tentative" not in clause


def test_rgb_v2_tentative_source_adds_the_tentative_status() -> None:
    (rgb,) = _sql(_filter(prediction_source=SymbolCellReviewPredictionSource.RGB_V2))
    (tentative,) = _sql(
        _filter(prediction_source=SymbolCellReviewPredictionSource.RGB_V2_TENTATIVE)
    )

    assert tentative.startswith("EXISTS")
    assert "rgb_revision.model_version = 'symbol-rgb-v2'" in tentative
    assert "'rgbV2', jsonb_build_object('status', 'tentative'))" in tentative
    assert tentative == rgb.replace(
        "'rgbV2', jsonb_build_object())", "'rgbV2', jsonb_build_object('status', 'tentative'))"
    )


def test_model_source_excludes_both_the_library_and_the_rgb_entry() -> None:
    (library,) = _sql(_filter(prediction_source=SymbolCellReviewPredictionSource.REFERENCE_LIBRARY))
    (rgb,) = _sql(_filter(prediction_source=SymbolCellReviewPredictionSource.RGB_V2))
    model = _sql(_filter(prediction_source=SymbolCellReviewPredictionSource.MODEL))

    # NOT library_entry AND NOT rgb_entry: ``model`` never matches a writer's own cell.
    assert model == [f"NOT ({library})", f"NOT ({rgb})"]
    # It excludes any ``rgbV2`` entry: a tentative cell goes out together with a confirmed one.
    assert "tentative" not in model[1]


def test_changed_range_bounds_updated_at() -> None:
    clauses = _sql(_filter(changed_from=MIDNIGHT, changed_to=MIDNIGHT + timedelta(days=1)))

    assert len(clauses) == 2
    assert all("updated_at" in clause for clause in clauses)
    assert ">=" in clauses[0]
    assert "<=" in clauses[1]


def test_import_job_filter_is_an_extended_scope_condition() -> None:
    import_job_id = uuid4()
    review_filter = _filter(import_job_id=import_job_id)
    (clause,) = _sql(review_filter)

    assert review_filter.has_extended_filters is True
    assert "image_symbol_review_cells.import_job_id" in clause
    assert str(import_job_id) in clause


@pytest.mark.parametrize(
    "changes",
    [
        {"changed_from": datetime(2026, 9, 30)},
        {"changed_from": MIDNIGHT + timedelta(days=1), "changed_to": MIDNIGHT},
    ],
)
def test_naive_or_reversed_changed_range_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(SymbolCellReviewError) as error:
        _filter(**changes)

    assert error.value.code == "SYMBOL_CELL_REVIEW_CHANGED_RANGE_INVALID"


def test_cursor_is_bound_to_extended_filters() -> None:
    symbol_id = uuid4()
    filtered = _filter(
        symbol_id=symbol_id,
        prediction_source=SymbolCellReviewPredictionSource.REFERENCE_LIBRARY,
        changed_from=MIDNIGHT,
    )
    unfiltered = _filter(symbol_id=symbol_id)
    key = (5, 3, uuid4())
    cursor = encode_symbol_cell_review_cursor(
        review_filter=filtered, direction=SymbolCellReviewCursorDirection.AFTER, key=key
    )

    decoded = decode_symbol_cell_review_cursor(
        cursor, review_filter=filtered, direction=SymbolCellReviewCursorDirection.AFTER
    )
    assert decoded == key
    with pytest.raises(SymbolCellReviewError) as error:
        decode_symbol_cell_review_cursor(
            cursor, review_filter=unfiltered, direction=SymbolCellReviewCursorDirection.AFTER
        )
    assert error.value.code == "SYMBOL_CELL_REVIEW_CURSOR_SCOPE_INVALID"


def test_cursor_is_bound_to_import_job_scope() -> None:
    import_job_id = uuid4()
    filtered = _filter(import_job_id=import_job_id)
    other_import = _filter(import_job_id=uuid4())
    key = (5, 3, uuid4())
    cursor = encode_symbol_cell_review_cursor(
        review_filter=filtered, direction=SymbolCellReviewCursorDirection.AFTER, key=key
    )

    assert (
        decode_symbol_cell_review_cursor(
            cursor, review_filter=filtered, direction=SymbolCellReviewCursorDirection.AFTER
        )
        == key
    )
    with pytest.raises(SymbolCellReviewError) as error:
        decode_symbol_cell_review_cursor(
            cursor, review_filter=other_import, direction=SymbolCellReviewCursorDirection.AFTER
        )
    assert error.value.code == "SYMBOL_CELL_REVIEW_CURSOR_SCOPE_INVALID"


def test_unfiltered_cursor_payload_has_no_extended_keys() -> None:
    cursor = encode_symbol_cell_review_cursor(
        review_filter=_filter(),
        direction=SymbolCellReviewCursorDirection.AFTER,
        key=(1, 0, uuid4()),
    )

    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))

    assert not {"predictionSource", "changedFrom", "changedTo", "importJobId"} & set(payload)


def _command(selection: SymbolCellReviewBulkFilterSelection) -> str:
    return SymbolCellReviewBulkRequest(
        action=SymbolCellReviewAction.APPROVE,
        target_symbol_id=None,
        explicit_targets=None,
        filter_selection=selection,
        actor="local-admin",
    ).command_sha256


def test_bulk_fingerprint_changes_only_when_extended_filters_are_set() -> None:
    symbol_id = uuid4()

    def selection(**changes: object) -> SymbolCellReviewBulkFilterSelection:
        return SymbolCellReviewBulkFilterSelection(
            symbol_id=symbol_id,
            state=SymbolCellReviewFilterState.PENDING,
            catalog_revision=3,
            **changes,  # type: ignore[arg-type]
        )

    base = _command(selection())

    assert base == _command(selection(prediction_source=None, changed_to=None, import_job_id=None))
    assert base != _command(
        selection(
            prediction_source=SymbolCellReviewPredictionSource.REFERENCE_LIBRARY,
            changed_from=datetime(2026, 9, 30, tzinfo=UTC),
        )
    )
    assert base != _command(selection(import_job_id=uuid4()))


def test_bulk_selection_rejects_a_reversed_range() -> None:
    with pytest.raises(SymbolCellReviewError) as error:
        SymbolCellReviewBulkFilterSelection(
            symbol_id=uuid4(),
            state=SymbolCellReviewFilterState.PENDING,
            catalog_revision=3,
            changed_from=datetime(2026, 10, 1, tzinfo=UTC),
            changed_to=datetime(2026, 9, 30, tzinfo=UTC),
        )

    assert error.value.code == "SYMBOL_CELL_REVIEW_BULK_CHANGED_RANGE_INVALID"


def test_cursor_is_stable_across_offsets_of_the_same_instant() -> None:
    symbol_id = uuid4()
    local = _filter(symbol_id=symbol_id, changed_from=MIDNIGHT)
    utc = _filter(symbol_id=symbol_id, changed_from=MIDNIGHT.astimezone(UTC))
    key = (5, 3, uuid4())
    cursor = encode_symbol_cell_review_cursor(
        review_filter=local, direction=SymbolCellReviewCursorDirection.AFTER, key=key
    )

    assert (
        decode_symbol_cell_review_cursor(
            cursor, review_filter=utc, direction=SymbolCellReviewCursorDirection.AFTER
        )
        == key
    )


def _v2_statements(review_filter: SymbolCellReviewListFilter) -> dict[str, str]:
    """Compile every V2 scope statement that shares the list filter semantics."""

    repository = SqlAlchemySymbolCellReviewQueryRepository.__new__(
        SqlAlchemySymbolCellReviewQueryRepository
    )
    dialect: Any = cast(Any, postgresql).dialect()
    statements = {
        "visible": repository._visible_statement(review_filter=review_filter),
        "count": repository._count_statement(review_filter=review_filter),
        "candidate_seek": repository._candidate_seek_statement(review_filter=review_filter),
        "bulk_visible_cells": _visible_cells_statement(
            game_id=GAME,
            selection=SymbolCellReviewBulkFilterSelection(
                symbol_id=review_filter.symbol_id,
                state=review_filter.state,
                catalog_revision=3,
                min_confidence=review_filter.min_confidence,
                max_confidence=review_filter.max_confidence,
                prediction_source=review_filter.prediction_source,
                changed_from=review_filter.changed_from,
                changed_to=review_filter.changed_to,
                import_job_id=review_filter.import_job_id,
            ),
        ),
    }
    return {name: str(statement.compile(dialect=dialect)) for name, statement in statements.items()}


_SOURCE_REVISION_ALIASES = {
    SymbolCellReviewPredictionSource.REFERENCE_LIBRARY: ("library_revision",),
    SymbolCellReviewPredictionSource.RGB_V2: ("rgb_revision",),
    SymbolCellReviewPredictionSource.RGB_V2_TENTATIVE: ("rgb_revision",),
    SymbolCellReviewPredictionSource.MODEL: ("library_revision", "rgb_revision"),
}


def test_every_source_has_an_expected_revision_alias() -> None:
    assert set(_SOURCE_REVISION_ALIASES) == set(SymbolCellReviewPredictionSource)


@pytest.mark.parametrize("source", list(SymbolCellReviewPredictionSource))
def test_source_filter_compiles_in_statements_that_join_the_revision(
    source: SymbolCellReviewPredictionSource,
) -> None:
    review_filter = _filter(prediction_source=source, min_confidence=0.5)
    aliases = _SOURCE_REVISION_ALIASES[source]

    for name, sql in _v2_statements(review_filter).items():
        for alias in aliases:
            assert f"image_symbol_prediction_revisions AS {alias}" in sql, (name, alias)
        # Correlated to the cell only: one revision lookup per writer the source distinguishes.
        assert sql.count("image_symbol_prediction_revisions") == len(aliases), name
        assert sql.count("EXISTS") == len(aliases), name


def test_v2_scope_statements_read_only_the_current_cell_projection() -> None:
    """The V2 path never joined legacy confidence or ownership sources (TASK-0754)."""

    review_filter = _filter(
        min_confidence=0.2,
        max_confidence=0.8,
        prediction_source=SymbolCellReviewPredictionSource.REFERENCE_LIBRARY,
        changed_from=MIDNIGHT,
        changed_to=MIDNIGHT + timedelta(days=1),
        import_job_id=uuid4(),
    )

    statements = _v2_statements(review_filter)

    for name, sql in statements.items():
        assert "cell_observations" not in sql, name
        assert "image_board_search_fast_documents" not in sql, name
        assert "coalesce" not in sql.lower(), name
        assert "image_symbol_review_cells.prediction_confidence >= " in sql, name
        assert "image_symbol_review_cells.prediction_confidence <= " in sql, name
        # The prediction revision is reached only through the correlated source filter.
        assert sql.count("image_symbol_prediction_revisions") == 1, name
        assert "image_symbol_review_cells.updated_at >= " in sql, name
        assert "image_symbol_review_cells.updated_at <= " in sql, name
        assert "image_symbol_review_cells.import_job_id = " in sql, name
    for name in ("visible", "count", "candidate_seek"):
        from_clause = statements[name].split("\nWHERE ")[0].split("\nFROM ")[1]
        assert from_clause == "image_symbol_review_cells ", name
    bulk_from_clause = statements["bulk_visible_cells"].split("\nWHERE ")[0].split("\nFROM ")[1]
    assert bulk_from_clause == (
        "image_symbol_review_cells JOIN recognized_boards "
        "ON recognized_boards.id = image_symbol_review_cells.recognized_board_id "
    )
    assert (
        "image_symbol_review_cells.geometry_revision = recognized_boards.geometry_revision"
        in statements["bulk_visible_cells"]
    )


def test_cell_paths_bind_the_game_store() -> None:
    """Each cell-query path without an ambient scope binds the store exactly once.

    The bind used to be a side effect of the removed V1/V2 storage probe; a
    refactor that drops a lone ``_bind_game_store(...)`` call would silently
    lose the search-path and row-level-security binding of that path.
    """

    import ast
    import inspect

    from game_predictor_api.storage import (
        board_cell_geometry_pending_repository,
        image_symbol_review_bulk_operation_repository,
        image_symbol_review_repository,
    )

    # D-467 (TASK-0790): the deferred-board repository no longer queries cells;
    # its legacy manual resolution moved to the virtual source path.
    # D-488 (TASK-0820/0821): the grid-correction symbol repository reads the
    # current cells and the active symbols, one bind each.
    expected = {
        image_symbol_review_repository: 9,
        image_symbol_review_bulk_operation_repository: 3,
        board_cell_geometry_pending_repository: 0,
    }
    for module, count in expected.items():
        tree = ast.parse(inspect.getsource(module))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_bind_game_store"
        ]
        assert len(calls) == count, module.__name__
