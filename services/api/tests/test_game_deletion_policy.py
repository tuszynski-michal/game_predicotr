from __future__ import annotations

from typing import Any, cast

import pytest
from game_predictor_api.storage.game_deletion_policy_v1 import (
    MAX_BATCH_BYTES,
    DeletionError,
    ForeignKey,
    deletion_order,
    digest,
    owner_chain,
    owner_sql,
    quote,
)
from game_predictor_api.storage.game_deletion_repository import (
    Schema,
    Table,
    _references,
    select_owned_batch,
)
from sqlalchemy import Connection


def test_trigger_ownership_locks_every_parent_without_changing_preview_sql() -> None:
    assert owner_chain("cell_observations") == (
        "jobs",
        "source_images",
        "recognized_boards",
        "cell_observations",
    )
    assert owner_sql("cell_observations", lock_parents=True).count("FOR SHARE") == 3
    assert "FOR SHARE" not in owner_sql("cell_observations")


def test_queue_trigger_and_game_cycle_have_explicit_order() -> None:
    order = deletion_order(
        (
            ForeignKey(
                "board", "recognized_boards", ("source_image_id",), "source_images", ("id",)
            ),
            ForeignKey("source", "source_images", ("import_job_id",), "jobs", ("id",)),
            ForeignKey(
                "cycle", "games", ("board_topology_rules_version_id",), "rules_versions", ("id",)
            ),
        )
    )
    assert order.index("recognized_boards") < order.index("source_images") < order.index("jobs")
    assert order.index("image_review_items") < order.index("image_review_queue_states")
    assert "image_review_queue_items" not in order
    assert order[-1] == "games"


def test_unknown_owner_and_self_relationship_fail_closed() -> None:
    with pytest.raises(DeletionError, match="FOREIGN_REFERENCE"):
        deletion_order((ForeignKey("foreign", "future_table", ("game_id",), "games", ("id",)),))
    with pytest.raises(DeletionError, match="SELF_REFERENCE"):
        deletion_order((ForeignKey("self", "symbols", ("parent_id",), "symbols", ("id",)),))
    with pytest.raises(DeletionError, match="SCHEMA_INVALID"):
        quote("symbols; DROP TABLE games")


def test_references_include_arrays_checksums_and_shared_executions_not_heavy_payload() -> None:
    refs = _references(
        {
            "artifact_paths": ["data/a.json", "data/b.jpg"],
            "payload": {"file_execution_key": "abc", "checksumSha256": "a" * 64},
            "unrelated": "do not persist",
            "predictions": [1, 2, 3],
        }
    )
    assert [item["value"] for item in refs] == ["data/a.json", "data/b.jpg", "abc", "a" * 64]
    assert digest(refs) == digest(list(refs))


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> _Rows:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class _LeafConnection:
    def __init__(self, sizes: list[int]) -> None:
        self.rows = [{"id": index + 1, "row_bytes": size} for index, size in enumerate(sizes)]

    def execute(self, statement: object, params: dict[str, Any]) -> _Rows:
        return _Rows(
            [row for row in self.rows if row["id"] > params.get("after_0", 0)][: params["limit"]]
        )


def test_byte_cut_does_not_advance_past_uncommitted_rows() -> None:
    connection = cast(Connection, _LeafConnection([5 * 1024 * 1024, 5 * 1024 * 1024]))
    schema = Schema({"symbols": Table("symbols", ("id",), ("id",))}, (), "test", (), "test")
    cursor: list[dict[str, Any]] = []
    first, _ = select_owned_batch(connection, schema, "symbols", cursor, 2000)
    assert [row["id"] for row in first] == [1]
    assert cursor[-1]["after"] == {"id": 1}
    second, done = select_owned_batch(connection, schema, "symbols", cursor, 2000)
    assert [row["id"] for row in second] == [2]
    assert done


def test_oversized_record_has_explicit_error_without_advancing_cursor() -> None:
    connection = cast(Connection, _LeafConnection([MAX_BATCH_BYTES + 1]))
    schema = Schema({"symbols": Table("symbols", ("id",), ("id",))}, (), "test", (), "test")
    cursor: list[dict[str, Any]] = []
    with pytest.raises(DeletionError, match="GAME_DELETE_ROW_TOO_LARGE"):
        select_owned_batch(connection, schema, "symbols", cursor, 2000)
    assert cursor == [{}]
