"""Bounded owned PostgreSQL JSONB/advance proof; source manifest access is a fixture boundary."""

# Shared owned-database fixtures are also needed during standalone Worker collection.
# ruff: noqa: E402
import os
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

API_INTEGRATION_TESTS = Path(__file__).resolve().parents[2] / "api/tests/integration"
sys.path.insert(0, str(API_INTEGRATION_TESTS))

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_cell_content import ContentRevision, ContentSource
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.schemas.grid_cell_content import ContentSessionAdvance
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_cell_content_models import (
    GridCellContentRevisionModel as Revision,
)
from game_predictor_api.storage.grid_cell_content_models import (
    GridCellContentSessionModel as Measurement,
)
from game_predictor_api.storage.grid_content_diagnostic_measurement import (
    diagnostic_measurement_ready,
)
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel
from game_predictor_worker.images.grid_cell_content_reference import run_blind_content_oracle
from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_crop_blocked_repeatability import blocked_fixture
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1", reason="Explicit owned PG only"
)


def test_actual_advance_jsonb_order_retains_diagnostic_repeatability(tmp_path):
    sql, old_game, identifier, snapshot, *_ = blocked_fixture(tmp_path)
    try:
        with Session(sql) as local:
            measured = local.get(Measurement, (old_game, identifier))
            document, progress, cohort = (
                deepcopy(measured.document),
                deepcopy(measured.progress),
                measured.cohort_id,
            )
            originals = [
                {c.name: getattr(row, c.name) for c in Revision.__table__.columns}
                for row in local.scalars(select(Revision)).all()
            ]
        with application_role_database("t1167parent", ("diagnostic-jsonb",)) as db:
            print("T1172 R1 owned PG migrated", flush=True)
            game = db.games["diagnostic-jsonb"]
            frames = {}
            original_frame = snapshot.frame()
            for index, raw in enumerate(document["targets"]):
                raw["gameId"] = str(game)
                pixels = original_frame.rgb.copy()
                pixels[0, 0, 0] = index
                sha = rgb_pixel_checksum_sha256(pixels)
                frames[sha] = replace(
                    original_frame,
                    source=replace(original_frame.source, normalized_pixel_checksum_sha256=sha),
                    rgb=pixels,
                )
            document["targets"].sort(
                key=lambda t: (t["source"]["sourceRepresentativeSha256"], t["positionIndex"])
            )
            document["manifestSha256"] = "a" * 64
            with game_storage_scope(game), Session(db.owner_engine) as session, session.begin():
                repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                repo.bind(game, write=True)
                session.add(
                    GridTrainingCohortModel(
                        game_id=game,
                        id=cohort,
                        status="frozen",
                        manifest_path="fixture/manifest.json",
                        manifest_sha256="a" * 64,
                        document={},
                        summary={},
                        created_by="fixture",
                    )
                )
                session.flush()
                session.add(
                    Measurement(
                        game_id=game,
                        id=identifier,
                        cohort_id=cohort,
                        revision=3,
                        phase="pass1",
                        document=document,
                        progress=progress,
                        report=None,
                    )
                )
                for raw in originals:
                    data = deepcopy(raw["document"])
                    data["reference"]["gameId"] = str(game)
                    annotation = ContentRevision.model_validate(data)
                    key = f"{raw['pixel_sha256']}:0"
                    oracle = (
                        None
                        if raw["revision"] == 1
                        else run_blind_content_oracle(
                            frames[raw["pixel_sha256"]], annotation, document["oracleContexts"][key]
                        )
                    )
                    session.add(
                        Revision(
                            **{
                                **raw,
                                "game_id": game,
                                "live_source_image_id": None,
                                "document": annotation.model_dump(mode="json"),
                                "document_sha256": annotation.sha256,
                                "oracle": oracle,
                            }
                        )
                    )
            print("T1172 R1 real oracle receipts persisted as JSONB", flush=True)
            sources = {
                UUID(t["source"]["sourceId"]): ContentSource.model_validate(t["source"])
                for t in document["targets"]
            }
            for number in (3, 4):
                with game_storage_scope(game), Session(db.app_engine) as session, session.begin():
                    repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                    # Full source/cohort admission is covered by the retained PG test;
                    # here only that boundary is replaced, not advance, locks, SQL or oracle.
                    repo.snapshot = lambda *a: SimpleNamespace()
                    repo.current_source = lambda game, source, **kw: sources[source]
                    result = repo.advance(
                        game,
                        identifier,
                        ContentSessionAdvance(
                            idempotencyKey=UUID(int=number), expectedSessionRevision=number
                        ),
                        "local-owner",
                    )
            assert result["session"]["report"]["qualificationState"] == "render_contract_blocked"
            with game_storage_scope(game), Session(db.app_engine) as session:
                repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                repo.bind(game)
                measured = session.get(Measurement, (game, identifier))
                before = digest(measured.report)
                assert diagnostic_measurement_ready(session, game, measured)
                assert digest(measured.report) == before
            print("T1172 R1 actual advance and reconstructed JSONB report PASS", flush=True)
    finally:
        sql.dispose()
