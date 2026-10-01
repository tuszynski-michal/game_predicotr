from __future__ import annotations

import hashlib
import json
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryCorrectionContext,
    BoardCellGeometryPendingRepository,
    BoardCellGeometryPendingService,
    BoardCellProcessingManifestStore,
    ManagedBoardCellProcessingManifestStore,
)
from game_predictor_api.application.reviewer_access import ReviewerAccessError
from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometryCell,
    VirtualGridGeometryPreview,
    VirtualGridGeometryRevision,
    VirtualGridGeometrySourceSaveResult,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    BoardCellProcessingManifestV1,
    ImageBoardGeometryPending,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.domain.symbol_model_snapshots import bootstrap_symbol_model_snapshot
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
        self.contexts: dict[UUID, BoardCellGeometryCorrectionContext] = {}

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

    def correction_context(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> BoardCellGeometryCorrectionContext | None:
        value = self.contexts.get(pending_id)
        if (
            value is None
            or value.pending.game_id != game_id
            or value.pending.import_job_id != import_job_id
        ):
            return None
        return value


def _manifest(
    *,
    game_id: UUID | None = None,
    import_job_id: UUID | None = None,
    source_image_id: UUID | None = None,
    sequence_number: int = 64,
    position_index: int = 0,
    pipeline: str = "d" * 64,
    source_checksum_sha256: str = "a" * 64,
    source_relative_path: str = "seq_64-72.jpg",
) -> BoardCellProcessingManifestV1:
    return BoardCellProcessingManifestV1(
        game_id=game_id or uuid4(),
        import_job_id=import_job_id or uuid4(),
        source_image_id=source_image_id or uuid4(),
        source_checksum_sha256=source_checksum_sha256,
        source_relative_path=source_relative_path,
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
    assert "gridRows" not in payload


def test_manifest_additively_pins_topology_without_changing_legacy_payload() -> None:
    rules_version_id = uuid4()
    manifest = replace(
        _manifest(),
        grid_rows=3,
        grid_columns=5,
        topology_rules_version_id=rules_version_id,
    )

    payload = manifest.payload()

    assert payload["gridRows"] == 3
    assert payload["gridColumns"] == 5
    assert payload["topologyRulesVersionId"] == str(rules_version_id)
    assert (
        manifest.checksum_sha256
        != _manifest(
            game_id=manifest.game_id,
            import_job_id=manifest.import_job_id,
            source_image_id=manifest.source_image_id,
        ).checksum_sha256
    )


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


class ScopedReviewerAccess:
    def __init__(self, game_id: UUID, import_job_id: UUID) -> None:
        self.session_id = uuid4()
        self._session = type(
            "ScopedSession",
            (),
            {"id": self.session_id, "game_id": game_id, "import_job_id": import_job_id},
        )()

    def authenticate(self, access_token: str):  # type: ignore[no-untyped-def]
        if access_token != "scoped-token":
            raise ReviewerAccessError("REVIEWER_TOKEN_INVALID", "Invalid token.")
        return self._session

    def authorize_scope(self, session, *, game_id, import_job_id):  # type: ignore[no-untyped-def]
        if session.game_id != game_id or session.import_job_id != import_job_id:
            raise ReviewerAccessError("REVIEWER_SCOPE_FORBIDDEN", "Foreign scope.")


class RecordingVirtualGeometry:
    """Stands in for ``VirtualGridGeometryService``; records the delegation."""

    def __init__(self, repository: MemoryPendingRepository) -> None:
        self._repository = repository
        self.previews: list[dict[str, object]] = []
        self.saves: list[dict[str, object]] = []
        self._by_key: dict[UUID, tuple[tuple[ImageReviewGeometryPoint, ...], str]] = {}

    def preview_pending_slot(self, **kwargs: object) -> VirtualGridGeometryPreview:
        self.previews.append(kwargs)
        return VirtualGridGeometryPreview(
            contact_sheet_png=PREVIEW_PNG,
            cells=tuple(_virtual_cell(index) for index in range(15)),
            cropper_version="virtual-cell-renderer-test",
        )

    def save_pending_slot(self, **kwargs: object) -> VirtualGridGeometrySourceSaveResult:
        self.saves.append(kwargs)
        pending_id = cast(UUID, kwargs["pending_geometry_id"])
        key = cast(UUID, kwargs["idempotency_key"])
        corners = tuple(cast(tuple[ImageReviewGeometryPoint, ...], kwargs["corners"]))
        actor = cast(str, kwargs["actor"])
        prior = self._by_key.get(key)
        if prior is not None:
            if prior != (corners, actor):
                raise ImageGridReviewError(
                    "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT",
                    "The geometry idempotency key already represents another command.",
                )
            return VirtualGridGeometrySourceSaveResult(
                revisions=(_virtual_revision(self._repository.get(pending_id), key, corners),),
                created=False,
            )
        pending = self._repository.get(pending_id)
        assert pending is not None
        if pending.status is BoardCellGeometryPendingStatus.RESOLVED:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
                "The virtual grid review changed after it was loaded.",
            )
        resolved = replace(
            pending,
            recognized_board_id=pending.id,
            review_item_id=uuid4(),
            status=BoardCellGeometryPendingStatus.RESOLVED,
            resolved_geometry_revision=pending.expected_geometry_revision + 1,
            resolved_at=datetime.now(UTC),
        )
        self._repository.values[self._repository.values.index(pending)] = resolved
        context = self._repository.contexts[pending_id]
        self._repository.contexts[pending_id] = replace(context, pending=resolved)
        self._by_key[key] = (corners, actor)
        return VirtualGridGeometrySourceSaveResult(
            revisions=(_virtual_revision(resolved, key, corners),),
            created=True,
        )


PREVIEW_PNG = b"virtual-contact-sheet-png"


def _virtual_cell(index: int) -> VirtualGridGeometryCell:
    return VirtualGridGeometryCell(
        cell_index=index,
        row_index=index // 5,
        column_index=index % 5,
        crop_sample_id=f"{index:064x}",
        crop_checksum_sha256=f"{index + 1:064x}",
        logical_cell_key=f"{index + 2:064x}",
        logical_cell_key_v2=None,
        render_identity_v2_sha256=None,
        render_spec={},
        render_spec_checksum_sha256=f"{index + 3:064x}",
        rendered_pixel_checksum_sha256=f"{index + 1:064x}",
        extractor_version="virtual-cell-renderer-test",
    )


def _virtual_revision(
    pending: ImageBoardGeometryPending | None,
    key: UUID,
    corners: tuple[ImageReviewGeometryPoint, ...],
) -> VirtualGridGeometryRevision:
    assert pending is not None and pending.review_item_id is not None
    return VirtualGridGeometryRevision(
        id=uuid4(),
        review_item_id=pending.review_item_id,
        recognized_board_id=pending.id,
        revision=pending.expected_geometry_revision + 1,
        idempotency_key=key,
        command_sha256="e" * 64,
        corners=corners,
        source_geometry_revision_id=uuid4(),
        geometry_checksum_sha256="f" * 64,
        virtual_render_spec_checksum_sha256="1" * 64,
        cropper_version="virtual-cell-renderer-test",
        cells=tuple(_virtual_cell(index) for index in range(15)),
        corrected_by="local-owner",
        created_at=datetime.now(UTC),
    )


def test_manual_pending_geometry_api_delegates_to_the_virtual_source_path(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    source_relative_path = "originals/manual-source.png"
    source_path = artifact_root / "data" / source_relative_path
    source_path.parent.mkdir(parents=True)
    rgb = np.full((420, 620, 3), 80, dtype=np.uint8)
    encoded, payload = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert encoded
    source_content = bytes(payload)
    source_path.write_bytes(source_content)
    source_checksum = hashlib.sha256(source_content).hexdigest()

    game_id, import_job_id = uuid4(), uuid4()
    repository = MemoryPendingRepository()
    pending, _ = BoardCellGeometryPendingService(
        repository,
        MemoryManifestStore(),
    ).defer(
        manifest=_manifest(
            game_id=game_id,
            import_job_id=import_job_id,
            source_checksum_sha256=source_checksum,
            source_relative_path=source_relative_path,
        ),
        reason_code=BoardCellGeometryPendingReason.INCOMPLETE_LATTICE,
    )
    quad = [
        {"x": 60.0, "y": 50.0},
        {"x": 560.0, "y": 50.0},
        {"x": 560.0, "y": 350.0},
        {"x": 60.0, "y": 350.0},
    ]
    repository.contexts[pending.id] = BoardCellGeometryCorrectionContext(
        pending=pending,
        source_order_index=7,
        source_width=620,
        source_height=420,
        board_geometry={"quad": quad, "source": "detected"},
        board_confidence=0.73,
        symbol_model=bootstrap_symbol_model_snapshot(),
    )
    virtual = RecordingVirtualGeometry(repository)
    reviewer_access = ScopedReviewerAccess(game_id, import_job_id)
    service = BoardCellGeometryPendingService(
        repository,
        MemoryManifestStore(),
        virtual_geometry=virtual,  # type: ignore[arg-type]
    )
    app = create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": (
                    "postgresql+psycopg://unused:unused@localhost:5432/unused"
                ),
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(artifact_root),
            }
        ),
        board_cell_geometry_pending_service_dependency=lambda: service,
        reviewer_access_service_dependency=lambda: reviewer_access,
    )
    base = (
        f"/api/v1/admin/games/{game_id}/image-imports/{import_job_id}/"
        f"board-cell-geometry-pending/{pending.id}"
    )
    corners = [{"x": round(point["x"]), "y": round(point["y"])} for point in quad]
    preview_command = {
        "corners": corners,
        "expectedGeometryRevision": 0,
        "expectedManifestChecksumSha256": pending.processing_manifest_checksum_sha256,
        "expectedResolutionRevision": 0,
    }
    idempotency_key = uuid4()
    reviewer = {"Authorization": "Bearer scoped-token"}
    resolution = {
        **preview_command,
        "correctedBy": "spoofed-actor",
        "idempotencyKey": str(idempotency_key),
    }

    with TestClient(app) as client:
        context = client.get(f"{base}/correction-context")
        source = client.get(f"{base}/source")
        stale_preview = client.post(
            f"{base}/geometry-preview",
            json={**preview_command, "expectedManifestChecksumSha256": "0" * 64},
        )
        preview = client.post(f"{base}/geometry-preview", json=preview_command, headers=reviewer)
        foreign_resolution = client.post(
            f"/api/v1/admin/games/{uuid4()}/image-imports/{import_job_id}/"
            f"board-cell-geometry-pending/{pending.id}/manual-resolution",
            json=resolution,
            headers=reviewer,
        )
        resolved = client.post(f"{base}/manual-resolution", json=resolution, headers=reviewer)
        replay = client.post(f"{base}/manual-resolution", json=resolution, headers=reviewer)
        changed_command = client.post(
            f"{base}/manual-resolution",
            json={**resolution, "corners": [{"x": 61, "y": 50}, *corners[1:]]},
            headers=reviewer,
        )
        other_key = client.post(
            f"{base}/manual-resolution",
            json={**resolution, "idempotencyKey": str(uuid4())},
            headers=reviewer,
        )

    assert context.status_code == 200
    assert context.json()["suggestedCorners"] == corners
    assert source.status_code == 200
    assert source.content == source_content
    assert stale_preview.status_code == 409
    assert stale_preview.json()["code"] == "IMAGE_BOARD_CELL_PENDING_MANIFEST_CONFLICT"
    assert preview.status_code == 200, preview.text
    assert preview.content == PREVIEW_PNG
    assert preview.headers["x-board-cell-count"] == "15"
    assert preview.headers["x-board-cell-cropper-version"] == "virtual-cell-renderer-test"
    assert foreign_resolution.status_code == 403
    assert foreign_resolution.json()["code"] == "REVIEWER_SCOPE_FORBIDDEN"
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["created"] is True
    assert resolved.json()["geometryRevision"] == 1
    assert resolved.json()["item"]["status"] == "resolved"
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert replay.json()["reviewItemId"] == resolved.json()["reviewItemId"]
    assert changed_command.status_code == 409
    assert changed_command.json()["code"] == "IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT"
    assert other_key.status_code == 409
    assert other_key.json()["code"] == "IMAGE_BOARD_CELL_PENDING_RESOLUTION_CONFLICT"
    # Every write went through the virtual source path with the session actor;
    # the client-supplied ``correctedBy`` is ignored for a reviewer session.
    assert len(virtual.saves) == 4
    reviewer_actor = f"reviewer-session:{reviewer_access.session_id}"
    assert {save["actor"] for save in virtual.saves} == {reviewer_actor}
    assert virtual.saves[0]["pending_geometry_id"] == pending.id
    assert virtual.saves[0]["game_id"] == game_id
    assert virtual.saves[0]["import_job_id"] == import_job_id
    assert len(virtual.previews) == 1
    assert virtual.previews[0]["pending_geometry_id"] == pending.id


def test_manual_resolution_without_virtual_geometry_is_unavailable() -> None:
    repository = MemoryPendingRepository()
    pending, _ = BoardCellGeometryPendingService(repository, MemoryManifestStore()).defer(
        manifest=_manifest(),
        reason_code=BoardCellGeometryPendingReason.INCOMPLETE_LATTICE,
    )
    repository.contexts[pending.id] = BoardCellGeometryCorrectionContext(
        pending=pending,
        source_order_index=0,
        source_width=620,
        source_height=420,
        board_geometry={},
        board_confidence=0.5,
        symbol_model=bootstrap_symbol_model_snapshot(),
    )

    with pytest.raises(JobError) as error:
        BoardCellGeometryPendingService(repository, MemoryManifestStore()).resolve_manual(
            pending.id,
            game_id=pending.game_id,
            import_job_id=pending.import_job_id,
            expected_manifest_checksum_sha256=pending.processing_manifest_checksum_sha256,
            idempotency_key=uuid4(),
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            corners=(
                ImageReviewGeometryPoint(x=60, y=50),
                ImageReviewGeometryPoint(x=560, y=50),
                ImageReviewGeometryPoint(x=560, y=350),
                ImageReviewGeometryPoint(x=60, y=350),
            ),
            corrected_by="local-owner",
            resolved_at=datetime.now(UTC),
        )

    assert error.value.code == "IMAGE_BOARD_CELL_MANUAL_PREVIEW_UNAVAILABLE"


def test_missing_final_quad_recovers_only_matching_manual_draft() -> None:
    import pytest
    from game_predictor_api.domain.jobs import JobConflictError
    from game_predictor_api.storage.board_cell_geometry_pending_repository import (
        _manual_draft_from_source_revision,
        _validated_detected_board_geometry,
    )

    quad = [{"x": 480, "y": 73}, {"x": 683, "y": 73}, {"x": 677, "y": 182}, {"x": 473, "y": 180}]
    board = {
        "positionIndex": 1,
        "sequenceNumber": 149636,
        "initialQuad": quad,
        "finalQuad": None,
        "disposition": "needs_manual_review",
    }
    draft = _manual_draft_from_source_revision(
        [board],
        position_index=1,
        sequence_number=149636,
    )
    assert draft == {"quad": quad, "source": "manual_review_draft"}
    assert (
        _validated_detected_board_geometry(
            draft,
            source_width=1520,
            source_height=864,
        )
        == draft
    )
    assert board["finalQuad"] is None
    for boards in ([], [board, board], [{**board, "sequenceNumber": 149637}]):
        with pytest.raises(JobConflictError):
            _manual_draft_from_source_revision(
                boards,
                position_index=1,
                sequence_number=149636,
            )
