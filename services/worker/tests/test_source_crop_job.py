"""TASK-1047 (D-562): the durable ``source_crop`` job, plan and execute phases."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.application.source_crop_runs import SourceCropRun, SourceCropScope
from game_predictor_api.domain.canonical_source import (
    decode_canonical_source_bytes,
    decode_cropped_source_bytes,
)
from game_predictor_api.domain.jobs import Job, JobConflictError, JobStatus, JobType, create_job
from game_predictor_api.domain.source_crop import (
    PixelBox,
    SourceCropAttestation,
    cropped_original_relative_paths,
)
from game_predictor_api.domain.source_crop_eligibility import (
    CropBlobEligibility,
    CropExclusion,
)
from game_predictor_api.storage.source_crop_run_repository import source_crop_job_payload
from game_predictor_worker import source_crop as module
from game_predictor_worker.images.jpegtran import (
    CROP_TIMEOUT_SECONDS,
    JpegtranCropper,
    SourceCropToolError,
    require_jpegtran_version,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError
from game_predictor_worker.source_crop import (
    RegisteredCrop,
    SourceCropHandler,
)
from PIL import Image

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


# ----- fixtures ---------------------------------------------------------------


def _blocks(seed: int, width: int = 320, height: int = 240) -> bytes:
    """A grayscale JPEG of flat 8x8 blocks: any 8-aligned re-encode is exact."""

    rng = np.random.default_rng(seed)
    pixels = np.kron(
        rng.integers(0, 256, (height // 8, width // 8), dtype=np.uint8),
        np.ones((8, 8), dtype=np.uint8),
    )
    buffer = io.BytesIO()
    Image.fromarray(pixels, "L").save(buffer, "JPEG", quality=100)
    return buffer.getvalue()


def _store_original(root: Path, content: bytes) -> str:
    checksum = hashlib.sha256(content).hexdigest()
    path = root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return checksum


def _eligibility(
    content: bytes,
    points: Sequence[tuple[float, float]] = ((100.0, 80.0), (180.0, 150.0)),
    exclusions: tuple[CropExclusion, ...] = (),
) -> CropBlobEligibility:
    checksum = hashlib.sha256(content).hexdigest()
    frame = decode_canonical_source_bytes(content, expected_source_checksum_sha256=checksum)
    return CropBlobEligibility(
        original_checksum_sha256=checksum,
        original_relative_path=f"originals/{checksum[:2]}/{checksum}.jpg",
        oriented_width=frame.source.width,
        oriented_height=frame.source.height,
        exif_orientation=frame.source.exif_orientation,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        source_image_ids=(uuid4(),),
        game_ids=(uuid4(),),
        exclusions=exclusions,
        protected_points=() if exclusions else tuple(points),
    )


class BlockCropper:
    """Python stand-in for jpegtran on block-aligned grayscale originals."""

    version = "python-block-cropper-test"

    def __init__(self, *, corrupt: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self._corrupt = corrupt or set()

    def crop(self, source: Path, target: Path, raw_box: PixelBox) -> None:
        self.calls.append(source.stem)
        with Image.open(source) as image:
            region = image.crop((raw_box.left, raw_box.top, raw_box.right, raw_box.bottom))
            if source.stem in self._corrupt:
                pixels = np.array(region)
                pixels[raw_box.height // 2, raw_box.width // 2] ^= 0xFF
                region = Image.fromarray(pixels, "L")
            region.save(target, "JPEG", quality=100)


@dataclass
class FakeCatalog:
    items: list[CropBlobEligibility]
    rows: dict[str, RegisteredCrop] = field(default_factory=dict)
    attestations: dict[str, SourceCropAttestation] = field(default_factory=dict)
    changed_before_record: set[str] = field(default_factory=set)
    # "after_insert": the row is written but the COMMIT answer is lost;
    # "before_insert": the write fails; "lease_lost": the fence refuses.
    record_failure: str | None = None
    lease_lost_at_check: bool = False
    locks: list[str] = field(default_factory=list)

    def eligibility_page(
        self, *, after: str | None, scope: SourceCropScope, page_size: int
    ) -> list[CropBlobEligibility]:
        ordered = sorted(self.items, key=lambda item: item.original_checksum_sha256)
        selected = [
            item
            for item in ordered
            if (after is None or item.original_checksum_sha256 > after)
            and (
                scope.only_checksums is None
                or item.original_checksum_sha256 in scope.only_checksums
            )
        ]
        return selected[:page_size]

    def registered(self, checksums: Sequence[str]) -> dict[str, RegisteredCrop]:
        return {checksum: self.rows[checksum] for checksum in checksums if checksum in self.rows}

    def current(self, checksum: str) -> tuple[CropBlobEligibility | None, RegisteredCrop | None]:
        item = next((i for i in self.items if i.original_checksum_sha256 == checksum), None)
        return item, self.rows.get(checksum)

    def record_if_still_eligible(
        self,
        attestation: SourceCropAttestation,
        *,
        attestation_sha256: str,
        protected_points: tuple[tuple[float, float], ...],
        job_id: UUID,
        lease_token: UUID,
        verified_at: datetime,
    ) -> bool:
        checksum = attestation.original_checksum_sha256
        if self.record_failure == "lease_lost":
            raise JobConflictError("JOB_LEASE_LOST", "lease lost")
        if self.record_failure == "before_insert":
            raise RuntimeError("connection reset before insert")
        if checksum in self.changed_before_record or checksum in self.rows:
            return False
        self.rows[checksum] = RegisteredCrop(
            job_id,
            attestation.original_size_bytes,
            attestation.crop_size_bytes,
            attestation_sha256=attestation_sha256,
        )
        self.attestations[checksum] = attestation
        if self.record_failure == "after_insert":
            raise RuntimeError("connection reset after commit")
        return True

    @contextmanager
    def blob_lock(self, checksum: str) -> Iterator[None]:
        self.locks.append(checksum)
        yield

    def assert_lease(self, job_id: UUID, lease_token: UUID) -> None:
        if self.lease_lost_at_check:
            raise JobConflictError("JOB_LEASE_LOST", "lease lost")


class FakeRuns:
    def __init__(self, run: SourceCropRun) -> None:
        self.run = run
        self.checkpoints: list[int] = []

    def get_run(self, run_id: UUID) -> SourceCropRun:
        assert run_id == self.run.id
        return self.run

    def mark_previewed(self, run_id: UUID, **values: Any) -> SourceCropRun:
        assert self.run.status == "planning" and values["plan_job_id"] == self.run.plan_job_id
        self.run = replace(
            self.run,
            status="previewed",
            manifest_checksum_sha256=values["manifest_checksum_sha256"],
            preview_token=values["preview_token"],
            eligible_count=values["eligible_count"],
            excluded_count=values["excluded_count"],
            exclusion_counts=dict(values["exclusion_counts"]),
            candidate_bytes=values["candidate_bytes"],
            estimated_saved_bytes=values["estimated_saved_bytes"],
        )
        self.manifest_relative_path = values["manifest_relative_path"]
        return self.run

    def start(self, job_id: UUID) -> None:
        self.run = replace(self.run, status="created", job_id=job_id)

    def manifest_of(self, run_id: UUID, *, job_id: UUID) -> SourceCropRun:
        assert self.run.job_id == job_id
        return self.run

    def mark_processing(self, run_id: UUID, *, job_id: UUID, lease_token: UUID) -> SourceCropRun:
        assert self.run.status in ("created", "processing") and job_id == self.run.job_id
        self.run = replace(self.run, status="processing")
        return self.run

    def checkpoint(
        self,
        run_id: UUID,
        *,
        job_id: UUID,
        lease_token: UUID,
        checkpoint_index: int,
        outcomes: Mapping[str, int],
        succeeded: int,
        skipped: int,
        failed: int,
        saved_bytes: int,
        failures: Sequence[Mapping[str, object]],
    ) -> None:
        self.checkpoints.append(checkpoint_index)
        self.run = replace(
            self.run,
            checkpoint_index=checkpoint_index,
            outcome_counts=dict(outcomes),
            succeeded_count=succeeded,
            skipped_count=skipped,
            failed_count=failed,
            processed_count=succeeded + skipped + failed,
            saved_bytes=saved_bytes,
            failures=tuple(dict(item) for item in failures),
        )

    def complete(self, run_id: UUID, *, job_id: UUID, lease_token: UUID) -> None:
        self.run = replace(self.run, status="completed")


class _Stopped(RuntimeError):
    def __init__(self, status: JobStatus) -> None:
        super().__init__(status.value)
        self.status = status


class FakeContext:
    def __init__(self, *, stop_after: int | None = None, status: JobStatus | None = None) -> None:
        self.checkpoints: list[dict[str, object]] = []
        self.lease_token = uuid4()
        self._stop_after = stop_after
        self._status = status

    def now(self) -> datetime:
        return NOW

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(values)
        if self._stop_after is not None and len(self.checkpoints) >= self._stop_after:
            assert self._status is not None
            raise _Stopped(self._status)


def _run(scope: SourceCropScope | None = None) -> tuple[SourceCropRun, Job]:
    run_id = uuid4()
    plan_job = create_job(
        JobType.SOURCE_CROP,
        game_id=None,
        input_payload=source_crop_job_payload(run_id, kind="crop", phase="plan"),
    )
    run = SourceCropRun(
        id=run_id,
        kind="crop",
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


def _execute_job(runs: FakeRuns) -> Job:
    job = create_job(
        JobType.SOURCE_CROP,
        game_id=None,
        input_payload=source_crop_job_payload(
            runs.run.id,
            kind="crop",
            phase="execute",
            manifest_checksum_sha256=runs.run.manifest_checksum_sha256,
        ),
    )
    runs.start(job.id)
    return job


def _call(handler: SourceCropHandler, context: FakeContext, job: Job) -> None:
    handler(cast(JobExecutionContext, context), job)


def _planned(
    tmp_path: Path,
    catalog: FakeCatalog,
    cropper: BlockCropper | None = None,
    scope: SourceCropScope | None = None,
) -> tuple[SourceCropHandler, FakeRuns, BlockCropper]:
    run, plan_job = _run(scope)
    runs = FakeRuns(run)
    used = cropper or BlockCropper()
    handler = SourceCropHandler(runs, catalog, tmp_path, cropper_factory=lambda: used)
    _call(handler, FakeContext(), plan_job)
    assert runs.run.status == "previewed"
    return handler, runs, used


def _manifest(tmp_path: Path, runs: FakeRuns) -> dict[str, Any]:
    path = tmp_path / runs.manifest_relative_path
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == runs.run.manifest_checksum_sha256
    return cast(dict[str, Any], json.loads(content))


def _crop_files(tmp_path: Path, checksum: str) -> tuple[Path, Path]:
    crop, attestation = cropped_original_relative_paths(checksum)
    return tmp_path / "data" / crop, tmp_path / "data" / attestation


def _touch_crop(tmp_path: Path, checksum: str) -> None:
    for path in _crop_files(tmp_path, checksum):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"registered")


# ----- plan -------------------------------------------------------------------


def test_plan_writes_an_immutable_manifest_with_counts_per_reason(tmp_path: Path) -> None:
    eligible = _blocks(1)
    registered = _blocks(2)
    excluded = _blocks(3)
    missing = _blocks(4)
    for content in (eligible, registered, excluded):
        _store_original(tmp_path, content)
    items = [
        _eligibility(eligible),
        _eligibility(registered),
        _eligibility(
            excluded, exclusions=(CropExclusion.GRID_ISSUE, CropExclusion.GEOMETRY_INCOMPLETE)
        ),
        _eligibility(missing),
    ]
    rows = {items[1].original_checksum_sha256: RegisteredCrop(uuid4(), 10, 5)}
    _, runs, _ = _planned(tmp_path, FakeCatalog(items, rows=rows))

    manifest = _manifest(tmp_path, runs)
    assert [entry["checksumSha256"] for entry in manifest["entries"]] == [
        items[0].original_checksum_sha256
    ]
    entry = manifest["entries"][0]
    assert entry["sizeBytes"] == len(eligible)
    assert 0 < entry["estimatedSavedBytes"] < len(eligible)
    assert manifest["exclusionCounts"] == {
        "ALREADY_CROPPED": 1,
        "GEOMETRY_INCOMPLETE": 1,
        "GRID_ISSUE": 1,
        "ORIGINAL_MISSING": 1,
    }
    assert (runs.run.eligible_count, runs.run.excluded_count) == (1, 3)
    assert runs.run.candidate_bytes == len(eligible)
    assert runs.run.preview_token is not None and len(runs.run.preview_token) == 64
    assert runs.manifest_relative_path == f"data/source-crop-runs/{runs.run.id}/manifest.json"


def test_plan_limit_bounds_the_eligible_entries(tmp_path: Path) -> None:
    contents = [_blocks(seed) for seed in range(10, 14)]
    for content in contents:
        _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content) for content in contents])
    _, runs, _ = _planned(tmp_path, catalog, scope=SourceCropScope(limit=2))

    manifest = _manifest(tmp_path, runs)
    expected = sorted(item.original_checksum_sha256 for item in catalog.items)[:2]
    assert [entry["checksumSha256"] for entry in manifest["entries"]] == expected
    assert runs.run.eligible_count == 2


def test_a_restarted_plan_job_keeps_the_recorded_preview(tmp_path: Path) -> None:
    content = _blocks(20)
    _store_original(tmp_path, content)
    run, plan_job = _run()
    runs = FakeRuns(run)
    handler = SourceCropHandler(
        runs, FakeCatalog([_eligibility(content)]), tmp_path, cropper_factory=BlockCropper
    )
    _call(handler, FakeContext(), plan_job)
    token = runs.run.preview_token
    _call(handler, FakeContext(), plan_job)
    assert runs.run.preview_token == token


# ----- execute ----------------------------------------------------------------


def test_execute_creates_verified_crops_and_leaves_originals_untouched(tmp_path: Path) -> None:
    contents = [_blocks(30), _blocks(31)]
    paths = []
    for content in contents:
        checksum = _store_original(tmp_path, content)
        paths.append(tmp_path / "data" / "originals" / checksum[:2] / f"{checksum}.jpg")
    before = [(path.stat().st_size, path.stat().st_mtime_ns) for path in paths]
    catalog = FakeCatalog([_eligibility(content) for content in contents])
    handler, runs, cropper = _planned(tmp_path, catalog)
    job = _execute_job(runs)

    context = FakeContext()
    _call(handler, context, job)

    assert runs.run.status == "completed"
    assert runs.run.succeeded_count == 2 and runs.run.outcome_counts == {"cropped": 2}
    assert runs.run.checkpoint_index == 2
    assert [(path.stat().st_size, path.stat().st_mtime_ns) for path in paths] == before
    for content, path in zip(contents, paths, strict=True):
        checksum = hashlib.sha256(content).hexdigest()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
        crop, attestation = _crop_files(tmp_path, checksum)
        frame = decode_cropped_source_bytes(
            crop.read_bytes(), attestation.read_bytes(), expected_source_checksum_sha256=checksum
        )
        box = catalog.attestations[checksum].crop_box
        original = decode_canonical_source_bytes(content, expected_source_checksum_sha256=checksum)
        assert np.array_equal(
            frame.rgb[box.top : box.bottom, box.left : box.right],
            original.rgb[box.top : box.bottom, box.left : box.right],
        )
        assert catalog.rows[checksum].job_id == job.id
        assert not list(crop.parent.glob("*.part"))
    saved = sum(row.original_size_bytes - row.crop_size_bytes for row in catalog.rows.values())
    assert runs.run.saved_bytes == saved > 0
    assert context.checkpoints[-1]["stage"] == "source_crop_execute"


def test_a_failed_verification_leaves_no_files_and_the_run_continues(tmp_path: Path) -> None:
    contents = [_blocks(40), _blocks(41)]
    for content in contents:
        _store_original(tmp_path, content)
    bad = hashlib.sha256(contents[0]).hexdigest()
    catalog = FakeCatalog([_eligibility(content) for content in contents])
    handler, runs, _ = _planned(tmp_path, catalog, BlockCropper(corrupt={bad}))
    _call(handler, FakeContext(), _execute_job(runs))

    assert runs.run.status == "completed"
    assert (runs.run.succeeded_count, runs.run.failed_count) == (1, 1)
    assert runs.run.failures[0]["checksumSha256"] == bad
    assert runs.run.failures[0]["code"] == "SOURCE_CROP_VERIFICATION_FAILED"
    crop, attestation = _crop_files(tmp_path, bad)
    assert not crop.exists() and not attestation.exists()
    assert not list(crop.parent.glob("*")) if crop.parent.exists() else True
    assert bad not in catalog.rows


def test_restart_resumes_after_the_checkpoint_without_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "CHECKPOINT_EVERY", 1)
    contents = [_blocks(seed) for seed in (50, 51, 52)]
    for content in contents:
        _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content) for content in contents])
    handler, runs, cropper = _planned(tmp_path, catalog)
    job = _execute_job(runs)

    with pytest.raises(_Stopped):
        _call(handler, FakeContext(stop_after=1, status=JobStatus.PROCESSING), job)
    assert runs.run.status == "processing" and runs.run.checkpoint_index == 1
    _call(handler, FakeContext(), job)

    assert runs.run.status == "completed"
    assert runs.run.outcome_counts == {"cropped": 3}
    assert sorted(cropper.calls) == sorted(item.original_checksum_sha256 for item in catalog.items)


def test_a_crop_recorded_by_this_job_before_a_checkpoint_counts_once(tmp_path: Path) -> None:
    content = _blocks(55)
    _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content)])
    handler, runs, cropper = _planned(tmp_path, catalog)
    job = _execute_job(runs)
    checksum = catalog.items[0].original_checksum_sha256
    catalog.rows[checksum] = RegisteredCrop(job.id, 1000, 400)
    _touch_crop(tmp_path, checksum)

    _call(handler, FakeContext(), job)

    assert cropper.calls == []
    assert runs.run.outcome_counts == {"cropped": 1} and runs.run.saved_bytes == 600


def test_ineligible_or_changed_originals_are_skipped_and_cleaned(tmp_path: Path) -> None:
    contents = [_blocks(60), _blocks(61), _blocks(62)]
    for content in contents:
        _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content) for content in contents])
    handler, runs, _ = _planned(tmp_path, catalog)
    first, second, third = (item.original_checksum_sha256 for item in catalog.items)
    catalog.items[0] = _eligibility(contents[0], exclusions=(CropExclusion.ACTIVE_IMAGE_JOB,))
    catalog.changed_before_record.add(second)
    catalog.rows[third] = RegisteredCrop(uuid4(), 10, 5)
    _touch_crop(tmp_path, third)

    _call(handler, FakeContext(), _execute_job(runs))

    assert runs.run.outcome_counts == {"notEligible": 2, "alreadyCropped": 1}
    assert runs.run.skipped_count == 3
    for checksum in (first, second):
        crop, attestation = _crop_files(tmp_path, checksum)
        assert not crop.exists() and not attestation.exists()


def test_a_crop_without_benefit_is_skipped(tmp_path: Path) -> None:
    content = _blocks(70)
    _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content, points=((52.0, 52.0), (300.0, 200.0)))])
    handler, runs, _ = _planned(tmp_path, catalog)
    _call(handler, FakeContext(), _execute_job(runs))

    assert runs.run.outcome_counts == {"notBeneficial": 1}
    crop, _ = _crop_files(tmp_path, catalog.items[0].original_checksum_sha256)
    assert not crop.exists()


def test_a_missing_tool_fails_before_any_file_is_written(tmp_path: Path) -> None:
    content = _blocks(80)
    _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content)])
    run, plan_job = _run()
    runs = FakeRuns(run)

    def unavailable() -> BlockCropper:
        raise SourceCropToolError("SOURCE_CROP_TOOL_UNAVAILABLE", "jpegtran was not found.")

    handler = SourceCropHandler(runs, catalog, tmp_path, cropper_factory=unavailable)
    _call(handler, FakeContext(), plan_job)
    with pytest.raises(JobHandlerError) as error:
        _call(handler, FakeContext(), _execute_job(runs))

    assert error.value.code == "SOURCE_CROP_TOOL_UNAVAILABLE"
    # The job failure reaches the run through synchronize_source_crop_job.
    assert runs.run.status == "created"
    assert not (tmp_path / "data" / "originals-cropped").exists()


def test_a_changed_manifest_fails_the_run(tmp_path: Path) -> None:
    content = _blocks(90)
    _store_original(tmp_path, content)
    handler, runs, _ = _planned(tmp_path, FakeCatalog([_eligibility(content)]))
    path = tmp_path / runs.manifest_relative_path
    path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(JobHandlerError) as error:
        _call(handler, FakeContext(), _execute_job(runs))
    assert error.value.code == "SOURCE_CROP_MANIFEST_CHANGED"
    assert not (tmp_path / "data" / "originals-cropped").exists()


def test_a_finished_run_refuses_a_bare_job_retry(tmp_path: Path) -> None:
    content = _blocks(95)
    _store_original(tmp_path, content)
    handler, runs, _ = _planned(tmp_path, FakeCatalog([_eligibility(content)]))
    job = _execute_job(runs)
    runs.run = replace(runs.run, status="failed")
    with pytest.raises(JobHandlerError) as error:
        _call(handler, FakeContext(), job)
    assert error.value.code == "SOURCE_CROP_RUN_FINISHED"


def test_every_blob_is_processed_under_its_lock(tmp_path: Path) -> None:
    contents = [_blocks(96), _blocks(97)]
    for content in contents:
        _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content) for content in contents])
    handler, runs, _ = _planned(tmp_path, catalog)
    _call(handler, FakeContext(), _execute_job(runs))
    assert sorted(catalog.locks) == sorted(item.original_checksum_sha256 for item in catalog.items)


def test_a_lost_commit_answer_keeps_the_recorded_crop(tmp_path: Path) -> None:
    content = _blocks(100)
    checksum = _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content)], record_failure="after_insert")
    handler, runs, _ = _planned(tmp_path, catalog)
    _call(handler, FakeContext(), _execute_job(runs))

    assert runs.run.outcome_counts == {"cropped": 1}
    crop, attestation = _crop_files(tmp_path, checksum)
    assert crop.is_file() and attestation.is_file()
    assert (
        catalog.rows[checksum].attestation_sha256
        == hashlib.sha256(attestation.read_bytes()).hexdigest()
    )


def test_a_failed_registry_write_removes_its_files_and_fails_the_job(tmp_path: Path) -> None:
    content = _blocks(101)
    checksum = _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content)], record_failure="before_insert")
    handler, runs, _ = _planned(tmp_path, catalog)
    with pytest.raises(RuntimeError, match="before insert"):
        _call(handler, FakeContext(), _execute_job(runs))
    crop, attestation = _crop_files(tmp_path, checksum)
    assert not crop.exists() and not attestation.exists()
    assert runs.run.checkpoint_index == 0


@pytest.mark.parametrize("where", ["record", "check"])
def test_a_lost_lease_never_leaves_or_removes_registered_files(tmp_path: Path, where: str) -> None:
    content = _blocks(102)
    checksum = _store_original(tmp_path, content)
    catalog = FakeCatalog(
        [_eligibility(content)],
        record_failure="lease_lost" if where == "record" else None,
        lease_lost_at_check=where == "check",
    )
    handler, runs, cropper = _planned(tmp_path, catalog)
    with pytest.raises(JobConflictError) as error:
        _call(handler, FakeContext(), _execute_job(runs))
    assert error.value.code == "JOB_LEASE_LOST"
    crop, attestation = _crop_files(tmp_path, checksum)
    assert not crop.exists() and not attestation.exists()
    assert checksum not in catalog.rows
    assert cropper.calls == ([] if where == "check" else [checksum])


def test_a_registered_crop_without_files_is_reported(tmp_path: Path) -> None:
    content = _blocks(103)
    checksum = _store_original(tmp_path, content)
    catalog = FakeCatalog([_eligibility(content)])
    handler, runs, cropper = _planned(tmp_path, catalog)
    catalog.rows[checksum] = RegisteredCrop(uuid4(), 1000, 400, attestation_sha256="e" * 64)
    _call(handler, FakeContext(), _execute_job(runs))

    assert cropper.calls == []
    assert runs.run.failed_count == 1
    assert runs.run.failures[0]["code"] == "SOURCE_CROP_FILES_MISSING"


# ----- jpegtran -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("output", "accepted"),
    [
        ("libjpeg-turbo version 3.2.0 (build 20260630)\n", True),
        ("libjpeg-turbo version 3.2.0", True),
        ("libjpeg-turbo version 3.2.01 (build 1)", False),
        ("libjpeg-turbo version 3.1.2 (build 20250101)", False),
        ("IJG JPEG 9f", False),
        ("", False),
    ],
)
def test_jpegtran_version_must_match_the_approved_release(output: str, accepted: bool) -> None:
    if accepted:
        assert require_jpegtran_version(output, "3.2.0").startswith("libjpeg-turbo version 3.2.0")
    else:
        with pytest.raises(SourceCropToolError) as error:
            require_jpegtran_version(output, "3.2.0")
        assert error.value.code == "SOURCE_CROP_TOOL_UNAVAILABLE"


def test_jpegtran_crop_uses_the_30_second_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_run(arguments: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        seen.update(options, arguments=arguments)
        raise subprocess.TimeoutExpired(arguments, 30)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cropper = JpegtranCropper(executable=tmp_path / "jpegtran.exe", version="v")
    with pytest.raises(SourceCropToolError) as error:
        cropper.crop(tmp_path / "a.jpg", tmp_path / "b.jpg", PixelBox(0, 0, 16, 16))
    assert error.value.code == "SOURCE_CROP_TOOL_FAILED"
    assert seen["timeout"] == CROP_TIMEOUT_SECONDS == 30
    assert seen["arguments"][1:6] == ["-copy", "all", "-optimize", "-crop", "16x16+0+0"]  # type: ignore[index]


def test_real_jpegtran_with_another_expected_version_is_refused() -> None:
    _jpegtran()
    with pytest.raises(SourceCropToolError) as error:
        JpegtranCropper.resolve({**os.environ, "GAME_PREDICTOR_JPEGTRAN_VERSION": "9.9.9"})
    assert error.value.code == "SOURCE_CROP_TOOL_UNAVAILABLE"


def test_jpegtran_resolution_refuses_a_missing_tool(tmp_path: Path) -> None:
    with pytest.raises(SourceCropToolError) as error:
        JpegtranCropper.resolve({"GAME_PREDICTOR_JPEGTRAN_PATH": str(tmp_path / "none.exe")})
    assert error.value.code == "SOURCE_CROP_TOOL_UNAVAILABLE"


def _jpegtran() -> JpegtranCropper:
    try:
        return JpegtranCropper.resolve()
    except SourceCropToolError:
        pytest.skip("jpegtran (libjpeg-turbo) is not installed")


def test_real_jpegtran_crops_a_rotated_subsampled_original(tmp_path: Path) -> None:
    cropper = _jpegtran()
    rng = np.random.default_rng(7)
    pixels = rng.integers(0, 256, size=(480, 640, 3), dtype=np.uint8)
    exif = Image.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, "JPEG", quality=90, subsampling=2, exif=exif.tobytes())
    content = buffer.getvalue()
    checksum = _store_original(tmp_path, content)
    # Oriented frame is 480 x 640 (portrait).
    catalog = FakeCatalog([_eligibility(content, points=((120.3, 170.0), (330.0, 410.7)))])
    run, plan_job = _run()
    runs = FakeRuns(run)
    handler = SourceCropHandler(runs, catalog, tmp_path, cropper_factory=lambda: cropper)
    _call(handler, FakeContext(), plan_job)
    _call(handler, FakeContext(), _execute_job(runs))

    assert runs.run.outcome_counts == {"cropped": 1}, runs.run.failures
    attestation = catalog.attestations[checksum]
    assert attestation.original_exif_orientation == 6
    assert attestation.tool_version.startswith("libjpeg-turbo version ")
    crop, document = _crop_files(tmp_path, checksum)
    frame = decode_cropped_source_bytes(
        crop.read_bytes(), document.read_bytes(), expected_source_checksum_sha256=checksum
    )
    assert frame.rgb.shape == (640, 480, 3)
