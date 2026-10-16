"""Own two-source retention boundary through real cleanup and game lifecycle."""

import hashlib
import json
import os
import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.cleanup import CleanupService, ManagedCleanupArtifactStore
from game_predictor_api.application.storage_gc import StorageGcArtifactStore
from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometryService,
    VirtualGridGeometrySourceCommand,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.cleanup import BoardSourceCleanupSelection, CleanupCommand
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes, SourcePoint
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.storage_retention import (
    StorageRetentionPolicy,
    evaluate_storage_retention,
)
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.database import create_cross_game_owner_session_factory
from game_predictor_api.storage.game_data_v2_manifest_v16 import ADDED_GAME_TABLES, GAME_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
    partition_name,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    game_storage_scope,
)
from game_predictor_api.storage.grid_cohort_asset_retention import acquire_cohort_asset_guard
from game_predictor_api.storage.grid_geometry_approvals import (
    SqlAlchemyGridGeometryApprovalRepository,
)
from game_predictor_api.storage.grid_quality_measurements import (
    SqlAlchemyGridQualityMeasurementRepository,
)
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortMemberModel,
    GridTrainingCohortModel,
    GridTrainingCohortPageModel,
)
from game_predictor_api.storage.models import SourceImageModel, SymbolModel
from game_predictor_api.storage.storage_gc_repository import SqlAlchemyStorageGcRepository
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from game_predictor_worker.filesystem import long_path_aware
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from test_grid_quality_measurements_postgres import seed as seed_canonical_source
from test_source_recording_groups_postgres import seed_source
from test_virtual_deferred_resolution_postgres import _factory

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Exact-owned disposable PostgreSQL opt-in required",
)


@pytest.fixture(autouse=True)
def owned_long_path_cleanup(tmp_path):
    identity = tmp_path.stat().st_dev, tmp_path.stat().st_ino
    marker = str(uuid4())
    (tmp_path / "fixture-owner").write_text(marker, encoding="utf-8")
    yield
    assert identity == (tmp_path.stat().st_dev, tmp_path.stat().st_ino)
    assert (tmp_path / "fixture-owner").read_text(encoding="utf-8") == marker
    target = long_path_aware(tmp_path)
    assert all(not p.is_symlink() and not p.is_junction() for p in (target, *target.rglob("*")))
    shutil.rmtree(target)


def _assert_owned_database_removed(evidence):
    journals = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (evidence / "resources").glob("*.json")
    ]
    results = []
    if journals:
        engine = create_engine(
            make_url(ApiSettings.from_environment().owner_database_url).set(database="postgres"),
            poolclass=NullPool,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
        )
        try:
            with engine.connect() as connection:
                for journal in journals:
                    name = journal["databaseName"]
                    assert journal["databaseCreatedHere"] and name.startswith(
                        "game_predictor_t0995gcr_"
                    )
                    roles = [
                        journal[key]["name"]
                        for key in ("capabilityRole", "runtimeRole")
                        if journal.get(key) and journal[key]["createdHere"]
                    ]
                    results.append(
                        {
                            "database": name,
                            "databaseOid": journal["databaseOid"],
                            "remainingDb": connection.scalar(
                                text("SELECT count(*) FROM pg_database WHERE datname=:name"),
                                {"name": name},
                            ),
                            "remainingRoles": connection.scalar(
                                text("SELECT count(*) FROM pg_roles WHERE rolname=ANY(:roles)"),
                                {"roles": roles},
                            ),
                            "pids": list(
                                connection.scalars(
                                    text("SELECT pid FROM pg_stat_activity WHERE datname=:name"),
                                    {"name": name},
                                )
                            ),
                        }
                    )
        finally:
            engine.dispose()
    (evidence / "cleanup.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for result in results:
        assert result["remainingDb"] == result["remainingRoles"] == 0 and not result["pids"]


def test_real_source_and_layout_cleanup_retain_refs_until_completed_game_deletion(
    tmp_path, monkeypatch
):
    evidence = Path(os.environ["GAME_PREDICTOR_GC_RETENTION_EVIDENCE_ROOT"]).resolve()
    assert evidence.is_relative_to(Path(__file__).resolve().parents[4] / "artifacts/audits")
    evidence.mkdir(parents=True, exist_ok=False)
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))
    started, stages = time.monotonic(), []

    def stage(value):
        assert time.monotonic() - started < 90, "Reserve own cleanup within the 120s hard limit"
        stages.append(value)
        (evidence / "progress.json").write_text(json.dumps(stages), encoding="utf-8")
        print("0995 GC retention " + value, flush=True)

    try:
        stage("starting_owned_fixture")
        with application_role_database("t0995gcr", ()) as db:
            stage("fixture_ready")
            game, _, canonical_source, root = seed_canonical_source(
                SimpleNamespace(engine=db.owner_engine, role=db.role), tmp_path
            )
            cohort, imports = uuid4(), tmp_path / "i"
            imports.mkdir()
            runtime = _factory(db.app_engine)
            with game_storage_scope(game), runtime() as session:
                measured = SqlAlchemyGridQualityMeasurementRepository(session, root).capture(
                    game,
                    {
                        "idempotencyKey": str(uuid4()),
                        "seed": "retention-canonical",
                        "sampleSize": 1,
                        "hardSourceIds": [str(canonical_source.source_image_id)],
                    },
                    "fixture-human:0995-approval",
                )["current"]
                session.commit()
            measured_member = next(
                member for member in measured["members"] if member["sampleKind"] == "random"
            )
            target = measured_member["positions"][0]
            assert target["approvalEligible"] and target["current"]["available"]
            approval_command = {
                "idempotencyKey": str(uuid4()),
                "measurementId": measured["measurementId"],
                "sourceId": str(canonical_source.source_image_id),
                "sampleKind": "random",
                "positionIndex": 0,
                "manifestSha256": measured["manifestSha256"],
                "targetSha256": target["targetSha256"],
            }
            with game_storage_scope(game), runtime() as session:
                approved = SqlAlchemyGridGeometryApprovalRepository(session, root).approve(
                    game,
                    canonical_source.import_job_id,
                    UUID(target["reviewItemId"]),
                    approval_command,
                    "fixture-human:0995-approval",
                )["receipt"]
                assert approved["kind"] == "approved_unchanged"
                session.commit()
            stage("actual_canonical_measurement_and_approval_committed")
            manual_source = seed_source(
                _factory(db.owner_engine),
                game,
                root,
                label="retention-manual-source",
                slot_count=1,
                sequence_base=200,
            )
            nodes = tuple(
                SourcePoint(
                    60 + column * 80 + (0.375 if row in (1, 2) and column in (2, 3) else 0),
                    50 + row * 90,
                )
                for row in range(4)
                for column in range(6)
            )
            with game_storage_scope(game), runtime() as session:
                for index, code in enumerate(("CYTRYNA", "WISNIA"), 1):
                    session.add(
                        SymbolModel(
                            game_id=game,
                            code=code,
                            name=code,
                            mobile_code=index,
                            display_order=index,
                            status="active",
                        )
                    )
                session.flush()
                source = session.get(SourceImageModel, manual_source.source_image_id)
                assert source is not None
                manual = VirtualGridGeometryService(
                    SqlAlchemyVirtualGridGeometryRepository(session), root
                ).save_source(
                    game_id=game,
                    import_job_id=manual_source.import_job_id,
                    commands=(
                        VirtualGridGeometrySourceCommand(
                            review_item_id=None,
                            pending_geometry_id=manual_source.pending_ids[0],
                            expected_geometry_revision=0,
                            expected_resolution_revision=0,
                            expected_source_checksum_sha256=source.checksum_sha256,
                            expected_source_width=source.oriented_width,
                            expected_source_height=source.oriented_height,
                            expected_grid_rows=3,
                            expected_grid_columns=5,
                            corners=tuple(
                                ImageReviewGeometryPoint(
                                    round(nodes[index].x), round(nodes[index].y)
                                )
                                for index in (0, 5, 23, 18)
                            ),
                            geometry_qualification=GeometryQualification(),
                            lattice_nodes=SourceLatticeNodes(nodes),
                        ),
                    ),
                    idempotency_key=uuid4(),
                    actor="fixture-human:0995-manual",
                    created_at=datetime.now(UTC),
                )
                assert manual.created and len(manual.revisions) == 1
                session.commit()
            sources = [canonical_source, manual_source]
            frozen = []
            with game_storage_scope(game), runtime() as session:
                GameStorageRouter().bind(session, game, intent=GameStorageIntent.READ)
                reader = GridCohortEvidenceReader(session, root)
                for ordinal, seed in enumerate(sources):
                    captured = reader.capture(
                        game,
                        seed.source_image_id,
                        ordinal,
                        {
                            "qualification": "unresolved",
                            "role": None,
                            "reasonCodes": ["RECORDING_MEMBERSHIP_REQUIRED"],
                        },
                        "grid-only",
                    )
                    assert not captured["used"] and captured["role"] is None
                    assert captured["qualification"] == "unresolved"
                    frozen.append(captured)
                checked = frozen[0]["positions"][0]["label"]["approval"]
                corrected = frozen[1]["positions"][0]["label"]["approval"]
                assert checked["origin"] == "human_checked_unchanged" and checked["weight"] == 1
                assert (
                    checked["basis"] == "canonical_approval_receipt"
                    and checked["manualRevisionId"] is None
                )
                assert checked["eventId"] == approved["eventId"]
                assert (
                    reader.cached_manifest is not None
                    and reader.cached_manifest[0] == measured["manifestSha256"]
                )
                assert corrected["origin"] == "human_corrected" and corrected["weight"] == 4
                assert corrected["basis"] == "guarded_manual_save" and corrected["manualRevisionId"]
                assert frozen[1]["positions"][0]["label"]["nodes"] == [
                    {"x": point.x, "y": point.y} for point in nodes
                ]
            stage("actual_0995_canonical_receipt_and_manual_proofs_captured")
            store = GridCohortArtifactStore(root)
            with Session(db.app_engine) as session:
                acquire_cohort_asset_guard(session, game, cohort)
                GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
                session.add(
                    GridTrainingCohortModel(
                        game_id=game,
                        id=cohort,
                        revision=1,
                        status="preparing",
                        document={"fixture": "retention-actual-writers-no-training-admission"},
                        summary={},
                        created_by="fixture:0995-gc-retention",
                        created_at=datetime.now(UTC),
                    )
                )
                session.flush()
                pins = []
                for ordinal, seed in enumerate(sources):
                    source = session.get(SourceImageModel, seed.source_image_id)
                    assert source is not None
                    pins.append(
                        store.copy_source(
                            game,
                            cohort,
                            {
                                column.name: getattr(source, column.name)
                                for column in source.__table__.columns
                            },
                        )
                    )
                    session.add(
                        GridTrainingCohortMemberModel(
                            game_id=game,
                            cohort_id=cohort,
                            source_id=source.id,
                            live_source_image_id=source.id,
                            ordinal=ordinal,
                            role=None,
                            frozen=frozen[ordinal],
                        )
                    )
                page = store.publish_json(game, cohort, {"sources": frozen})
                document = {"assets": [*pins, page]}
                session.add(
                    GridTrainingCohortPageModel(
                        game_id=game,
                        cohort_id=cohort,
                        kind="capture",
                        page_index=0,
                        path=page["path"],
                        sha256=page["sha256"],
                        document=document,
                    )
                )
                session.flush()
                session.execute(
                    text(
                        "UPDATE game_data_v2.grid_training_cohorts SET status='canceled',"
                        "revision=revision+1 WHERE game_id=:game AND id=:cohort"
                    ),
                    {"game": game, "cohort": cohort},
                )
                session.commit()
            all_pins = [*pins, page]
            original_sha = {
                pin["path"]: hashlib.sha256(store.safe(pin["path"]).read_bytes()).hexdigest()
                for pin in all_pins
            }
            gc = SqlAlchemyStorageGcRepository(sessionmaker(db.app_engine))
            scanner = StorageGcArtifactStore(root, imports)
            cross_reader = create_cross_game_owner_session_factory(db.owner_engine)

            def retained(expected_links):
                with game_storage_scope(game), runtime() as session:
                    members = list(
                        session.scalars(
                            select(GridTrainingCohortMemberModel).order_by(
                                GridTrainingCohortMemberModel.ordinal
                            )
                        )
                    )
                    assert [member.live_source_image_id for member in members] == expected_links
                    assert [member.frozen for member in members] == frozen
                    saved = session.get(GridTrainingCohortPageModel, (game, cohort, "capture", 0))
                    assert (
                        saved is not None
                        and saved.document == document
                        and saved.sha256 == page["sha256"]
                    )
                for pin in all_pins:
                    assert (
                        hashlib.sha256(store.safe(pin["path"]).read_bytes()).hexdigest()
                        == original_sha[pin["path"]]
                    )
                    with gc.cohort_asset_gc_guard(pin["path"]) as state:
                        assert state.referenced and not state.unresolved
                        observation = scanner.cohort_asset_observation(pin["path"], state)
                        assert observation is not None
                        assert not evaluate_storage_retention(
                            observation,
                            policy=StorageRetentionPolicy(),
                            now=datetime.now(UTC) + timedelta(days=2),
                        ).eligible

            retained([seed.source_image_id for seed in sources])
            stage("canceled_page_and_two_originals_retained")
            with game_storage_scope(game), runtime() as session:
                service = CleanupService(
                    SqlAlchemyCleanupRepository(session, cross_reader),
                    ManagedCleanupArtifactStore(root),
                )
                selection = BoardSourceCleanupSelection((100, 101))
                preview = service.preview_board_sources(game, selection)
                assert not preview.snapshot.blockers
                assert not set(preview.snapshot.artifact_paths).intersection(original_sha)
                service.delete_board_sources(
                    game,
                    selection,
                    CleanupCommand(
                        preview.preview_token, preview.snapshot.confirmation_target, True
                    ),
                )
                session.commit()
                service.finalize_committed_artifacts()
            retained([None, sources[1].source_image_id])
            with game_storage_scope(game), runtime() as session:
                assert session.get(SourceImageModel, sources[0].source_image_id) is None
                assert session.get(SourceImageModel, sources[1].source_image_id) is not None
            stage("actual_source_cleanup_detached_only_first_link")
            with game_storage_scope(game), runtime() as session:
                service = CleanupService(
                    SqlAlchemyCleanupRepository(session, cross_reader),
                    ManagedCleanupArtifactStore(root),
                )
                preview = service.preview_game_reset(game)
                assert not preview.snapshot.blockers
                assert not set(preview.snapshot.artifact_paths).intersection(original_sha)
                service.reset_game(
                    game,
                    CleanupCommand(
                        preview.preview_token, preview.snapshot.confirmation_target, True
                    ),
                )
                session.commit()
            retained([None, None])
            with game_storage_scope(game), runtime() as session:
                assert all(
                    session.get(SourceImageModel, seed.source_image_id) is None for seed in sources
                )
            stage("actual_layout_reset_detached_second_link_and_preserved_page")
            # No game runtime/GC transaction may survive into owner partition DDL.
            with Session(db.owner_engine) as session, session.begin():
                operation = (
                    GamePartitionLifecycleRepository(session)
                    .start_or_resume(game_id=game, kind=GamePartitionLifecycleKind.DELETE)
                    .operation_id
                )
            for index in range(len(GAME_TABLES) + 2):
                with Session(db.owner_engine) as session, session.begin():
                    receipt = GamePartitionLifecycleRepository(session).run_next(operation)
                if index % 20 == 0:
                    stage("deletion_checkpoint_" + str(receipt.next_table_index))
                if receipt.status == "done":
                    break
            assert receipt.status == "done"
            with Session(db.owner_engine) as session:
                actual = (
                    session.execute(
                        text(
                            "SELECT status,manifest_version,next_table_index,completed_tables,"
                            "updated_at FROM public.game_storage_lifecycle_operations WHERE id=:id"
                        ),
                        {"id": operation},
                    )
                    .mappings()
                    .one()
                )
                assert (
                    actual["status"] == "done"
                    and actual["manifest_version"] == "game-data-v2-manifest-v16"
                )
                assert actual["next_table_index"] == len(GAME_TABLES)
                assert set(actual["completed_tables"]) == set(GAME_TABLES)
                assert len(actual["completed_tables"]) == len(GAME_TABLES)
                for table, column in (("games", "id"), ("game_storage_locations", "game_id")):
                    assert not session.scalar(
                        text(f"SELECT EXISTS(SELECT 1 FROM public.{table} WHERE {column}=:game)"),
                        {"game": game},
                    )
                for table in ADDED_GAME_TABLES:
                    assert (
                        session.scalar(
                            text("SELECT to_regclass(:name)"),
                            {"name": "game_data_v2." + partition_name(game, table)},
                        )
                        is None
                    )
            for pin in all_pins:
                assert (
                    hashlib.sha256(store.safe(pin["path"]).read_bytes()).hexdigest()
                    == original_sha[pin["path"]]
                )
                with gc.cohort_asset_gc_guard(pin["path"]) as state:
                    assert not state.referenced and not state.unresolved
                    assert state.latest_dependency_at == actual["updated_at"]
                    observation = scanner.cohort_asset_observation(pin["path"], state)
                    assert observation is not None
                    assert not evaluate_storage_retention(
                        observation, policy=StorageRetentionPolicy(), now=datetime.now(UTC)
                    ).eligible
                    assert evaluate_storage_retention(
                        observation,
                        policy=StorageRetentionPolicy(),
                        now=actual["updated_at"] + timedelta(hours=25),
                    ).eligible
            stage("real_done_receipt_absence_and_fresh_runtime_no_refs")
            (evidence / "proof.json").write_text(
                json.dumps(
                    {
                        "stages": stages,
                        "gameId": str(game),
                        "cohortId": str(cohort),
                        "deletionOperationId": str(operation),
                        "deletionUpdatedAt": actual["updated_at"].isoformat(),
                        "cohortAssets": original_sha,
                        "physicalFilesIntact": True,
                        "labelOrigins": [checked, corrected],
                        "canonicalApprovalMeasurementSha256": measured["manifestSha256"],
                        "actualMeasurementManifestVerifiedBy0995Reader": True,
                        "trainingAdmission": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        stage("fixture_cleanup_complete")
    finally:
        _assert_owned_database_removed(evidence)


def test_completed_game_deletion_releases_actual_canceled_cohort_references(tmp_path, monkeypatch):
    evidence = Path(os.environ["GAME_PREDICTOR_GC_RETENTION_EVIDENCE_ROOT"]).resolve()
    assert evidence.is_relative_to(Path(__file__).resolve().parents[4] / "artifacts/audits")
    evidence.mkdir(parents=True, exist_ok=False)
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))
    started, stages = time.monotonic(), []

    def stage(value):
        assert time.monotonic() - started < 90, "Reserve own cleanup within the 120s hard limit"
        stages.append(value)
        (evidence / "progress.json").write_text(json.dumps(stages), encoding="utf-8")
        print("0995 GC full delete " + value, flush=True)

    try:
        stage("starting_owned_fixture")
        with application_role_database("t0995gcr", ("cohort-delete",)) as db:
            stage("fixture_ready")
            game, cohort = db.games["cohort-delete"], uuid4()
            root, imports = tmp_path / "a", tmp_path / "i"
            root.mkdir()
            imports.mkdir()
            sources = [
                seed_source(
                    _factory(db.owner_engine),
                    game,
                    root,
                    label="delete-source" + "x" * (ordinal + 1),
                    slot_count=1,
                    sequence_base=100 + 100 * ordinal,
                )
                for ordinal in range(2)
            ]
            store = GridCohortArtifactStore(root)
            with Session(db.app_engine) as session:
                acquire_cohort_asset_guard(session, game, cohort)
                GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
                session.add(
                    GridTrainingCohortModel(
                        game_id=game,
                        id=cohort,
                        revision=1,
                        status="preparing",
                        document={"fixture": "full-delete-no-training-labels"},
                        summary={},
                        created_by="fixture:0995-gc-delete",
                        created_at=datetime.now(UTC),
                    )
                )
                session.flush()
                pins = []
                for ordinal, seed in enumerate(sources):
                    source = session.get(SourceImageModel, seed.source_image_id)
                    assert source is not None
                    pins.append(
                        store.copy_source(
                            game,
                            cohort,
                            {
                                column.name: getattr(source, column.name)
                                for column in source.__table__.columns
                            },
                        )
                    )
                    session.add(
                        GridTrainingCohortMemberModel(
                            game_id=game,
                            cohort_id=cohort,
                            source_id=source.id,
                            live_source_image_id=source.id,
                            ordinal=ordinal,
                            role=None,
                            frozen={"sourceId": str(source.id), "used": False},
                        )
                    )
                page = store.publish_json(
                    game,
                    cohort,
                    {
                        "sources": [
                            {"sourceId": str(seed.source_image_id), "used": False}
                            for seed in sources
                        ]
                    },
                )
                session.add(
                    GridTrainingCohortPageModel(
                        game_id=game,
                        cohort_id=cohort,
                        kind="capture",
                        page_index=0,
                        path=page["path"],
                        sha256=page["sha256"],
                        document={"assets": [*pins, page]},
                    )
                )
                session.flush()
                session.execute(
                    text(
                        "UPDATE game_data_v2.grid_training_cohorts "
                        "SET status='canceled',revision=revision+1 "
                        "WHERE game_id=:game AND id=:cohort"
                    ),
                    {"game": game, "cohort": cohort},
                )
                session.commit()
            all_pins = [*pins, page]
            assert len({pin["path"] for pin in all_pins}) == 3
            original_sha = {
                pin["path"]: hashlib.sha256(store.safe(pin["path"]).read_bytes()).hexdigest()
                for pin in all_pins
            }
            gc = SqlAlchemyStorageGcRepository(sessionmaker(db.app_engine))
            scanner = StorageGcArtifactStore(root, imports)
            for pin in all_pins:
                with gc.cohort_asset_gc_guard(pin["path"]) as state:
                    assert state.referenced and not state.unresolved
            stage("actual_canceled_page_and_two_originals_referenced")
            with Session(db.owner_engine) as session, session.begin():
                operation = (
                    GamePartitionLifecycleRepository(session)
                    .start_or_resume(game_id=game, kind=GamePartitionLifecycleKind.DELETE)
                    .operation_id
                )
            for index in range(len(GAME_TABLES) + 2):
                with Session(db.owner_engine) as session, session.begin():
                    receipt = GamePartitionLifecycleRepository(session).run_next(operation)
                if index % 20 == 0:
                    stage("deletion_checkpoint_" + str(receipt.next_table_index))
                if receipt.status == "done":
                    break
            assert receipt.status == "done"
            with Session(db.owner_engine) as session:
                actual = (
                    session.execute(
                        text(
                            "SELECT status,manifest_version,next_table_index,"
                            "completed_tables,updated_at "
                            "FROM public.game_storage_lifecycle_operations "
                            "WHERE id=:id"
                        ),
                        {"id": operation},
                    )
                    .mappings()
                    .one()
                )
                assert (
                    actual["status"] == "done"
                    and actual["manifest_version"] == "game-data-v2-manifest-v16"
                )
                assert actual["next_table_index"] == len(GAME_TABLES)
                assert len(actual["completed_tables"]) == len(GAME_TABLES)
                assert set(actual["completed_tables"]) == set(GAME_TABLES)
                for table, column in (("games", "id"), ("game_storage_locations", "game_id")):
                    assert not session.scalar(
                        text(f"SELECT EXISTS(SELECT 1 FROM public.{table} WHERE {column}=:game)"),
                        {"game": game},
                    )
                partitions = {
                    table: session.scalar(
                        text("SELECT to_regclass(:name)"),
                        {"name": "game_data_v2." + partition_name(game, table)},
                    )
                    for table in ADDED_GAME_TABLES
                }
                assert all(value is None for value in partitions.values()) and len(partitions) == 6
            for pin in all_pins:
                assert (
                    hashlib.sha256(store.safe(pin["path"]).read_bytes()).hexdigest()
                    == original_sha[pin["path"]]
                )
                with gc.cohort_asset_gc_guard(pin["path"]) as state:
                    assert not state.referenced and not state.unresolved
                    assert state.latest_dependency_at == actual["updated_at"]
                    observation = scanner.cohort_asset_observation(pin["path"], state)
                    assert observation is not None
                    assert not evaluate_storage_retention(
                        observation, policy=StorageRetentionPolicy(), now=datetime.now(UTC)
                    ).eligible
                    assert evaluate_storage_retention(
                        observation,
                        policy=StorageRetentionPolicy(),
                        now=actual["updated_at"] + timedelta(hours=25),
                    ).eligible
            stage("real_done_receipt_absence_and_fresh_runtime_no_refs")
            (evidence / "proof.json").write_text(
                json.dumps(
                    {
                        "stages": stages,
                        "gameId": str(game),
                        "cohortId": str(cohort),
                        "deletionOperationId": str(operation),
                        "deletionUpdatedAt": actual["updated_at"].isoformat(),
                        "completedTableCount": len(actual["completed_tables"]),
                        "absentCohortPartitions": partitions,
                        "cohortAssets": original_sha,
                        "physicalFilesIntact": True,
                        "trainingAdmission": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        stage("fixture_cleanup_complete")
    finally:
        _assert_owned_database_removed(evidence)
