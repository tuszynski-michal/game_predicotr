"""TASK-1048 (D-562): the irreversible ``source_original_deletion`` job."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.source_crop_runs import SourceCropRun, SourceCropScope
from game_predictor_api.domain.jobs import Job, JobConflictError, JobType, create_job
from game_predictor_api.domain.source_crop_eligibility import CropExclusion
from game_predictor_api.storage.source_crop_run_repository import source_crop_job_payload
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError
from game_predictor_worker.source_crop import SourceCropHandler
from game_predictor_worker.source_original_deletion import SourceOriginalDeletionHandler
from test_source_crop_job import (
    BlockCropper,
    FakeCatalog,
    FakeContext,
    FakeRuns,
    _blocks,
    _crop_files,
    _eligibility,
    _execute_job,
    _store_original,
)


@dataclass
class DeletionCatalog(FakeCatalog):
    """FakeCatalog plus the fenced delete unit; ``ineligible_at_delete`` re-check fails."""

    ineligible_at_delete: set[str] = field(default_factory=set)
    commit_lost_after_unlink: set[str] = field(default_factory=set)
    busy: set[str] = field(default_factory=set)
    deleted: list[str] = field(default_factory=list)

    def delete_original_if_still_eligible(
        self,
        checksum: str,
        *,
        attestation_sha256: str,
        game_ids: Sequence[UUID],
        still_covered: Callable[[tuple[tuple[float, float], ...]], bool],
        job_id: UUID,
        lease_token: UUID,
        deleted_at: datetime,
        unlink: Callable[[], None],
    ) -> str:
        if self.lease_lost_at_check:
            raise JobConflictError("JOB_LEASE_LOST", "lease lost")
        if checksum in self.busy:
            return "game_busy"
        row = self.rows.get(checksum)
        item = next(i for i in self.items if i.original_checksum_sha256 == checksum)
        if (
            checksum in self.ineligible_at_delete
            or row is None
            or row.state != "verified"
            or row.attestation_sha256 != attestation_sha256
        ):
            return "not_eligible"
        if not still_covered(item.protected_points):
            return "crop_outdated"
        unlink()
        if checksum in self.commit_lost_after_unlink:
            self.commit_lost_after_unlink.discard(checksum)
            raise RuntimeError("process killed before the state write")
        self.rows[checksum] = replace(row, state="original_deleted", deletion_job_id=job_id)
        self.deleted.append(checksum)
        return "deleted"


def _deletion_run(scope: SourceCropScope | None = None) -> tuple[SourceCropRun, Job]:
    run_id = uuid4()
    plan_job = create_job(
        JobType.SOURCE_ORIGINAL_DELETION,
        game_id=None,
        input_payload=source_crop_job_payload(run_id, kind="original_deletion", phase="plan"),
    )
    run = SourceCropRun(
        id=run_id,
        kind="original_deletion",
        status="planning",
        scope=scope or SourceCropScope(),
        plan_job_id=plan_job.id,
        job_id=None,
        manifest_checksum_sha256=None,
        preview_token=None,
        eligible_count=0,
        excluded_count=0,
        exclusion_counts={},
        candidate_bytes=0,
        estimated_saved_bytes=0,
        processed_count=0,
        succeeded_count=0,
        skipped_count=0,
        failed_count=0,
        saved_bytes=0,
        checkpoint_index=0,
        outcome_counts={},
    )
    return run, plan_job


def _deletion_execute_job(runs: FakeRuns) -> Job:
    job = create_job(
        JobType.SOURCE_ORIGINAL_DELETION,
        game_id=None,
        input_payload=source_crop_job_payload(
            runs.run.id,
            kind="original_deletion",
            phase="execute",
            manifest_checksum_sha256=runs.run.manifest_checksum_sha256,
        ),
    )
    runs.start(job.id)
    return job


def _call(handler: Any, job: Job) -> None:
    handler(cast(JobExecutionContext, FakeContext()), job)


def _cropped(tmp_path: Path, seeds: list[int]) -> tuple[DeletionCatalog, list[str]]:
    """Originals cropped by the real crop handler, registry rows ``verified``."""

    contents = [_blocks(seed) for seed in seeds]
    checksums = [_store_original(tmp_path, content) for content in contents]
    catalog = DeletionCatalog([_eligibility(content) for content in contents])
    crop_run, plan_job = _crop_run()
    runs = FakeRuns(crop_run)
    cropper = BlockCropper()
    handler = SourceCropHandler(runs, catalog, tmp_path, cropper_factory=lambda: cropper)
    _call(handler, plan_job)
    _call(handler, _execute_job(runs))
    assert runs.run.outcome_counts == {"cropped": len(seeds)}
    return catalog, checksums


def _crop_run() -> tuple[SourceCropRun, Job]:
    from test_source_crop_job import _run

    return _run()


def _planned(
    tmp_path: Path, catalog: DeletionCatalog
) -> tuple[SourceOriginalDeletionHandler, FakeRuns]:
    run, plan_job = _deletion_run()
    runs = FakeRuns(run)
    handler = SourceOriginalDeletionHandler(runs, catalog, tmp_path)
    _call(handler, plan_job)
    assert runs.run.status == "previewed"
    return handler, runs


def _original(tmp_path: Path, checksum: str) -> Path:
    return tmp_path / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"


def test_plan_lists_only_verified_eligible_crops_with_bytes(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [1, 2])
    uncropped = _blocks(3)
    _store_original(tmp_path, uncropped)
    blocked = _blocks(4)
    _store_original(tmp_path, blocked)
    catalog.items += [
        _eligibility(uncropped),
        _eligibility(blocked, exclusions=(CropExclusion.ACTIVE_IMAGE_JOB,)),
    ]
    catalog.rows[checksums[1]] = replace(catalog.rows[checksums[1]], state="original_deleted")

    _, runs = _planned(tmp_path, catalog)

    manifest = json.loads((tmp_path / runs.manifest_relative_path).read_bytes())
    assert manifest["kind"] == "original_deletion" and manifest["irreversible"] is True
    assert [entry["checksumSha256"] for entry in manifest["entries"]] == [checksums[0]]
    assert (
        manifest["entries"][0]["attestationSha256"] == catalog.rows[checksums[0]].attestation_sha256
    )
    assert manifest["exclusionCounts"] == {
        "ACTIVE_IMAGE_JOB": 1,
        "ALREADY_DELETED": 1,
        "NOT_CROPPED": 1,
    }
    assert runs.run.candidate_bytes == catalog.rows[checksums[0]].original_size_bytes


def test_execute_deletes_verified_originals_and_keeps_crops(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [10, 11])
    handler, runs = _planned(tmp_path, catalog)
    sizes = {checksum: _original(tmp_path, checksum).stat().st_size for checksum in checksums}

    _call(handler, _deletion_execute_job(runs))

    assert runs.run.status == "completed"
    assert runs.run.outcome_counts == {"deleted": 2}
    assert runs.run.saved_bytes == sum(sizes.values())
    for checksum in checksums:
        assert not _original(tmp_path, checksum).exists()
        crop, attestation = _crop_files(tmp_path, checksum)
        assert crop.is_file() and attestation.is_file()
        assert catalog.rows[checksum].state == "original_deleted"


def test_originals_are_kept_when_anything_changed(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [20, 21, 22, 23, 24])
    handler, runs = _planned(tmp_path, catalog)
    ineligible, changed, broken_crop, recheck, replaced = checksums
    catalog.items = [
        _eligibility(
            _original(tmp_path, ineligible).read_bytes(), exclusions=(CropExclusion.GRID_ISSUE,)
        )
        if item.original_checksum_sha256 == ineligible
        else item
        for item in catalog.items
    ]
    original = _original(tmp_path, changed)
    original.write_bytes(original.read_bytes() + b"x")
    crop, _ = _crop_files(tmp_path, broken_crop)
    crop.write_bytes(crop.read_bytes()[:-10])
    catalog.ineligible_at_delete.add(recheck)
    catalog.rows[replaced] = replace(catalog.rows[replaced], attestation_sha256="f" * 64)

    _call(handler, _deletion_execute_job(runs))

    assert runs.run.outcome_counts == {"notEligible": 2, "failed": 2, "cropChanged": 1}
    codes = {failure["checksumSha256"]: failure["code"] for failure in runs.run.failures}
    assert codes == {changed: "ORIGINAL_CHANGED", broken_crop: "SOURCE_CROP_CHECKSUM_MISMATCH"}
    for checksum in checksums:
        assert _original(tmp_path, checksum).exists()
        assert catalog.rows[checksum].state == "verified"
    assert catalog.deleted == []


def test_an_unlink_without_state_write_is_reconciled_after_restart(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [30])
    handler, runs = _planned(tmp_path, catalog)
    job = _deletion_execute_job(runs)
    checksum = checksums[0]
    size = _original(tmp_path, checksum).stat().st_size
    catalog.commit_lost_after_unlink.add(checksum)

    with pytest.raises(RuntimeError, match="killed"):
        _call(handler, job)
    assert not _original(tmp_path, checksum).exists()
    assert catalog.rows[checksum].state == "verified" and runs.run.checkpoint_index == 0

    _call(handler, job)

    assert catalog.rows[checksum].state == "original_deleted"
    assert runs.run.outcome_counts == {"deleted": 1} and runs.run.saved_bytes == size


def test_a_missing_original_with_an_invalid_crop_is_never_marked(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [40])
    handler, runs = _planned(tmp_path, catalog)
    checksum = checksums[0]
    _original(tmp_path, checksum).unlink()
    _, attestation = _crop_files(tmp_path, checksum)
    attestation.unlink()

    _call(handler, _deletion_execute_job(runs))

    assert runs.run.outcome_counts == {"failed": 1}
    assert runs.run.failures[0]["code"] == "SOURCE_CROP_FILES_MISSING"
    assert catalog.rows[checksum].state == "verified"


def test_a_lost_lease_deletes_nothing(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [50])
    handler, runs = _planned(tmp_path, catalog)
    catalog.lease_lost_at_check = True
    with pytest.raises(JobConflictError) as error:
        _call(handler, _deletion_execute_job(runs))
    assert error.value.code == "JOB_LEASE_LOST"
    assert _original(tmp_path, checksums[0]).exists()


def test_a_crop_job_payload_is_refused(tmp_path: Path) -> None:
    catalog, _ = _cropped(tmp_path, [60])
    run, _ = _deletion_run()
    handler = SourceOriginalDeletionHandler(FakeRuns(run), catalog, tmp_path)
    crop_job = create_job(
        JobType.SOURCE_CROP,
        game_id=None,
        input_payload=source_crop_job_payload(run.id, kind="crop", phase="plan"),
    )
    with pytest.raises(JobHandlerError) as error:
        _call(handler, crop_job)
    assert error.value.code == "SOURCE_CROP_PAYLOAD_INVALID"


def test_a_crop_that_no_longer_covers_the_geometry_keeps_the_original(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [70])
    handler, runs = _planned(tmp_path, catalog)
    checksum = checksums[0]
    content = _original(tmp_path, checksum).read_bytes()
    # A board approved after the crop reaches the image corner.
    catalog.items = [_eligibility(content, points=((2.0, 2.0), (180.0, 150.0)))]

    _call(handler, _deletion_execute_job(runs))

    assert runs.run.outcome_counts == {"cropOutdated": 1}
    assert _original(tmp_path, checksum).exists()
    assert catalog.rows[checksum].state == "verified"


def test_a_deletion_recorded_before_the_checkpoint_counts_once(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [71])
    handler, runs = _planned(tmp_path, catalog)
    job = _deletion_execute_job(runs)
    checksum = checksums[0]
    size = catalog.rows[checksum].original_size_bytes
    _original(tmp_path, checksum).unlink()
    catalog.rows[checksum] = replace(
        catalog.rows[checksum], state="original_deleted", deletion_job_id=job.id
    )

    _call(handler, job)

    assert runs.run.outcome_counts == {"deleted": 1} and runs.run.saved_bytes == size


def test_a_busy_game_skips_the_original(tmp_path: Path) -> None:
    catalog, checksums = _cropped(tmp_path, [72])
    handler, runs = _planned(tmp_path, catalog)
    catalog.busy.add(checksums[0])
    _call(handler, _deletion_execute_job(runs))
    assert runs.run.outcome_counts == {"gameBusy": 1}
    assert _original(tmp_path, checksums[0]).exists()
