"""TASK-1048: the irreversible deletion of cropped originals on PostgreSQL.

Runs on dedicated ``*_test`` databases only, with the real worker store and
``LocalJobWorker``: originals are cropped first, then deleted through their own
preview, token and acknowledgement. Guards of calibration anchors, cohorts and
cleanup read the shared registry on the application role.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import ApplicationRoleDatabase, application_role_database
from game_predictor_api.application.source_crop_runs import SourceCropRunService, SourceCropScope
from game_predictor_api.domain.jobs import JobConflictError, JobStatus, JobType, requeue_job
from game_predictor_api.domain.source_crop import cropped_original_relative_paths
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.database import (
    create_owner_session_factory,
    create_session_factory,
)
from game_predictor_api.storage.source_crop_run_repository import (
    SqlAlchemySourceCropRunRepository,
)
from game_predictor_api.storage.source_image_crop_repository import SourceImageCropRepository
from game_predictor_api.storage.source_original_availability import deleted_original_checksums
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from game_predictor_worker.source_crop import SourceCropHandler, SqlSourceCropCatalog
from game_predictor_worker.source_original_deletion import SourceOriginalDeletionHandler
from sqlalchemy.orm import Session
from test_source_crop_runs_postgres import LEASE, _BlockCropper, _job, _save, _seed_eligible

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


def _worker(db: ApplicationRoleDatabase, root: Path) -> LocalJobWorker:
    app_sessions = create_session_factory(db.app_engine)
    runs = SqlAlchemySourceCropRunRepository(app_sessions)
    catalog = SqlSourceCropCatalog(create_owner_session_factory(db.owner_engine))
    cropper = _BlockCropper()
    return LocalJobWorker(
        SqlAlchemyWorkerJobStore(app_sessions),
        {
            JobType.SOURCE_CROP: SourceCropHandler(
                runs, catalog, root, cropper_factory=lambda: cropper
            ),
            JobType.SOURCE_ORIGINAL_DELETION: SourceOriginalDeletionHandler(runs, catalog, root),
        },
        worker_id=f"task-1048-{uuid4().hex[:8]}",
        worker_version="task-1048-test",
        lease_duration=LEASE,
    )


def _run_preview(
    service: SourceCropRunService, worker: LocalJobWorker, kind: str, acknowledge: bool
) -> object:
    run = service.create_preview(kind=kind, scope=SourceCropScope())  # type: ignore[arg-type]
    assert worker.run_once() is JobExecutionResult.COMPLETED
    previewed = service.get(run.id)
    assert previewed.status == "previewed", previewed.error_code
    assert previewed.manifest_checksum_sha256 is not None and previewed.preview_token is not None
    return service.start(
        preview_id=run.id,
        manifest_checksum_sha256=previewed.manifest_checksum_sha256,
        preview_token=previewed.preview_token,
        confirmed=True,
        acknowledge_irreversible=acknowledge,
    )


def test_cropped_originals_are_deleted_once_and_a_lost_state_write_is_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with application_role_database("t1048d", ("a",)) as db:
        first, _ = _seed_eligible(db, tmp_path, 7)
        second, _ = _seed_eligible(db, tmp_path, 8)
        app_sessions = create_session_factory(db.app_engine)
        service = SourceCropRunService(SqlAlchemySourceCropRunRepository(app_sessions))
        worker = _worker(db, tmp_path)
        _run_preview(service, worker, "crop", acknowledge=False)
        assert worker.run_once() is JobExecutionResult.COMPLETED

        run = service.create_preview(kind="original_deletion", scope=SourceCropScope())
        assert worker.run_once() is JobExecutionResult.COMPLETED
        previewed = service.get(run.id)
        assert previewed.eligible_count == 2 and previewed.candidate_bytes > 0
        assert (
            previewed.manifest_checksum_sha256 is not None and previewed.preview_token is not None
        )
        with pytest.raises(JobConflictError) as refused:
            service.start(
                preview_id=run.id,
                manifest_checksum_sha256=previewed.manifest_checksum_sha256,
                preview_token=previewed.preview_token,
                confirmed=True,
                acknowledge_irreversible=False,
            )
        assert refused.value.code == "SOURCE_ORIGINAL_DELETION_ACKNOWLEDGEMENT_REQUIRED"
        started = service.start(
            preview_id=run.id,
            manifest_checksum_sha256=previewed.manifest_checksum_sha256,
            preview_token=previewed.preview_token,
            confirmed=True,
            acknowledge_irreversible=True,
        )

        # The first state write fails after its unlink: the job and run fail,
        # the original is gone and the row is still ``verified``.
        original_mark = SourceImageCropRepository.mark_original_deleted
        calls = {"count": 0}

        def flaky_mark(self: SourceImageCropRepository, checksum: str, **values: object) -> None:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("connection lost before the state write")
            original_mark(self, checksum, **values)  # type: ignore[arg-type]

        monkeypatch.setattr(SourceImageCropRepository, "mark_original_deleted", flaky_mark)
        assert worker.run_once() is JobExecutionResult.FAILED
        assert service.get(run.id).status == "failed"
        ordered = sorted([first, second])
        gone = tmp_path / "data" / "originals" / ordered[0][:2] / f"{ordered[0]}.jpg"
        assert not gone.exists()
        with Session(db.owner_engine) as session:
            row = SourceImageCropRepository(session).get(ordered[0])
            assert row is not None and row.state == "verified"

        _save(app_sessions, requeue_job(_job(app_sessions, started.job_id)))
        assert service.get(run.id).status == "created"
        assert worker.run_once() is JobExecutionResult.COMPLETED

        finished = service.get(run.id)
        assert finished.status == "completed", finished.failures
        assert finished.outcome_counts == {"deleted": 2}
        assert _job(app_sessions, started.job_id).status is JobStatus.COMPLETED
        for checksum in (first, second):
            original = tmp_path / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
            assert not original.exists()
            with Session(db.owner_engine) as session:
                row = SourceImageCropRepository(session).get(checksum)
                assert row is not None and row.state == "original_deleted"
            frame = CanonicalSourceLoader(allow_crop=True).load(
                original, expected_source_checksum_sha256=checksum
            )
            assert frame.crop is not None

        # Guards read the registry on the application role.
        with app_sessions() as session:
            assert deleted_original_checksums(session, [first, second, "0" * 64]) == {
                first,
                second,
            }

        # A second deletion preview finds nothing left to delete.
        again = service.create_preview(kind="original_deletion", scope=SourceCropScope())
        assert worker.run_once() is JobExecutionResult.COMPLETED
        assert service.get(again.id).exclusion_counts == {"ALREADY_DELETED": 2}

        # R10: the last reference to an original takes its crop row with it.
        crop, attestation = cropped_original_relative_paths(first)
        original_path = f"originals/{first[:2]}/{first}.jpg"
        with app_sessions.begin() as session:
            SqlAlchemyCleanupRepository(session)._delete_crop_registry(
                (original_path, crop.as_posix(), attestation.as_posix())
            )
        with app_sessions() as session:
            assert deleted_original_checksums(session, [first, second]) == {second}
