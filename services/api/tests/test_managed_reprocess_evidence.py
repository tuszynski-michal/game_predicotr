import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobType,
    checkpoint_job,
    complete_job,
    create_job,
    request_job_cancellation,
    start_job,
)
from game_predictor_api.schemas.jobs import JobResponse
from test_jobs_domain import MemoryJobRepository

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)


def _write_json(path: Path, value: object) -> tuple[str, str]:
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest(), path.as_posix()


def _terminal_import(
    game_id: UUID,
    *,
    selection_id: UUID,
    source_manifest_sha256: str,
    page_descriptor: dict[str, object] | None,
    managed_source_job_id: UUID | None = None,
) -> Job:
    payload: dict[str, object] = {
        "schema_version": 5 if managed_source_job_id is None else 4,
        "import_kind": "image_directory",
        "source_selection_id": str(selection_id),
        "source_directory": "C:/managed-source",
        "source_display_name": "seq import",
        "source_manifest_sha256": source_manifest_sha256,
        "pipeline_fingerprint": "a" * 64,
    }
    if page_descriptor is not None:
        payload["page_geometry_manifest"] = page_descriptor
    if managed_source_job_id is not None:
        payload["managed_source_job_id"] = str(managed_source_job_id)
    return request_job_cancellation(
        create_job(JobType.IMPORT, game_id=game_id, input_payload=payload, created_at=NOW)
    )


def _completed_preflight(
    game_id: UUID,
    *,
    selection_id: UUID,
    source_manifest_sha256: str,
    geometry_checksum: str,
    geometry_relative_path: str,
) -> Job:
    job = create_job(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "source_selection_id": str(selection_id),
            "source_directory": "C:/managed-source",
            "source_display_name": "seq import",
            "source_manifest_sha256": source_manifest_sha256,
            "page_registration_profile": {},
            "page_geometry_overrides": {},
            "canonical_sequence_numbers": [],
        },
        created_at=NOW,
    )
    lease = uuid4()
    job = start_job(
        job,
        worker_version="test",
        worker_id="test",
        lease_token=lease,
        lease_expires_at=NOW + timedelta(minutes=1),
        started_at=NOW,
    )
    job = checkpoint_job(
        job,
        lease_token=lease,
        checkpoint_payload={
            "schema_version": 1,
            "complete": True,
            "geometry_manifest_checksum_sha256": geometry_checksum,
            "geometry_manifest_relative_path": geometry_relative_path,
        },
        stage="page_geometry_manifest_ready",
        current=1,
        total=1,
        success_count=1,
        failure_count=0,
        review_count=0,
        updated_at=NOW,
    )
    return complete_job(job, lease_token=lease, finished_at=NOW)


def _write_managed_manifest(
    artifact_root: Path,
    source: Job,
    *,
    source_checksum: str,
) -> str:
    path = artifact_root / "data" / "originals" / "manifests" / f"{source.id}.json"
    checksum, _ = _write_json(
        path,
        {
            "contractVersion": "image-source-ingestion-v1",
            "gameId": str(source.game_id),
            "jobId": str(source.id),
            "originals": [
                {
                    "checksumSha256": source_checksum,
                    "managedRelativePath": f"data/originals/aa/{source_checksum}.jpg",
                    "sequenceRangeEnd": 9,
                    "sequenceRangeStart": 1,
                    "sequenceRangeSource": "filename",
                    "sizeBytes": 100,
                    "sourceRelativePath": "seq_1-9.jpg",
                }
            ],
            "schemaVersion": 1,
            "sourceDirectory": "C:/managed-source",
        },
    )
    return checksum


def _arrange_source_with_evidence(
    tmp_path: Path,
) -> tuple[MemoryJobRepository, Job, str, dict[str, object]]:
    game_id = uuid4()
    selection_id = uuid4()
    source_manifest_sha256 = "b" * 64
    source_checksum = "c" * 64
    artifact_root = tmp_path / "artifacts"
    page_path = artifact_root / "data" / "page-geometry-manifests" / "page.json"
    page_checksum, _ = _write_json(
        page_path,
        {
            "entries": {
                source_checksum: {
                    "boardRedEdgeCoverages": [1.0] * 9,
                    "imageHeight": 1_920,
                    "imageWidth": 1_080,
                    "quads": [[]] * 9,
                    "sourceRelativePath": "seq_1-9.jpg",
                    "status": "registered",
                }
            },
            "gameId": str(game_id),
            "registeredSourceCount": 1,
            "reviewRequiredSourceCount": 0,
            "schemaVersion": 2,
            "skippedHumanResolvedSourceCount": 0,
            "sourceCount": 1,
            "sourceManifestChecksumSha256": source_manifest_sha256,
            "sourceSelectionId": str(selection_id),
            "version": "page-geometry-preflight-v2-auto-anchor",
        },
    )
    descriptor: dict[str, object] = {
        "checksumSha256": page_checksum,
        "relativePath": "data/page-geometry-manifests/page.json",
    }
    source = _terminal_import(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256=source_manifest_sha256,
        page_descriptor=None,
    )
    preflight = _completed_preflight(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256=source_manifest_sha256,
        geometry_checksum=page_checksum,
        geometry_relative_path="data/page-geometry-manifests/page.json",
    )
    descriptor["preflightJobId"] = str(preflight.id)
    source = replace(
        source,
        input_payload={**source.input_payload, "page_geometry_manifest": descriptor},
    )
    repository = MemoryJobRepository(game_id)
    repository.add_job(preflight)
    repository.add_job(source)
    _write_managed_manifest(artifact_root, source, source_checksum=source_checksum)
    return repository, source, source_checksum, descriptor


def test_managed_reprocess_v6_pins_exact_source_and_page_manifests(tmp_path: Path) -> None:
    repository, source, _source_checksum, descriptor = _arrange_source_with_evidence(tmp_path)
    service = JobService(repository, artifact_root=tmp_path / "artifacts")

    job = service.create_managed_image_reprocess_job(source.id, pipeline_fingerprint="d" * 64)

    assert job.input_payload["schema_version"] == 6
    assert job.input_payload["page_geometry_manifest"] == descriptor
    assert job.input_payload["source_manifest_sha256"] == "b" * 64
    assert len(str(job.input_payload["managed_source_manifest_checksum_sha256"])) == 64
    assert job.input_payload["geometry_systemic_guard_policy"] == {
        "policyVersion": "image-geometry-systemic-guard-v1",
        "minimumSourceCount": 100,
        "minimumActiveBoardCount": 500,
        "sampleSourceLimit": 25,
        "minimumFinalCellGridReadyRate": 0.98,
        "requireZeroInvariantViolations": True,
    }
    assert JobResponse.from_domain(job).input_payload.schema_version == 6


def test_managed_reprocess_v6_resolves_page_manifest_through_v4_lineage(tmp_path: Path) -> None:
    repository, root, source_checksum, descriptor = _arrange_source_with_evidence(tmp_path)
    child = _terminal_import(
        repository.game_id,
        selection_id=UUID(str(root.input_payload["source_selection_id"])),
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
        managed_source_job_id=root.id,
    )
    repository.add_job(child)
    _write_managed_manifest(tmp_path / "artifacts", child, source_checksum=source_checksum)
    service = JobService(repository, artifact_root=tmp_path / "artifacts")

    job = service.create_managed_image_reprocess_job(child.id, pipeline_fingerprint="d" * 64)

    assert job.input_payload["schema_version"] == 6
    assert job.input_payload["managed_source_job_id"] == str(child.id)
    assert job.input_payload["page_geometry_manifest"] == descriptor


def test_managed_reprocess_rejects_missing_exact_page_manifest(tmp_path: Path) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    source = _terminal_import(
        game_id,
        selection_id=uuid4(),
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
    )
    repository.add_job(source)
    _write_managed_manifest(tmp_path / "artifacts", source, source_checksum="c" * 64)
    service = JobService(repository, artifact_root=tmp_path / "artifacts")

    with pytest.raises(JobConflictError) as captured:
        service.create_managed_image_reprocess_job(source.id, pipeline_fingerprint="d" * 64)

    assert captured.value.code == "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_REQUIRED"


def test_managed_reprocess_rejects_partial_page_manifest_inventory(tmp_path: Path) -> None:
    repository, source, _source_checksum, _descriptor = _arrange_source_with_evidence(tmp_path)
    page_path = tmp_path / "artifacts" / "data" / "page-geometry-manifests" / "page.json"
    value = json.loads(page_path.read_bytes())
    value["entries"] = {}
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    page_path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    raw_descriptor = source.input_payload["page_geometry_manifest"]
    assert isinstance(raw_descriptor, dict)
    preflight_id = UUID(str(raw_descriptor["preflightJobId"]))
    preflight = repository.get_job(preflight_id)
    assert preflight is not None
    descriptor = {
        "checksumSha256": checksum,
        "preflightJobId": str(preflight_id),
        "relativePath": "data/page-geometry-manifests/page.json",
    }
    repository.items[source.id] = replace(
        source,
        input_payload={**source.input_payload, "page_geometry_manifest": descriptor},
    )
    repository.items[preflight_id] = replace(
        preflight,
        checkpoint_payload={
            **(preflight.checkpoint_payload or {}),
            "geometry_manifest_checksum_sha256": checksum,
        },
    )
    service = JobService(repository, artifact_root=tmp_path / "artifacts")

    with pytest.raises(JobConflictError) as captured:
        service.create_managed_image_reprocess_job(source.id, pipeline_fingerprint="d" * 64)

    assert captured.value.code == "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE"


def test_managed_reprocess_rejects_page_manifest_checksum_drift(tmp_path: Path) -> None:
    repository, source, _source_checksum, _descriptor = _arrange_source_with_evidence(tmp_path)
    page_path = tmp_path / "artifacts" / "data" / "page-geometry-manifests" / "page.json"
    page_path.write_bytes(page_path.read_bytes() + b" ")
    service = JobService(repository, artifact_root=tmp_path / "artifacts")

    with pytest.raises(JobConflictError) as captured:
        service.create_managed_image_reprocess_job(source.id, pipeline_fingerprint="d" * 64)

    assert captured.value.code == "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE"


def test_managed_reprocess_rejects_cyclic_lineage(tmp_path: Path) -> None:
    game_id = uuid4()
    selection_id = uuid4()
    first = _terminal_import(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
        managed_source_job_id=uuid4(),
    )
    second = _terminal_import(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
        managed_source_job_id=first.id,
    )
    first = replace(
        first,
        input_payload={**first.input_payload, "managed_source_job_id": str(second.id)},
    )
    repository = MemoryJobRepository(game_id)
    repository.add_job(first)
    repository.add_job(second)
    _write_managed_manifest(tmp_path / "artifacts", first, source_checksum="c" * 64)
    service = JobService(repository, artifact_root=tmp_path / "artifacts")

    with pytest.raises(JobConflictError) as captured:
        service.create_managed_image_reprocess_job(first.id, pipeline_fingerprint="d" * 64)

    assert captured.value.code == "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE"


def test_managed_reprocess_rejects_foreign_game_lineage(tmp_path: Path) -> None:
    game_id = uuid4()
    foreign_game_id = uuid4()
    selection_id = uuid4()
    foreign = _terminal_import(
        foreign_game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
    )
    source = _terminal_import(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
        managed_source_job_id=foreign.id,
    )
    repository = MemoryJobRepository(game_id)
    repository.add_job(source)
    repository.add_job(foreign)
    _write_managed_manifest(tmp_path / "artifacts", source, source_checksum="c" * 64)
    service = JobService(repository, artifact_root=tmp_path / "artifacts")

    with pytest.raises(JobConflictError) as captured:
        service.create_managed_image_reprocess_job(source.id, pipeline_fingerprint="d" * 64)

    assert captured.value.code == "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE"
