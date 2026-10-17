"""TASK-1047: crop runs (migration 0168) and the ``source_crop`` job on PostgreSQL.

Runs on dedicated ``*_test`` databases only. The API side writes runs on the
application role; the worker reads eligibility as schema owner in one
REPEATABLE READ snapshot, exactly as the worker CLI wires it. Jobs are claimed
by the real worker store, so every worker write carries a real lease.
"""

from __future__ import annotations

import hashlib
import io
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
from _application_role_database import ApplicationRoleDatabase, application_role_database
from alembic import command
from game_predictor_api.application.source_crop_runs import SourceCropScope
from game_predictor_api.domain.canonical_source import (
    decode_canonical_source_bytes,
    decode_cropped_source_bytes,
)
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobStatus,
    JobType,
    request_job_cancellation,
    requeue_job,
)
from game_predictor_api.domain.source_crop import PixelBox, cropped_original_relative_paths
from game_predictor_api.storage.database import (
    create_owner_session_factory,
    create_session_factory,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.source_crop_run_repository import (
    SqlAlchemySourceCropRunRepository,
)
from game_predictor_api.storage.source_image_crop_repository import SourceImageCropRepository
from game_predictor_worker import source_crop as source_crop_module
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from game_predictor_worker.source_crop import SourceCropHandler, SqlSourceCropCatalog
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from test_source_image_crops_postgres import _config, _seed_source

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

LEASE = timedelta(minutes=5)


class _BlockCropper:
    """Exact for block-aligned grayscale originals; jpegtran is exercised elsewhere."""

    version = "python-block-cropper-test"

    def __init__(self, *, crash_on_call: int | None = None) -> None:
        self.calls: list[str] = []
        self._crash_on_call = crash_on_call

    def crop(self, source: Path, target: Path, raw_box: PixelBox) -> None:
        self.calls.append(source.stem)
        if self._crash_on_call == len(self.calls):
            raise SystemExit("worker process killed")
        with Image.open(source) as image:
            image.crop((raw_box.left, raw_box.top, raw_box.right, raw_box.bottom)).save(
                target, "JPEG", quality=100
            )


def _job(session_factory: sessionmaker[Session], job_id: UUID | None) -> Job:
    assert job_id is not None
    with session_factory() as session:
        job = SqlAlchemyJobRepository(session).get_job(job_id)
        assert job is not None
        return job


def _save(session_factory: sessionmaker[Session], job: Job) -> None:
    with session_factory.begin() as session:
        SqlAlchemyJobRepository(session).save_job(job)


def _claim(session_factory: sessionmaker[Session]) -> Job:
    job = SqlAlchemyWorkerJobStore(session_factory).claim_next(
        worker_id="task-1047-test",
        worker_version="task-1047-test",
        lease_duration=LEASE,
        claimed_at=datetime.now(UTC),
        allowed_job_types=frozenset({JobType.SOURCE_CROP}),
    )
    assert job is not None and job.lease_token is not None
    return job


def _expire(db: ApplicationRoleDatabase, job_id: UUID) -> None:
    with db.owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.jobs SET lease_expires_at = now() - interval '1 minute', "
                "heartbeat_at = now() - interval '6 minutes' WHERE id = :id"
            ),
            {"id": job_id},
        )


def _preview(runs: SqlAlchemySourceCropRunRepository, run_id: UUID, job: Job) -> None:
    assert job.lease_token is not None
    runs.mark_previewed(
        run_id,
        plan_job_id=job.id,
        lease_token=job.lease_token,
        manifest_relative_path=f"data/source-crop-runs/{run_id}/manifest.json",
        manifest_checksum_sha256="c" * 64,
        preview_token="d" * 64,
        eligible_count=1,
        excluded_count=2,
        exclusion_counts={"GRID_ISSUE": 2},
        candidate_bytes=100,
        estimated_saved_bytes=60,
    )


def _original(root: Path, seed: int) -> tuple[str, bytes, str]:
    pixels = np.kron(
        np.random.default_rng(seed).integers(0, 256, (74, 135), dtype=np.uint8),
        np.ones((8, 8), dtype=np.uint8),
    )[:589]
    buffer = io.BytesIO()
    Image.fromarray(pixels, "L").save(buffer, "JPEG", quality=100)
    content = buffer.getvalue()
    checksum = hashlib.sha256(content).hexdigest()
    path = root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    frame = decode_canonical_source_bytes(content, expected_source_checksum_sha256=checksum)
    return checksum, content, frame.source.normalized_pixel_checksum_sha256


def _seed_eligible(db: ApplicationRoleDatabase, root: Path, seed: int) -> tuple[str, bytes]:
    checksum, content, pixels = _original(root, seed)
    _seed_source(db.owner_engine, db.games["a"], checksum)
    with db.owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE game_data_v2.source_images SET normalized_pixel_checksum_sha256=:p "
                "WHERE checksum_sha256=:c"
            ),
            {"p": pixels, "c": checksum},
        )
    return checksum, content


def _worker(
    db: ApplicationRoleDatabase, root: Path, cropper: _BlockCropper
) -> tuple[LocalJobWorker, SqlAlchemySourceCropRunRepository]:
    """Fresh objects, as a newly started worker process builds them."""

    app_sessions = create_session_factory(db.app_engine)
    runs = SqlAlchemySourceCropRunRepository(app_sessions)
    handler = SourceCropHandler(
        runs,
        SqlSourceCropCatalog(create_owner_session_factory(db.owner_engine)),
        root,
        cropper_factory=lambda: cropper,
    )
    worker = LocalJobWorker(
        SqlAlchemyWorkerJobStore(app_sessions),
        {JobType.SOURCE_CROP: handler},
        worker_id=f"task-1047-{uuid4().hex[:8]}",
        worker_version="task-1047-test",
        lease_duration=LEASE,
    )
    return worker, runs


def test_migration_grants_the_application_role_and_guards_its_downgrade() -> None:
    with application_role_database("t1047m", ()) as db:
        runs = SqlAlchemySourceCropRunRepository(create_session_factory(db.app_engine))
        config = _config(db)
        command.downgrade(config, "0167_source_image_crops")
        with db.owner_engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('public.source_crop_runs')")) is None
        command.upgrade(config, "head")
        run = runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        assert run.status == "planning"
        with pytest.raises(Exception, match="SOURCE_CROP_RUNS_DOWNGRADE_HAS_HISTORY"):
            command.downgrade(config, "0167_source_image_crops")


def test_run_lifecycle_is_fenced_by_the_current_lease() -> None:
    with application_role_database("t1047r", ()) as db:
        app_sessions = create_session_factory(db.app_engine)
        runs = SqlAlchemySourceCropRunRepository(app_sessions)
        catalog = SqlSourceCropCatalog(create_owner_session_factory(db.owner_engine))
        run = runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        assert _job(app_sessions, run.plan_job_id).input_payload["phase"] == "plan"
        with pytest.raises(JobConflictError) as active:
            runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        assert active.value.code == "SOURCE_CROP_RUN_ACTIVE"

        stale = _claim(app_sessions)
        _expire(db, stale.id)
        current = _claim(app_sessions)  # lease recovery hands the job to a new worker
        assert current.id == stale.id and current.lease_token != stale.lease_token
        assert stale.lease_token is not None and current.lease_token is not None
        with pytest.raises(JobConflictError) as lost:
            _preview(runs, run.id, stale)
        assert lost.value.code == "JOB_LEASE_LOST"
        with pytest.raises(JobConflictError):
            catalog.assert_lease(stale.id, stale.lease_token)
        catalog.assert_lease(current.id, current.lease_token)
        _preview(runs, run.id, current)

        with pytest.raises(JobConflictError) as stale_token:
            runs.start_run(
                run_id=run.id,
                expected_manifest_checksum_sha256="c" * 64,
                expected_preview_token="e" * 64,
            )
        assert stale_token.value.code == "SOURCE_CROP_PREVIEW_STALE"
        started = runs.start_run(
            run_id=run.id,
            expected_manifest_checksum_sha256="c" * 64,
            expected_preview_token="d" * 64,
        )
        again = runs.start_run(
            run_id=run.id,
            expected_manifest_checksum_sha256="c" * 64,
            expected_preview_token="d" * 64,
        )
        assert started.status == "created" and again.job_id == started.job_id
        SqlAlchemyWorkerJobStore(app_sessions).complete(
            current.id, lease_token=current.lease_token, completed_at=datetime.now(UTC)
        )
        execute = _claim(app_sessions)
        assert execute.id == started.job_id and execute.lease_token is not None
        runs.mark_processing(run.id, job_id=execute.id, lease_token=execute.lease_token)
        with pytest.raises(JobConflictError):
            runs.checkpoint(
                run.id,
                job_id=execute.id,
                lease_token=uuid4(),
                checkpoint_index=1,
                outcomes={"cropped": 1},
                succeeded=1,
                skipped=0,
                failed=0,
                saved_bytes=60,
                failures=[],
            )
        runs.checkpoint(
            run.id,
            job_id=execute.id,
            lease_token=execute.lease_token,
            checkpoint_index=1,
            outcomes={"cropped": 1},
            succeeded=1,
            skipped=0,
            failed=0,
            saved_bytes=60,
            failures=[],
        )
        with (
            Session(db.owner_engine) as session,
            pytest.raises(IntegrityError),
            session.begin(),
        ):
            session.execute(
                text("UPDATE public.source_crop_runs SET processed_count=5 WHERE id=:i"),
                {"i": run.id},
            )
        runs.complete(run.id, job_id=execute.id, lease_token=execute.lease_token)
        assert runs.get_run(run.id).status == "completed"
        runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())


def test_job_state_changes_outside_the_handler_reach_the_run() -> None:
    with application_role_database("t1047s", ()) as db:
        app_sessions = create_session_factory(db.app_engine)
        runs = SqlAlchemySourceCropRunRepository(app_sessions)
        store = SqlAlchemyWorkerJobStore(app_sessions)

        # Cancelled before any worker claimed it: the run no longer blocks.
        first = runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        _save(app_sessions, request_job_cancellation(_job(app_sessions, first.plan_job_id)))
        assert runs.get_run(first.id).status == "cancelled"

        # A failed plan job fails the run; a retry reopens it.
        second = runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        claimed = _claim(app_sessions)
        assert claimed.lease_token is not None
        store.fail(
            claimed.id,
            lease_token=claimed.lease_token,
            error_code="SOURCE_CROP_TOOL_UNAVAILABLE",
            error_message="jpegtran was not found.",
            failed_at=datetime.now(UTC),
        )
        failed = runs.get_run(second.id)
        assert (failed.status, failed.error_code) == ("failed", "SOURCE_CROP_TOOL_UNAVAILABLE")
        third = runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        with pytest.raises(JobConflictError) as blocked:
            _save(app_sessions, requeue_job(_job(app_sessions, second.plan_job_id)))
        assert blocked.value.code == "SOURCE_CROP_RUN_ACTIVE"
        assert _job(app_sessions, second.plan_job_id).status is JobStatus.FAILED
        _save(app_sessions, request_job_cancellation(_job(app_sessions, third.plan_job_id)))
        _save(app_sessions, requeue_job(_job(app_sessions, second.plan_job_id)))
        reopened = runs.get_run(second.id)
        assert (reopened.status, reopened.error_code) == ("planning", None)

        # Cancellation requested while processing, then lease recovery.
        processing = _claim(app_sessions)
        _save(app_sessions, request_job_cancellation(_job(app_sessions, processing.id)))
        assert runs.get_run(second.id).status == "planning"
        _expire(db, processing.id)
        assert (
            store.claim_next(
                worker_id="task-1047-test",
                worker_version="task-1047-test",
                lease_duration=LEASE,
                claimed_at=datetime.now(UTC),
                allowed_job_types=frozenset({JobType.SOURCE_CROP}),
            )
            is None
        )
        assert runs.get_run(second.id).status == "cancelled"

        # A reviewed but unstarted preview is superseded by a new preview.
        fourth = runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        planner = _claim(app_sessions)
        _preview(runs, fourth.id, planner)
        assert planner.lease_token is not None
        store.complete(planner.id, lease_token=planner.lease_token, completed_at=datetime.now(UTC))
        assert runs.get_run(fourth.id).status == "previewed"
        runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        superseded = runs.get_run(fourth.id)
        assert (superseded.status, superseded.error_code) == (
            "cancelled",
            "SOURCE_CROP_PREVIEW_SUPERSEDED",
        )


def test_the_job_plans_crops_and_resumes_in_a_new_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_crop_module, "CHECKPOINT_EVERY", 1)
    with application_role_database("t1047e", ("a",)) as db:
        first, first_content = _seed_eligible(db, tmp_path, 5)
        second, second_content = _seed_eligible(db, tmp_path, 6)
        ordered = sorted([first, second])
        app_sessions = create_session_factory(db.app_engine)
        crashing = _BlockCropper(crash_on_call=2)
        worker, runs = _worker(db, tmp_path, crashing)
        run = runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())

        assert worker.run_once() is JobExecutionResult.COMPLETED
        previewed = runs.get_run(run.id)
        assert previewed.status == "previewed"
        assert previewed.eligible_count == 2 and previewed.excluded_count == 0
        assert previewed.manifest_checksum_sha256 is not None
        assert previewed.preview_token is not None
        started = runs.start_run(
            run_id=run.id,
            expected_manifest_checksum_sha256=previewed.manifest_checksum_sha256,
            expected_preview_token=previewed.preview_token,
        )
        # The process dies while cropping the second original, after the first
        # checkpoint: the job keeps its lease and the run stays processing.
        with pytest.raises(SystemExit):
            worker.run_once()
        interrupted = runs.get_run(run.id)
        assert (interrupted.status, interrupted.checkpoint_index) == ("processing", 1)
        assert crashing.calls == ordered

        _expire(db, started.job_id)  # type: ignore[arg-type]
        resumed_cropper = _BlockCropper()
        resumed, runs = _worker(db, tmp_path, resumed_cropper)
        assert resumed.run_once() is JobExecutionResult.COMPLETED

        finished = runs.get_run(run.id)
        assert finished.status == "completed", finished.failures
        assert finished.outcome_counts == {"cropped": 2}
        assert resumed_cropper.calls == [ordered[1]]
        execute_job = _job(app_sessions, started.job_id)
        assert execute_job.status is JobStatus.COMPLETED
        saved = 0
        for checksum, content in ((first, first_content), (second, second_content)):
            original = tmp_path / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
            assert original.read_bytes() == content
            with Session(db.owner_engine) as session:
                row = SourceImageCropRepository(session).get(checksum)
                assert row is not None and row.state == "verified"
                assert row.job_id == execute_job.id
                saved += row.original_size_bytes - row.crop_size_bytes
            crop, attestation = cropped_original_relative_paths(checksum)
            decode_cropped_source_bytes(
                (tmp_path / "data" / crop).read_bytes(),
                (tmp_path / "data" / attestation).read_bytes(),
                expected_source_checksum_sha256=checksum,
            )
            assert not list((tmp_path / "data" / crop).parent.glob("*.part"))
        assert finished.saved_bytes == saved > 0

        # A second run finds both originals already cropped.
        again = runs.create_planning_run(run_id=uuid4(), kind="crop", scope=SourceCropScope())
        assert resumed.run_once() is JobExecutionResult.COMPLETED
        assert runs.get_run(again.id).exclusion_counts == {"ALREADY_CROPPED": 2}
