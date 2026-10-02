"""Isolated PostgreSQL coverage of the read-only production geometry export (TASK-0800).

Builds a game routed to ``game_data_v2`` with a complete image that carries every
label level, a board whose manifest disagrees with its quads, a board without a
manifest, a rejected board and a partial board; plus skipped images and a second
game. The export runs through ``vision_lab_geometry_export.run_export`` and its
output is compared with what the rows say. Nothing in the database changes.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    GameModel,
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_worker.vision_lab import production_geometry as pg
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_image_geometry_completeness_repository import (
    PARTIAL,
    _Builder,
    _import_job,
    _provision_v2_storage_location,
    _quote,
    _sha,
)

from scripts import vision_lab_geometry_export as exporter

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)

GRID: pg.Quad = ((100.0, 50.0), (600.0, 62.5), (590.0, 350.25), (95.5, 340.0))
ENGINE_ACTOR = "system:image-pipeline-v0.10"


def _points(quad: pg.Quad) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in quad]


def _grid(position: int, revision: int = 0) -> pg.Quad:
    shift = position * 3.0 + revision * 0.5
    return tuple((x + shift, y + shift / 2) for x, y in GRID)  # type: ignore[return-value]


@dataclass(slots=True)
class _World:
    game_id: UUID
    other_game_id: UUID
    images: dict[str, UUID]
    boards: dict[str, UUID]


_EXTRA_PARTITIONED_TABLES = ("board_render_manifests", "image_board_geometry_revisions")


def _provision(session: Session, game_id: UUID) -> None:
    """The completeness fixtures' partitions plus the tables the export also reads."""

    _provision_v2_storage_location(session, game_id=game_id)
    for table in _EXTRA_PARTITIONED_TABLES:
        session.execute(
            text(
                f"CREATE TABLE game_data_v2.{table}_g_{game_id.hex} "
                f"PARTITION OF game_data_v2.{table} FOR VALUES IN ('{game_id}')"
            )
        )


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    name = "game_predictor_task0800_" + uuid4().hex[:12]
    url = make_url(ApiSettings.from_environment().owner_database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        connection.execute(text(f"CREATE DATABASE {_quote(name)}"))
    try:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text(f"DROP DATABASE {_quote(name)}"))
        maintenance.dispose()


def _manifest(
    session: Session,
    game_id: UUID,
    board: RecognizedBoardModel,
    quad: pg.Quad,
    *,
    columns: int = 5,
    skip: tuple[int, ...] = (),
    shift: float = 0.0,
) -> None:
    """The render manifest of the board's current revision, cut from ``quad``."""

    cells = []
    for index, cell in enumerate(pg.cell_quads_from_nodes(pg.derive_grid_nodes(quad))):
        if index in skip:
            continue
        cells.append(
            {
                "cellIndex": index,
                "renderSpec": {
                    "cellIndex": index,
                    "coordinateSpace": pg.COORDINATE_SPACE,
                    "sourceQuad": [{"x": x + shift, "y": y} for x, y in cell],
                    "topology": {"rows": 3, "columns": columns},
                },
            }
        )
    document = {"assetMode": "virtual_source", "cells": cells, "schemaVersion": "fixture"}
    assert board.source_geometry_revision_id is not None
    session.add(
        BoardRenderManifestModel(
            game_id=game_id,
            recognized_board_id=board.id,
            geometry_revision=board.geometry_revision,
            asset_mode="virtual_source",
            source_geometry_revision_id=board.source_geometry_revision_id,
            extractor_version="fixture-renderer-v1",
            cells=document,
            manifest_checksum_sha256=hashlib.sha256(
                json.dumps(document, sort_keys=True).encode()
            ).hexdigest(),
        )
    )
    session.flush()


def _revision(
    session: Session,
    board: RecognizedBoardModel,
    revision: int,
    author: str,
    quad: pg.Quad,
) -> None:
    item = session.query(ImageReviewItemModel).filter_by(recognized_board_id=board.id).one()
    assert board.source_geometry_revision_id is not None
    session.add(
        ImageBoardGeometryRevisionModel(
            review_item_id=item.id,
            recognized_board_id=board.id,
            revision=revision,
            idempotency_key=uuid4(),
            command_sha256=_sha(f"command:{board.id}:{revision}"),
            corners=_points(quad),
            geometry={},
            asset_mode="virtual_source",
            source_geometry_revision_id=board.source_geometry_revision_id,
            geometry_checksum_sha256=_sha(f"geometry:{board.id}:{revision}"),
            virtual_render_spec={"cells": []},
            virtual_render_spec_checksum_sha256=_sha(f"spec:{board.id}:{revision}"),
            cropper_version="fixture-cropper-v1",
            corrected_by=author,
        )
    )
    session.flush()


def _approve(board: RecognizedBoardModel, revision: int, actor: str) -> None:
    board.approved_geometry_revision = revision
    board.geometry_approved_at = datetime.now(UTC)
    board.geometry_approved_by = actor


def _gate(source: SourceImageModel, status: str | None) -> None:
    source.geometry_completeness_status = status
    source.geometry_completeness_evaluated_at = datetime.now(UTC) if status else None


def _set_revision_quads(revision: ImageSourceGeometryRevisionModel, slots: int = 9) -> None:
    revision.board_geometries = [
        {
            "disposition": "automatic",
            "positionIndex": position,
            "sequenceNumber": revision.sequence_range_start + position,
            "finalQuad": _points(GRID),
            "symbolGridQuad": _points(_grid(position)),
        }
        for position in range(slots)
    ]
    revision.engine_kind = (
        "structured_opencv_v1" if revision.geometry_source == "auto" else "manual_v1"
    )
    revision.created_by = ENGINE_ACTOR


@pytest.fixture(scope="module")
def world(database: Engine) -> _World:
    images: dict[str, UUID] = {}
    boards: dict[str, UUID] = {}
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="geo-x", name="Export A", expected_layout_count=100000)
        other = GameModel(code="geo-y", name="Export B", expected_layout_count=100000)
        session.add_all([game, other])
        session.flush()
        _provision(session, game.id)
        build = _Builder(session, game.id)
        job = _import_job(session, game_id=game.id)
        job.input_payload = {
            "import_kind": "image_directory",
            "source_directory": r"C:\imports\browser-selections\selection-aaa",
            "source_display_name": "1-99 cut",
        }
        session.flush()

        # Image one: every label level and exclusion in a single complete image.
        one = build.source(job, "one.jpg")
        images["one"] = one.id
        _gate(one, "geometry_complete")
        auto = build.revision(one, revision=0, range_start=1000)
        _set_revision_quads(auto)
        session.flush()

        def add(
            position: int,
            name: str,
            *,
            revision: int = 0,
            source: ImageSourceGeometryRevisionModel = auto,
            **kwargs: Any,
        ) -> RecognizedBoardModel:
            board = build.board(one, source, position, geometry_revision=revision, **kwargs)
            boards[name] = board.id
            return board

        b_board = add(0, "B")
        _manifest(session, game.id, b_board, _grid(0))
        s_board = add(1, "S", revision=1)
        _approve(s_board, 1, "system:grid-reverify-777-v1")
        _revision(session, s_board, 1, "system:grid-reverify-777-v1", _grid(1, 1))
        _manifest(session, game.id, s_board, _grid(1, 1))
        g_board = add(2, "G")
        _approve(g_board, 0, "local-admin")
        _manifest(session, game.id, g_board, _grid(2))
        legacy = add(3, "Greviewer", revision=2)
        _revision(session, legacy, 1, "reviewer-operator", _grid(3, 1))
        _revision(session, legacy, 2, "system:legacy-board-conversion-v1", _grid(3, 2))
        _manifest(session, game.id, legacy, _grid(3, 2))
        mystery = add(4, "U")
        _approve(mystery, 0, "system:mystery-job")
        _manifest(session, game.id, mystery, _grid(4))
        shifted = add(5, "shifted")
        _manifest(session, game.id, shifted, _grid(5), shift=2.0)
        add(6, "nomanifest")
        add(7, "rejected", board_status="rejected", item_status=None)
        partial = add(8, "partial", completeness=PARTIAL)
        _manifest(session, game.id, partial, _grid(8), skip=(0,))
        build.cells(
            b_board,
            auto,
            job,
            specs=[(0.95, "pending", True)] * 14 + [(0.5, "pending", True)],
        )
        build.cells(s_board, auto, job, specs=[(0.4, "approved", True)] * 15)

        # Image two is incomplete and image three outside the gate: never exported.
        two = build.source(job, "two.jpg")
        _gate(two, "geometry_incomplete")
        two_revision = build.revision(two, revision=0, range_start=2000)
        _set_revision_quads(two_revision)
        _manifest(session, game.id, build.board(two, two_revision, 0), _grid(0))
        three = build.source(job, "three.jpg")
        _gate(three, None)
        three_revision = build.revision(three, revision=0, range_start=3000)
        _set_revision_quads(three_revision)
        _manifest(session, game.id, build.board(three, three_revision, 0), _grid(0))
        images.update(two=two.id, three=three.id)

        # Image four: complete, a 3 x 3 manifest is not a 5 x 3 board.
        four = build.source(job, "four.jpg")
        images["four"] = four.id
        _gate(four, "geometry_complete")
        four_revision = build.revision(four, revision=0, range_start=4000, slots=2)
        _set_revision_quads(four_revision, slots=2)
        three_by_three = build.board(four, four_revision, 0)
        boards["threeByThree"] = three_by_three.id
        _manifest(session, game.id, three_by_three, _grid(0), columns=3)
        fine = build.board(four, four_revision, 1)
        boards["fine"] = fine.id
        _manifest(session, game.id, fine, _grid(1))
        game_id, other_id = game.id, other.id

    with Session(database, expire_on_commit=False) as session, session.begin():
        _provision(session, other_id)
        build = _Builder(session, other_id)
        other_job = _import_job(session, game_id=other_id)
        five = build.source(other_job, "five.jpg")
        _gate(five, "geometry_complete")
        five_revision = build.revision(five, revision=0, range_start=100, slots=1)
        _set_revision_quads(five_revision, slots=1)
        other_board = build.board(five, five_revision, 0)
        boards["other"] = other_board.id
        images["five"] = five.id
        _manifest(session, other_id, other_board, _grid(0))
    return _World(game_id, other_id, images, boards)


@pytest.fixture
def output_root() -> Iterator[Path]:
    root = Path.cwd().resolve() / ".test-artifacts" / ("geo-" + uuid4().hex[:8])
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def _read(directory: Path, name: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (directory / name).read_text(encoding="utf-8").splitlines()
        if line
    ]


def _table_state(database: Engine) -> dict[str, int]:
    tables = (
        "source_images",
        "recognized_boards",
        "image_source_geometry_revisions",
        "image_board_geometry_revisions",
        "board_render_manifests",
        "image_symbol_review_cells",
        "image_review_items",
    )
    with database.connect() as connection:
        state = {
            table: int(
                connection.execute(text(f"SELECT count(*) FROM game_data_v2.{table}")).scalar_one()
            )
            for table in tables
        }
        state["jobs"] = int(connection.execute(text("SELECT count(*) FROM jobs")).scalar_one())
    return state


def test_export_levels_exclusions_and_reconciliation(
    database: Engine, world: _World, output_root: Path
) -> None:
    before = _table_state(database)
    directory = exporter.run_export(
        database, world.game_id, output_root, export_id="export", batch_images=1
    )
    assert directory == output_root / "export"
    assert not list(output_root.glob(".partial-*"))
    rows = {row["recognizedBoardId"]: row for row in _read(directory, "candidates.jsonl")}
    boards = world.boards
    ids = {name: str(board_id) for name, board_id in boards.items()}

    expected = {
        "B": ("B", "engine_accepted_unapproved", None),
        "S": ("S", "system_reverify", "system:grid-reverify-777-v1"),
        "G": ("G", "human_approval", "local-admin"),
        "Greviewer": ("G", "human_saved_revision_via_legacy_conversion", "reviewer-operator"),
        "U": ("U", "unknown_system_approver", "system:mystery-job"),
        "partial": ("B", "engine_accepted_unapproved", None),
        "fine": ("B", "engine_accepted_unapproved", None),
    }
    assert set(rows) == {ids[name] for name in expected}
    for name, (level, basis, actor) in expected.items():
        label = rows[ids[name]]["label"]
        assert (label["level"], label["basis"], label["approvalActor"]) == (level, basis, actor)

    # Rows carry the identifiers, the 24 nodes and a manifest deviation of zero.
    row = rows[ids["B"]]
    assert row["gameId"] == str(world.game_id)
    assert row["sourceImageId"] == str(world.images["one"])
    assert row["sequenceNumber"] == 1000
    assert row["expectedBoardsOnImage"] == 9
    assert row["candidateBoardsOnImage"] == 6
    assert row["coordinateSpace"] == pg.COORDINATE_SPACE
    assert len(row["geometry"]["nodes"]) == 24
    assert row["geometry"]["nodes"][0] == [
        round(_grid(0)[0][0], 4),
        round(_grid(0)[0][1], 4),
    ]
    assert row["geometry"]["maxManifestDeviationPx"] == 0.0
    assert row["geometry"]["quadSource"] == "source_revision_symbol_grid_quad"
    assert rows[ids["S"]]["geometry"]["quadSource"] == "board_revision_corners"
    assert rows[ids["Greviewer"]]["geometry"]["quadSource"] == "board_revision_corners"
    assert row["family"]["familyId"] == "selection:selection-aaa"
    assert row["family"]["sourceDisplayName"] == "1-99 cut"

    # Symbol-filter signals use the completeness-report definition (<= 0.80).
    signals = row["symbolSignals"]
    assert (signals["cells"], signals["lowQualityCells"], signals["cellsBelowFilter"]) == (15, 1, 1)
    assert signals["minLowQualityConfidence"] == pytest.approx(0.5)
    assert signals["humanDecidedCells"] == 0
    all_decided = rows[ids["S"]]["symbolSignals"]
    assert (all_decided["humanDecidedCells"], all_decided["cellsBelowFilter"]) == (15, 0)
    assert rows[ids["G"]]["symbolSignals"]["cells"] == 0

    # Partial board: the missing manifest cell is covered by its unavailable mask.
    assert rows[ids["partial"]]["partial"]["isPartial"] is True
    assert rows[ids["partial"]]["partial"]["manifestMissingCellIndices"] == [0]
    assert rows[ids["partial"]]["partial"]["unavailableCellIndices"] == [0]

    exclusions = {
        item["recognizedBoardId"]: item["reason"] for item in _read(directory, "exclusions.jsonl")
    }
    assert exclusions == {
        ids["shifted"]: pg.EXCLUSION_NODES_MISMATCH,
        ids["nomanifest"]: pg.EXCLUSION_MANIFEST_MISSING,
        ids["threeByThree"]: pg.EXCLUSION_TOPOLOGY_NOT_5X3,
    }
    # Nothing of the incomplete image, the ungated image, the rejected board or game B.
    assert ids["rejected"] not in rows and ids["rejected"] not in exclusions
    assert str(boards["other"]) not in rows
    assert {row["sourceImageId"] for row in rows.values()} == {
        str(world.images["one"]),
        str(world.images["four"]),
    }

    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    assert report["transactionReadOnlyVerified"] is True
    assert report["reconciliation"]["matches"] is True
    assert report["reconciliation"]["liveBoardsOnCompleteImages"] == 10
    assert report["reconciliation"]["candidateRows"] == 7
    assert report["reconciliation"]["excludedRows"] == 3
    assert report["candidates"]["byLevel"] == {"B": 3, "G": 2, "S": 1, "U": 1}
    assert report["candidates"]["images"] == 2
    assert report["exclusions"]["byReason"] == {
        pg.EXCLUSION_MANIFEST_MISSING: 1,
        pg.EXCLUSION_NODES_MISMATCH: 1,
        pg.EXCLUSION_TOPOLOGY_NOT_5X3: 1,
    }
    assert report["exclusions"]["rejectedBoardsOnCompleteImages"] == 1
    assert report["universe"]["liveBoardsByImageGateStatus"] == {
        "None": 1,
        "geometry_complete": 10,
        "geometry_incomplete": 1,
    }
    assert report["families"]["count"] == 1
    manifest = json.loads((directory / "export_manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidateRows"] == 7
    assert (
        manifest["files"]["candidates.jsonl"]["sha256"]
        == hashlib.sha256((directory / "candidates.jsonl").read_bytes()).hexdigest()
    )

    assert _table_state(database) == before


def test_second_game_never_leaks_into_the_first_export(
    database: Engine, world: _World, output_root: Path
) -> None:
    directory = exporter.run_export(
        database, world.other_game_id, output_root, export_id="other", batch_images=5
    )
    assert directory is not None
    rows = _read(directory, "candidates.jsonl")
    assert [row["recognizedBoardId"] for row in rows] == [str(world.boards["other"])]
    assert {row["gameId"] for row in rows} == {str(world.other_game_id)}
    assert _read(directory, "exclusions.jsonl") == []


def test_resume_after_interruption_does_not_duplicate_rows(
    database: Engine, world: _World, output_root: Path
) -> None:
    whole = exporter.run_export(
        database, world.game_id, output_root, export_id="whole", batch_images=1
    )
    assert whole is not None
    stopped = exporter.run_export(
        database,
        world.game_id,
        output_root,
        export_id="resumed",
        batch_images=1,
        stop_after_batches=1,
    )
    assert stopped is None
    partial = output_root / ".partial-resumed"
    progress = json.loads((partial / "progress.json").read_text(encoding="utf-8"))
    assert progress["images"] == 1 and progress.get("completed") is None
    # A crash between the row append and the progress write leaves bytes the progress
    # does not know; resuming must drop them instead of duplicating the batch.
    with (partial / "candidates.jsonl").open("ab") as handle:
        handle.write(b'{"torn":')
    with pytest.raises(exporter.GeometryExportError, match="--resume"):
        exporter.run_export(
            database, world.game_id, output_root, export_id="resumed", batch_images=1
        )
    resumed = exporter.run_export(
        database, world.game_id, output_root, export_id="resumed", batch_images=1, resume=True
    )
    assert resumed == output_root / "resumed"
    for name in ("candidates.jsonl", "exclusions.jsonl"):
        assert (resumed / name).read_bytes() == (whole / name).read_bytes()
    report = json.loads((resumed / "report.json").read_text(encoding="utf-8"))
    assert report["run"]["resumes"] == 1
    assert report["reconciliation"]["matches"] is True
    with pytest.raises(exporter.GeometryExportError, match="already exists"):
        exporter.run_export(database, world.game_id, output_root, export_id="resumed")


def test_export_transaction_cannot_write(database: Engine, world: _World) -> None:
    with exporter._batch_transaction(database, world.game_id, None) as connection:
        assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
        assert (
            connection.exec_driver_sql("SHOW transaction_isolation").scalar_one()
            == "repeatable read"
        )
        with pytest.raises(DBAPIError, match="read-only"):
            connection.execute(text("UPDATE source_images SET status = status"))
