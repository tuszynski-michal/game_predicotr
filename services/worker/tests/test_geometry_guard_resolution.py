from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardBoardTarget,
    ImageGeometryGuardDisposition,
    create_guard_decision,
    payload_checksum,
    resolution_manifest_payload,
)
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_worker.images.geometry_guard_resolution import (
    load_geometry_guard_resolutions,
)
from game_predictor_worker.images.source_ingestion import ManagedOriginal
from game_predictor_worker.jobs.runtime import JobHandlerError

GAME_ID = UUID("11111111-1111-1111-1111-111111111111")
UPLOAD_ID = UUID("22222222-2222-2222-2222-222222222222")
GUARD_JOB_ID = UUID("33333333-3333-3333-3333-333333333333")
MANIFEST_ID = UUID("44444444-4444-4444-4444-444444444444")
SOURCE_CHECKSUM = "a" * 64
SOURCE_MANIFEST_CHECKSUM = "b" * 64
PAGE_MANIFEST_CHECKSUM = "c" * 64
REPORT_CHECKSUM = "d" * 64


def _quad() -> tuple[dict[str, int], ...]:
    return (
        {"x": 10, "y": 20},
        {"x": 110, "y": 20},
        {"x": 110, "y": 80},
        {"x": 10, "y": 80},
    )


def _fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    original = ManagedOriginal(
        checksum_sha256=SOURCE_CHECKSUM,
        source_relative_path="seq_20530-20538.jpg",
        managed_relative_path=f"data/originals/aa/{SOURCE_CHECKSUM}.jpg",
        size_bytes=100,
        sequence_range_start=20530,
        sequence_range_end=20538,
        sequence_range_source="filename",
    )
    target = ImageGeometryGuardBoardTarget(
        source_checksum_sha256=SOURCE_CHECKSUM,
        source_relative_path=original.source_relative_path,
        position_index=2,
        sequence_number=20532,
        reason_codes=("incomplete_lattice",),
        page_geometry=None,
        analysis_quad=None,
        proposed_symbol_grid_quad=None,
        evidence=None,
    )
    decision = create_guard_decision(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=GUARD_JOB_ID,
        guard_report_checksum_sha256=REPORT_CHECKSUM,
        target=target,
        revision=1,
        disposition=ImageGeometryGuardDisposition.PARTIAL,
        symbol_grid_quad=_quad(),
        unavailable_cell_indices=(10, 11, 12, 13, 14),
        reason=None,
        actor="local-admin",
    )
    payload = resolution_manifest_payload(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=GUARD_JOB_ID,
        guard_report_checksum_sha256=REPORT_CHECKSUM,
        source_manifest_checksum_sha256=SOURCE_MANIFEST_CHECKSUM,
        page_geometry_manifest_checksum_sha256=PAGE_MANIFEST_CHECKSUM,
        decisions=(decision,),
    )
    checksum = payload_checksum(payload)
    relative = f"data/image-geometry-guard-resolutions/{checksum[:2]}/{checksum}.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="ascii")
    job = create_job(
        JobType.IMPORT,
        game_id=GAME_ID,
        input_payload={
            "schema_version": 7,
            "import_kind": "image_directory",
            "source_selection_id": str(UPLOAD_ID),
            "source_directory": str(tmp_path),
            "pipeline_fingerprint": "e" * 64,
            "image_geometry_rollout": {"geometryMode": "structured_lattice_v3"},
            "geometry_guard_resolution_manifest": {
                "id": str(MANIFEST_ID),
                "checksumSha256": checksum,
                "relativePath": relative,
                "guardJobId": str(GUARD_JOB_ID),
                "guardReportChecksumSha256": REPORT_CHECKSUM,
                "sourceManifestChecksumSha256": SOURCE_MANIFEST_CHECKSUM,
                "pageGeometryManifestChecksumSha256": PAGE_MANIFEST_CHECKSUM,
            },
        },
    )
    return job, original, path


def test_loader_accepts_exact_partial_resolution(tmp_path: Path) -> None:
    job, original, _path = _fixture(tmp_path)

    result = load_geometry_guard_resolutions(
        artifact_root=tmp_path,
        job=job,
        originals=(original,),
        source_manifest_checksum_sha256=SOURCE_MANIFEST_CHECKSUM,
        page_geometry_manifest_checksum_sha256=PAGE_MANIFEST_CHECKSUM,
    )

    assert result is not None
    resolution = result.for_source(SOURCE_CHECKSUM)[2]
    assert resolution.sequence_number == 20532
    assert resolution.unavailable_cell_indices == (10, 11, 12, 13, 14)


def test_loader_rejects_tampered_decision(tmp_path: Path) -> None:
    job, original, path = _fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="ascii"))
    payload["decisions"][0]["sequenceNumber"] = 20533
    path.write_text(json.dumps(payload), encoding="ascii")

    with pytest.raises(JobHandlerError) as captured:
        load_geometry_guard_resolutions(
            artifact_root=tmp_path,
            job=job,
            originals=(original,),
            source_manifest_checksum_sha256=SOURCE_MANIFEST_CHECKSUM,
            page_geometry_manifest_checksum_sha256=PAGE_MANIFEST_CHECKSUM,
        )

    assert captured.value.code == "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE"
