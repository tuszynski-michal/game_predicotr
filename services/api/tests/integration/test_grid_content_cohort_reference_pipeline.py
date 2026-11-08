"""Real blind labels -> opt-in frozen geometry -> worker, with legacy GT unchanged."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.domain.grid_training_cohorts import digest, exact_lattice
from game_predictor_api.domain.grid_visibility_contract import CellContentReference
from game_predictor_api.schemas.grid_cell_content import (
    ContentBlindWrite,
    ContentSessionAdvance,
    ContentSessionCreate,
    ContentSessionTargetSelection,
    ContentWriteCommand,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_correction_split import split_mapping
from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.models import SymbolModel
from game_predictor_worker.images.grid_cell_content_reference import frozen_content_reference
from game_predictor_worker.images.grid_cohort_dataset import (
    GridAssessmentDataset,
    GridBoardDataset,
    GridCohortSnapshot,
)
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_training_cohort_e2e_postgres import (
    _freeze_body,
    _install_base,
    _nodes,
    _providers,
    _save_source,
)
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only; no operator sources or model runs",
)

ACTOR = "local-owner"
CONTENT_POLICY = "full-symbol-content-sampling-v1"


@contextmanager
def _owned_pooled_database():
    """Reuse test connections without changing LOGIN roles, RLS or domain guards."""
    with application_role_database("t1165pipe", ("content-pipeline",)) as owned:
        owner = create_engine(owned.owner_url, connect_args={"connect_timeout": 5})
        app = create_engine(owned.app_url, connect_args={"connect_timeout": 5})
        try:
            yield replace(owned, owner_engine=owner, app_engine=app)
        finally:
            app.dispose()
            owner.dispose()


def _measured_nodes(position, shift):
    # Match the DTO's floating-point JSON representation before pinning its SHA.
    return tuple((float(point.x + shift), float(point.y)) for point in _nodes(position))


def _cells(position, shift=0.0):
    nodes = _measured_nodes(position, shift)
    return tuple(
        CellContentReference(
            state="visible",
            quad=((x + 6, y + 6), (x + 24, y + 6), (x + 24, y + 24), (x + 6, y + 24)),
        )
        for x, y in (nodes[(index // 5) * 6 + index % 5] for index in range(15))
    )


def _service(session, root, provider_sha):
    return GridTrainingCohortService(
        SqlAlchemyGridTrainingCohortRepository(session, root), root, provider_sha
    )


def _freeze(factory, root, game, command, provider_sha, stage):
    with game_storage_scope(game), factory.begin() as session:
        response = _service(session, root, provider_sha).prepare(game, command, ACTOR)
    state = response["cohort"]
    cohort = UUID(state["id"])
    stage("prepared " + str(cohort))
    for kind, cursor_key in (
        ("prepare-page", "nextCaptureCursor"),
        ("materialize-page", "nextMaterializationCursor"),
    ):
        for _ in range(30):
            if state[cursor_key] is None:
                break
            with game_storage_scope(game), factory.begin() as session:
                response = _service(session, root, provider_sha).command(
                    game,
                    cohort,
                    kind,
                    {
                        "idempotencyKey": str(uuid4()),
                        "expectedRevision": state["revision"],
                        "cursor": state[cursor_key],
                    },
                    ACTOR,
                )
            state = response["cohort"]
        else:
            pytest.fail("Cohort exceeded its bounded page count")
        stage(kind + " complete")
    assert state["status"] == "ready_to_freeze", state
    with game_storage_scope(game), factory.begin() as session:
        _service(session, root, provider_sha).command(
            game, cohort, "freeze", _freeze_body(state), ACTOR
        )
    with game_storage_scope(game), factory() as session:
        SqlAlchemyGridTrainingCohortRepository(session, root).bind(game)
        row = session.get(GridTrainingCohortModel, (game, cohort))
        assert row is not None and row.status == "frozen"
        snapshot = GridCohortSnapshot(root, row.manifest_path, row.manifest_sha256)
    stage("frozen " + str(cohort))
    return cohort, snapshot


def _canonical_rows(db, game, sources):
    """xmin also detects an UPDATE that silently writes the same geometry back."""
    with db.owner_engine.connect() as connection:
        return {
            table: list(
                connection.execute(
                    text(
                        f"SELECT id::text, xmin::text, to_jsonb(t)::text "
                        f"FROM game_data_v2.{table} t WHERE game_id=:g "
                        "AND source_image_id=ANY(:sources) ORDER BY id"
                    ),
                    {"g": game, "sources": sources},
                )
            )
            for table in ("recognized_boards", "image_source_geometry_revisions")
        }


def _write_manual(factory, root, game, source_id, expected, slots=9):
    with game_storage_scope(game), factory.begin() as session:
        repo = SqlAlchemyGridCellContentRepository(session, root)
        repo.bind(game, write=True)
        source = repo.current_source(game, source_id)
        for position in range(slots):
            repo.write(
                game,
                ContentWriteCommand(
                    idempotencyKey=uuid4(),
                    sourceId=source_id,
                    expectedSourceSha256=source.sourceSha256,
                    expectedPixelSha256=source.sourceRepresentativeSha256,
                    positionIndex=position,
                    sequenceNumber=expected[f"{source_id}:{position}"]["sequenceNumber"],
                    expectedRevision=0,
                    cells=_cells(position),
                    humanApproval=True,
                ),
                ACTOR,
            )


def test_blind_a_geometry_survives_real_prepare_freeze_and_worker_without_canonical_update(
    tmp_path,
):
    started = time.monotonic()

    def stage(message):
        print(f"T1165 content pipeline +{time.monotonic() - started:.2f}s: {message}", flush=True)

    with _owned_pooled_database() as db:
        stage("owned database migrated")
        # Record only owned identifiers for cleanup if an external timeout kills pytest.
        receipt = Path("artifacts/TASK-1165-content-pipeline-owned.json")
        receipt.parent.mkdir(exist_ok=True)
        receipt.write_text(
            json.dumps({"database": db.owner_url.database, "role": db.role}), encoding="utf-8"
        )
        game = next(iter(db.games.values()))
        base, family = _install_base(db, game)
        providers = _providers(db, tmp_path, base)
        factory = create_session_factory(db.app_engine)
        with Session(db.owner_engine) as session, session.begin():
            session.add(
                SymbolModel(
                    game_id=game,
                    code="FIXTURE",
                    name="Fixture",
                    mobile_code=1,
                    display_order=1,
                    status="active",
                )
            )
        expected, sources, imports = {}, [], []
        for ordinal in range(1, 22):
            slots = 9 if 11 <= ordinal <= 15 else 3
            source, _, import_id = _save_source(db, tmp_path, game, ordinal, slots, expected)
            sources.append(source)
            imports.append(str(import_id))
            if ordinal % 5 == 0:
                stage(f"guarded human source {ordinal}/21")
        command = {
            "idempotencyKey": str(uuid4()),
            "mode": "grid-only",
            "familyId": str(family),
            "baseVersionId": str(base),
            "selector": {"importJobIds": list(imports)},
            "recordings": [],
            "policyVersion": "application-grid-corrections-v4",
            "validationAssignments": {
                **{str(source): "A" for source in sources[10:15]},
                str(sources[-1]): "B",
            },
        }
        legacy_id, legacy = _freeze(factory, tmp_path, game, command, providers.index_sha256, stage)
        original_sources = list(legacy.sources())
        legacy_serialization = json.dumps(original_sources, sort_keys=True)
        canonical = _canonical_rows(db, game, sources)
        a_sources = [source for source, _ in GridBoardDataset(legacy, "VALIDATION").indexed()]
        train_sources = [source for source, _ in GridBoardDataset(legacy, "TRAIN").indexed()]
        assert len(a_sources) >= 5 and len(train_sources) >= 10
        assert {
            source["sourceId"]
            for source in original_sources
            if source.get("validationPurpose") == "B"
        } == {str(sources[-1])}
        chosen = a_sources + train_sources[:5]
        selections = [
            ContentSessionTargetSelection(
                sourceId=UUID(source["sourceId"]),
                positionIndices=list(range(9 if source in a_sources else 3)),
            )
            for source in chosen
        ]
        with game_storage_scope(game), factory.begin() as session:
            made = SqlAlchemyGridCellContentRepository(session, tmp_path).create_session(
                game,
                ContentSessionCreate(
                    idempotencyKey=uuid4(),
                    cohortId=legacy_id,
                    expectedManifestSha256=legacy.manifest_sha256,
                    sourceIds=[selection.sourceId for selection in selections],
                    targetSelection=selections,
                ),
                ACTOR,
            )
        measurement = made["session"]
        measurement_id = UUID(measurement["sessionId"])
        assert measurement["total"] >= 60
        stage("blind session created")
        for pass_number, shift in ((1, 0.5), (2, 0.75)):
            for selection in selections:
                with game_storage_scope(game), factory.begin() as session:
                    repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                    for position in selection.positionIndices:
                        written = repo.blind_write(
                            game,
                            measurement_id,
                            ContentBlindWrite(
                                idempotencyKey=uuid4(),
                                expectedSessionRevision=measurement["revision"],
                                passNumber=pass_number,
                                sourceId=selection.sourceId,
                                positionIndex=position,
                                cells=_cells(position, shift),
                                measuredNodes=_measured_nodes(position, shift),
                                humanApproval=True,
                            ),
                            ACTOR,
                        )
                        measurement = written["session"]
            if pass_number == 1:
                with game_storage_scope(game), factory.begin() as session:
                    SqlAlchemyGridCellContentRepository(session, tmp_path).bind(game, write=True)
                    with (
                        pytest.raises(DBAPIError, match="CONTENT_IMMUTABLE_HISTORY"),
                        session.begin_nested(),
                    ):
                        session.execute(
                            text(
                                "UPDATE grid_cell_content_sessions SET progress="
                                "jsonb_set(progress, ARRAY['pass1', "
                                "(SELECT jsonb_object_keys(progress->'pass1') LIMIT 1)], "
                                "jsonb_build_array(progress->'pass1'->"
                                "(SELECT jsonb_object_keys(progress->'pass1') LIMIT 1))), "
                                "revision=revision+1 WHERE game_id=:game AND id=:id"
                            ),
                            {"game": game, "id": measurement_id},
                        )
            with game_storage_scope(game), factory.begin() as session:
                advanced = SqlAlchemyGridCellContentRepository(session, tmp_path).advance(
                    game,
                    measurement_id,
                    ContentSessionAdvance(
                        idempotencyKey=uuid4(), expectedSessionRevision=measurement["revision"]
                    ),
                    ACTOR,
                )
            measurement = advanced["session"]
            stage(f"blind pass {pass_number} completed")
        assert measurement["phase"] == "frozen"
        assert measurement["report"]["qualificationState"] == "ready", measurement["report"]
        assert measurement["report"]["oracle"]["blockedBoards"] == 0

        fresh = []
        for ordinal in range(22, 27):
            source, _, import_id = _save_source(db, tmp_path, game, ordinal, 9, expected)
            fresh.append(source)
            imports.append(str(import_id))
            _write_manual(factory, tmp_path, game, source, expected)
        _write_manual(factory, tmp_path, game, sources[-1], expected, slots=3)
        stage("five fresh fully labelled REG candidates and B labels ready")
        new_command = {
            **command,
            "idempotencyKey": str(uuid4()),
            "selector": {"importJobIds": imports},
            "contentSamplingPolicy": CONTENT_POLICY,
        }
        _, current = _freeze(factory, tmp_path, game, new_command, providers.index_sha256, stage)
        selection = current.manifest["photoSplit"]["contentSampling"]
        assert selection["state"] == "ready" and selection["fullPhotos"] == 5
        assert selection["seed"] == 20261108
        assert set(selection["sourceIds"]) == {str(source) for source in fresh}
        assert selection["ancestrySha256"] and selection["recordingIndependence"] == "not_claimed"
        pins = {pin["sourceId"]: pin for pin in current.manifest["photoSplit"]["sources"]}
        current_sources = list(current.sources())
        for source in current_sources:
            if source["used"]:
                assert pins[source["sourceId"]]["qualifiedLabelsSha256"] == digest(
                    source["targets"]
                )
        indexed = GridBoardDataset(current, "VALIDATION").indexed()
        assert {source["sourceId"] for source, _ in indexed} == {
            source["sourceId"] for source in a_sources
        }
        legacy_by_id = {source["sourceId"]: source for source in original_sources}
        for source, targets in indexed:
            current.frame(source, "VALIDATION")  # Byte/pixel identity is verified on real files.
            old = {
                target["positionIndex"]: target
                for target in legacy_by_id[source["sourceId"]]["targets"]
            }
            for target, (worker_nodes, _) in zip(source["targets"], targets, strict=True):
                position = target["positionIndex"]
                expected_nodes, expected_quads = exact_lattice(
                    {
                        "latticeNodes": [
                            {"x": x, "y": y} for x, y in _measured_nodes(position, 0.75)
                        ]
                    },
                    620,
                    420,
                )
                assert target["nodes"] == expected_nodes != old[position]["nodes"]
                assert target["render"]["cellQuads"] == expected_quads
                assert target["canonicalRender"] == old[position]["render"]
                assert target["canonicalApproval"] == old[position]["approval"]
                assert target["blindGeometry"]["nodesSha256"] == digest(expected_nodes)
                assert target["blindGeometry"]["passNumber"] == 2
                assert target["blindGeometry"]["sessionId"] == str(measurement_id)
                np.testing.assert_array_equal(
                    worker_nodes, np.asarray(_measured_nodes(position, 0.75), np.float32)
                )
                reference = frozen_content_reference(game, source, target)
                assert reference is not None and reference.revision == 2
                assert reference.cells == _cells(position, 0.75)
        b_rows = GridAssessmentDataset(current, "VALIDATION").indexed()
        assert len(b_rows) == 1
        for source, _ in b_rows:
            assert source["sourceId"] == str(sources[-1])
            for target in source["targets"]:
                assert "contentAnnotation" in target and "blindGeometry" not in target
                assert (
                    target["nodes"]
                    == legacy_by_id[source["sourceId"]]["targets"][target["positionIndex"]]["nodes"]
                )
        regression_rows = GridAssessmentDataset(current, "REGRESSION").indexed()
        assert {source["sourceId"] for source, _ in regression_rows} == {
            str(source) for source in fresh
        }
        old_regression = {
            source["sourceId"] for source in original_sources if source["role"] == "REGRESSION"
        }
        assert len(old_regression) == 5
        assert all(
            pins[source_id]["contentExcluded"] and pins[source_id]["eligibleBoards"] == 0
            for source_id in old_regression
        )
        assert all(
            not source["used"] for source in current_sources if source["sourceId"] in old_regression
        )
        legacy_mapping = split_mapping(legacy.manifest["photoSplit"])
        with game_storage_scope(game), factory() as session:
            SqlAlchemyGridTrainingCohortRepository(session, tmp_path).bind(game)
            reader = GridCohortEvidenceReader(session, tmp_path)
            for source in a_sources:
                captured = reader.capture(
                    game,
                    UUID(source["sourceId"]),
                    source["ordinal"],
                    legacy_mapping[source["sourceId"]],
                    "grid-only",
                )
                labels = [
                    position["label"]
                    for position in captured["positions"]
                    if position["label"] is not None
                ]
                assert labels == source["targets"]
                assert all(
                    "contentAnnotation" not in target and "blindGeometry" not in target
                    for target in labels
                )
        assert json.dumps(list(legacy.sources()), sort_keys=True) == legacy_serialization
        assert _canonical_rows(db, game, sources) == canonical
        stage("actual worker blind A/B, label hashes and legacy canonical rows verified")
    stage("owned database and role cleaned")
