"""TASK-0809: per-game data isolation and readiness of a brand-new game (PostgreSQL).

Runs on a dedicated ``*_test`` database only, with a real LOGIN application
role (``_application_role_database``): the schema owner migrates the database
and provisions the games through the real partition lifecycle, while every
pipeline operation (seeding, import, gate, search projection, reports) runs as
the application role, so the forced row-level security applies exactly as in
production.

Two games live side by side:

* a "big" game provisioned first and seeded with several imported images;
* a "new" game provisioned afterwards (after migration ``0139``) by the same
  lifecycle and used from its very first import.

Checked for the new game: the complete partition set and an active location,
the ``0139`` columns/constraints/indexes on its ``source_images`` partition, the
gate states of a complete and an 8-of-9 image, a completeness report free of
the big game's data, and ``EXPLAIN`` plans of four paths (completeness report,
recompute and gate, cell materialization, search projection) that name no
partition of the big game. The plan assertions run the statements that the
repositories really executed (captured at the cursor), not hand-written copies.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from _application_role_database import (
    ApplicationRoleDatabase,
    application_role_database,
    provision_game,
)
from game_predictor_api.domain.image_geometry_completeness import (
    LowQualityThresholds,
    SourceImageGeometryStatus,
)
from game_predictor_api.domain.image_reviews import ImageReviewNotFoundError
from game_predictor_api.storage import models  # noqa: F401  (registers every ORM table)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_data_v2_manifest_v7 import GAME_TABLES, VERSION, ownership
from game_predictor_api.storage.game_partition_lifecycle import partition_name
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    GameStorageStatus,
    game_storage_scope,
)
from game_predictor_api.storage.image_geometry_completeness_repository import (
    SqlAlchemyImageGeometryCompletenessRepository,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SqlAlchemyImageGeometryCompletenessStateRepository,
    active_review_item_ids,
    recompute_source_image_geometry_completeness,
    withheld_review_item_ids,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.metadata import Base
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from sqlalchemy import Engine, event, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from test_image_geometry_completeness_gate import _import, _state
from test_reviewer_operational_geometry_postgres import _add_symbols
from test_virtual_deferred_resolution_postgres import _factory, _Seed, _seed

_REQUIRES_POSTGRES = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_MIGRATION_0139 = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0139_source_image_geometry_completeness.py"
)
_SCHEMA = "game_data_v2"
_GAME_TABLE_NAME = re.compile(r"\b(?:" + "|".join(GAME_TABLES) + r")\b")
_ROW_KEYS = ("source_image_id", "recognized_board_id", "review_item_id")


# -- guard: which ORM tables may carry a per-photo / per-board key ------------


def test_orm_tables_with_image_board_or_item_keys_are_game_owned() -> None:
    """A table that keys rows by photo, board or review item must be partitioned per game.

    ``test_game_data_v2_schema`` already proves that every ORM table is
    classified (catalog, shared or game). It does not prove the class of the
    tables that hold row-per-photo data, which is what a shared table of this
    shape would break (data of two games in one physical table).
    """

    offenders = sorted(
        name
        for name, table in Base.metadata.tables.items()
        if any(key in table.columns for key in _ROW_KEYS)
        and not (name in GAME_TABLES and ownership(name) == "game")
    )
    assert offenders == []
    holders = {
        name
        for name, table in Base.metadata.tables.items()
        if any(key in table.columns for key in _ROW_KEYS)
    }
    # Not vacuous: the photo/board/item tables of the pipeline are among them.
    assert {
        "recognized_boards",
        "image_review_items",
        "image_symbol_review_cells",
        "image_board_search_candidates",
    } <= holders


# -- plan reading ------------------------------------------------------------


def _plan_relations(plan: Any) -> list[tuple[str | None, str]]:
    """``(schema, relation)`` of every scanned relation in an ``EXPLAIN (FORMAT JSON)`` plan.

    The root relation of a ``ModifyTable`` node is the partitioned parent of an
    UPDATE/DELETE; its partitions are listed as the child scans.
    """

    found: list[tuple[str | None, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            name = node.get("Relation Name")
            if isinstance(name, str) and node.get("Node Type") != "ModifyTable":
                schema = node.get("Schema")
                found.append((schema if isinstance(schema, str) else None, name))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(plan)
    return found


def _foreign_relations(
    relations: Iterable[tuple[str | None, str]], own_partitions: frozenset[str]
) -> list[str]:
    """Relations a game's query must not touch: other partitions, parents, public copies."""

    bad: list[str] = []
    for schema, name in relations:
        if schema == _SCHEMA or name.startswith("gpv2_"):
            if name not in own_partitions:
                bad.append(f"{schema}.{name}")
        elif name in GAME_TABLES:
            bad.append(f"{schema}.{name}")
    return bad


def test_plan_reader_flags_partitions_of_another_game() -> None:
    mine, other = uuid4(), uuid4()
    own = frozenset(partition_name(mine, table) for table in GAME_TABLES)
    plan = [
        {
            "Plan": {
                "Node Type": "Append",
                "Plans": [
                    {
                        "Node Type": "Seq Scan",
                        "Relation Name": partition_name(mine, "source_images"),
                        "Schema": _SCHEMA,
                    },
                    {
                        "Node Type": "Index Scan",
                        "Relation Name": partition_name(other, "source_images"),
                        "Schema": _SCHEMA,
                    },
                    {"Node Type": "Seq Scan", "Relation Name": "games", "Schema": "public"},
                ],
            }
        }
    ]
    assert _foreign_relations(_plan_relations(plan), own) == [
        f"{_SCHEMA}.{partition_name(other, 'source_images')}"
    ]
    modify = [
        {
            "Plan": {
                "Node Type": "ModifyTable",
                "Relation Name": "source_images",
                "Schema": _SCHEMA,
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Relation Name": partition_name(mine, "source_images"),
                        "Schema": _SCHEMA,
                    }
                ],
            }
        }
    ]
    assert _foreign_relations(_plan_relations(modify), own) == []
    leaked_parent = [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "source_images"}}]
    assert _foreign_relations(_plan_relations(leaked_parent), own) == ["None.source_images"]


# -- fixture: a big game and a brand-new game --------------------------------


@dataclass(frozen=True)
class _Worlds:
    database: ApplicationRoleDatabase
    factory: sessionmaker[Session]
    big_game: UUID
    big_seeds: tuple[_Seed, ...]
    new_game: UUID
    new_complete: _Seed
    new_incomplete: _Seed
    big_partitions: frozenset[str]
    new_partitions: frozenset[str]


def _bound_partitions(engine: Engine, game_id: UUID) -> frozenset[str]:
    """Partitions of a game read from ``pg_inherits`` (not from the naming rule)."""

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """SELECT child.relname
                FROM pg_inherits link
                JOIN pg_class child ON child.oid = link.inhrelid
                JOIN pg_class parent ON parent.oid = link.inhparent
                JOIN pg_namespace ns ON ns.oid = parent.relnamespace
                WHERE ns.nspname = :schema AND parent.relname = ANY (:tables)
                  AND pg_get_expr(child.relpartbound, child.oid) = :bound"""
            ),
            {
                "schema": _SCHEMA,
                "tables": list(GAME_TABLES),
                "bound": f"FOR VALUES IN ('{game_id}')",
            },
        ).all()
    return frozenset(str(row[0]) for row in rows)


@pytest.fixture(scope="module")
def worlds(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Worlds]:
    if os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Explicit isolated PostgreSQL tests only")
    artifact_root = tmp_path_factory.mktemp("task0809") / "artifacts"
    with application_role_database("t0809", ("t0809-big",)) as database:
        factory = _factory(database.app_engine)
        big_game = database.games["t0809-big"]

        # The big game: several imported images (three complete, one with 8 of 9 grids).
        specs = (("a", 9, 9), ("bb", 9, 9), ("ccc", 9, 9), ("dddd", 9, 8))
        big_seeds = tuple(
            _seed(
                factory,
                big_game,
                artifact_root,
                label=f"t0809-big-{tag}",
                slot_count=slots,
                sequence_base=1000 * (index + 1),
            )
            for index, (tag, slots, _imported) in enumerate(specs)
        )
        _add_symbols(factory, big_game)
        for seed, (tag, _slots, imported) in zip(big_seeds, specs, strict=True):
            _import(factory, seed, f"t0809-big-{tag}", range(imported))

        # The new game: created after the big game was filled, by the same lifecycle.
        new_game = provision_game(database.owner_engine, "t0809-new")
        new_complete = _seed(
            factory,
            new_game,
            artifact_root,
            label="t0809-new-complete",
            slot_count=9,
            sequence_base=100,
        )
        new_incomplete = _seed(
            factory,
            new_game,
            artifact_root,
            label="t0809-new-eight-of-nine-grids",
            slot_count=9,
            sequence_base=200,
        )
        _add_symbols(factory, new_game)
        _import(factory, new_complete, "t0809-new-complete", range(9))
        _import(factory, new_incomplete, "t0809-new-eight-of-nine-grids", range(8))

        yield _Worlds(
            database=database,
            factory=factory,
            big_game=big_game,
            big_seeds=big_seeds,
            new_game=new_game,
            new_complete=new_complete,
            new_incomplete=new_incomplete,
            big_partitions=_bound_partitions(database.owner_engine, big_game),
            new_partitions=_bound_partitions(database.owner_engine, new_game),
        )


# -- new game: partitions, location, 0139 columns ----------------------------


@_REQUIRES_POSTGRES
def test_new_game_has_the_complete_manifest_partition_set_and_an_active_location(
    worlds: _Worlds,
) -> None:
    expected = {table: partition_name(worlds.new_game, table) for table in GAME_TABLES}
    assert len(set(expected.values())) == len(GAME_TABLES)
    # What pg_inherits says equals the deterministic naming rule, one per table.
    assert worlds.new_partitions == frozenset(expected.values())
    assert worlds.big_partitions == frozenset(
        partition_name(worlds.big_game, table) for table in GAME_TABLES
    )
    assert not worlds.new_partitions & worlds.big_partitions

    with worlds.database.owner_engine.connect() as connection:
        parents = dict(
            connection.execute(
                text(
                    """SELECT parent.relname, child.relname
                    FROM pg_inherits link
                    JOIN pg_class child ON child.oid = link.inhrelid
                    JOIN pg_class parent ON parent.oid = link.inhparent
                    JOIN pg_namespace ns ON ns.oid = parent.relnamespace
                    WHERE ns.nspname = :schema
                      AND pg_get_expr(child.relpartbound, child.oid) = :bound"""
                ),
                {"schema": _SCHEMA, "bound": f"FOR VALUES IN ('{worlds.new_game}')"},
            ).all()
        )
        assert parents == expected
        security = connection.execute(
            text(
                """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = :schema AND c.relname = ANY (:tables)"""
            ),
            {"schema": _SCHEMA, "tables": list(GAME_TABLES)},
        ).all()
        assert {row[0] for row in security} == set(GAME_TABLES)
        assert all(row[1] and row[2] for row in security)
        manifest = {
            str(row[0])
            for row in connection.execute(
                text(
                    "SELECT table_name FROM public.game_storage_table_manifest "
                    "WHERE manifest_version = :version AND ownership = 'game'"
                ),
                {"version": VERSION},
            )
        }
        assert manifest == set(GAME_TABLES)
        lifecycle = connection.execute(
            text(
                "SELECT status, next_table_index, manifest_version "
                "FROM public.game_storage_lifecycle_operations "
                "WHERE game_id = :game_id AND operation_kind = 'provision'"
            ),
            {"game_id": worlds.new_game},
        ).one()
        assert tuple(lifecycle) == ("done", len(GAME_TABLES), VERSION)

    with worlds.factory() as session:
        for game_id in (worlds.new_game, worlds.big_game):
            location = GameStorageRouter().describe(session, game_id)
            assert location.status is GameStorageStatus.ACTIVE
            assert location.write_available
            assert location.store_schema.value == _SCHEMA
            assert location.manifest_version == VERSION


def _migration_0139() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0139_task0809", _MIGRATION_0139)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@_REQUIRES_POSTGRES
def test_new_game_source_images_partition_has_the_0139_columns_constraints_and_indexes(
    worlds: _Worlds,
) -> None:
    migration = _migration_0139()
    partition = partition_name(worlds.new_game, "source_images")
    columns = {
        "geometry_completeness_status": "character varying(24)",
        "geometry_completeness_evaluated_at": "timestamp with time zone",
        "geometry_exception_reason": "text",
        "geometry_exception_by": "character varying(200)",
        "geometry_exception_at": "timestamp with time zone",
    }
    checks = {name for name, _expression in migration._CHECKS}
    indexes = {migration.QUEUE_INDEX, migration.BACKFILL_INDEX}

    def shape(relation: str) -> dict[str, Any]:
        with worlds.database.owner_engine.connect() as connection:
            attributes = dict(
                connection.execute(
                    text(
                        """SELECT a.attname, format_type(a.atttypid, a.atttypmod)
                        FROM pg_attribute a WHERE a.attrelid = CAST(:relation AS regclass)
                          AND a.attnum > 0 AND NOT a.attisdropped"""
                    ),
                    {"relation": f"{_SCHEMA}.{relation}"},
                ).all()
            )
            constraints = {
                str(row[0]): (str(row[1]), bool(row[2]))
                for row in connection.execute(
                    text(
                        """SELECT conname, pg_get_constraintdef(oid), convalidated
                        FROM pg_constraint
                        WHERE conrelid = CAST(:relation AS regclass) AND contype = 'c'"""
                    ),
                    {"relation": f"{_SCHEMA}.{relation}"},
                )
            }
        return {"attributes": attributes, "constraints": constraints}

    parent = shape("source_images")
    child = shape(partition)
    assert columns.items() <= child["attributes"].items()
    # The partition has exactly the parent's columns and the same CHECK definitions.
    assert child["attributes"] == parent["attributes"]
    assert child["constraints"] == parent["constraints"]
    assert checks <= child["constraints"].keys()
    assert all(validated for _definition, validated in child["constraints"].values())

    with worlds.database.owner_engine.connect() as connection:
        partial_indexes = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                text(
                    """SELECT parent_index.relname, pg_get_expr(ix.indpred, ix.indrelid)
                    FROM pg_index ix
                    JOIN pg_inherits link ON link.inhrelid = ix.indexrelid
                    JOIN pg_class parent_index ON parent_index.oid = link.inhparent
                    WHERE ix.indrelid = CAST(:relation AS regclass)
                      AND parent_index.relname = ANY (:names) AND ix.indpred IS NOT NULL"""
                ),
                {"relation": f"{_SCHEMA}.{partition}", "names": sorted(indexes)},
            )
        }
    assert partial_indexes.keys() == indexes

    # The constraints are enforced on the new game's partition, not only declared.
    game_id = worlds.new_game
    source_id = worlds.new_complete.source_image_id
    for assignment, constraint in (
        ("geometry_completeness_status = 'bogus'", "ck_source_images_geometry_completeness_status"),
        (
            "geometry_completeness_status = 'geometry_exception', "
            "geometry_completeness_evaluated_at = now(), geometry_exception_reason = '   ', "
            "geometry_exception_by = 'task-0809', geometry_exception_at = now()",
            "ck_source_images_geometry_exception",
        ),
        (
            "geometry_completeness_status = 'geometry_exception', "
            "geometry_completeness_evaluated_at = now(), geometry_exception_reason = NULL, "
            "geometry_exception_by = 'task-0809', geometry_exception_at = now()",
            "ck_source_images_geometry_exception",
        ),
        (
            "geometry_completeness_status = 'geometry_incomplete', "
            "geometry_completeness_evaluated_at = NULL",
            "ck_source_images_geometry_completeness_evaluated",
        ),
    ):
        with (
            worlds.database.owner_engine.connect() as connection,
            pytest.raises(IntegrityError) as refused,
        ):
            connection.execute(
                text(
                    f"UPDATE {_SCHEMA}.source_images SET {assignment} "
                    "WHERE game_id = :game_id AND id = :source_id"
                ),
                {"game_id": game_id, "source_id": source_id},
            )
        assert constraint in str(refused.value.orig)


# -- new game: gate, cells, report -------------------------------------------


@_REQUIRES_POSTGRES
def test_first_imports_of_the_new_game_set_the_gate_state_and_cut_cells_only_when_admitted(
    worlds: _Worlds,
) -> None:
    complete = _state(worlds.factory, worlds.new_game, worlds.new_complete.source_image_id)
    assert complete["status"] == "geometry_complete"
    assert complete["evaluated"] is True
    assert complete["boards"] == 9
    assert complete["cells"] == 135
    assert complete["distinct_cells"] == 135
    assert complete["candidates_with_evidence"] == 9
    assert complete["documents_with_evidence"] == 9

    incomplete = _state(worlds.factory, worlds.new_game, worlds.new_incomplete.source_image_id)
    assert incomplete["status"] == "geometry_incomplete"
    assert incomplete["boards"] == 8
    assert incomplete["cells"] == 0
    # The sequence documents exist (the grid correction needs them) without evidence.
    assert incomplete["candidates"] == 8
    assert incomplete["candidates_with_evidence"] == 0
    assert incomplete["documents_with_evidence"] == 0

    # The same states in the big game, which was filled first.
    big = [
        _state(worlds.factory, worlds.big_game, seed.source_image_id) for seed in worlds.big_seeds
    ]
    assert [item["status"] for item in big] == [
        "geometry_complete",
        "geometry_complete",
        "geometry_complete",
        "geometry_incomplete",
    ]
    assert [item["cells"] for item in big] == [135, 135, 135, 0]


@_REQUIRES_POSTGRES
def test_new_game_completeness_report_contains_nothing_of_the_big_game(worlds: _Worlds) -> None:
    factory = worlds.factory
    new_ids = {worlds.new_complete.source_image_id, worlds.new_incomplete.source_image_id}
    big_ids = {seed.source_image_id for seed in worlds.big_seeds}
    with game_storage_scope(worlds.new_game), factory() as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        report = repository.completeness_report(worlds.new_game)
        page = repository.incomplete_images(
            worlds.new_game, completeness_status=SourceImageGeometryStatus.GEOMETRY_INCOMPLETE
        )
        low_quality = repository.low_quality_boards(
            worlds.new_game, thresholds=LowQualityThresholds(max_confidence=1.0, min_cells=1)
        )
        # A job of the other game is not an import of this game.
        with pytest.raises(ImageReviewNotFoundError) as foreign_import:
            repository.completeness_report(
                worlds.new_game, import_job_id=worlds.big_seeds[0].import_job_id
            )
        assert foreign_import.value.code == "IMAGE_GEOMETRY_COMPLETENESS_IMPORT_NOT_FOUND"
        with pytest.raises(ImageReviewNotFoundError) as foreign_image:
            repository.source_image_asset(worlds.new_game, worlds.big_seeds[0].source_image_id)
        assert foreign_image.value.code == "IMAGE_GEOMETRY_COMPLETENESS_SOURCE_IMAGE_NOT_FOUND"
        # Queries without any game predicate see only the bound game (RLS + routing).
        counts = {
            table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in (
                "source_images",
                "recognized_boards",
                "image_review_items",
                "image_symbol_review_cells",
                "image_board_search_candidates",
            )
        }
        games_seen = {
            table: {
                row[0] for row in session.execute(text(f"SELECT DISTINCT game_id FROM {table}"))
            }
            for table in ("source_images", "image_symbol_review_cells")
        }
        session.rollback()
    assert report is not None and report.gate is not None
    assert report.game_id == worlds.new_game
    assert report.images.total == 2
    assert report.images.complete == 1
    assert report.gate.geometry_complete == 1
    assert report.gate.geometry_incomplete == 1
    assert report.gate.geometry_exception == 0
    assert report.gate.withheld_boards == 8
    assert page is not None
    assert {image.source_image_id for image in page.images} == {
        worlds.new_incomplete.source_image_id
    }
    assert {image.import_job_id for image in page.images} == {worlds.new_incomplete.import_job_id}
    assert low_quality is not None
    assert {board.source_image_id for board in low_quality.boards} <= new_ids
    assert not {board.source_image_id for board in low_quality.boards} & big_ids
    assert counts == {
        "source_images": 2,
        "recognized_boards": 17,
        "image_review_items": 17,
        "image_symbol_review_cells": 135,
        "image_board_search_candidates": 17,
    }
    assert games_seen == {
        "source_images": {worlds.new_game},
        "image_symbol_review_cells": {worlds.new_game},
    }

    with game_storage_scope(worlds.big_game), factory() as session:
        big_report = SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(
            worlds.big_game
        )
        foreign_rows = session.execute(
            text("SELECT count(*) FROM source_images WHERE id = ANY (:ids)"),
            {"ids": sorted(new_ids, key=str)},
        ).scalar_one()
        session.rollback()
    assert big_report is not None and big_report.gate is not None
    assert big_report.images.total == len(big_ids)
    assert big_report.gate.geometry_complete == 3
    assert big_report.gate.geometry_incomplete == 1
    # Bound to the big game, the new game's images do not exist.
    assert foreign_rows == 0


# -- plan assertions: four paths ---------------------------------------------


@dataclass(frozen=True)
class _Captured:
    statement: str
    parameters: Any


@contextmanager
def _capture(engine: Engine) -> Iterator[list[_Captured]]:
    """Record every statement the code under test sends to the database."""

    captured: list[_Captured] = []

    def listener(
        _connection: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        executemany: bool,
    ) -> None:
        if not executemany:
            captured.append(_Captured(statement, parameters))

    event.listen(engine, "before_cursor_execute", listener)
    try:
        yield captured
    finally:
        event.remove(engine, "before_cursor_execute", listener)


def _explainable(captured: Sequence[_Captured]) -> list[_Captured]:
    """Distinct read/update/delete statements (INSERT plans only name the parent)."""

    unique: dict[str, _Captured] = {}
    for item in captured:
        normalized = " ".join(item.statement.split())
        keyword = normalized.split(" ", 1)[0].upper()
        if keyword not in {"SELECT", "WITH", "UPDATE", "DELETE"}:
            continue
        if "set_config" in normalized or "pg_advisory" in normalized:
            continue
        unique.setdefault(normalized, item)
    return list(unique.values())


def _explain_relations(
    worlds: _Worlds, statements: Sequence[_Captured]
) -> tuple[int, set[tuple[str | None, str]]]:
    """Plan each statement in a transaction bound to the new game and collect relations."""

    relations: set[tuple[str | None, str]] = set()
    with game_storage_scope(worlds.new_game), worlds.factory() as session:
        GameStorageRouter().bind(session, worlds.new_game, intent=GameStorageIntent.READ)
        connection = session.connection()
        for item in statements:
            try:
                plan = connection.exec_driver_sql(
                    "EXPLAIN (VERBOSE, FORMAT JSON) " + item.statement, item.parameters
                ).scalar_one()
            except DBAPIError as error:  # pragma: no cover - names the statement
                raise AssertionError(f"EXPLAIN failed for: {item.statement}") from error
            relations.update(_plan_relations(json.loads(plan) if isinstance(plan, str) else plan))
        session.rollback()
    return len(statements), relations


def _assert_plans_stay_in_the_new_game(
    worlds: _Worlds, captured: Sequence[_Captured], *, minimum_statements: int
) -> set[str]:
    statements = _explainable(captured)
    assert len(statements) >= minimum_statements, [item.statement for item in statements]
    explained, relations = _explain_relations(worlds, statements)
    assert explained == len(statements)
    assert _foreign_relations(relations, worlds.new_partitions) == []
    names = {name for _schema, name in relations}
    assert not names & worlds.big_partitions
    # Not vacuous: the plans do read partitions of the new game.
    touched = names & worlds.new_partitions
    assert touched
    return touched


@_REQUIRES_POSTGRES
def test_plan_of_the_completeness_report_path_names_only_the_new_games_partitions(
    worlds: _Worlds,
) -> None:
    engine = worlds.database.app_engine
    with (
        _capture(engine) as captured,
        game_storage_scope(worlds.new_game),
        worlds.factory() as session,
    ):
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        assert repository.completeness_report(worlds.new_game) is not None
        assert (
            repository.completeness_report(
                worlds.new_game, import_job_id=worlds.new_incomplete.import_job_id
            )
            is not None
        )
        assert (
            repository.incomplete_images(
                worlds.new_game, completeness_status=SourceImageGeometryStatus.GEOMETRY_INCOMPLETE
            )
            is not None
        )
        assert (
            repository.low_quality_boards(
                worlds.new_game, thresholds=LowQualityThresholds(max_confidence=1.0, min_cells=1)
            )
            is not None
        )
        session.rollback()
    touched = _assert_plans_stay_in_the_new_game(worlds, captured, minimum_statements=6)
    assert {
        partition_name(worlds.new_game, table)
        for table in ("source_images", "recognized_boards", "image_symbol_review_cells")
    } <= touched


@_REQUIRES_POSTGRES
def test_plan_of_the_recompute_and_gate_path_names_only_the_new_games_partitions(
    worlds: _Worlds,
) -> None:
    engine = worlds.database.app_engine
    game_id = worlds.new_game
    incomplete_id = worlds.new_incomplete.source_image_id
    with game_storage_scope(game_id), worlds.factory() as session:
        rows = [
            (row[0], row[1], row[2])
            for row in session.execute(
                select(ImageReviewItemModel.id, RecognizedBoardModel, SourceImageModel)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .where(SourceImageModel.id == incomplete_id)
            )
        ]
        assert len(rows) == 8
        with _capture(engine) as captured:
            recomputed = recompute_source_image_geometry_completeness(
                session, game_id, incomplete_id
            )
            complete = recompute_source_image_geometry_completeness(
                session, game_id, worlds.new_complete.source_image_id
            )
            withheld = withheld_review_item_ids(session, game_id, rows)
        session.rollback()
    assert recomputed.status is SourceImageGeometryStatus.GEOMETRY_INCOMPLETE
    assert complete.status is SourceImageGeometryStatus.GEOMETRY_COMPLETE
    # The gate really withholds the 8 boards without cells (it is not skipped).
    assert withheld == {row[0] for row in rows}
    touched = _assert_plans_stay_in_the_new_game(worlds, captured, minimum_statements=6)
    assert {
        partition_name(worlds.new_game, table)
        for table in ("source_images", "image_symbol_review_cells")
    } <= touched


@_REQUIRES_POSTGRES
def test_plan_of_the_cell_materialization_path_names_only_the_new_games_partitions(
    worlds: _Worlds,
) -> None:
    engine = worlds.database.app_engine
    game_id = worlds.new_game
    incomplete_id = worlds.new_incomplete.source_image_id
    with game_storage_scope(game_id), worlds.factory() as session:
        with _capture(engine) as captured:
            # An operator exception admits the 8-of-9 image: the boards are cut
            # into cells (and projected into search) in this transaction.
            exception = SqlAlchemyImageGeometryCompletenessStateRepository(session).set_exception(
                game_id, incomplete_id, reason="TASK-0809 plan probe", actor="task-0809"
            )
            ids = active_review_item_ids(session, game_id, incomplete_id)
            coordinator = SymbolCellReviewWriteThroughCoordinator(session)
            for review_item_id in ids:
                coordinator.synchronize_after_geometry_admission(
                    game_id=game_id, review_item_id=review_item_id, actor="task-0809"
                )
        session.rollback()
    assert exception is not None
    assert exception.status is SourceImageGeometryStatus.GEOMETRY_EXCEPTION
    assert exception.materialized_review_item_count == 8
    touched = _assert_plans_stay_in_the_new_game(worlds, captured, minimum_statements=8)
    assert partition_name(game_id, "image_symbol_review_cells") in touched
    # Rolled back: the probe left the image as it was.
    after = _state(worlds.factory, game_id, incomplete_id)
    assert (after["status"], after["cells"]) == ("geometry_incomplete", 0)


@_REQUIRES_POSTGRES
def test_plan_of_the_search_projection_path_names_only_the_new_games_partitions(
    worlds: _Worlds,
) -> None:
    engine = worlds.database.app_engine
    game_id = worlds.new_game
    with game_storage_scope(game_id), worlds.factory() as session:
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
        ids = active_review_item_ids(session, game_id, worlds.new_complete.source_image_id)
        assert len(ids) == 9
        repository = SqlAlchemyBoardSearchProjectionRepository(session)
        with _capture(engine) as captured:
            assert repository.stale_review_item_ids(ids) == frozenset()
            repository.sync_review_items(ids)
            rebuilt = repository.rebuild_game(game_id)
        session.rollback()
    assert rebuilt is not None
    touched = _assert_plans_stay_in_the_new_game(worlds, captured, minimum_statements=6)
    assert {
        partition_name(game_id, table)
        for table in ("image_board_search_candidates", "image_board_search_fast_documents")
    } <= touched


@_REQUIRES_POSTGRES
def test_statement_without_a_game_predicate_is_pruned_to_the_bound_game_by_row_security(
    worlds: _Worlds,
) -> None:
    """Some repository statements filter only by a row id (``session.get``, ``DELETE ... WHERE
    review_item_id``). Their isolation rests on the transaction binding plus the row-security
    policy, which lets the planner prune every partition but the bound game's. Run as the
    application role, the plan of such a statement names exactly one partition."""

    source_image_id = worlds.new_complete.source_image_id
    statement = "SELECT count(*) FROM source_images WHERE id = :source_image_id"
    with game_storage_scope(worlds.new_game), worlds.factory() as session:
        GameStorageRouter().bind(session, worlds.new_game, intent=GameStorageIntent.READ)
        connection = session.connection()
        plan = connection.execute(
            text("EXPLAIN (VERBOSE, FORMAT JSON) " + statement),
            {"source_image_id": source_image_id},
        ).scalar_one()
        found = connection.execute(text(statement), {"source_image_id": source_image_id})
        session.rollback()
    relations = _plan_relations(json.loads(plan) if isinstance(plan, str) else plan)
    assert relations == [(_SCHEMA, partition_name(worlds.new_game, "source_images"))]
    assert found.scalar_one() == 1


# -- behaviour without a game binding ----------------------------------------


@_REQUIRES_POSTGRES
def test_state_and_report_queries_without_a_game_binding_fail_instead_of_returning_nothing(
    worlds: _Worlds,
) -> None:
    engine = worlds.database.app_engine
    # The repositories bind the game themselves: called on a session with no
    # ambient scope they still return the game's own data.
    with worlds.factory() as session:
        bound_report = SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(
            worlds.new_game
        )
        session.rollback()
    assert bound_report is not None and bound_report.images.total == 2

    with (
        _capture(engine) as captured,
        game_storage_scope(worlds.new_game),
        worlds.factory() as session,
    ):
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        assert repository.completeness_report(worlds.new_game) is not None
        assert repository.incomplete_images(worlds.new_game) is not None
        session.rollback()
    game_statements = [
        item
        for item in _explainable(captured)
        if _GAME_TABLE_NAME.search(item.statement)
        and "game_storage_locations" not in item.statement
    ]
    assert len(game_statements) >= 4

    # The very SQL the repository ran, sent without a game binding, errors out
    # (relation missing from the search path, or the RLS scope check) -- it never
    # silently yields an empty result.
    for item in game_statements:
        with engine.connect() as connection, pytest.raises(DBAPIError) as refused:
            connection.exec_driver_sql(item.statement, item.parameters)
        assert getattr(refused.value.orig, "sqlstate", None) in {"42P01", "42501"}, item.statement

    # The same holds for the ORM models of the state, and for the qualified name.
    factory = create_session_factory(engine)
    with factory() as session, pytest.raises(DBAPIError) as orm_refused:
        session.execute(select(SourceImageModel.geometry_completeness_status)).all()
    assert getattr(orm_refused.value.orig, "sqlstate", None) == "42P01"
    with engine.connect() as connection, pytest.raises(DBAPIError) as qualified_refused:
        connection.exec_driver_sql(
            f"SELECT geometry_completeness_status FROM {_SCHEMA}.source_images"
        )
    assert getattr(qualified_refused.value.orig, "sqlstate", None) == "42501"
    assert "GAME_STORAGE_SCOPE_REQUIRED" in str(qualified_refused.value.orig)

    # A transaction bound to one game cannot read the other game's rows even
    # when it names them.
    with game_storage_scope(worlds.big_game), worlds.factory() as session:
        GameStorageRouter().bind(session, worlds.big_game, intent=GameStorageIntent.READ)
        leaked = session.execute(
            text("SELECT count(*) FROM source_images WHERE game_id = :other"),
            {"other": worlds.new_game},
        ).scalar_one()
        session.rollback()
    assert leaked == 0
