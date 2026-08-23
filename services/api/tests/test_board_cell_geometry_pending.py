from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryPendingRepository,
    BoardCellGeometryPendingService,
    BoardCellProcessingManifestStore,
    ManagedBoardCellProcessingManifestStore,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    BoardCellProcessingManifestV1,
    ImageBoardGeometryPending,
)
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.main import create_app


class MemoryManifestStore(BoardCellProcessingManifestStore):
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def put(self, manifest: BoardCellProcessingManifestV1) -> str:
        self.values.setdefault(manifest.checksum_sha256, manifest.canonical_bytes())
        return f"manifests/{manifest.checksum_sha256}.json"


class MemoryPendingRepository(BoardCellGeometryPendingRepository):
    def __init__(self) -> None:
        self.values: list[ImageBoardGeometryPending] = []
        self.human_revision_changed: set[UUID] = set()

    def defer(
        self,
        *,
        manifest: BoardCellProcessingManifestV1,
        reason_code: BoardCellGeometryPendingReason,
        manifest_relative_path: str,
    ) -> tuple[ImageBoardGeometryPending, bool]:
        existing = next(
            (
                value
                for value in self.values
                if value.import_job_id == manifest.import_job_id
                and value.source_image_id == manifest.source_image_id
                and value.position_index == manifest.position_index
                and value.processing_manifest_checksum_sha256 == manifest.checksum_sha256
            ),
            None,
        )
        if existing is not None:
            return existing, False
        now = datetime.now(UTC)
        for index, value in enumerate(self.values):
            if (
                value.import_job_id == manifest.import_job_id
                and value.source_image_id == manifest.source_image_id
                and value.position_index == manifest.position_index
                and value.status is BoardCellGeometryPendingStatus.PENDING
            ):
                self.values[index] = replace(
                    value,
                    status=BoardCellGeometryPendingStatus.SUPERSEDED,
                    updated_at=now,
                    superseded_at=now,
                )
        value = ImageBoardGeometryPending(
            id=uuid4(),
            game_id=manifest.game_id,
            import_job_id=manifest.import_job_id,
            source_image_id=manifest.source_image_id,
            recognized_board_id=None,
            review_item_id=None,
            sequence_number=manifest.sequence_number,
            position_index=manifest.position_index,
            source_checksum_sha256=manifest.source_checksum_sha256,
            source_relative_path=manifest.source_relative_path,
            status=BoardCellGeometryPendingStatus.PENDING,
            reason_code=reason_code,
            processing_manifest_checksum_sha256=manifest.checksum_sha256,
            processing_manifest_relative_path=manifest_relative_path,
            pipeline_fingerprint_sha256=manifest.pipeline_fingerprint_sha256,
            expected_geometry_revision=manifest.expected_geometry_revision,
            expected_review_resolution_revision=manifest.expected_review_resolution_revision,
            resolved_geometry_revision=None,
            created_at=now,
            updated_at=now,
            resolved_at=None,
            superseded_at=None,
        )
        self.values.append(value)
        return value, True

    def get(self, pending_id: UUID) -> ImageBoardGeometryPending | None:
        return next((value for value in self.values if value.id == pending_id), None)

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        status: BoardCellGeometryPendingStatus | None,
        after_key: tuple[int, int, UUID] | None,
        limit: int,
    ) -> tuple[ImageBoardGeometryPending, ...]:
        values = sorted(
            (
                value
                for value in self.values
                if value.game_id == game_id
                and value.import_job_id == import_job_id
                and (status is None or value.status is status)
            ),
            key=lambda value: (value.sequence_number, value.position_index, value.id),
        )
        if after_key is not None:
            values = [
                value
                for value in values
                if (value.sequence_number, value.position_index, value.id) > after_key
            ]
        return tuple(values[:limit])

    def counts(self, *, game_id: UUID, import_job_id: UUID) -> BoardCellGeometryJobCounts:
        values = [
            value
            for value in self.values
            if value.game_id == game_id and value.import_job_id == import_job_id
        ]
        return BoardCellGeometryJobCounts(
            total=len(values),
            pending=sum(value.status is BoardCellGeometryPendingStatus.PENDING for value in values),
            resolved=sum(
                value.status is BoardCellGeometryPendingStatus.RESOLVED for value in values
            ),
            superseded=sum(
                value.status is BoardCellGeometryPendingStatus.SUPERSEDED for value in values
            ),
        )

    def resolve(
        self,
        *,
        pending_id: UUID,
        expected_manifest_checksum_sha256: str,
        resolved_geometry_revision: int,
    ) -> ImageBoardGeometryPending | None:
        value = self.get(pending_id)
        if value is None:
            return None
        if value.status is not BoardCellGeometryPendingStatus.PENDING:
            return value
        now = datetime.now(UTC)
        if pending_id in self.human_revision_changed:
            updated = replace(
                value,
                status=BoardCellGeometryPendingStatus.SUPERSEDED,
                updated_at=now,
                superseded_at=now,
            )
        else:
            updated = replace(
                value,
                status=BoardCellGeometryPendingStatus.RESOLVED,
                resolved_geometry_revision=resolved_geometry_revision,
                updated_at=now,
                resolved_at=now,
            )
        self.values[self.values.index(value)] = updated
        return updated


def _manifest(
    *,
    game_id: UUID | None = None,
    import_job_id: UUID | None = None,
    source_image_id: UUID | None = None,
    sequence_number: int = 64,
    position_index: int = 0,
    pipeline: str = "d" * 64,
) -> BoardCellProcessingManifestV1:
    return BoardCellProcessingManifestV1(
        game_id=game_id or uuid4(),
        import_job_id=import_job_id or uuid4(),
        source_image_id=source_image_id or uuid4(),
        source_checksum_sha256="a" * 64,
        source_relative_path="seq_64-72.jpg",
        position_index=position_index,
        sequence_number=sequence_number,
        pipeline_fingerprint_sha256=pipeline,
        estimator_version="board-cell-geometry-v19",
        estimator_fingerprint_sha256="b" * 64,
        cropper_version="board-cell-crops-v19",
        cropper_fingerprint_sha256="c" * 64,
        expected_geometry_revision=0,
        expected_review_resolution_revision=0,
    )


def test_manifest_is_content_addressed_and_pins_all_processing_inputs(tmp_path: Path) -> None:
    manifest = _manifest()
    replay = _manifest(
        game_id=manifest.game_id,
        import_job_id=manifest.import_job_id,
        source_image_id=manifest.source_image_id,
    )
    store = ManagedBoardCellProcessingManifestStore(tmp_path)

    first_path = store.put(manifest)
    second_path = store.put(replay)

    assert manifest.checksum_sha256 == replay.checksum_sha256
    assert first_path == second_path
    payload = json.loads((tmp_path / first_path).read_text(encoding="ascii"))
    assert payload["schemaVersion"] == "board-cell-processing-manifest-v1"
    assert payload["sequenceNumber"] == 64
    assert payload["estimatorFingerprintSha256"] == "b" * 64
    assert payload["cropperFingerprintSha256"] == "c" * 64
    assert payload["pipelineFingerprintSha256"] == "d" * 64


@pytest.mark.parametrize(
    "change",
    (
        {"position_index": 9},
        {"sequence_number": 0},
        {"source_relative_path": "../escape.jpg"},
        {"pipeline_fingerprint_sha256": "not-a-hash"},
    ),
)
def test_manifest_rejects_ambiguous_or_unpinned_inputs(change: dict[str, object]) -> None:
    manifest = _manifest()
    arguments = {
        field.name: getattr(manifest, field.name)
        for field in fields(manifest)
        if field.name != "schema_version"
    }
    arguments.update(change)
    with pytest.raises(JobError, match="manifest|position|sequence|relative|SHA-256"):
        BoardCellProcessingManifestV1(**arguments)


def test_reason_codes_are_closed_and_stable() -> None:
    assert {value.value for value in BoardCellGeometryPendingReason} == {
        "insufficient_centers",
        "incomplete_lattice",
        "residual_too_high",
        "source_unavailable",
    }


def test_defer_is_idempotent_and_new_manifest_supersedes_previous() -> None:
    repository = MemoryPendingRepository()
    store = MemoryManifestStore()
    service = BoardCellGeometryPendingService(repository, store)
    first_manifest = _manifest()

    first, created = service.defer(
        manifest=first_manifest,
        reason_code=BoardCellGeometryPendingReason.INSUFFICIENT_CENTERS,
    )
    replay, replay_created = service.defer(
        manifest=first_manifest,
        reason_code=BoardCellGeometryPendingReason.INSUFFICIENT_CENTERS,
    )
    replacement, replacement_created = service.defer(
        manifest=replace(first_manifest, pipeline_fingerprint_sha256="e" * 64),
        reason_code=BoardCellGeometryPendingReason.RESIDUAL_TOO_HIGH,
    )

    assert created is True
    assert replay_created is False
    assert replay.id == first.id
    assert replacement_created is True
    assert replacement.status is BoardCellGeometryPendingStatus.PENDING
    assert repository.get(first.id).status is BoardCellGeometryPendingStatus.SUPERSEDED  # type: ignore[union-attr]
    assert repository.counts(
        game_id=first.game_id, import_job_id=first.import_job_id
    ) == BoardCellGeometryJobCounts(total=2, pending=1, resolved=0, superseded=1)


def test_resolution_is_fail_closed_and_concurrent_human_revision_wins() -> None:
    repository = MemoryPendingRepository()
    service = BoardCellGeometryPendingService(repository, MemoryManifestStore())
    first, _ = service.defer(
        manifest=_manifest(),
        reason_code=BoardCellGeometryPendingReason.INCOMPLETE_LATTICE,
    )
    second_manifest = _manifest(
        game_id=first.game_id,
        import_job_id=first.import_job_id,
        sequence_number=65,
        position_index=1,
    )
    second, _ = service.defer(
        manifest=second_manifest,
        reason_code=BoardCellGeometryPendingReason.SOURCE_UNAVAILABLE,
    )
    repository.human_revision_changed.add(second.id)

    resolved = service.resolve(
        pending_id=first.id,
        expected_manifest_checksum_sha256=first.processing_manifest_checksum_sha256,
        resolved_geometry_revision=1,
    )
    superseded = service.resolve(
        pending_id=second.id,
        expected_manifest_checksum_sha256=second.processing_manifest_checksum_sha256,
        resolved_geometry_revision=1,
    )

    assert resolved.status is BoardCellGeometryPendingStatus.RESOLVED
    assert resolved.resolved_geometry_revision == 1
    assert superseded.status is BoardCellGeometryPendingStatus.SUPERSEDED
    assert superseded.resolved_geometry_revision is None
    assert not hasattr(superseded, "cells_prediction")


def test_api_lists_pages_counts_and_scopes_single_item(tmp_path: Path) -> None:
    game_id, import_job_id = uuid4(), uuid4()
    repository = MemoryPendingRepository()
    service = BoardCellGeometryPendingService(repository, MemoryManifestStore())
    first, _ = service.defer(
        manifest=_manifest(game_id=game_id, import_job_id=import_job_id, sequence_number=64),
        reason_code=BoardCellGeometryPendingReason.INSUFFICIENT_CENTERS,
    )
    service.defer(
        manifest=_manifest(game_id=game_id, import_job_id=import_job_id, sequence_number=65),
        reason_code=BoardCellGeometryPendingReason.INCOMPLETE_LATTICE,
    )
    app = create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": (
                    "postgresql+psycopg://unused:unused@localhost:5432/unused"
                ),
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
            }
        ),
        board_cell_geometry_pending_service_dependency=lambda: service,
    )

    with TestClient(app) as client:
        page = client.get(
            f"/api/v1/admin/games/{game_id}/image-imports/{import_job_id}/"
            "board-cell-geometry-pending",
            params={"limit": 1},
        )
        item = client.get(
            f"/api/v1/admin/games/{game_id}/image-imports/{import_job_id}/"
            f"board-cell-geometry-pending/{first.id}"
        )
        missing_scope = client.get(
            f"/api/v1/admin/games/{uuid4()}/image-imports/{import_job_id}/"
            f"board-cell-geometry-pending/{first.id}"
        )

    assert page.status_code == 200
    assert page.json()["counts"] == {
        "total": 2,
        "pending": 2,
        "resolved": 0,
        "superseded": 0,
    }
    assert len(page.json()["items"]) == 1
    assert page.json()["nextCursor"] is not None
    assert item.status_code == 200
    assert item.json()["reasonCode"] == "insufficient_centers"
    assert missing_scope.status_code == 404
