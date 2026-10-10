"""Real PostgreSQL predicates and count keys must partition every logical cell."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    _count_scope_keys,
    _CountedCellState,
    _logical_cell_visible_clause,
    _symbol_scope_filter_clause,
)
from game_predictor_api.storage.models import ImageReviewItemModel, ImageSymbolReviewCellModel
from sqlalchemy import Engine, MetaData, Table, select, text
from sqlalchemy.sql import visitors
from test_symbol_source_visibility_migration import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 for isolated PostgreSQL tests.",
)


def test_all_eight_symbols_unknown_and_outside_partition_real_rows(database: Engine) -> None:  # noqa: F811
    game_id = uuid4()
    symbols = [uuid4() for _ in range(8)]
    rows = []
    expected: dict[str, set] = {"all": set(), "unknown": set(), "outside": set()}
    expected.update({f"symbol:{symbol}": set() for symbol in symbols})
    for visibility in ("full", "partial", "outside"):
        for assigned in (None, *symbols):
            for quality in (None, "partial_visibility", "blurry", "unreadable", "grid_issue"):
                for state in ("pending", "approved"):
                    if state == "approved" and (
                        quality == "grid_issue" or (assigned is None and quality != "unreadable")
                    ):
                        continue
                    identity = uuid4()
                    outside = visibility == "outside"
                    rows.append(
                        {
                            "id": identity,
                            "game_id": game_id,
                            "import_job_id": uuid4(),
                            "review_item_id": uuid4(),
                            "recognized_board_id": uuid4(),
                            "sequence_number": len(rows) + 1,
                            "cell_index": 0,
                            "row_index": 0,
                            "column_index": 0,
                            "geometry_revision": 1,
                            "cropper_version": "test",
                            "review_state": state,
                            "assignment_source": "human",
                            "last_reviewed_by": "test",
                            "asset_mode": "none" if outside else "legacy_file",
                            "source_available": not outside,
                            "source_visibility": visibility,
                            "assigned_symbol_id": assigned,
                            "quality_issue": quality,
                            "crop_sample_id": None if outside else "a" * 64,
                            "crop_checksum_sha256": None if outside else "b" * 64,
                            "crop_relative_path": None if outside else "test.png",
                        }
                    )
                    if outside:
                        scope = "outside" if assigned is None else f"symbol:{assigned}"
                    elif assigned is None or quality in ("unreadable", "grid_issue"):
                        scope = "unknown"
                    else:
                        scope = f"symbol:{assigned}"
                    expected["all"].add(identity)
                    expected[scope].add(identity)

    # Historical absent pixels with no evaluated visibility are deliberately hidden.
    historical = dict(rows[0], id=uuid4(), source_available=False, source_visibility=None)
    rows.append(historical)
    # TASK-0970: a cell of a rejected review item leaves symbol verification
    # (its row stays as history), so it belongs to no scope.
    rejected_item_id = uuid4()
    rejected_cell = dict(rows[0], id=uuid4(), review_item_id=rejected_item_id)
    with database.begin() as connection:
        connection.execute(
            text(
                "CREATE TEMP TABLE visibility_groups_probe (LIKE "
                "game_data_v2.image_symbol_review_cells INCLUDING DEFAULTS "
                "INCLUDING CONSTRAINTS) ON COMMIT DROP"
            )
        )
        # The visibility predicate reads the review items' status (TASK-0970);
        # the probe stands in for the game-routed ``image_review_items``.
        connection.execute(
            text(
                "CREATE TEMP TABLE visibility_groups_item_probe "
                "(id UUID PRIMARY KEY, status VARCHAR(20) NOT NULL) ON COMMIT DROP"
            )
        )
        probe = Table("visibility_groups_probe", MetaData(), autoload_with=connection)
        item_probe = Table("visibility_groups_item_probe", MetaData(), autoload_with=connection)
        connection.execute(probe.insert(), [*rows, rejected_cell])
        connection.execute(
            item_probe.insert(),
            [
                {"id": item_id, "status": "pending"}
                for item_id in {row["review_item_id"] for row in rows}
            ]
            + [{"id": rejected_item_id, "status": "rejected"}],
        )
        model_table = ImageSymbolReviewCellModel.__table__
        item_table = ImageReviewItemModel.__table__

        def substitute(element):
            table = getattr(element, "table", None)
            if table is model_table:
                return probe.c[element.name]
            if table is item_table or getattr(table, "element", None) is item_table:
                return item_probe.c[element.name]
            return None

        actual = {}
        for scope in expected:
            review_filter = SymbolCellReviewListFilter(
                game_id=game_id,
                symbol_id=next((symbol for symbol in symbols if scope == f"symbol:{symbol}"), None),
                state=SymbolCellReviewFilterState.ALL,
                include_all_symbols=scope == "all",
                outside_only=scope == "outside",
                storage_generation=2,
            )
            conditions = [_logical_cell_visible_clause()]
            if scope != "all":
                conditions.append(_symbol_scope_filter_clause(review_filter))
            conditions = [
                visitors.replacement_traverse(clause, {}, substitute) for clause in conditions
            ]
            actual[scope] = set(connection.scalars(select(probe.c.id).where(*conditions)))
            assert actual[scope] == expected[scope], scope

        membership = Counter(
            identity for scope, ids in actual.items() if scope != "all" for identity in ids
        )
        assert set(membership) == actual["all"]
        assert set(membership.values()) == {1}
        assert sum(len(ids) for scope, ids in actual.items() if scope != "all") == len(
            actual["all"]
        )
        for row in rows:
            keys = _count_scope_keys(_CountedCellState.from_model(SimpleNamespace(**row)))
            assert set(keys) == {scope for scope, ids in expected.items() if row["id"] in ids}


def test_bulk_scope_migration_extends_existing_partitions(database: Engine) -> None:  # noqa: F811
    assert database.url.database.startswith("game_predictor_task0708_")
    with database.begin() as connection:
        game_id = uuid4()
        connection.execute(
            text(
                "CREATE TABLE game_data_v2.task0709_bulk_operations PARTITION OF "
                f"game_data_v2.image_symbol_review_bulk_operations FOR VALUES IN ('{game_id}')"
            )
        )
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", database.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    command.upgrade(config, "0127_symbol_review_bulk_filter_scope")
    with database.connect() as connection:
        columns = connection.execute(
            text(
                "SELECT table_name, is_nullable, character_maximum_length "
                "FROM information_schema.columns WHERE table_schema = 'game_data_v2' "
                "AND table_name IN ('image_symbol_review_bulk_operations', "
                "'task0709_bulk_operations') "
                "AND column_name = 'filter_scope' ORDER BY table_name"
            )
        ).all()
        assert len(columns) == 2
        assert all(nullable == "YES" and length == 50 for _, nullable, length in columns)
