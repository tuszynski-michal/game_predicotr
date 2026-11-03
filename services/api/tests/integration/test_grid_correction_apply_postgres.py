"""Controlled evidence boundary; real apply receipts, PostgreSQL and manual geometry.

This does not claim a measured model PASS. Admission/evidence gates have separate
T2/T3 tests; this scenario exercises the write boundary after those gates.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.grid_correction_apply import GridCorrectionApplyService
from game_predictor_api.application.grid_correction_learning import (
    LEARNING_KIND,
    GridCorrectionLearningService,
)
from game_predictor_api.domain.grid_model_registry import historical_catalogue
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import (
    JobExecutionSlot,
    JobStatus,
    JobType,
    complete_job,
    create_job,
    fail_job,
    start_job,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    game_storage_scope,
)
from game_predictor_api.storage.grid_model_registry_models import GridModelEvaluationReportModel
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import GameModel
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from test_grid_model_publication_and_activation import execute, registry, seed_report
from test_grid_model_registry import candidate
from test_grid_training_cohort_e2e_postgres import _save_source

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def _completed(job):
    if job.status is JobStatus.PROCESSING:
        return complete_job(job, lease_token=job.lease_token)
    token = uuid4()
    running = start_job(
        job,
        worker_version="fixture1123",
        worker_id="no-worker-process",
        lease_token=token,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    return complete_job(running, lease_token=token)


def _manual_snapshot(engine, game):
    result = {}
    with game_storage_scope(game), Session(engine) as session:
        GameStorageRouter().bind(session, game, intent=GameStorageIntent.READ)
        for name in (
            "source_images",
            "image_source_geometry_revisions",
            "recognized_boards",
            "image_board_geometry_revisions",
            "image_board_geometry_review_events",
            "image_review_items",
            "image_symbol_review_cells",
        ):
            # These identifiers are a literal test-owned allowlist, never user input.
            rows = session.execute(
                text("SELECT to_jsonb(t) FROM " + name + " t WHERE game_id=:g"),
                {"g": game},
            ).scalars()
            result[name] = sorted(json.dumps(row, sort_keys=True, default=str) for row in rows)
    return result


def _asset_snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "data").rglob("*")
        if p.is_file()
    }


def _pin(session, root, game):
    return SqlAlchemyGridProfileSnapshotResolver(session, root).resolve_neural_grid_proposal(
        game_id=game
    )


def _assert_fresh_process(db, root, game, manifest, old_job, new_job, original_pin):
    program = """
import json, os
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import GameModel

engine = create_engine(os.environ["T1122_TEST_URL"], connect_args={"connect_timeout": 5})
try:
    with Session(engine) as session:
        new = SqlAlchemyGridProfileSnapshotResolver(
            session, Path(os.environ["T1122_ROOT"])
        ).resolve_neural_grid_proposal(game_id=UUID(os.environ["T1122_GAME"]))
        assert new["catalogueManifest"]["versionId"] == os.environ["T1122_VERSION"]
        old = SqlAlchemyJobRepository(session).get_job(UUID(os.environ["T1122_JOB"]))
        assert old.input_payload["neural_grid_proposal"] == json.loads(os.environ["T1122_OLD_PIN"])
        persisted_new = SqlAlchemyJobRepository(session).get_job(UUID(os.environ["T1122_NEW_JOB"]))
        assert persisted_new.input_payload["neural_grid_proposal"] == new
        print("fresh-process-import-pin-preserved-history")
finally:
    engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=20,
        env=db.subprocess_environment(
            T1122_TEST_URL=db.app_url.render_as_string(hide_password=False),
            T1122_ROOT=str(root),
            T1122_GAME=str(game),
            T1122_VERSION=manifest["versionId"],
            T1122_JOB=str(old_job.id),
            T1122_NEW_JOB=str(new_job.id),
            T1122_OLD_PIN=json.dumps(original_pin),
        ),
    )
    assert result.returncode == 0, result.stderr
    assert "fresh-process-import-pin-preserved-history" in result.stdout


def _save(factory, job):
    with factory() as session, session.begin():
        return SqlAlchemyJobRepository(session).save_job(job)


def _get(factory, identifier):
    with factory() as session:
        return SqlAlchemyJobRepository(session).get_job(identifier)


def _claim(worker):
    return worker.claim_next(
        worker_id="fixture:1122",
        worker_version="test",
        lease_duration=timedelta(seconds=60),
        claimed_at=datetime.now(UTC),
        allowed_job_types=frozenset(
            {JobType.GRID_CORRECTION_LEARNING, JobType.GRID_MODEL_EVALUATION}
        ),
        execution_slot=JobExecutionSlot.GENERAL,
    )


def _waiting_apply_claim(factory, game, original, worker):
    """Queue-only controlled child: an older apply cannot occupy the slot it needs."""
    child = create_job(
        JobType.GRID_MODEL_EVALUATION,
        game_id=None,
        input_payload={
            "schema_version": 1,
            "evaluation_kind": "grid-assigned-comparison-v1",
            "idempotency_key": str(uuid4()),
        },
    )
    payload = copy.deepcopy(original.input_payload)
    payload["idempotency_key"] = str(uuid4())
    payload["command"]["idempotencyKey"] = payload["idempotency_key"]
    parent = create_job(
        JobType.GRID_CORRECTION_LEARNING,
        game_id=game,
        input_payload=payload,
        created_at=child.created_at - timedelta(seconds=1),
    )
    parent = replace(parent, checkpoint_payload={"waitingForJobId": str(child.id)})
    with factory() as session, session.begin():
        repository = SqlAlchemyJobRepository(session)
        repository.add_job(parent)
        repository.add_job(child)
    claimed = _claim(worker)
    assert claimed.id == child.id
    _save(factory, _completed(claimed))
    resumed = _claim(worker)
    assert resumed.id == parent.id
    _save(factory, _completed(resumed))


@pytest.mark.parametrize("publication_origin", ["first_apply", "manual", "different_evidence"])
def test_real_apply_republication_recovery_import_and_history(
    tmp_path, monkeypatch, publication_origin
):
    # Expensive model evidence is controlled, but no preview/query/control/queue write is mocked.
    with application_role_database("t1122apply", ("apply-import",)) as db:
        print("1122 disposable database ready: " + publication_origin, flush=True)
        game = next(iter(db.games.values()))
        root = tmp_path / "assets"
        root.mkdir()
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' "
                    "WHERE id=:g"
                ),
                {"g": game},
            )
        expected = {}
        _save_source(db, root, game, 1, 1, expected)
        before_manual, before_assets = _manual_snapshot(db.app_engine, game), _asset_snapshot(root)
        assert (
            before_manual["image_board_geometry_revisions"] and before_assets and len(expected) == 1
        )
        baseline, manifest = historical_catalogue()[0], candidate(root)
        manifest["cohortId"] = str(uuid4())
        factory = sessionmaker(db.app_engine)
        with factory() as session, session.begin():
            control = registry(session, root)
            control.register(uuid4(), manifest)
            report_id = seed_report(session, manifest, [game])
            other_report = seed_report(session, manifest, [game])
            execute(control, "publish", baseline["versionId"])
            execute(control, "set_default", baseline["versionId"])
            execute(control, "activate", baseline["versionId"], game=game)
            original_pin = (
                SqlAlchemyGridProfileSnapshotResolver(session, root)
                ._assigned_snapshot(session.get(GameModel, game))
                .to_payload()
            )
            old_job = _completed(
                create_job(
                    JobType.IMPORT,
                    game_id=game,
                    input_payload={
                        "schema_version": 2,
                        "import_kind": "image_directory",
                        "neural_grid_proposal": original_pin,
                    },
                )
            )
            repository = SqlAlchemyJobRepository(session)
            repository.add_job(old_job)
            initial = {
                "gameId": str(game),
                "baseVersionId": baseline["versionId"],
                "defaultRevision": control.repository.default().revision,
                "previewSha256": "c" * 64,
                "requiredGameIds": [str(game)],
                "exclusions": [],
            }
            learning = _completed(
                replace(
                    create_job(
                        JobType.GRID_CORRECTION_LEARNING,
                        game_id=game,
                        input_payload={
                            "schema_version": 1,
                            "learning_kind": LEARNING_KIND,
                            "idempotency_key": str(uuid4()),
                            "preview": initial,
                            "command": {},
                            "pins": {},
                            "actor": "fixture:1122",
                        },
                    ),
                    checkpoint_payload={
                        "candidateVersionId": manifest["versionId"],
                        "evaluationId": str(uuid4()),
                        "reportId": str(report_id),
                    },
                )
            )
            repository.add_job(learning)
            before_receipts = session.scalar(
                text("SELECT count(*) FROM public.grid_model_control_events")
            )
            before_assignments = session.scalar(
                text(
                    "SELECT count(*) FROM public.game_grid_model_assignment_events WHERE game_id=:g"
                ),
                {"g": game},
            )
        cohort = {"gameId": str(game), "cohortId": manifest["cohortId"], "manifestSha256": "f" * 64}
        controlled_report = {
            "scope": {
                "currentGameId": str(game),
                "trainingGameIds": [str(game)],
                "priorVerifiedGameIds": [],
                "priorScopeDocumented": False,
                "exclusions": [],
            },
            "cohorts": [cohort],
            "requiredGameIds": [str(game)],
            "verdict": "PASS",
        }

        def controlled_evidence(self, session, control, actual_game, actual_learning):
            assert (actual_game, actual_learning) == (game, learning.id)
            return (
                _get(factory, learning.id),
                control.control._version(UUID(manifest["versionId"])),
                copy.deepcopy(controlled_report),
                session.get(GridModelEvaluationReportModel, report_id),
            )

        monkeypatch.setattr(
            GridCorrectionApplyService, "_registry", lambda self, s: registry(s, root)
        )
        monkeypatch.setattr(GridCorrectionApplyService, "_evidence", controlled_evidence)

        def service():
            return GridCorrectionApplyService(db.app_engine, factory, root)

        def command(preview):
            return {
                "idempotencyKey": str(uuid4()),
                "previewSha256": preview["previewSha256"],
                "additionalGameIds": [],
                "confirmLimitedEvidence": True,
            }

        worker = SqlAlchemyWorkerJobStore(factory)
        conflicted_history = None
        if publication_origin == "different_evidence":
            before_publication = service().preview(game, learning.id, [])
            historical = service().start(
                game, learning.id, command(before_publication), "fixture:1122"
            )
            claimed = _claim(worker)
            assert str(claimed.id) == historical["applyId"]
            _save(
                factory,
                fail_job(
                    claimed,
                    lease_token=claimed.lease_token,
                    error_code="COMPARISON_INTERRUPTED",
                    error_message="fixture before publication",
                ),
            )
            conflicted_history = claimed.id
        if publication_origin in {"manual", "different_evidence"}:
            with factory() as session, session.begin():
                execute(
                    registry(session, root),
                    "publish",
                    manifest["versionId"],
                    evaluation=report_id if publication_origin == "manual" else other_report,
                )
        preview = service().preview(game, learning.id, [])
        if publication_origin == "different_evidence":
            assert not preview["canApply"]
            assert "GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT" in preview["blockers"]
            with pytest.raises(GridCohortError) as error:
                service().start(game, learning.id, command(preview), "fixture:1122")
            assert error.value.code == "GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT"
            history = service().list(game, learning.id)["items"]
            assert len(history) == 1 and history[0]["applyId"] == str(conflicted_history)
            assert history[0]["status"] == "failed"
            assert history[0]["steps"][0]["status"] == "pending"
            assert service().get(game, learning.id, conflicted_history) == history[0]
            assert _manual_snapshot(db.app_engine, game) == before_manual
            assert _asset_snapshot(root) == before_assets
            return
        assert preview["canApply"], preview
        first_command = command(preview)
        started = service().start(game, learning.id, first_command, "fixture:1122")
        assert service().start(game, learning.id, first_command, "fixture:1122") == started
        identifier = UUID(started["applyId"])
        assert service().get(game, learning.id, identifier) == started
        assert [item["applyId"] for item in service().list(game, learning.id)["items"]] == [
            str(identifier)
        ]
        with pytest.raises(GridCohortError) as busy:
            service().start(game, learning.id, command(preview), "fixture:1122")
        assert busy.value.code == "GRID_APPLY_BUSY"
        assert [
            item["learningId"]
            for item in GridCorrectionLearningService(db.app_engine, factory, root).list(game)[
                "items"
            ]
        ] == [str(learning.id)]
        if publication_origin == "first_apply":
            claimed = _claim(worker)
            assert claimed.id == identifier
            state, finished = service().advance(claimed)
            assert not finished and state["steps"][0]["status"] == "completed"
            assert service().advance(claimed) == (state, finished)
            with factory() as session, session.begin():
                control = registry(session, root)
                execute(
                    control,
                    "set_default",
                    baseline["versionId"],
                    expected=control.repository.default().revision,
                )
            with pytest.raises(GridCohortError) as changed:
                service().advance(replace(claimed, checkpoint_payload=state))
            assert changed.value.code == "GRID_APPLY_DEFAULT_CHANGED"
            # Crash before checkpoint: receipt survives independently of the failed parent.
            _save(
                factory,
                fail_job(
                    claimed,
                    lease_token=claimed.lease_token,
                    error_code="GRID_APPLY_DEFAULT_CHANGED",
                    error_message="fixture",
                ),
            )
            assert service().get(game, learning.id, identifier)["steps"][0]["status"] == "completed"
            fresh = service().preview(game, learning.id, [])
            assert fresh["canApply"] and fresh["previewSha256"] != preview["previewSha256"]
            started = service().start(game, learning.id, command(fresh), "fixture:1122")
            assert started["applyId"] != str(identifier)
            with pytest.raises(GridCohortError) as competing_resume:
                service().resume(game, learning.id, identifier, "fixture:1122")
            assert competing_resume.value.code == "GRID_APPLY_BUSY"
            assert _get(factory, identifier).status is JobStatus.FAILED
            identifier = UUID(started["applyId"])
        for index in range(3):
            job = _get(factory, identifier)
            if job.status is JobStatus.CREATED:
                job = _claim(worker)
                assert job.id == identifier
            state, finished = service().advance(job)
            assert service().advance(job) == (state, finished)
            assert state["steps"][0]["receipt"]["kind"] == "already-published"
            updated = replace(job, checkpoint_payload=state)
            if index == 0:
                _save(
                    factory,
                    fail_job(
                        updated,
                        lease_token=job.lease_token,
                        error_code="FIXTURE_INTERRUPTED",
                        error_message="fixture",
                    ),
                )
                resumed = service().resume(game, learning.id, identifier, "fixture:1122")
                assert resumed["applyId"] == str(identifier) and resumed["status"] == "created"
                assert service().resume(game, learning.id, identifier, "fixture:1122") == resumed
            else:
                _save(factory, _completed(updated) if finished else updated)
            print("1122 recovered apply step " + str(index + 1), flush=True)
        assert finished
        complete = service().get(game, learning.id, identifier)
        assert complete["status"] == "completed"
        assert service().resume(game, learning.id, identifier, "fixture:1122") == complete
        assert "GRID_APPLY_ALREADY_DEFAULT" in service().preview(game, learning.id, [])["blockers"]
        with factory() as session, session.begin():
            assert registry(session, root).repository.default().version_id == UUID(
                manifest["versionId"]
            )
            new_pin = _pin(session, root, game)
            assert new_pin["catalogueManifest"]["versionId"] == manifest["versionId"]
            new_job = create_job(
                JobType.IMPORT,
                game_id=game,
                input_payload={
                    "schema_version": 2,
                    "import_kind": "image_directory",
                    "neural_grid_proposal": new_pin,
                },
            )
            repository = SqlAlchemyJobRepository(session)
            repository.add_job(new_job)
            assert repository.get_job(old_job.id).input_payload == old_job.input_payload
            assert repository.get_job(old_job.id).input_key == old_job.input_key
            assert session.scalar(
                text("SELECT count(*) FROM public.grid_model_control_events")
            ) == (before_receipts + (3 if publication_origin == "first_apply" else 2))
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM public.game_grid_model_assignment_events "
                        "WHERE game_id=:g"
                    ),
                    {"g": game},
                )
                == before_assignments + 1
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM public.grid_model_publications WHERE version_id=:v"),
                    {"v": UUID(manifest["versionId"])},
                )
                == 1
            )
        assert _manual_snapshot(db.app_engine, game) == before_manual
        assert _asset_snapshot(root) == before_assets
        _assert_fresh_process(db, root, game, manifest, old_job, new_job, original_pin)
        _waiting_apply_claim(factory, game, _get(factory, identifier), worker)
