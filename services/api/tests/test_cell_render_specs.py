"""D-467 S7 (TASK-0792): cell render specifications come from board render manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage import cell_render_specs
from game_predictor_api.storage.cell_render_specs import (
    RENDER_MANIFEST_MISSING,
    RENDER_SPEC_MISMATCH,
    RENDER_SPEC_MISSING,
    CellRenderSpecError,
    CellRenderSpecKey,
    load_cell_render_specs,
    verified_cell_render_spec,
)


def _spec(index: int) -> dict[str, object]:
    return {
        "cellIndex": index,
        "columnIndex": index % 5,
        "configuration": {"outputHeight": 64, "outputWidth": 64},
        "rowIndex": index // 5,
        "sourceQuad": [{"x": index, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}],
    }


def _entry(index: int, spec: Mapping[str, object] | None = None) -> dict[str, object]:
    value = dict(spec if spec is not None else _spec(index))
    return {
        "cellIndex": index,
        "renderSpec": value,
        "renderSpecChecksumSha256": sha256_canonical_json(value),
    }


def _key(board_id: UUID, index: int, *, revision: int = 0) -> CellRenderSpecKey:
    return CellRenderSpecKey(board_id, revision, index, sha256_canonical_json(_spec(index)))


class _Result:
    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> Sequence[Mapping[str, object]]:
        return self._rows


class _Connection:
    """Answers the batched statement from an in-memory manifest table."""

    def __init__(self, manifests: Mapping[tuple[UUID, int], Sequence[object]]) -> None:
        self.manifests = manifests
        self.statements: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: object, parameters: dict[str, Any]) -> _Result:
        self.statements.append((str(statement), parameters))
        rows: list[Mapping[str, object]] = []
        for board_id, revision, index in zip(
            parameters["board_ids"],
            parameters["revisions"],
            parameters["cell_indices"],
            strict=True,
        ):
            manifest = self.manifests.get((board_id, revision))
            matches = [
                entry
                for entry in (manifest or ())
                if isinstance(entry, Mapping) and entry.get("cellIndex") == index
            ]
            for match in matches or [None]:
                rows.append(
                    {
                        "recognized_board_id": str(board_id),
                        "geometry_revision": revision,
                        "cell_index": index,
                        "manifest_present": manifest is not None,
                        "manifest_cell": match,
                    }
                )
        return _Result(rows)


def test_manifest_spec_is_returned_for_every_key_in_one_statement() -> None:
    board_a, board_b = uuid4(), uuid4()
    connection = _Connection(
        {
            (board_a, 0): [_entry(index) for index in range(15)],
            (board_b, 2): [_entry(index) for index in (2, 3, 4)],
        }
    )
    keys = [_key(board_a, 0), _key(board_a, 7), _key(board_b, 3, revision=2)]

    specs = load_cell_render_specs(cast(Any, connection), game_id=uuid4(), keys=keys)

    assert specs == {keys[0]: _spec(0), keys[1]: _spec(7), keys[2]: _spec(3)}
    assert len(connection.statements) == 1
    sql, parameters = connection.statements[0]
    assert "FROM wanted w" in sql and "LEFT JOIN board_render_manifests m" in sql
    assert "m.game_id = :game_id" in sql and "image_symbol_review_cells" not in sql
    assert parameters["cell_indices"] == [0, 7, 3]


def test_reads_are_chunked_and_duplicate_keys_are_read_once() -> None:
    board_id = uuid4()
    connection = _Connection({(board_id, 0): [_entry(index) for index in range(15)]})
    keys = [_key(board_id, index) for index in range(5)] + [_key(board_id, 1)]

    with patch.object(cell_render_specs, "_CHUNK_SIZE", 2):
        specs = load_cell_render_specs(cast(Any, connection), game_id=uuid4(), keys=keys)

    assert len(specs) == 5
    assert [len(parameters["cell_indices"]) for _sql, parameters in connection.statements] == [
        2,
        2,
        1,
    ]


def test_no_keys_issue_no_statement() -> None:
    connection = _Connection({})
    assert load_cell_render_specs(cast(Any, connection), game_id=uuid4(), keys=()) == {}
    assert connection.statements == []


def test_script_schema_reads_the_qualified_table() -> None:
    board_id = uuid4()
    connection = _Connection({(board_id, 0): [_entry(0)]})
    load_cell_render_specs(
        cast(Any, connection), game_id=uuid4(), keys=[_key(board_id, 0)], schema="game_data_v2"
    )
    assert "LEFT JOIN game_data_v2.board_render_manifests m" in connection.statements[0][0]


def test_missing_manifest_fails_closed() -> None:
    board_id = uuid4()
    with pytest.raises(CellRenderSpecError) as raised:
        load_cell_render_specs(
            cast(Any, _Connection({})), game_id=uuid4(), keys=[_key(board_id, 3)]
        )
    assert raised.value.code == RENDER_MANIFEST_MISSING
    assert isinstance(raised.value, ImageReviewConflictError)
    assert raised.value.details == {
        "recognizedBoardId": str(board_id),
        "geometryRevision": 0,
        "cellIndex": 3,
    }


def test_manifest_of_another_revision_is_not_used() -> None:
    board_id = uuid4()
    connection = _Connection({(board_id, 1): [_entry(index) for index in range(15)]})
    with pytest.raises(CellRenderSpecError) as raised:
        load_cell_render_specs(cast(Any, connection), game_id=uuid4(), keys=[_key(board_id, 3)])
    assert raised.value.code == RENDER_MANIFEST_MISSING


def test_cell_missing_from_the_manifest_fails_closed() -> None:
    board_id = uuid4()
    connection = _Connection({(board_id, 0): [_entry(index) for index in range(15) if index != 4]})
    with pytest.raises(CellRenderSpecError) as raised:
        load_cell_render_specs(cast(Any, connection), game_id=uuid4(), keys=[_key(board_id, 4)])
    assert raised.value.code == RENDER_SPEC_MISSING


def test_mismatched_checksum_is_rejected_not_substituted() -> None:
    board_id = uuid4()
    connection = _Connection({(board_id, 0): [_entry(index) for index in range(15)]})
    foreign = CellRenderSpecKey(board_id, 0, 2, sha256_canonical_json(_spec(9)))
    with pytest.raises(CellRenderSpecError) as raised:
        load_cell_render_specs(cast(Any, connection), game_id=uuid4(), keys=[foreign])
    assert raised.value.code == RENDER_SPEC_MISMATCH


def test_declared_checksum_must_match_the_canonical_render_spec() -> None:
    key = _key(uuid4(), 0)
    tampered = {**_entry(0), "renderSpec": {**_spec(0), "rowIndex": 2}}
    with pytest.raises(CellRenderSpecError) as raised:
        verified_cell_render_spec(key, manifest_present=True, manifest_cells=[tampered])
    assert raised.value.code == RENDER_SPEC_MISMATCH


@pytest.mark.parametrize(
    "cells",
    (
        [],
        [_entry(0), _entry(0)],
        [{"cellIndex": 0, "renderSpecChecksumSha256": "0" * 64}],
        ["not-a-mapping"],
    ),
)
def test_absent_duplicated_or_shapeless_entries_are_missing(cells: list[object]) -> None:
    with pytest.raises(CellRenderSpecError) as raised:
        verified_cell_render_spec(_key(uuid4(), 0), manifest_present=True, manifest_cells=cells)
    assert raised.value.code == RENDER_SPEC_MISSING


def test_verified_spec_equals_the_cell_column_it_replaces() -> None:
    # The manifest entry and the former cell column hold the same canonical
    # JSON; the checksum ties both to the cell.
    column = _spec(11)
    spec = verified_cell_render_spec(
        CellRenderSpecKey(uuid4(), 3, 11, sha256_canonical_json(column)),
        manifest_present=True,
        manifest_cells=[_entry(11)],
    )
    assert spec == column
    assert sha256_canonical_json(spec) == sha256_canonical_json(column)


def test_cell_render_spec_column_is_write_only_for_the_orm() -> None:
    """Loading a review cell never reads the duplicated column; access raises."""

    import re

    from game_predictor_api.storage.models import ImageSymbolReviewCellModel
    from sqlalchemy import inspect, select
    from sqlalchemy.dialects import postgresql

    prop = inspect(ImageSymbolReviewCellModel).attrs["render_spec"]
    assert prop.deferred is True
    assert ("raiseload", True) in prop.strategy_key
    sql = str(select(ImageSymbolReviewCellModel).compile(dialect=postgresql.dialect()))
    assert re.search(r"\.render_spec\b(?!_)", sql) is None
    assert "image_symbol_review_cells.render_spec_checksum_sha256" in sql
    # Writers still set it (the cell CHECK requires it until TASK-0793).
    assert ImageSymbolReviewCellModel(render_spec={"a": 1}).render_spec == {"a": 1}
