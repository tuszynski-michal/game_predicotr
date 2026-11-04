"""New neural acceptance, cold replay and rollback on disposable PostgreSQL."""

import json
from contextlib import nullcontext, suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from itertools import count
from unittest.mock import patch
from uuid import uuid4

import pytest
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange, canonical_json_bytes
from game_predictor_api.domain.neural_crop_policy import NEURAL_AUTO_CROP_POLICY
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    build_neural_source_binding,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
)
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot
from game_predictor_api.domain.v3_engine_acceptance import (
    GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
    V3_ENGINE_ACCEPTANCE_ACTOR,
    V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY,
    V3_ENGINE_ACCEPTANCE_POLICY,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.v3_engine_acceptance_repository import finalize_v3_engine_acceptance
from game_predictor_worker.images import pipeline_store
from game_predictor_worker.images.board_cell_geometry_activation import (
    board_cell_processing_snapshot,
)
from game_predictor_worker.images.board_cell_geometry_contract import BoardCellTopology
from game_predictor_worker.images.orchestration import ImageBatchCandidate, ImageFileExecution
from game_predictor_worker.images.pipeline_contract import GeometryPipelineRolloutSnapshot
from game_predictor_worker.images.pipeline_execution import (
    ImageStageContext,
    StoredImageStageResult,
    validate_stage_payload,
)
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from game_predictor_worker.images.production_workflow import ProductionImageStageAdapterSuite
from sqlalchemy import select
from test_virtual_deferred_resolution_postgres import _factory, _provision_game, _seed
from test_virtual_deferred_resolution_postgres import database as _database_fixture
from test_virtual_deferred_resolution_postgres import pytestmark as pytestmark

_SEED_COUNTER = count(1)


@pytest.fixture(autouse=True)
def current_partition_budget():
    """This head-schema test needs the live manifest, not the helper's frozen v19 budget."""
    from game_predictor_api.storage import game_partition_lifecycle

    with patch(
        "test_virtual_deferred_resolution_postgres.CREATE_TABLES",
        game_partition_lifecycle.CREATE_TABLES,
    ):
        yield


@pytest.fixture(scope="module")
def database():
    # One schema migration per module; every case owns a fresh game partition.
    # Persist the exact target for safe cleanup if an external timeout kills pytest.
    generator = _database_fixture.__wrapped__()
    value = next(generator)
    from pathlib import Path

    from sqlalchemy.engine import make_url

    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/task1017-postgres-receipt.json").write_text(
        json.dumps({"database": make_url(value.url).database}), encoding="utf-8"
    )
    try:
        yield value
    finally:
        with suppress(StopIteration):
            next(generator)


def execution(
    database,
    tmp_path,
    *,
    legacy=False,
    missing=False,
    crop_policy=NEURAL_AUTO_CROP_POLICY,
    acceptance_policy=V3_ENGINE_ACCEPTANCE_POLICY,
    fit_reason=None,
    forged_game_evidence=False,
    evaluated_game=False,
    forged_ready=False,
    forged_manual=False,
    workflow_recheck=False,
    calibrated_report=None,
    slot_count=2,
):
    game = _provision_game(database.engine, "task1017-" + uuid4().hex[:8])
    factory = _factory(database.engine)
    root = tmp_path / "artifacts"
    # The existing source fixture derives pixels from label length; distinct
    # lengths also give distinct global file-execution identities per game.
    seed = _seed(
        factory,
        game,
        root,
        label="v3-acceptance" + "x" * next(_SEED_COUNTER),
        slot_count=slot_count,
    )
    now, token = datetime.now(UTC), uuid4()
    snapshot = NeuralGridSnapshot.for_game(
        500000,
        grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1).current,
    )
    evaluated_descriptor = None
    if evaluated_game:
        from test_grid_model_registry import candidate as candidate_descriptor

        evaluated_descriptor = candidate_descriptor(tmp_path)
        evaluated_descriptor["cohortId"] = str(uuid4())
        evaluated_descriptor["familyCode"] = "t1156_" + uuid4().hex[:12]
        snapshot = NeuralGridSnapshot.from_catalogue(
            game_id=str(game),
            game_configuration="neural_grid_v3",
            expected_layout_count=500000,
            descriptor=evaluated_descriptor,
        )
    with game_storage_scope(game), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        source = session.get(SourceImageModel, seed.source_image_id)
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game,
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        assert revision.game_id == game and revision.source_image_id == seed.source_image_id, (
            f"Fixture selected game/source {revision.game_id}/{revision.source_image_id}; "
            f"intended {game}/{seed.source_image_id}"
        )
        job.status = "processing"
        job.lease_token, job.lease_owner = token, "task1017"
        job.started_at, job.heartbeat_at, job.lease_expires_at = (
            now,
            now,
            now + timedelta(minutes=5),
        )
        operation_pin = None
        if acceptance_policy in (
            GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
            "v3-engine-acceptance-v4",
        ):
            from game_predictor_api.domain.neural_grid_operation_pin import (
                GAME_EVALUATION_REQUIRED,
                make_operation_pin,
            )

            qualification = {"state": "unqualified", "reasonCodes": [GAME_EVALUATION_REQUIRED]}
            if forged_game_evidence:
                qualification = {
                    "state": "qualified",
                    "reasonCodes": [],
                    "evaluationId": str(uuid4()),
                    "evaluationSha256": "a" * 64,
                    "publicationEvidenceSha256": "b" * 64,
                }
            operation_pin = make_operation_pin(
                snapshot=snapshot,
                game_id=str(game),
                rules_version_id=str(revision.topology_rules_version_id),
                rows=3,
                columns=5,
                qualification=qualification,
            )
            if evaluated_game:
                from game_predictor_api.storage.neural_grid_operation_qualification import (
                    prepare_operation_pin,
                )
                from test_grid_model_publication_and_activation import (
                    execute,
                    registry,
                    seed_report,
                )

                service = registry(session, tmp_path)
                service.register(uuid4(), evaluated_descriptor)
                report = (
                    calibrated_report(session, evaluated_descriptor, game, tmp_path)
                    if calibrated_report
                    else seed_report(session, evaluated_descriptor, [game])
                )
                execute(service, "publish", evaluated_descriptor["versionId"], evaluation=report)
                operation_pin = prepare_operation_pin(
                    session,
                    snapshot=snapshot,
                    game_id=game,
                    rules_version_id=revision.topology_rules_version_id,
                    rows=3,
                    columns=5,
                    artifact_root=tmp_path if calibrated_report else None,
                )
                assert operation_pin["qualification"]["state"] == "qualified"
                if not calibrated_report:
                    operation_pin = make_operation_pin(
                        snapshot=snapshot,
                        game_id=str(game),
                        rules_version_id=str(revision.topology_rules_version_id),
                        rows=3,
                        columns=5,
                        qualification=operation_pin["qualification"],
                    )
                else:
                    assert operation_pin["automaticQualification"]["state"] == "qualified"
        job.input_payload = {
            **job.input_payload,
            "neural_grid_execution_policy_version": crop_policy,
            "neural_grid_proposal": snapshot.to_payload(),
            **({} if legacy else {V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY: acceptance_policy}),
            **({"neural_grid_operation_pin": operation_pin} if operation_pin is not None else {}),
        }
        for pending in session.scalars(
            select(ImageBoardGeometryPendingModel).where(
                ImageBoardGeometryPendingModel.game_id == game,
                ImageBoardGeometryPendingModel.source_image_id == seed.source_image_id,
            )
        ):
            if not missing or pending.position_index == 0:
                pending.status = "superseded"
                pending.superseded_at = now
        width, height, rules = source.width, source.height, revision.topology_rules_version_id
        source_key, source_sha, relative = (
            source.file_execution_key,
            source.checksum_sha256,
            source.relative_path,
        )
        from game_predictor_api.storage.job_repository import job_from_record

        domain_job = job_from_record(job)
        model = SymbolModelJobSnapshot.from_payload(job.input_payload["symbol_model"])
        rollout = GeometryPipelineRolloutSnapshot.from_payload(
            job.input_payload["image_geometry_rollout"]
        )
    detections = []
    for position in range(1 if missing else slot_count):
        nodes = [
            {
                "x": float(20 + position % 3 * 200 + column * 34),
                "y": float(15 + position // 3 * 130 + row * 34),
            }
            if slot_count == 9
            else {"x": float(60 + column * 80), "y": float(25 + position * 190 + row * 50)}
            for row in range(4)
            for column in range(6)
        ]
        quads = lattice_cell_quads(nodes, width=width, height=height)
        detections.append(
            {
                "detectionId": str(position),
                "score": 0.9,
                "latticeNodes": nodes,
                "cellQuads": [quad.to_dict() for quad in quads],
                "cellVisibility": lattice_visibility(quads, width=width, height=height),
                "structurallyValid": True,
                "reasonCodes": ["NEURAL_GRID_GATE_UNCALIBRATED"],
            }
        )
    if fit_reason is not None:
        detections[0]["reasonCodes"].append(fit_reason)
    proposal = build_neural_source_proposal(
        game_id=str(game),
        source_selection_id=str(uuid4()),
        source_checksum_sha256=source_sha,
        source_width=width,
        source_height=height,
        original_range=AttestedSequenceRange(start=100, end=99 + slot_count),
        snapshot=snapshot,
        detections=detections,
    )
    binding = build_neural_source_binding(
        proposal,
        confirmed_range=AttestedSequenceRange(start=100, end=99 + slot_count),
        assignments=[{"positionIndex": i, "detectionId": str(i)} for i in range(len(detections))],
    )
    suite_options = dict(
        repository_root=tmp_path,
        manual_geometry_import=True,
        neural_execution_policy=crop_policy,
        engine_acceptance_policy=None if legacy else acceptance_policy,
        symbol_model=model,
        geometry_rollout=rollout,
        page_geometry_manifest={
            source_sha: {
                "status": "review_required",
                "neuralProposal": proposal,
                "neuralProposalBinding": binding,
            }
        },
        board_cell_processing=board_cell_processing_snapshot(
            cell_output_size=model.crop_output_size,
            topology=BoardCellTopology(rows=3, columns=5, rules_version_id=str(rules)),
        ),
    )
    if calibrated_report:
        from game_predictor_api.domain.full_board_calibration import AXES
        from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest

        evidence = {}
        for item in detections:
            body = {
                "version": "full-board-result-evidence-v1",
                "sourceSha256": source_sha,
                "modelManifestSha256": operation_pin["catalogueManifestSha256"],
                "operationPinSha256": operation_pin["pinSha256"],
                "profileSha256": operation_pin["automaticQualification"]["profile"]["sha256"],
                "detectionId": item["detectionId"],
                "nodesSha256": digest(item["latticeNodes"]),
                "features": {"values": dict.fromkeys(AXES, 0.5)},
            }
            evidence[item["detectionId"]] = {**body, "sha256": digest(body)}
        suite_options["page_geometry_manifest"][source_sha]["calibrationEvidence"] = evidence
    if workflow_recheck:
        from game_predictor_worker.images.production_workflow import ProductionImageImportWorkflow

        workflow = ProductionImageImportWorkflow.__new__(ProductionImageImportWorkflow)
        workflow._artifact_root = root
        workflow._session_factory = factory
        with game_storage_scope(game):
            suite = workflow._new_stage_adapters(domain_job, **suite_options)
        expected = () if evaluated_game else ("NEURAL_GRID_GAME_EVALUATION_REQUIRED",)
        assert suite._qualification_blockers == expected
    else:
        suite = ProductionImageStageAdapterSuite(
            root,
            operation_pin=operation_pin,
            # Only deliberate forged-worker fixtures bypass the workflow reader.
            qualification_blockers=() if forged_game_evidence or evaluated_game else None,
            **suite_options,
        )
    context = ImageStageContext(
        seed.import_job_id, source_key, source_sha, relative, "b" * 64, {}, (100, 99 + slot_count)
    )
    stages = {}
    from game_predictor_worker.images.neural_pending_geometry import neural_pending_payload

    def forged_pending(*args, **kwargs):
        result = neural_pending_payload(*args, **kwargs)
        structured = result["structuredGeometry"]
        structured.update(status="ready", rolloutMode="structured_default")
        if forged_manual:
            structured.update(engineKind="manual_v1", geometrySource="manual")
        structured.pop("resultChecksumSha256")
        structured["resultChecksumSha256"] = sha256(canonical_json_bytes(structured)).hexdigest()
        return result

    with (
        patch(
            "game_predictor_worker.images.neural_pending_geometry.neural_pending_payload",
            side_effect=forged_pending,
        )
        if forged_ready
        else nullcontext()
    ):
        for adapter in suite.adapters():
            if adapter.stage == "discovery":
                continue
            payload = adapter.execute(context)
            validate_stage_payload(adapter.stage, payload, context)
            stages[adapter.stage] = StoredImageStageResult(adapter.version, payload)
            context = replace(
                context, previous_results={name: item.payload for name, item in stages.items()}
            )
    candidate = ImageBatchCandidate(
        ImageFileExecution(source_key, source_sha, "b" * 64, {}, "processing", False),
        0,
        relative,
        seed.import_job_id,
        token,
        now,
    )
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_source_geometry(
            candidate, stage_results=stages
        )
    return game, factory, seed, candidate, stages


def snapshot_state(factory, game, seed):
    with game_storage_scope(game), factory() as session:
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game,
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        boards = session.scalars(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id == seed.source_image_id,
            )
        ).all()
        assert all(
            board.approved_geometry_revision is None and board.geometry_approved_by is None
            for board in boards
        )
        cells = session.scalars(
            select(ImageSymbolReviewCellModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .where(
                ImageSymbolReviewCellModel.game_id == game,
                RecognizedBoardModel.source_image_id == seed.source_image_id,
            )
            .order_by(ImageSymbolReviewCellModel.id)
        ).all()
        assert all(
            cell.game_id == game and cell.import_job_id == seed.import_job_id for cell in cells
        ), (
            f"Snapshot intended {game}/{seed.import_job_id}; selected "
            f"{sorted({(str(cell.game_id), str(cell.import_job_id)) for cell in cells})}"
        )
        return (
            revision.status,
            revision.created_by,
            revision.geometry_checksum_sha256,
            revision.board_geometries,
            revision.global_initialization,
            session.get(SourceImageModel, seed.source_image_id).geometry_completeness_status,
            [(cell.id, cell.revision, cell.crop_sample_id, cell.quality_issue) for cell in cells],
        )


@pytest.mark.parametrize("forged_game_evidence", [False, True])
def test_v3_new_game_keeps_source_and_api_rejects_unqualified_or_forged_worker(
    database,
    tmp_path,
    forged_game_evidence,
):
    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy=GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
        forged_game_evidence=forged_game_evidence,
    )
    before = snapshot_state(factory, game, seed)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    after = snapshot_state(factory, game, seed)
    assert after[0] == "needs_review"
    assert after[2:5] == before[2:5]
    with game_storage_scope(game), factory() as session:
        assert session.get(SourceImageModel, seed.source_image_id) is not None
        pin = session.get(JobModel, seed.import_job_id).input_payload["neural_grid_operation_pin"]
        assert pin["qualification"]["state"] == (
            "qualified" if forged_game_evidence else "unqualified"
        )


def test_v3_exact_evaluated_game_passes_real_prewrite_guard(database, tmp_path):
    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy=GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
        evaluated_game=True,
    )
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    after = snapshot_state(factory, game, seed)
    assert after[0] == "accepted"
    assert after[5] == "geometry_complete"
    assert all(board["disposition"] == "automatic" for board in after[3])


@pytest.mark.parametrize("forged_manual", [False, True])
def test_v3_forged_ready_is_not_accepted_before_recognition(database, tmp_path, forged_manual):
    game, factory, seed, _candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy=GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
        forged_ready=True,
        forged_manual=forged_manual,
    )
    # execution committed project_source_geometry in its own transaction. Stop
    # here, then read only durable state through a fresh session, as after a crash.
    structured = stages["board_cell_geometry"].payload["structuredGeometry"]
    assert structured["status"] == "ready"
    assert structured["engineKind"] == ("manual_v1" if forged_manual else "neural_grid_v1")
    assert snapshot_state(factory, game, seed)[0] == "needs_review"
    with game_storage_scope(game), factory() as session:
        accepted = session.scalars(
            select(ImageSourceGeometryRevisionModel).where(
                ImageSourceGeometryRevisionModel.game_id == game,
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id,
                # The shared fixture deliberately retains an older accepted
                # manual revision. Only the new forged candidate is in scope.
                ImageSourceGeometryRevisionModel.geometry_checksum_sha256
                == structured["resultChecksumSha256"],
                ImageSourceGeometryRevisionModel.status == "accepted",
            )
        ).all()
        assert accepted == []
        assert session.get(SourceImageModel, seed.source_image_id) is not None


def test_v3_qualified_ready_promotes_only_at_finalize_without_rewriting_sealed_geometry(
    database,
    tmp_path,
):
    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy=GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
        evaluated_game=True,
        forged_ready=True,
    )
    before = snapshot_state(factory, game, seed)
    assert before[0] == "needs_review"
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    after = snapshot_state(factory, game, seed)
    assert after[0] == "accepted"
    assert after[5] == "geometry_complete"
    assert after[2:5] == before[2:5]  # sealed SHA, board payload and initialization


@pytest.mark.parametrize("qualified", [False, True])
def test_workflow_real_recheck_reaches_production_suite(database, tmp_path, qualified):
    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy=GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY,
        evaluated_game=qualified,
        workflow_recheck=True,
    )
    boards = stages["board_detection"].payload["structuredGeometry"]["boards"]
    assert all(
        board["disposition"] == ("automatic" if qualified else "needs_manual_review")
        for board in boards
    )
    assert all(
        "NEURAL_GRID_GAME_EVALUATION_UNCHECKED" not in board["reasonCodes"] for board in boards
    )
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed)[0] == ("accepted" if qualified else "needs_review")


@pytest.mark.parametrize(
    "policy", [V3_ENGINE_ACCEPTANCE_POLICY, GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY]
)
def test_worker_qualification_cannot_mint_human_approval_for_strict_jobs(
    database, tmp_path, policy
):
    from game_predictor_api.domain.geometry_qualification import GeometryQualification
    from game_predictor_worker.vision_lab.production_geometry import (
        LabelFacts,
        classify_label_level,
    )

    strict = policy == GAME_SCOPED_V3_ENGINE_ACCEPTANCE_POLICY
    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy=policy,
        forged_game_evidence=strict,
    )
    # A forged worker can keep its own crop/symbol metadata mutually consistent;
    # the test must reach the human-stamp branch, not fail that structural fence.
    for stage in ("board_crops", "symbol_inference"):
        for board in stages[stage].payload["boards"]:
            board["geometryQualification"] = GeometryQualification().to_dict()
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    with game_storage_scope(game), factory() as session:
        boards = session.scalars(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id == seed.source_image_id
            )
        ).all()
        assert boards
        for board in boards:
            assert board.geometry_qualification is not None  # availability metadata stays
            assert board.approved_geometry_revision == (None if strict else 0)
            if strict:
                assert board.geometry_approved_by is None and board.geometry_approved_at is None
                revision = session.get(
                    ImageSourceGeometryRevisionModel, board.source_geometry_revision_id
                )
                level = classify_label_level(
                    LabelFacts(
                        geometry_revision=board.geometry_revision,
                        approved_geometry_revision=board.approved_geometry_revision,
                        approved_by=board.geometry_approved_by,
                        revision_authors=[],
                        source_geometry_source=revision.geometry_source,
                        source_status=revision.status,
                        source_created_by=revision.created_by,
                    )
                )
                assert level.level == "U" and level.approval_actor is None
        source = session.get(SourceImageModel, seed.source_image_id)
        assert source.geometry_completeness_status == (
            "geometry_incomplete" if strict else "geometry_complete"
        )


def test_exact_prepare_is_serialized_across_publication_and_rejects_duplicate_identity(
    database, tmp_path
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace

    from game_predictor_api.application.jobs import JobService
    from game_predictor_api.domain.jobs import JobConflictError, JobStatus, JobType, create_job
    from game_predictor_api.domain.neural_grid_operation_pin import (
        CAPABILITY_PREFLIGHT_POLICY,
        OPERATION_PIN_KEY,
    )
    from game_predictor_api.storage.job_repository import (
        SqlAlchemyJobRepository,
        job_record_from_domain,
    )
    from game_predictor_api.storage.neural_grid_operation_qualification import prepare_operation_pin
    from test_grid_model_publication_and_activation import execute, registry, seed_report
    from test_grid_model_registry import candidate as candidate_descriptor

    game = _provision_game(database.engine, "t1156-cas-" + uuid4().hex[:8])
    factory = _factory(database.engine)
    root = tmp_path / "artifacts"
    seed = _seed(factory, game, root, label="t1156-exact", slot_count=2)
    descriptor = candidate_descriptor(tmp_path)
    descriptor["familyCode"] = "t1156_cas_" + uuid4().hex[:10]
    descriptor["cohortId"] = str(uuid4())
    snapshot = NeuralGridSnapshot.from_catalogue(
        game_id=str(game),
        game_configuration="neural_grid_v3",
        expected_layout_count=500000,
        descriptor=descriptor,
    )
    with game_storage_scope(game), factory.begin() as session:
        session.get(JobModel, seed.import_job_id).status = JobStatus.COMPLETED
        registry(session, tmp_path).register(uuid4(), descriptor)
        report = seed_report(session, descriptor, [game])
    request = {
        "schema_version": 2,
        "validation_kind": "page_geometry_preflight",
        "preflight_policy_version": CAPABILITY_PREFLIGHT_POLICY,
        "source_selection_id": str(uuid4()),
        "source_manifest_sha256": "a" * 64,
        "source_directory": str(root),
        "source_display_name": "same explicit selection",
        "neural_grid_proposal": snapshot.to_payload(),
    }
    first_read, second_started, allow_commit = Event(), Event(), Event()
    calls = []

    def prepare(second):
        if second:
            assert first_read.wait(5)
            second_started.set()
        with game_storage_scope(game), factory.begin() as session:

            def resolve(**kwargs):
                calls.append(second)
                pin = prepare_operation_pin(
                    session,
                    snapshot=snapshot,
                    game_id=game,
                    rules_version_id=kwargs["rules_version_id"],
                    rows=kwargs["rows"],
                    columns=kwargs["columns"],
                )
                assert pin["qualification"]["state"] == "unqualified"
                first_read.set()
                assert allow_commit.wait(5)
                return pin

            repository = SqlAlchemyJobRepository(session)
            service = JobService(
                repository,
                grid_profile_snapshot_resolver=SimpleNamespace(
                    resolve_neural_operation_pin=resolve
                ),
            )
            payload = dict(request)
            service._pin_neural_operation(game, payload)
            try:
                job = service._persist_job(
                    JobType.VALIDATE,
                    game_id=game,
                    input_payload=payload,
                    game_already_validated=True,
                )
            except JobConflictError as error:
                assert error.code == "JOB_INPUT_ALREADY_EXISTS"
                job = repository.get_job_by_input_key(
                    create_job(JobType.VALIDATE, game_id=game, input_payload=payload).input_key
                )
            assert job is not None
            return job.id, payload[OPERATION_PIN_KEY]

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(prepare, False)
        assert first_read.wait(5)
        second = pool.submit(prepare, True)
        assert second_started.wait(5)
        try:
            # A real immutable publication can happen while the first operation
            # holds admission: registry publication has its own existing lock.
            with game_storage_scope(game), factory.begin() as session:
                execute(
                    registry(session, tmp_path),
                    "publish",
                    descriptor["versionId"],
                    evaluation=report,
                )
        finally:
            allow_commit.set()
        left, right = first.result(timeout=10), second.result(timeout=10)
    assert left == right and calls == [False]
    assert left[1]["qualification"]["state"] == "unqualified"
    with game_storage_scope(game), factory.begin() as session:
        topology = SqlAlchemyJobRepository(session).get_or_pin_board_topology(game)
        assert topology is not None
        fresh = prepare_operation_pin(
            session,
            snapshot=snapshot,
            game_id=game,
            rules_version_id=topology.rules_version_id,
            rows=3,
            columns=5,
        )
        assert fresh["qualification"]["evaluationId"] == str(report)
        assert fresh["qualification"]["state"] == "qualified"
        # Model a pre-existing duplicate from earlier faulty code: a different
        # derived fingerprint must not permit arbitrary selection of one pin.
        duplicate = create_job(
            JobType.VALIDATE,
            game_id=game,
            input_payload={**request, OPERATION_PIN_KEY: left[1], "pipeline_fingerprint": "b" * 64},
        )
        session.add(job_record_from_domain(replace(duplicate, status=JobStatus.COMPLETED)))
    with game_storage_scope(game), factory.begin() as session:
        repository = SqlAlchemyJobRepository(session)
        with pytest.raises(JobConflictError) as error:
            repository.find_neural_operation_pin(
                game_id=game, job_type=JobType.VALIDATE, input_payload=request
            )
        assert error.value.code == "NEURAL_GRID_OPERATION_IDENTITY_AMBIGUOUS"


@pytest.mark.parametrize("legacy,missing", [(False, False), (True, False), (False, True)])
@pytest.mark.parametrize("version", [1, 2])
def test_complete_acceptance_and_legacy_or_deferred_cold_replay(
    database, tmp_path, legacy, missing, version
):
    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        legacy=legacy,
        missing=missing,
        crop_policy=f"neural-auto-crop-v{version}",
        acceptance_policy=f"v3-engine-acceptance-v{version}",
    )
    before = snapshot_state(factory, game, seed)
    assert before[0] == "needs_review"
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    after = snapshot_state(factory, game, seed)
    assert after[0] == ("needs_review" if legacy or missing else "accepted")
    assert after[1] == ("system:image-pipeline-v0.10" if legacy else V3_ENGINE_ACCEPTANCE_ACTOR)
    assert after[2:5] == before[2:5]
    assert after[5] == ("geometry_incomplete" if legacy or missing else "geometry_complete")
    assert len(after[6]) == ((15 if version == 1 else 0) if missing else 30)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_source_geometry(
            candidate, stage_results=stages
        )
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed) == after


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("reason", ["NEURAL_GRID_FIT_FAILED", "NEURAL_GRID_FIT_OUTLIERS"])
def test_fit_errors_never_materialize_v2_automatic_cells(database, tmp_path, version, reason):
    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        crop_policy=f"neural-auto-crop-v{version}",
        acceptance_policy=f"v3-engine-acceptance-v{version}",
        fit_reason=reason,
    )
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    after = snapshot_state(factory, game, seed)
    assert after[0] == ("accepted" if version == 1 else "needs_review")
    assert len(after[6]) == (30 if version == 1 else 15)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed) == after


@pytest.mark.parametrize(
    "fault", ["model", "owner", "revision", "partial", "grid_issue", "stale_issue"]
)
def test_persisted_conflicts_block_acceptance_without_changing_payload(database, tmp_path, fault):
    game, factory, seed, candidate, stages = execution(database, tmp_path)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    before = snapshot_state(factory, game, seed)
    assert before[0] == "accepted"
    with game_storage_scope(game), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        source = session.get(SourceImageModel, seed.source_image_id)
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game,
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        board = session.scalar(
            select(RecognizedBoardModel)
            .where(RecognizedBoardModel.source_image_id == seed.source_image_id)
            .order_by(RecognizedBoardModel.position_index)
            .limit(1)
        )
        if fault == "model":
            job.input_payload = {**job.input_payload, "neural_grid_proposal": {"drift": True}}
        elif fault == "owner":
            item = session.scalar(
                select(ImageReviewItemModel).where(
                    ImageReviewItemModel.game_id == game,
                    ImageReviewItemModel.recognized_board_id == board.id,
                )
            )
            item.sequence_number = 999
        elif fault == "revision":
            board.geometry_revision += 1
        elif fault == "partial":
            board.completeness_status = "pending_partial"
            board.unavailable_cell_indices = [0]
        elif fault in ("grid_issue", "stale_issue"):
            cell = session.scalar(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == game,
                    ImageSymbolReviewCellModel.recognized_board_id == board.id,
                )
                .limit(1)
            )
            cell.quality_issue = "grid_issue"
            if fault == "stale_issue":
                cell.source_geometry_revision_id = session.scalar(
                    select(ImageSourceGeometryRevisionModel.id)
                    .where(
                        ImageSourceGeometryRevisionModel.game_id == game,
                        ImageSourceGeometryRevisionModel.source_image_id == source.id,
                    )
                    .order_by(ImageSourceGeometryRevisionModel.revision)
                    .limit(1)
                )
        blockers = finalize_v3_engine_acceptance(
            session,
            job=job,
            source=source,
            revision=revision,
            structured=stages["board_cell_geometry"].payload["structuredGeometry"],
        )
        assert bool(blockers) == (fault != "stale_issue")
    after = snapshot_state(factory, game, seed)
    assert after[0] == ("accepted" if fault == "stale_issue" else "needs_review")
    assert after[2:5] == before[2:5]


def test_current_grid_issue_survives_cold_retry_and_removes_engine_acceptance(database, tmp_path):
    game, factory, seed, candidate, stages = execution(database, tmp_path)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    with game_storage_scope(game), factory.begin() as session:
        cell = session.scalar(
            select(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game,
                ImageSymbolReviewCellModel.import_job_id == seed.import_job_id,
            )
            .limit(1)
        )
        cell.quality_issue = "grid_issue"
    before = snapshot_state(factory, game, seed)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    after = snapshot_state(factory, game, seed)
    assert after[0] == "needs_review"
    assert after[2:5] == before[2:5]
    assert after[6] == before[6]


def test_failed_gate_rolls_back_engine_acceptance_and_recognition(database, tmp_path, monkeypatch):
    game, factory, seed, candidate, stages = execution(database, tmp_path)
    before = snapshot_state(factory, game, seed)

    def fail(*args, **kwargs):
        raise RuntimeError("TASK1017 forced gate failure")

    monkeypatch.setattr(pipeline_store, "recompute_source_image_geometry_completeness", fail)
    with game_storage_scope(game), pytest.raises(RuntimeError, match="forced gate failure"):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed) == before
