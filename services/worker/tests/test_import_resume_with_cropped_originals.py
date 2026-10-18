"""TASK-1052 (D-563, R11): an import retry after its originals were replaced by crops.

A retry re-runs ``ensure_original`` for every original of the import manifest.
An original whose registry row is ``original_deleted`` and whose crop attests
it is neither copied back nor fails the retry. Without that row, with a crop
that does not attest it, or in a new import of the same file, nothing changes:
the original is copied from its source as before (R10).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import cast

import pytest
from game_predictor_api.domain.source_crop import cropped_original_relative_paths
from game_predictor_worker.images.source_ingestion import (
    ImageSourceIngestionHandler,
    ManagedOriginalStore,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError
from game_predictor_worker.source_crop import SourceCropHandler
from test_image_source_ingestion import RecordingContext, _job
from test_source_crop_job import (
    BlockCropper,
    FakeCatalog,
    FakeContext,
    FakeRuns,
    _blocks,
    _eligibility,
    _execute_job,
    _run,
)


def _imported_and_cropped(tmp_path: Path) -> tuple[Path, Path, object, str, Path]:
    """An image import whose only original was cropped and then deleted."""

    source = tmp_path / "source"
    source.mkdir()
    content = _blocks(42)
    (source / "page-001.jpg").write_bytes(content)
    artifact_root = tmp_path / "artifacts"
    job = _job(source)
    handler = ImageSourceIngestionHandler(ManagedOriginalStore(artifact_root))
    handler(RecordingContext(), job)  # type: ignore[arg-type]
    checksum = hashlib.sha256(content).hexdigest()
    original = artifact_root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    assert original.read_bytes() == content

    run, plan_job = _run()
    runs = FakeRuns(run)
    cropper = BlockCropper()
    crop_handler = SourceCropHandler(
        runs, FakeCatalog([_eligibility(content)]), artifact_root, cropper_factory=lambda: cropper
    )
    crop_handler(cast(JobExecutionContext, FakeContext()), plan_job)
    crop_handler(cast(JobExecutionContext, FakeContext()), _execute_job(runs))
    assert runs.run.outcome_counts == {"cropped": 1}
    original.unlink()  # what the deletion job does after its checks
    return source, artifact_root, job, checksum, original


def _crop_files(artifact_root: Path, checksum: str) -> tuple[Path, Path]:
    crop, attestation = cropped_original_relative_paths(checksum)
    return artifact_root / "data" / crop, artifact_root / "data" / attestation


@pytest.mark.parametrize("staging_present", [False, True])
def test_a_retry_keeps_an_original_replaced_by_its_attested_crop(
    tmp_path: Path, staging_present: bool
) -> None:
    source, artifact_root, job, checksum, original = _imported_and_cropped(tmp_path)
    if not staging_present:
        shutil.rmtree(source)  # browser staging is removed 24 h after the handoff
    crop, attestation = _crop_files(artifact_root, checksum)
    before = (crop.read_bytes(), attestation.read_bytes())

    resumed = RecordingContext()
    ImageSourceIngestionHandler(ManagedOriginalStore(artifact_root)).ingest(
        resumed,  # type: ignore[arg-type]
        job,  # type: ignore[arg-type]
        replaced_originals=frozenset({checksum}),
    )

    assert resumed.checkpoints[-1]["stage"] == "image_originals_copied"
    assert resumed.checkpoints[-1]["current"] == 1
    assert not original.exists()  # neither copied back nor failed
    assert (crop.read_bytes(), attestation.read_bytes()) == before


@pytest.mark.parametrize("damage", ["attestation", "crop", "foreign"])
def test_a_crop_that_does_not_attest_the_original_changes_nothing(
    tmp_path: Path, damage: str
) -> None:
    source, artifact_root, job, checksum, original = _imported_and_cropped(tmp_path)
    crop, attestation = _crop_files(artifact_root, checksum)
    if damage == "attestation":
        document = json.loads(attestation.read_bytes())
        document["crop"]["edgeMismatchPixels"] += 1  # not resealed: checksum fails
        attestation.write_bytes(json.dumps(document).encode("utf-8"))
    elif damage == "crop":
        crop.write_bytes(crop.read_bytes() + b"\0")
    else:
        document = json.loads(attestation.read_bytes())
        document["original"]["sizeBytes"] += 1
        attestation.write_bytes(json.dumps(document).encode("utf-8"))
    shutil.rmtree(source)

    with pytest.raises(JobHandlerError) as error:
        ImageSourceIngestionHandler(ManagedOriginalStore(artifact_root)).ingest(
            RecordingContext(),  # type: ignore[arg-type]
            job,  # type: ignore[arg-type]
            replaced_originals=frozenset({checksum}),
        )

    assert error.value.code == "IMAGE_SOURCE_UNAVAILABLE"
    assert not original.exists()


def test_without_an_original_deleted_row_a_valid_crop_changes_nothing(tmp_path: Path) -> None:
    source, artifact_root, job, checksum, original = _imported_and_cropped(tmp_path)
    shutil.rmtree(source)

    with pytest.raises(JobHandlerError) as error:
        ImageSourceIngestionHandler(ManagedOriginalStore(artifact_root)).ingest(
            RecordingContext(),  # type: ignore[arg-type]
            job,  # type: ignore[arg-type]
        )

    assert error.value.code == "IMAGE_SOURCE_UNAVAILABLE"


def test_a_new_import_of_the_same_file_restores_the_original(tmp_path: Path) -> None:
    source, artifact_root, _job_unused, checksum, original = _imported_and_cropped(tmp_path)
    store = ManagedOriginalStore(artifact_root)
    new_import = _job(source)
    assert not store.manifest_exists(new_import)

    ImageSourceIngestionHandler(store)(RecordingContext(), new_import)  # type: ignore[arg-type]

    assert hashlib.sha256(original.read_bytes()).hexdigest() == checksum


def test_a_reprocess_sees_originals_replaced_in_the_source_manifest(tmp_path: Path) -> None:
    _source, artifact_root, job, checksum, _original = _imported_and_cropped(tmp_path)
    store = ManagedOriginalStore(artifact_root)

    assert store.originals_replaced_in_manifest(job.id) == (checksum,)
    _, attestation = _crop_files(artifact_root, checksum)
    attestation.unlink()
    assert store.originals_replaced_in_manifest(job.id) == ()


def test_with_a_damaged_crop_and_staging_the_original_is_restored(tmp_path: Path) -> None:
    source, artifact_root, job, checksum, original = _imported_and_cropped(tmp_path)
    crop, _ = _crop_files(artifact_root, checksum)
    crop.write_bytes(b"not the attested crop")

    ImageSourceIngestionHandler(ManagedOriginalStore(artifact_root)).ingest(
        RecordingContext(),  # type: ignore[arg-type]
        job,  # type: ignore[arg-type]
        replaced_originals=frozenset({checksum}),
    )

    assert hashlib.sha256(original.read_bytes()).hexdigest() == checksum


class _Reached(Exception):
    """Raised right after ingestion: everything later is outside this test."""


class _WorkflowContext(RecordingContext):
    def __init__(self, job: object) -> None:
        super().__init__()
        self.job = job
        self.lease_token = None

    def now(self) -> object:
        return getattr(self.job, "created_at", None)


def _workflow(artifact_root: Path, replaced: frozenset[str], calls: list[str]) -> object:
    from game_predictor_worker.images.production_workflow import ProductionImageImportWorkflow

    workflow = ProductionImageImportWorkflow.__new__(ProductionImageImportWorkflow)
    store = ManagedOriginalStore(artifact_root)
    workflow._artifact_root = artifact_root  # type: ignore[attr-defined]
    workflow._original_store = store  # type: ignore[attr-defined]
    workflow._source_handler = ImageSourceIngestionHandler(store)  # type: ignore[attr-defined]

    def replaced_originals(_manifest: object) -> frozenset[str]:
        calls.append("registry")
        return replaced

    def reached(*_args: object, **_kwargs: object) -> None:
        raise _Reached

    workflow._replaced_originals = replaced_originals  # type: ignore[attr-defined,method-assign]
    workflow._record_browser_staging_handoff = reached  # type: ignore[attr-defined,method-assign]
    return workflow


@pytest.mark.parametrize("staging_present", [False, True])
def test_the_import_workflow_retry_keeps_crops_and_a_new_import_restores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, staging_present: bool
) -> None:
    """The workflow asks the registry only on a retry of the same import."""

    import game_predictor_worker.images.production_workflow as workflow_module

    monkeypatch.setattr(workflow_module, "_require_virtual_geometry_rollout", lambda *_: None)
    monkeypatch.setattr(workflow_module, "_geometry_rollout_snapshot", lambda *_: None)
    source, artifact_root, job, checksum, original = _imported_and_cropped(tmp_path)
    if not staging_present:
        shutil.rmtree(source)
    calls: list[str] = []

    retry = _workflow(artifact_root, frozenset({checksum}), calls)
    with pytest.raises(_Reached):
        retry(_WorkflowContext(job), job)  # type: ignore[operator]
    assert calls == ["registry"] and not original.exists()

    if not staging_present:
        return
    new_import = _job(source)
    calls.clear()
    fresh = _workflow(artifact_root, frozenset({checksum}), calls)
    with pytest.raises(_Reached):
        fresh(_WorkflowContext(new_import), new_import)  # type: ignore[operator]
    assert calls == [] and hashlib.sha256(original.read_bytes()).hexdigest() == checksum
