from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.image_import_geometry_guard import (
    ImageGeometryGuardDecisionCommand,
    ImageImportGeometryGuardService,
)
from game_predictor_api.domain.geometry_qualification import GeometryQualification
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
PREFLIGHT_JOB_ID = UUID("44444444-4444-4444-4444-444444444444")
REPORT_CHECKSUM = "d" * 64
SOURCE_CHECKSUM = "a" * 64


def test_new_partial_contract_preserves_all_missing_cells_and_uses_new_manifest(
    tmp_path: Path,
) -> None:
    service, repository = _service(tmp_path)
    qualification = GeometryQualification(
        "pending_partial", tuple(range(15)), True, "missing_pixels"
    )
    command = replace(
        _command(0, ImageGeometryGuardDisposition.PARTIAL),
        unavailable_cell_indices=tuple(range(15)),
        geometry_qualification=qualification,
    )
    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)
    results = service.save_decisions(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-owner",
        commands=(command,),
    )
    assert results[0].geometry_qualification == qualification
    assert results[0].unavailable_cell_indices == tuple(range(15))
    assert repository.latest_decisions(guard_job_id=JOB_ID)[0] == results[0]
    from game_predictor_api.domain.image_import_geometry_guard import resolution_manifest_payload

    payload = resolution_manifest_payload(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        source_manifest_checksum_sha256="b" * 64,
        page_geometry_manifest_checksum_sha256="c" * 64,
        decisions=results,
    )
    assert payload["schemaVersion"] == "ImageGeometryGuardResolutionManifestV3"
    assert payload["decisions"][0]["geometryQualification"] == qualification.to_dict()
    # This foundation may persist decisions, but cannot pass them to the old renderer.
    checksum = payload_checksum(payload)
    relative = f"data/image-geometry-guard-resolutions/{checksum}.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = ImageGeometryGuardResolutionManifest(
        id=uuid4(),
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        source_manifest_checksum_sha256="b" * 64,
        page_geometry_manifest_checksum_sha256="c" * 64,
        manifest_relative_path=relative,
        manifest_checksum_sha256=checksum,
        decision_count=1,
        sealed_by="local-owner",
        created_at=datetime.now(UTC),
    )
    repository.add_manifest(manifest)
    with pytest.raises(JobConflictError) as unsupported:
        service.require_manifest_descriptor(
            game_id=GAME_ID,
            browser_selection_id=UPLOAD_ID,
            manifest_id=manifest.id,
            expected_manifest_checksum_sha256=checksum,
            source_manifest_checksum_sha256="b" * 64,
            page_geometry_manifest_checksum_sha256="c" * 64,
        )
    assert unsupported.value.code == "IMAGE_GEOMETRY_GUARD_QUALIFICATION_NOT_ENABLED"
    with pytest.raises(JobError):
        service.save_decisions(
            game_id=GAME_ID,
            browser_selection_id=UPLOAD_ID,
            guard_job_id=JOB_ID,
            expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
            actor="local-owner",
            commands=(replace(command, geometry_qualification=None),),
        )


def test_legacy_update_cannot_remove_manual_training_exclusion(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)
    command = replace(
        _command(0, ImageGeometryGuardDisposition.CORRECTED_FULL),
        geometry_qualification=GeometryQualification(
            exclude_from_geometry_training=True, exclusion_reason="manual_exclusion"
        ),
    )
    arguments = dict(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-owner",
    )
    service.save_decisions(**arguments, commands=(command,))
    with pytest.raises(JobConflictError) as missing:
        service.save_decisions(
            **arguments, commands=(replace(command, geometry_qualification=None),)
        )
    assert missing.value.code == "IMAGE_GEOMETRY_GUARD_QUALIFICATION_REQUIRED"
    assert len(repository.decisions) == 1
    assert repository.decisions[0].geometry_qualification == command.geometry_qualification


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
            "page_geometry_manifest": {
                "checksumSha256": "c" * 64,
                "preflightJobId": str(PREFLIGHT_JOB_ID),
            },
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
    assert len(queue.boards) == 9
    assert [item.requires_decision for item in queue.boards[:4]] == [True, True, True, False]
    assert [item.sequence_number for item in queue.targets] == [20530, 20531, 20532]
    assert queue.targets[0].analysis_quad == list(_quad(0))


def test_ready_board_can_receive_an_explicit_operator_correction(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)

    decisions = service.save_decisions(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
        commands=(_command(4, ImageGeometryGuardDisposition.CORRECTED_FULL),),
    )

    assert decisions[0].position_index == 4
    assert decisions[0].sequence_number == 20534
    assert repository.decisions == list(decisions)


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


def test_queue_restores_only_the_manifest_matching_latest_decisions(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)
    assert queue.page_geometry_preflight_job_id == PREFLIGHT_JOB_ID
    assert queue.current_resolution_manifest is None

    service.save_decisions(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
        commands=tuple(
            _command(position, ImageGeometryGuardDisposition.CORRECTED_FULL)
            for position in (0, 1, 2)
        ),
    )
    manifest = service.seal_manifest(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
    )

    restored = service.queue(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
    )
    assert restored.current_resolution_manifest == manifest

    service.save_decisions(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
        commands=(_command(0, ImageGeometryGuardDisposition.CORRECTED_FULL),),
    )

    changed = service.queue(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
    )
    assert changed.current_resolution_manifest is None


def test_manifest_includes_optional_ready_board_override(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    queue = service.queue(game_id=GAME_ID, browser_selection_id=UPLOAD_ID, guard_job_id=JOB_ID)
    service.save_decisions(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
        commands=tuple(
            _command(position, ImageGeometryGuardDisposition.CORRECTED_FULL)
            for position in (0, 1, 2, 4)
        ),
    )

    manifest = service.seal_manifest(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        expected_guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
        actor="local-admin",
    )
    payload = json.loads((tmp_path / manifest.manifest_relative_path).read_text(encoding="ascii"))

    assert payload["schemaVersion"] == "ImageGeometryGuardResolutionManifestV2"
    assert [item["positionIndex"] for item in payload["decisions"]] == [0, 1, 2, 4]
    assert manifest.decision_count == 4


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
    report = {
        "jobId": str(JOB_ID),
        "selectedSourceChecksums": [SOURCE_CHECKSUM],
        "sources": [],
    }
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

    reconstruction = service.report_reconstruction_input(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
    )
    assert reconstruction.legacy_report_checksum_sha256 == checksum

    derived = {
        "schemaVersion": "image-geometry-systemic-guard-report-v2",
        "derivedFromReportChecksumSha256": checksum,
        "jobId": str(JOB_ID),
        "sources": [
            {
                "sourceChecksumSha256": SOURCE_CHECKSUM,
                "sourceRelativePath": "seq_20530-20538.jpg",
                "boards": [
                    {
                        "positionIndex": 0,
                        "sequenceNumber": 20530,
                        "status": "deferred",
                        "reasonCodes": ["incomplete_lattice"],
                    }
                ],
            }
        ],
    }
    derived_checksum = payload_checksum(derived)
    derived_relative = (
        f"data/image-geometry-guards/derived/{derived_checksum[:2]}/{derived_checksum}.json"
    )
    derived_path = tmp_path / derived_relative
    derived_path.parent.mkdir(parents=True)
    derived_path.write_text(
        json.dumps({"report": derived, "reportChecksumSha256": derived_checksum}),
        encoding="ascii",
    )
    repository.scope = ImageGeometryGuardScope(
        game_id=repository.scope.game_id,
        browser_selection_id=repository.scope.browser_selection_id,
        browser_manifest_checksum_sha256=(repository.scope.browser_manifest_checksum_sha256),
        job_input_payload=repository.scope.job_input_payload,
        job_checkpoint_payload=repository.scope.job_checkpoint_payload,
        derived_report_checkpoint={
            "sourceGuardJobId": str(JOB_ID),
            "legacyReportChecksumSha256": checksum,
            "sourceManifestChecksumSha256": "b" * 64,
            "pageGeometryManifestChecksumSha256": "c" * 64,
            "reportChecksumSha256": derived_checksum,
            "reportRelativePath": derived_relative,
        },
    )

    queue = service.queue(
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
    )
    assert queue.guard_report_checksum_sha256 == derived_checksum
    assert [(item.position_index, item.sequence_number) for item in queue.targets] == [(0, 20530)]
