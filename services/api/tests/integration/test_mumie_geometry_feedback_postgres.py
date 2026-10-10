"""Exact human geometry export survives process loss on a guarded disposable DB."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import test_vision_lab_geometry_export_postgres as legacy
from _application_role_database import application_role_database
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    ImageBoardGeometryRevisionModel,
    ImageSourceGeometryRevisionModel,
    RecognizedBoardModel,
)
from game_predictor_worker.vision_lab import production_geometry as geometry
from sqlalchemy.orm import Session

from scripts import vision_lab_geometry_export as exporter

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit guarded disposable PostgreSQL test only.",
)


def test_current_exact_human_export_resumes_cold_without_database_writes(tmp_path: Path):
    with application_role_database("t0883", ()) as database:
        assert database.owner_url.database.endswith("_test")
        assert database.owner_url.database != "game_predictor"
        # Reuse the old row fixtures, never their unguarded database fixture.
        world = legacy.world.__wrapped__(database.owner_engine)
        expected = {}
        with Session(database.owner_engine) as session, session.begin():
            GameStorageRouter().bind(session, world.game_id, intent=GameStorageIntent.WRITE)
            for name in ("S", "Greviewer"):
                board = session.get(RecognizedBoardModel, world.boards[name])
                assert board is not None
                revision = (
                    session.query(ImageBoardGeometryRevisionModel)
                    .filter_by(recognized_board_id=board.id, revision=board.geometry_revision)
                    .one()
                )
                source = session.get(
                    ImageSourceGeometryRevisionModel, board.source_geometry_revision_id
                )
                assert source is not None
                nodes = list(
                    geometry.derive_grid_nodes(
                        legacy._grid(board.position_index, board.geometry_revision)
                    )
                )
                nodes[7] = (nodes[7][0] + 2.123456789, nodes[7][1] + 7.987654321)
                raw_nodes = [{"x": x, "y": y} for x, y in nodes]
                cells = [
                    {
                        "cellIndex": index,
                        "renderSpec": {
                            "cellIndex": index,
                            "coordinateSpace": geometry.COORDINATE_SPACE,
                            "topology": {"rows": 3, "columns": 5},
                            "sourceQuad": [{"x": x, "y": y} for x, y in quad],
                        },
                    }
                    for index, quad in enumerate(geometry.cell_quads_from_nodes(nodes))
                ]
                render = {"latticeNodes": raw_nodes, "cells": cells}
                revision.geometry = {"latticeNodes": raw_nodes}
                revision.virtual_render_spec = render
                revision.virtual_render_spec_checksum_sha256 = hashlib.sha256(
                    canonical_json_bytes(render)
                ).hexdigest()
                entries = [dict(entry) for entry in source.board_geometries]
                entries[board.position_index]["latticeNodes"] = raw_nodes
                source.board_geometries = entries
                manifest = (
                    session.query(BoardRenderManifestModel)
                    .filter_by(
                        recognized_board_id=board.id, geometry_revision=board.geometry_revision
                    )
                    .one()
                )
                manifest.cells = render
                manifest.manifest_checksum_sha256 = hashlib.sha256(
                    canonical_json_bytes(render)
                ).hexdigest()
                expected[str(board.id)] = [list(point) for point in nodes]
                if name == "S":
                    legacy._approve(board, board.geometry_revision, "local-admin")
        before = legacy._table_state(database.owner_engine)
        output = tmp_path / "exports"
        assert (
            exporter.run_export(
                database.app_engine,
                world.game_id,
                output,
                export_id="exact",
                batch_images=1,
                workers=1,
                stop_after_batches=1,
            )
            is None
        )
        # A new interpreter and connection resume the persisted receipt. The
        # ephemeral credential is passed privately via environment, never logged.
        env = os.environ.copy()
        env["MUMIE_TEST_DB_URL"] = database.app_url.render_as_string(hide_password=False)
        env["MUMIE_TEST_GAME"] = str(world.game_id)
        env["MUMIE_TEST_OUTPUT"] = str(output)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; from uuid import UUID; from pathlib import Path; "
                "from sqlalchemy import create_engine; "
                "from scripts import vision_lab_geometry_export as e; "
                "db=create_engine(os.environ['MUMIE_TEST_DB_URL'],"
                "connect_args={'connect_timeout':5}); "
                "e.run_export(db,UUID(os.environ['MUMIE_TEST_GAME']),Path(os.environ['MUMIE_TEST_OUTPUT']),"
                "export_id='exact',batch_images=1,workers=1,resume=True); db.dispose()",
            ],
            cwd=Path(__file__).resolve().parents[4],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        published = output / "exact"
        rows = {
            row["recognizedBoardId"]: row for row in legacy._read(published, "candidates.jsonl")
        }
        assert rows[str(world.boards["S"])]["geometry"]["nodes"] == expected[str(world.boards["S"])]
        assert rows[str(world.boards["S"])]["partial"]["cellVisibility"] == ["full"] * 15
        exclusions = {
            row["recognizedBoardId"]: row["reason"]
            for row in legacy._read(published, "exclusions.jsonl")
        }
        assert (
            exclusions[str(world.boards["Greviewer"])] == geometry.EXCLUSION_HUMAN_APPROVAL_REQUIRED
        )
        assert legacy._table_state(database.owner_engine) == before
        report = json.loads((published / "report.json").read_bytes())
        assert report["transactionReadOnlyVerified"] is True
        assert report["run"]["resumes"] == 1
        assert report["reconciliation"]["matches"] is True
        checksum = hashlib.sha256((published / "candidates.jsonl").read_bytes()).hexdigest()
        with pytest.raises(exporter.GeometryExportError, match="already exists"):
            exporter.run_export(
                database.app_engine, world.game_id, output, export_id="exact", resume=True
            )
        assert hashlib.sha256((published / "candidates.jsonl").read_bytes()).hexdigest() == checksum
        assert legacy._table_state(database.owner_engine) == before
