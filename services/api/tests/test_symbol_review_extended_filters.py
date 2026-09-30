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


def test_model_source_is_the_complement_of_the_library_entry() -> None:
    (library,) = _sql(_filter(prediction_source=SymbolCellReviewPredictionSource.REFERENCE_LIBRARY))
    (model,) = _sql(_filter(prediction_source=SymbolCellReviewPredictionSource.MODEL))

    assert model == f"NOT ({library})"


def test_changed_range_bounds_updated_at() -> None:
    clauses = _sql(_filter(changed_from=MIDNIGHT, changed_to=MIDNIGHT + timedelta(days=1)))

    assert len(clauses) == 2
    assert all("updated_at" in clause for clause in clauses)
    assert ">=" in clauses[0]
    assert "<=" in clauses[1]


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


def test_unfiltered_cursor_payload_has_no_extended_keys() -> None:
    cursor = encode_symbol_cell_review_cursor(
        review_filter=_filter(),
        direction=SymbolCellReviewCursorDirection.AFTER,
        key=(1, 0, uuid4()),
    )

    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))

    assert not {"predictionSource", "changedFrom", "changedTo"} & set(payload)


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

    assert base == _command(selection(prediction_source=None, changed_to=None))
    assert base != _command(
        selection(
            prediction_source=SymbolCellReviewPredictionSource.REFERENCE_LIBRARY,
            changed_from=datetime(2026, 9, 30, tzinfo=UTC),
        )
    )


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


@pytest.mark.parametrize("uses_current_projection", [False, True])
@pytest.mark.parametrize("source", list(SymbolCellReviewPredictionSource))
def test_source_filter_compiles_in_statements_that_join_the_revision(
    uses_current_projection: bool, source: SymbolCellReviewPredictionSource
) -> None:
    review_filter = _filter(
        prediction_source=source,
        min_confidence=0.5,
        uses_current_projection=uses_current_projection,
    )
    repository = SqlAlchemySymbolCellReviewQueryRepository.__new__(
        SqlAlchemySymbolCellReviewQueryRepository
    )
    dialect: Any = cast(Any, postgresql).dialect()
    statements = [
        repository._visible_statement(review_filter=review_filter),
        repository._count_statement(review_filter=review_filter),
        _visible_cells_statement(
            game_id=GAME,
            selection=SymbolCellReviewBulkFilterSelection(
                symbol_id=review_filter.symbol_id,
                state=SymbolCellReviewFilterState.PENDING,
                catalog_revision=3,
                min_confidence=0.5,
                prediction_source=source,
            ),
            uses_current_projection=uses_current_projection,
        ),
    ]

    for statement in statements:
        sql = str(statement.compile(dialect=dialect))
        assert "image_symbol_prediction_revisions AS library_revision" in sql
