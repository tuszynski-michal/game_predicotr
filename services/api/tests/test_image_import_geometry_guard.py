from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_api.application.image_import_geometry_guard import (
    ImageGeometryGuardDecisionCommand,
    ImageImportGeometryGuardService,
)
from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardDecision,
    ImageGeometryGuardDisposition,
    ImageGeometryGuardResolutionManifest,
    ImageGeometryGuardScope,
    payload_checksum,
)
from game_predictor_api.domain.jobs import JobConflictError, JobError

GAME_ID = UUID("11111111-1111-1111-1111-111111111111")
UPLOAD_ID = UUID("22222222-2222-2222-2222-222222222222")
JOB_ID = UUID("33333333-3333-3333-3333-333333333333")
REPORT_CHECKSUM = "d" * 64
SOURCE_CHECKSUM = "a" * 64


class _Repository:
    def __init__(self, scope: ImageGeometryGuardScope) -> None:
        self.scope = scope
        self.decisions: list[ImageGeometryGuardDecision] = []
        self.manifests: list[ImageGeometryGuardResolutionManifest] = []

    def get_scope(self, **_kwargs: object) -> ImageGeometryGuardScope:
        return self.scope

    def latest_decisions(self, *, guard_job_id: UUID) -> tuple[ImageGeometryGuardDecision, ...]:
        assert guard_job_id == JOB_ID
        latest: dict[tuple[str, int], ImageGeometryGuardDecision] = {}
        for item in self.decisions:
            key = (item.source_checksum_sha256, item.position_index)
            if key not in latest or latest[key].revision < item.revision:
                latest[key] = item
        return tuple(latest[key] for key in sorted(latest))

    def add_decisions(
        self, values: list[ImageGeometryGuardDecision]
    ) -> tuple[ImageGeometryGuardDecision, ...]:
        self.decisions.extend(values)
        return tuple(values)

    def get_manifest_by_checksum(
        self, *, guard_job_id: UUID, manifest_checksum_sha256: str
    ) -> ImageGeometryGuardResolutionManifest | None:
        return next(
            (
                item
                for item in self.manifests
                if item.guard_job_id == guard_job_id
                and item.manifest_checksum_sha256 == manifest_checksum_sha256
            ),
            None,
        )

    def get_manifest_by_id(
        self, *, manifest_id: UUID
    ) -> ImageGeometryGuardResolutionManifest | None:
        return next((item for item in self.manifests if item.id == manifest_id), None)

    def add_manifest(
        self, value: ImageGeometryGuardResolutionManifest
    ) -> ImageGeometryGuardResolutionManifest:
        self.manifests.append(value)
        return value


def _service(tmp_path: Path) -> tuple[ImageImportGeometryGuardService, _Repository]:
    report = {
        "schemaVersion": "image-geometry-systemic-guard-report-v2",
        "sources": [
            {
                "sourceChecksumSha256": SOURCE_CHECKSUM,
                "sourceRelativePath": "seq_20530-20538.jpg",
                "boards": [
                    {
                        "positionIndex": index,
                        "sequenceNumber": 20530 + index,
                        "status": "deferred" if index < 3 else "ready",
                        "reasonCodes": ["incomplete_lattice"] if index < 3 else [],
                        "pageGeometry": {"quad": _quad(index)},
                        "analysisQuad": _quad(index),
                        "symbolGridQuad": None,
                        "evidence": {"supportedIntersectionCount": 12},
                    }
                    for index in range(9)
                ],
            }
        ],
    }
    checksum = payload_checksum(report)
    relative = f"data/image-geometry-guards/{JOB_ID}.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"report": report, "reportChecksumSha256": checksum}), encoding="ascii"
    )
    scope = ImageGeometryGuardScope(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        browser_manifest_checksum_sha256="b" * 64,
        job_input_payload={
            "source_manifest_sha256": "b" * 64,
            "page_geometry_manifest": {"checksumSha256": "c" * 64},
        },
        job_checkpoint_payload={
            "geometry_systemic_guard": {
                "reportRelativePath": relative,
                "reportChecksumSha256": checksum,
            }
        },
    )
    repository = _Repository(scope)
    return ImageImportGeometryGuardService(repository, tmp_path), repository


def _quad(offset: int = 0) -> tuple[dict[str, int], ...]:
    return (
        {"x": offset, "y": 0},
        {"x": offset + 100, "y": 0},
        {"x": offset + 100, "y": 60},
        {"x": offset, "y": 60},
    )


def _command(
    position: int, disposition: ImageGeometryGuardDisposition
) -> ImageGeometryGuardDecisionCommand:
    return ImageGeometryGuardDecisionCommand(
        source_checksum_sha256=SOURCE_CHECKSUM,
        position_index=position,
        sequence_number=20530 + position,
        disposition=disposition,
        symbol_grid_quad=(
            None if disposition is ImageGeometryGuardDisposition.REJECTED else _quad()
        ),
        unavailable_cell_indices=(
            (10, 11, 12, 13, 14) if disposition is ImageGeometryGuardDisposition.PARTIAL else ()
        ),
        reason="cropped_or_unreadable"
        if disposition is ImageGeometryGuardDisposition.REJECTED
        else None,
    )


def test_queue_exposes_only_exact_deferred_boards(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)

    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)

    assert queue.unresolved_count == 3
    assert [item.sequence_number for item in queue.targets] == [20530, 20531, 20532]
    assert queue.targets[0].analysis_quad == list(_quad(0))


def test_mixed_decisions_are_append_only_and_seal_content_addressed_manifest(
    tmp_path: Path,
) -> None:
    service, repository = _service(tmp_path)
    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)

    decisions = service.save_decisions(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
        commands=(
            _command(0, ImageGeometryGuardDisposition.CORRECTED_FULL),
            _command(1, ImageGeometryGuardDisposition.PARTIAL),
            _command(2, ImageGeometryGuardDisposition.REJECTED),
        ),
    )
    manifest = service.seal_manifest(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
    )
    descriptor = service.require_manifest_descriptor(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        manifest_id=manifest.id,
        expected_manifest_checksum_sha256=manifest.manifest_checksum_sha256,
        source_manifest_checksum_sha256="b" * 64,
        page_geometry_manifest_checksum_sha256="c" * 64,
    )

    assert [item.revision for item in decisions] == [1, 1, 1]
    assert decisions[1].unavailable_cell_indices == (10, 11, 12, 13, 14)
    assert manifest.decision_count == 3
    assert descriptor["checksumSha256"] == manifest.manifest_checksum_sha256
    assert repository.manifests == [manifest]
    assert (tmp_path / manifest.manifest_relative_path).is_file()
    assert (
        service.seal_manifest(
            game_id=GAME_ID,
            browser_selection_id=UPLOAD_ID,
            guard_job_id=JOB_ID,
            expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
            actor="another-actor",
        )
        == manifest
    )


def test_manifest_refuses_unresolved_board(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)
    service.save_decisions(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
        commands=(_command(0, ImageGeometryGuardDisposition.CORRECTED_FULL),),
    )

    with pytest.raises(JobConflictError) as captured:
        service.seal_manifest(
            game_id=GAME_ID,
            browser_selection_id=UPLOAD_ID,
            guard_job_id=JOB_ID,
            expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
            actor="local-admin",
        )

    assert captured.value.code == "IMAGE_GEOMETRY_GUARD_DECISIONS_INCOMPLETE"


def test_partial_requires_sorted_unique_nonempty_mask(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)
    invalid = _command(0, ImageGeometryGuardDisposition.PARTIAL)
    invalid = ImageGeometryGuardDecisionCommand(
        source_checksum_sha256=invalid.source_checksum_sha256,
        position_index=invalid.position_index,
        sequence_number=invalid.sequence_number,
        disposition=invalid.disposition,
        symbol_grid_quad=invalid.symbol_grid_quad,
        unavailable_cell_indices=(2, 2),
        reason=None,
    )

    with pytest.raises(JobError) as captured:
        service.save_decisions(
            game_id=GAME_ID,
            browser_selection_id=UPLOAD_ID,
            guard_job_id=JOB_ID,
            expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
            actor="local-admin",
            commands=(invalid,),
        )

    assert captured.value.code == "IMAGE_GEOMETRY_GUARD_DECISION_INVALID"


def test_legacy_report_requires_board_diagnostic_reconstruction(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    relative = repository.scope.job_checkpoint_payload["geometry_systemic_guard"][
        "reportRelativePath"
    ]
    report = {"sources": []}
    checksum = payload_checksum(report)
    (tmp_path / relative).write_text(
        json.dumps({"report": report, "reportChecksumSha256": checksum}), encoding="ascii"
    )
    repository.scope.job_checkpoint_payload["geometry_systemic_guard"]["reportChecksumSha256"] = (
        checksum
    )

    with pytest.raises(JobConflictError) as captured:
        service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)

    assert captured.value.code == "IMAGE_GEOMETRY_GUARD_BOARD_REPORT_REQUIRED"
