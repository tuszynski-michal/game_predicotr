from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_review_assets import (
    resolve_operational_source_asset,
)
from game_predictor_api.application.image_reviews import (
    OperationalImageReviewRepository,
    OperationalImageReviewService,
    PendingGridReinferencePreview,
)
from game_predictor_api.application.reviewer_access import ReviewerAccessService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewAlternative,
    ImageReviewCell,
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryRevision,
    ImageReviewGridIssueView,
    ImageReviewItem,
    ImageReviewNotFoundError,
    ImageReviewPage,
    ImageReviewResolutionEvent,
    ImageReviewView,
    ValidatedImageReviewGeometryCommand,
    ValidatedImageReviewResolution,
)
from game_predictor_api.main import create_app
from game_predictor_worker.images.manual_board_cell_geometry_preview import (
    ManualBoardCellGeometryPreviewer,
)


class MemoryOperationalImageReviewRepository(OperationalImageReviewRepository):
    def __init__(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        items: Sequence[ImageReviewItem],
        grid_issue_review_item_ids: Sequence[UUID] = (),
    ) -> None:
        self.game_id = game_id
        self.import_job_id = import_job_id
        self.items = {item.id: item for item in items}
        self.grid_issue_review_item_ids = frozenset(grid_issue_review_item_ids)
        self.queue_version = 1 if self.items else 0
        self.events: dict[UUID, list[ImageReviewResolutionEvent]] = {}
        self.geometry_revisions: dict[UUID, list[ImageReviewGeometryRevision]] = {}
        self.staging: dict[UUID, tuple[int, tuple[str, ...]]] = {}

    def require_context(self, *, game_id: UUID, import_job_id: UUID) -> None:
        if game_id != self.game_id or import_job_id != self.import_job_id:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_CONTEXT_NOT_FOUND",
                "The selected operational review context does not exist.",
            )

    def list_items(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        grid_issue_view: ImageReviewGridIssueView,
        after_key: tuple[int, int, str] | None,
        before_key: tuple[int, int, str] | None,
        expected_queue_version: int | None,
        sequence_number: int | None,
        resume_at_first_pending: bool,
        limit: int,
    ) -> ImageReviewPage:
        self.require_context(game_id=game_id, import_job_id=import_job_id)

        def belongs_to_view(item: ImageReviewItem) -> bool:
            if view is ImageReviewView.PENDING:
                return item.status == "pending"
            if view is ImageReviewView.COMPLETED:
                return item.status in {"accepted", "corrected"}
            return item.status in {
                "pending",
                "accepted",
                "corrected",
                "rejected",
                "superseded",
            }

        def effective_sequence_number(item: ImageReviewItem) -> int | None:
            if view is ImageReviewView.PENDING:
                return item.suggested_sequence_number
            if view is ImageReviewView.COMPLETED:
                return item.queue_sequence_number
            return item.queue_sequence_number or item.suggested_sequence_number

        def matches_grid_issue_view(item: ImageReviewItem) -> bool:
            return grid_issue_view is ImageReviewGridIssueView.ALL or (
                item.id in self.grid_issue_review_item_ids and item.status == "pending"
            )

        if expected_queue_version is not None and expected_queue_version != self.queue_version:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_CURSOR_STALE",
                "The operational review queue topology changed.",
            )

        def key(item: ImageReviewItem) -> tuple[int, int, str]:
            return item.queue_order_key

        candidates = [
            item
            for item in self.items.values()
            if belongs_to_view(item)
            and matches_grid_issue_view(item)
            and (sequence_number is None or effective_sequence_number(item) == sequence_number)
        ]
        candidates.sort(key=key)
        if resume_at_first_pending:
            first_pending = next(
                (item for item in candidates if item.status == "pending"),
                None,
            )
            if first_pending is not None:
                first_pending_key = key(first_pending)
                candidates = [item for item in candidates if key(item) >= first_pending_key]
        if after_key is not None:
            candidates = [item for item in candidates if key(item) > after_key]
        if before_key is not None:
            candidates = [item for item in candidates if key(item) < before_key]
            visible = candidates[-limit:]
        else:
            visible = candidates[:limit]
        all_for_view = sorted(
            (
                item
                for item in self.items.values()
                if belongs_to_view(item) and matches_grid_issue_view(item)
            ),
            key=key,
        )
        return ImageReviewPage(
            items=tuple(visible),
            counts=self._counts(),
            has_previous=bool(
                visible and any(key(item) < key(visible[0]) for item in all_for_view)
            ),
            has_next=bool(visible and any(key(item) > key(visible[-1]) for item in all_for_view)),
            queue_version=self.queue_version,
            needs_grid_fix_count=sum(
                item.id in self.grid_issue_review_item_ids and item.status == "pending"
                for item in self.items.values()
            ),
        )

    def queue_snapshot(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> tuple[int, ImageReviewCounts]:
        self.require_context(game_id=game_id, import_job_id=import_job_id)
        return self.queue_version, self._counts()

    def get_item(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        for_update: bool = False,
    ) -> ImageReviewItem | None:
        del for_update
        self.require_context(game_id=game_id, import_job_id=import_job_id)
        return self.items.get(review_item_id)

    def active_symbol_codes(self, game_id: UUID) -> Sequence[str]:
        return ("lemon", "seven") if game_id == self.game_id else ()

    def save_resolution(
        self,
        *,
        review_item_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        expected_revision: int,
        resolution: ValidatedImageReviewResolution,
        resolved_at: datetime,
    ) -> tuple[ImageReviewItem, ImageReviewResolutionEvent, bool]:
        item = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        assert item is not None
        history = self.events.setdefault(review_item_id, [])
        for event in history:
            if event.idempotency_key == idempotency_key:
                if event.command_sha256 != resolution.command_sha256:
                    raise ImageReviewConflictError(
                        "IMAGE_REVIEW_IDEMPOTENCY_CONFLICT",
                        "The idempotency key represents another command.",
                    )
                return item, event, False
        if item.resolution_revision != expected_revision:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_REVISION_CONFLICT",
                "The operational review item changed after it was loaded.",
                details={
                    "actualRevision": item.resolution_revision,
                    "actualStatus": item.status,
                    "conflictScope": "item",
                    "expectedRevision": expected_revision,
                    "reviewItemId": str(review_item_id),
                },
            )
        revision = item.resolution_revision + 1
        event = ImageReviewResolutionEvent(
            id=uuid4(),
            review_item_id=review_item_id,
            revision=revision,
            idempotency_key=idempotency_key,
            action=resolution.action.value,
            command_sha256=resolution.command_sha256,
            resolved_value=resolution.resolved_value,
            resolved_by=resolution.resolved_by,
            created_at=resolved_at,
        )
        updated = replace(
            item,
            status=resolution.action.value,
            queue_sequence_number=resolution.sequence_number,
            cells=tuple(
                replace(
                    cell,
                    current_symbol_code=resolution.cells[cell.cell_index].symbol_code,
                )
                for cell in item.cells
            )
            if resolution.cells
            else item.cells,
            resolved_value=resolution.resolved_value,
            resolved_by=resolution.resolved_by,
            resolved_at=resolved_at,
            resolution_revision=revision,
        )
        if resolution.action is ImageReviewAction.REJECTED:
            self.staging.pop(item.recognized_board_id, None)
        else:
            assert resolution.sequence_number is not None
            self.staging[item.recognized_board_id] = (
                resolution.sequence_number,
                tuple(cell.symbol_code for cell in resolution.cells),
            )
        history.append(event)
        self.items[review_item_id] = updated
        return updated, event, True

    def list_resolution_events(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> Sequence[ImageReviewResolutionEvent]:
        self.require_context(game_id=game_id, import_job_id=import_job_id)
        return tuple(self.events.get(review_item_id, ()))

    def get_geometry_revision_by_idempotency(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
    ) -> ImageReviewGeometryRevision | None:
        self.require_context(game_id=game_id, import_job_id=import_job_id)
        return next(
            (
                revision
                for revision in self.geometry_revisions.get(review_item_id, ())
                if revision.idempotency_key == idempotency_key
            ),
            None,
        )

    def save_geometry_revision(
        self,
        *,
        review_item_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        command: ValidatedImageReviewGeometryCommand,
        artifacts: ImageReviewGeometryArtifacts,
        created_at: datetime,
    ) -> tuple[ImageReviewItem, ImageReviewGeometryRevision, bool]:
        item = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        assert item is not None
        prior = self.get_geometry_revision_by_idempotency(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=idempotency_key,
        )
        if prior is not None:
            return item, prior, False
        if (
            item.geometry_revision != command.expected_geometry_revision
            or item.resolution_revision != command.expected_resolution_revision
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT",
                "The review item changed before geometry persistence.",
            )
        revision_number = item.geometry_revision + 1
        revision = ImageReviewGeometryRevision(
            id=uuid4(),
            review_item_id=review_item_id,
            recognized_board_id=item.recognized_board_id,
            revision=revision_number,
            idempotency_key=idempotency_key,
            command_sha256=command.command_sha256,
            decision_checksum_sha256=(
                str(artifacts.geometry["decisionChecksumSha256"])
                if "decisionChecksumSha256" in artifacts.geometry
                else None
            ),
            corners=command.corners,
            board_relative_path=artifacts.board_relative_path,
            board_checksum_sha256=artifacts.board_checksum_sha256,
            cropper_version=artifacts.cropper_version,
            cells=artifacts.cells,
            corrected_by=command.corrected_by,
            created_at=created_at,
        )
        revised_cells = tuple(
            replace(
                cell,
                crop_sample_id=hashlib.sha256(
                    (
                        f"{item.recognized_board_id}:{revision_number}:"
                        f"{cell.cell_index}:{artifacts.cells[cell.cell_index].crop_checksum_sha256}"
                    ).encode()
                ).hexdigest(),
                crop_relative_path=artifacts.cells[cell.cell_index].crop_relative_path,
                crop_checksum_sha256=artifacts.cells[cell.cell_index].crop_checksum_sha256,
                current_symbol_code=cell.predicted_symbol_code,
            )
            for cell in item.cells
        )
        updated = replace(
            item,
            status="pending",
            board_relative_path=artifacts.board_relative_path,
            board_checksum_sha256=artifacts.board_checksum_sha256,
            geometry_revision=revision_number,
            geometry=artifacts.geometry,
            cells=revised_cells,
            resolved_value=None,
            resolved_by=None,
            resolved_at=None,
            resolution_revision=item.resolution_revision + 1,
        )
        self.geometry_revisions.setdefault(review_item_id, []).append(revision)
        self.staging.pop(item.recognized_board_id, None)
        self.items[review_item_id] = updated
        return updated, revision, True

    def _counts(self) -> ImageReviewCounts:
        statuses = [item.status for item in self.items.values()]
        return ImageReviewCounts(
            pending=statuses.count("pending"),
            accepted=statuses.count("accepted"),
            corrected=statuses.count("corrected"),
            rejected=statuses.count("rejected"),
            superseded=statuses.count("superseded"),
        )

    def pending_grid_reinference_preview(
        self,
        game_id: UUID,
        *,
        geometry_version: str,
        cropper_version: str,
        audit_report_checksum_sha256: str,
    ) -> PendingGridReinferencePreview:
        if game_id != self.game_id:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_CONTEXT_NOT_FOUND",
                "The selected operational review context does not exist.",
            )
        items = tuple(self.items.values())
        pending = tuple(item for item in items if item.status == "pending")
        current = tuple(
            item
            for item in pending
            if item.geometry.get("geometryVersion") == geometry_version
            and item.geometry.get("cropperVersion") == cropper_version
        )
        return PendingGridReinferencePreview(
            game_id=game_id,
            pending_board_count=len(pending),
            recalculable_board_count=len(pending) - len(current),
            current_v19_board_count=len(current),
            protected_board_count=len(items) - len(pending),
            pending_source_count=len(pending),
            partially_resolved_source_count=0,
            fully_resolved_source_count=len(items) - len(pending),
            geometry_version=geometry_version,
            cropper_version=cropper_version,
            audit_report_checksum_sha256=audit_report_checksum_sha256,
        )


def _item(
    game_id: UUID,
    import_job_id: UUID,
    *,
    source_order_index: int,
    suggested_sequence_number: int,
) -> ImageReviewItem:
    review_item_id = uuid4()
    board_id = uuid4()
    cells = tuple(
        ImageReviewCell(
            observation_id=uuid4(),
            cell_index=index,
            row_index=index // 5,
            column_index=index % 5,
            crop_sample_id=hashlib.sha256(f"crop-{review_item_id}-{index}".encode()).hexdigest(),
            crop_relative_path=f"crops/{review_item_id}-{index}.png",
            crop_checksum_sha256="1" * 64,
            predicted_symbol_code="lemon",
            confidence=0.9,
            alternatives=(
                ImageReviewAlternative(symbol_code="lemon", confidence=0.9),
                ImageReviewAlternative(symbol_code="seven", confidence=0.1),
            ),
            current_symbol_code="lemon",
        )
        for index in range(15)
    )
    return ImageReviewItem(
        id=review_item_id,
        game_id=game_id,
        import_job_id=import_job_id,
        source_image_id=uuid4(),
        recognized_board_id=board_id,
        status="pending",
        source_order_index=source_order_index,
        position_index=0,
        queue_sequence_number=None,
        suggested_sequence_number=suggested_sequence_number,
        source_relative_path=f"sources/{review_item_id}.jpg",
        source_checksum_sha256="2" * 64,
        board_relative_path=f"boards/{review_item_id}.png",
        board_checksum_sha256="3" * 64,
        geometry_revision=0,
        geometry={"corners": [[0, 0], [1, 0], [1, 1], [0, 1]]},
        pipeline_fingerprint="4" * 64,
        cells=cells,
        resolved_value=None,
        resolved_by=None,
        resolved_at=None,
        resolution_revision=0,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def operational_review_context() -> tuple[
    TestClient,
    MemoryOperationalImageReviewRepository,
    UUID,
    UUID,
]:
    game_id = uuid4()
    import_job_id = uuid4()
    repository = MemoryOperationalImageReviewRepository(
        game_id=game_id,
        import_job_id=import_job_id,
        items=[
            _item(
                game_id,
                import_job_id,
                source_order_index=index,
                suggested_sequence_number=index + 1,
            )
            for index in range(3)
        ],
    )
    app = create_app(
        ApiSettings.from_environment({}),
        image_review_service_dependency=lambda: OperationalImageReviewService(repository),
    )
    return TestClient(app), repository, game_id, import_job_id


def _resolution_payload(
    item: ImageReviewItem,
    *,
    idempotency_key: UUID,
    expected_revision: int = 0,
    action: str = "accepted",
    sequence_number: int | None = None,
    corrected_cell: int | None = None,
) -> dict[str, object]:
    return {
        "idempotencyKey": str(idempotency_key),
        "expectedRevision": expected_revision,
        "action": action,
        "sequenceNumber": sequence_number or item.suggested_sequence_number,
        "geometryRevision": item.geometry_revision,
        "cells": [
            {
                "cellIndex": cell.cell_index,
                "cropSampleId": cell.crop_sample_id,
                "symbolCode": (
                    "seven" if corrected_cell == cell.cell_index else cell.predicted_symbol_code
                ),
            }
            for cell in item.cells
        ],
        "resolvedBy": "local-admin",
    }


def test_pending_grid_preview_distinguishes_v19_from_recalculable_pending_boards(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, _import_job_id = operational_review_context
    current_id = next(iter(repository.items))
    current = repository.items[current_id]
    repository.items[current_id] = replace(
        current,
        geometry={
            **current.geometry,
            "cropperVersion": ("board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1"),
            "geometryVersion": "board-cell-geometry-v19-multi-point-source-direct-v1",
        },
    )

    response = client.get(
        f"/api/v1/admin/image-review-items/pending-grid-reinference/preview/{game_id}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pendingBoardCount"] == 3
    assert payload["recalculableBoardCount"] == 2
    assert payload["currentV19BoardCount"] == 1
    assert payload["protectedBoardCount"] == 0
    assert payload["geometryVersion"] == ("board-cell-geometry-v19-multi-point-source-direct-v1")
    assert payload["cropperVersion"] == (
        "board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1"
    )
    assert len(payload["auditReportChecksumSha256"]) == 64


def test_reviewer_token_enforces_scope_and_overrides_decision_actor() -> None:
    game_id = uuid4()
    import_job_id = uuid4()
    item = _item(
        game_id,
        import_job_id,
        source_order_index=0,
        suggested_sequence_number=1,
    )
    repository = MemoryOperationalImageReviewRepository(
        game_id=game_id,
        import_job_id=import_job_id,
        items=[item],
        grid_issue_review_item_ids=[item.id],
    )
    access = ReviewerAccessService("http://127.0.0.1:3001")
    created = access.create(
        game_id=game_id,
        import_job_id=import_job_id,
        lifetime_minutes=60,
    )
    token = access.unlock(created.session.id, created.code).access_token
    app = create_app(
        ApiSettings.from_environment({}),
        image_review_service_dependency=lambda: OperationalImageReviewService(repository),
        reviewer_access_service_dependency=lambda: access,
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    allowed = client.get(
        "/api/v1/admin/image-review-items",
        params={
            "gameId": str(game_id),
            "importJobId": str(import_job_id),
            "view": "all",
            "gridIssueView": "needs_grid_fix",
            "limit": 1,
        },
        headers=headers,
    )
    assert allowed.status_code == 200

    forbidden = client.get(
        "/api/v1/admin/image-review-items",
        params={
            "gameId": str(game_id),
            "importJobId": str(uuid4()),
            "view": "all",
            "gridIssueView": "needs_grid_fix",
            "limit": 1,
        },
        headers=headers,
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "REVIEWER_SCOPE_FORBIDDEN"

    resolved = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/resolution",
        params={"gameId": str(game_id), "importJobId": str(import_job_id)},
        json=_resolution_payload(item, idempotency_key=uuid4()),
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["event"]["resolvedBy"] == (f"reviewer-session:{created.session.id}")


def test_geometry_preview_and_revision_reopen_without_copying_human_labels(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    import_job_id = uuid4()
    original = _item(
        game_id,
        import_job_id,
        source_order_index=0,
        suggested_sequence_number=1,
    )
    rgb = np.zeros((420, 720, 3), dtype=np.uint8)
    rgb[60:350, 90:630] = (30, 160, 220)
    encoded, buffer = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert encoded
    source_content = bytes(buffer)
    source_relative_path = f"sources/{original.id}.png"
    source_path = tmp_path / "data" / source_relative_path
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source_content)
    item = replace(
        original,
        source_relative_path=source_relative_path,
        source_checksum_sha256=hashlib.sha256(source_content).hexdigest(),
        queue_sequence_number=1,
        geometry={
            **original.geometry,
            "sequenceSource": "filename",
            "sequenceLabelQuad": [
                {"x": 260, "y": 370},
                {"x": 450, "y": 370},
                {"x": 450, "y": 395},
                {"x": 260, "y": 395},
            ],
            "sourceContextBounds": {
                "height": 380,
                "width": 680,
                "x": 20,
                "y": 20,
            },
        },
        status="corrected",
        resolved_value={
            "action": "corrected",
            "geometryRevision": 0,
            "sequenceNumber": 1,
            "symbolCodes": ["seven"] * 15,
        },
        resolved_by="local-admin",
        resolved_at=datetime.now(UTC),
        resolution_revision=1,
        cells=tuple(replace(cell, current_symbol_code="seven") for cell in original.cells),
    )
    untouched = _item(
        game_id,
        import_job_id,
        source_order_index=1,
        suggested_sequence_number=2,
    )
    repository = MemoryOperationalImageReviewRepository(
        game_id=game_id,
        import_job_id=import_job_id,
        items=[item, untouched],
    )
    settings = ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path)})
    service = OperationalImageReviewService(
        repository,
        artifact_root=tmp_path,
        board_cell_geometry_previewer=ManualBoardCellGeometryPreviewer(),
    )
    client = TestClient(
        create_app(
            settings,
            image_review_service_dependency=lambda: service,
        )
    )
    query = {"gameId": str(game_id), "importJobId": str(import_job_id)}
    corners = [
        {"x": 90, "y": 60},
        {"x": 630, "y": 65},
        {"x": 635, "y": 350},
        {"x": 85, "y": 345},
    ]
    preview = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-preview",
        params=query,
        json={
            "expectedGeometryRevision": 0,
            "expectedResolutionRevision": 1,
            "corners": corners,
        },
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["x-board-cell-count"] == "15"
    assert preview.headers["x-board-cell-preview-kind"] == "contact-sheet-5x3"
    assert preview.headers["x-board-cell-cropper-version"] == (
        "board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1"
    )
    contact_sheet = cv2.imdecode(np.frombuffer(preview.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert contact_sheet is not None
    assert contact_sheet.shape[:2] == (3 * 64, 5 * 64)
    assert not (tmp_path / "data" / "image-review-geometry").exists()

    idempotency_key = uuid4()
    payload = {
        "idempotencyKey": str(idempotency_key),
        "expectedGeometryRevision": 0,
        "expectedResolutionRevision": 1,
        "corners": corners,
        "correctedBy": "local-admin",
    }
    saved = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-revisions",
        params=query,
        json=payload,
    )

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["created"] is True
    assert body["item"]["status"] == "pending"
    assert body["item"]["geometryRevision"] == 1
    assert body["item"]["resolutionRevision"] == 2
    assert body["item"]["resolvedValue"] is None
    assert body["item"]["geometry"]["sourceContextBounds"] == {
        "height": 380,
        "width": 680,
        "x": 20,
        "y": 20,
    }
    assert body["item"]["geometry"]["sequenceLabelQuad"] == item.geometry["sequenceLabelQuad"]
    assert body["item"]["geometry"]["source"] == "manual_override"
    assert body["item"]["geometry"]["cornerSemantics"] == ("symbol-lattice-outer-bounds-5x3")
    assert body["item"]["geometry"]["geometryVersion"] == (
        "board-cell-geometry-v19-multi-point-source-direct-v1"
    )
    assert body["item"]["geometry"]["cropperVersion"] == (
        "board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1"
    )
    assert body["item"]["geometry"]["sourceImageChecksumSha256"] == (item.source_checksum_sha256)
    assert body["item"]["geometry"]["sourceOrderIndex"] == item.source_order_index
    assert body["item"]["geometry"]["positionIndex"] == item.position_index
    assert body["item"]["geometry"]["correctedBy"] == "local-admin"
    assert len(body["item"]["geometry"]["cells"]) == 15
    assert (
        body["geometryRevision"]["decisionChecksumSha256"]
        == (body["item"]["geometry"]["decisionChecksumSha256"])
    )
    assert body["geometryRevision"]["cropperVersion"] == (
        "board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1"
    )
    assert len(body["geometryRevision"]["cells"]) == 15
    assert all(
        cell["currentSymbolCode"] == cell["predictedSymbolCode"] for cell in body["item"]["cells"]
    )
    assert all(
        revised["cropSampleId"] != previous.crop_sample_id
        for revised, previous in zip(body["item"]["cells"], item.cells, strict=True)
    )
    persisted_cells = list(
        (tmp_path / "data" / "image-review-board-cell-geometry-v19").rglob("*.png")
    )
    assert len(persisted_cells) == 15
    assert not (tmp_path / "data" / "image-review-geometry").exists()
    first_revision = repository.geometry_revisions[item.id][0]
    for cell in first_revision.cells:
        persisted = cv2.imread(str(tmp_path / "data" / cell.crop_relative_path))
        assert persisted is not None
        size = 64
        expected = contact_sheet[
            cell.row_index * size : (cell.row_index + 1) * size,
            cell.column_index * size : (cell.column_index + 1) * size,
        ]
        assert np.array_equal(persisted, expected)
    assert repository.items[untouched.id] == untouched

    retry = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-revisions",
        params=query,
        json=payload,
    )
    assert retry.status_code == 200
    assert retry.json()["created"] is False

    reused_for_other_payload = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-revisions",
        params=query,
        json={**payload, "correctedBy": "another-operator"},
    )
    assert reused_for_other_payload.status_code == 409
    assert reused_for_other_payload.json()["code"] == "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT"

    stale = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-revisions",
        params=query,
        json={**payload, "idempotencyKey": str(uuid4())},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT"

    second_preview = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-preview",
        params=query,
        json={
            "expectedGeometryRevision": 1,
            "expectedResolutionRevision": 2,
            "corners": corners,
        },
    )
    assert second_preview.status_code == 200
    assert second_preview.headers["content-type"] == "image/png"

    second_corners = [
        {"x": 95, "y": 62},
        {"x": 625, "y": 67},
        {"x": 630, "y": 347},
        {"x": 90, "y": 342},
    ]
    second_saved = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-revisions",
        params=query,
        json={
            "idempotencyKey": str(uuid4()),
            "expectedGeometryRevision": 1,
            "expectedResolutionRevision": 2,
            "corners": second_corners,
            "correctedBy": "second-owner",
        },
    )
    assert second_saved.status_code == 200, second_saved.text
    assert second_saved.json()["geometryRevision"]["revision"] == 2
    assert second_saved.json()["item"]["geometryRevision"] == 2
    assert second_saved.json()["item"]["resolutionRevision"] == 3
    assert len(repository.geometry_revisions[item.id]) == 2
    assert repository.geometry_revisions[item.id][0] == first_revision
    assert (
        repository.geometry_revisions[item.id][1].decision_checksum_sha256
        != first_revision.decision_checksum_sha256
    )
    assert (
        len(list((tmp_path / "data" / "image-review-board-cell-geometry-v19").rglob("*.png"))) == 30
    )

    invalid = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-preview",
        params=query,
        json={
            "expectedGeometryRevision": 2,
            "expectedResolutionRevision": 3,
            "corners": [
                {"x": 90, "y": 60},
                {"x": 630, "y": 350},
                {"x": 630, "y": 60},
                {"x": 90, "y": 350},
            ],
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["code"] == "IMAGE_REVIEW_GEOMETRY_CORNERS_INVALID"


def test_v19_geometry_preview_does_not_treat_an_unattested_suggestion_as_sequence(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, import_job_id = operational_review_context
    item = next(iter(repository.items.values()))

    response = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-preview",
        params={"gameId": str(game_id), "importJobId": str(import_job_id)},
        json={
            "expectedGeometryRevision": item.geometry_revision,
            "expectedResolutionRevision": item.resolution_revision,
            "corners": [
                {"x": 0, "y": 0},
                {"x": 10, "y": 0},
                {"x": 10, "y": 10},
                {"x": 0, "y": 10},
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "BOARD_CELL_GEOMETRY_PREVIEW_SEQUENCE_UNRESOLVED"

    saved = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-revisions",
        params={"gameId": str(game_id), "importJobId": str(import_job_id)},
        json={
            "idempotencyKey": str(uuid4()),
            "expectedGeometryRevision": item.geometry_revision,
            "expectedResolutionRevision": item.resolution_revision,
            "corners": [
                {"x": 0, "y": 0},
                {"x": 10, "y": 0},
                {"x": 10, "y": 10},
                {"x": 0, "y": 10},
            ],
            "correctedBy": "local-admin",
        },
    )
    assert saved.status_code == 409
    assert saved.json()["code"] == "BOARD_CELL_GEOMETRY_PREVIEW_SEQUENCE_UNRESOLVED"


def test_cursor_queue_is_bounded_reversible_and_scope_bound(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, _repository, game_id, import_job_id = operational_review_context
    query = {"gameId": str(game_id), "importJobId": str(import_job_id), "limit": 2}
    first = client.get("/api/v1/admin/image-review-items", params=query)
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["counts"] == {
        "pending": 3,
        "accepted": 0,
        "corrected": 0,
        "rejected": 0,
        "superseded": 0,
        "completed": 0,
        "total": 3,
    }
    assert first_body["queueVersion"] == 1
    assert first_body["previousCursor"] is None
    assert first_body["nextCursor"]
    padding = "=" * (-len(first_body["nextCursor"]) % 4)
    cursor_payload = json.loads(base64.urlsafe_b64decode(first_body["nextCursor"] + padding))
    assert cursor_payload["version"] == 3
    assert cursor_payload["queueVersion"] == 1
    assert cursor_payload["gridIssueView"] == "all"
    assert cursor_payload["key"] == [
        first_body["items"][-1]["sourceOrderIndex"],
        first_body["items"][-1]["positionIndex"],
        first_body["items"][-1]["id"],
    ]

    second = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "afterCursor": first_body["nextCursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["previousCursor"]
    assert second_body["nextCursor"] is None

    back = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "beforeCursor": second_body["previousCursor"]},
    )
    assert [item["id"] for item in back.json()["items"]] == [
        item["id"] for item in first_body["items"]
    ]
    wrong_scope = client.get(
        "/api/v1/admin/image-review-items",
        params={
            **query,
            "gameId": str(uuid4()),
            "afterCursor": first_body["nextCursor"],
        },
    )
    assert wrong_scope.status_code in {404, 409}


def test_grid_issue_view_lists_each_flagged_pending_board_once_and_scopes_cursors() -> None:
    game_id = uuid4()
    import_job_id = uuid4()
    first = _item(
        game_id,
        import_job_id,
        source_order_index=0,
        suggested_sequence_number=1,
    )
    second = _item(
        game_id,
        import_job_id,
        source_order_index=1,
        suggested_sequence_number=2,
    )
    completed = replace(
        _item(
            game_id,
            import_job_id,
            source_order_index=2,
            suggested_sequence_number=3,
        ),
        status="accepted",
    )
    rejected = replace(
        _item(
            game_id,
            import_job_id,
            source_order_index=3,
            suggested_sequence_number=4,
        ),
        status="rejected",
    )
    superseded = replace(
        _item(
            game_id,
            import_job_id,
            source_order_index=4,
            suggested_sequence_number=5,
        ),
        status="superseded",
    )
    repository = MemoryOperationalImageReviewRepository(
        game_id=game_id,
        import_job_id=import_job_id,
        items=[first, second, completed, rejected, superseded],
        grid_issue_review_item_ids=[
            first.id,
            second.id,
            completed.id,
            rejected.id,
            superseded.id,
        ],
    )
    app = create_app(
        ApiSettings.from_environment({}),
        image_review_service_dependency=lambda: OperationalImageReviewService(repository),
    )
    client = TestClient(app)
    context = {
        "gameId": str(game_id),
        "importJobId": str(import_job_id),
        "view": "all",
        "gridIssueView": "needs_grid_fix",
        "limit": 1,
    }

    first_page = client.get("/api/v1/admin/image-review-items", params=context)
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert first_body["gridIssueView"] == "needs_grid_fix"
    assert first_body["needsGridFixCount"] == 2
    assert [item["id"] for item in first_body["items"]] == [str(first.id)]
    assert first_body["nextCursor"] is not None

    second_page = client.get(
        "/api/v1/admin/image-review-items",
        params={**context, "afterCursor": first_body["nextCursor"]},
    )
    assert second_page.status_code == 200
    assert [item["id"] for item in second_page.json()["items"]] == [str(second.id)]

    wrong_filter = client.get(
        "/api/v1/admin/image-review-items",
        params={
            **context,
            "gridIssueView": "all",
            "afterCursor": first_body["nextCursor"],
        },
    )
    assert wrong_filter.status_code == 409
    assert wrong_filter.json()["code"] == "IMAGE_REVIEW_CURSOR_SCOPE_INVALID"


def test_pending_cursor_survives_boundary_resolution_but_not_topology_change(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, import_job_id = operational_review_context
    query = {
        "gameId": str(game_id),
        "importJobId": str(import_job_id),
        "view": "pending",
        "limit": 1,
    }
    first = client.get("/api/v1/admin/image-review-items", params=query)
    assert first.status_code == 200
    first_body = first.json()
    first_item = repository.items[UUID(first_body["items"][0]["id"])]

    resolved = client.post(
        f"/api/v1/admin/image-review-items/{first_item.id}/resolution",
        params={"gameId": str(game_id), "importJobId": str(import_job_id)},
        json=_resolution_payload(
            first_item,
            idempotency_key=uuid4(),
            action="corrected",
            sequence_number=999,
            corrected_cell=0,
        ),
    )
    assert resolved.status_code == 200

    next_page = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "afterCursor": first_body["nextCursor"]},
    )
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["sourceOrderIndex"] == 1
    assert next_page.json()["queueVersion"] == 1

    repository.queue_version += 1
    stale = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "afterCursor": first_body["nextCursor"]},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "IMAGE_REVIEW_CURSOR_STALE"


def test_all_view_keeps_source_order_and_cursor_valid_after_resolution(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, import_job_id = operational_review_context
    query = {
        "gameId": str(game_id),
        "importJobId": str(import_job_id),
        "view": "all",
        "limit": 1,
    }
    first = client.get("/api/v1/admin/image-review-items", params=query)
    assert first.status_code == 200
    first_body = first.json()
    first_id = UUID(first_body["items"][0]["id"])
    assert first_body["nextCursor"]

    item = repository.items[first_id]
    resolved = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/resolution",
        params={"gameId": str(game_id), "importJobId": str(import_job_id)},
        json=_resolution_payload(
            item,
            idempotency_key=uuid4(),
            action="corrected",
            sequence_number=99,
            corrected_cell=0,
        ),
    )
    assert resolved.status_code == 200

    next_page = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "afterCursor": first_body["nextCursor"]},
    )
    assert next_page.status_code == 200
    next_body = next_page.json()
    assert next_body["items"][0]["sourceOrderIndex"] == 1
    assert next_body["previousCursor"]

    previous_page = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "beforeCursor": next_body["previousCursor"]},
    )
    assert previous_page.status_code == 200
    assert previous_page.json()["items"][0]["id"] == str(first_id)
    assert previous_page.json()["nextCursor"] is not None

    exact_jump = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "sequenceNumber": 99},
    )
    assert exact_jump.status_code == 200
    assert exact_jump.json()["items"][0]["id"] == str(first_id)

    ordered = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "limit": 3},
    )
    assert [item["sourceOrderIndex"] for item in ordered.json()["items"]] == [0, 1, 2]


def test_all_view_can_resume_at_first_pending_with_previous_navigation(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, import_job_id = operational_review_context
    first_item = min(repository.items.values(), key=lambda item: item.source_order_index)
    resolved = client.post(
        f"/api/v1/admin/image-review-items/{first_item.id}/resolution",
        params={"gameId": str(game_id), "importJobId": str(import_job_id)},
        json=_resolution_payload(first_item, idempotency_key=uuid4()),
    )
    assert resolved.status_code == 200

    query = {
        "gameId": str(game_id),
        "importJobId": str(import_job_id),
        "view": "all",
        "resumeAtFirstPending": "true",
        "limit": 1,
    }
    resumed = client.get("/api/v1/admin/image-review-items", params=query)
    assert resumed.status_code == 200
    resumed_body = resumed.json()
    assert resumed_body["items"][0]["sourceOrderIndex"] == 1
    assert resumed_body["previousCursor"]

    previous = client.get(
        "/api/v1/admin/image-review-items",
        params={
            "gameId": str(game_id),
            "importJobId": str(import_job_id),
            "view": "all",
            "beforeCursor": resumed_body["previousCursor"],
            "limit": 1,
        },
    )
    assert previous.status_code == 200
    assert previous.json()["items"][0]["sourceOrderIndex"] == 0
    assert previous.json()["nextCursor"] is not None

    invalid = client.get(
        "/api/v1/admin/image-review-items",
        params={
            "gameId": str(game_id),
            "importJobId": str(import_job_id),
            "view": "pending",
            "resumeAtFirstPending": "true",
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["code"] == "IMAGE_REVIEW_PAGE_INVALID"


def test_all_view_resume_falls_back_to_first_item_when_nothing_is_pending(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, import_job_id = operational_review_context
    context = {"gameId": str(game_id), "importJobId": str(import_job_id)}
    for item in sorted(repository.items.values(), key=lambda value: value.source_order_index):
        response = client.post(
            f"/api/v1/admin/image-review-items/{item.id}/resolution",
            params=context,
            json=_resolution_payload(item, idempotency_key=uuid4()),
        )
        assert response.status_code == 200

    resumed = client.get(
        "/api/v1/admin/image-review-items",
        params={
            **context,
            "view": "all",
            "resumeAtFirstPending": "true",
            "limit": 1,
        },
    )
    assert resumed.status_code == 200
    assert resumed.json()["items"][0]["sourceOrderIndex"] == 0
    assert resumed.json()["previousCursor"] is None


def test_whole_board_resolution_is_idempotent_and_reeditable(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, import_job_id = operational_review_context
    item = min(repository.items.values(), key=lambda value: value.source_order_index)
    endpoint = f"/api/v1/admin/image-review-items/{item.id}/resolution"
    query = {"gameId": str(game_id), "importJobId": str(import_job_id)}
    key = uuid4()
    accepted_payload = _resolution_payload(item, idempotency_key=key)

    accepted = client.post(endpoint, params=query, json=accepted_payload)
    assert accepted.status_code == 200
    assert accepted.json()["created"] is True
    assert accepted.json()["item"]["resolutionRevision"] == 1
    assert len(repository.staging) == 1

    retry = client.post(endpoint, params=query, json=accepted_payload)
    assert retry.status_code == 200
    assert retry.json()["created"] is False
    assert len(repository.events[item.id]) == 1

    corrected_payload = _resolution_payload(
        repository.items[item.id],
        idempotency_key=uuid4(),
        expected_revision=1,
        action="corrected",
        sequence_number=99,
        corrected_cell=0,
    )
    corrected = client.post(endpoint, params=query, json=corrected_payload)
    assert corrected.status_code == 200
    assert corrected.json()["item"]["status"] == "corrected"
    assert corrected.json()["item"]["sequenceNumber"] == 99
    assert len(repository.staging) == 1
    assert repository.staging[item.recognized_board_id][0] == 99

    completed = client.get(
        "/api/v1/admin/image-review-items",
        params={**query, "view": "completed", "sequenceNumber": 99},
    )
    assert completed.status_code == 200
    assert [value["id"] for value in completed.json()["items"]] == [str(item.id)]
    history = client.get(
        f"/api/v1/admin/image-review-items/{item.id}/resolution-events",
        params=query,
    )
    assert [event["revision"] for event in history.json()] == [1, 2]


def test_resolution_uses_item_revision_and_returns_authoritative_queue_snapshot(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, import_job_id = operational_review_context
    items = sorted(repository.items.values(), key=lambda value: value.source_order_index)
    current, neighbor, remaining = items
    endpoint = f"/api/v1/admin/image-review-items/{current.id}/resolution"
    context = {"gameId": str(game_id), "importJobId": str(import_job_id)}
    command_key = uuid4()
    command = _resolution_payload(current, idempotency_key=command_key)

    neighbor_response = client.post(
        f"/api/v1/admin/image-review-items/{neighbor.id}/resolution",
        params=context,
        json=_resolution_payload(neighbor, idempotency_key=uuid4()),
    )
    assert neighbor_response.status_code == 200

    resolved = client.post(endpoint, params=context, json=command)
    assert resolved.status_code == 200
    assert resolved.json()["created"] is True
    assert resolved.json()["queueVersion"] == 1
    assert resolved.json()["counts"] == {
        "pending": 1,
        "accepted": 2,
        "corrected": 0,
        "rejected": 0,
        "superseded": 0,
        "completed": 2,
        "total": 3,
    }

    last_response = client.post(
        f"/api/v1/admin/image-review-items/{remaining.id}/resolution",
        params=context,
        json=_resolution_payload(remaining, idempotency_key=uuid4()),
    )
    assert last_response.status_code == 200

    exact_retry = client.post(endpoint, params=context, json=command)
    assert exact_retry.status_code == 200
    assert exact_retry.json()["created"] is False
    assert exact_retry.json()["queueVersion"] == 1
    assert exact_retry.json()["counts"]["pending"] == 0
    assert exact_retry.json()["counts"]["accepted"] == 3

    stale = client.post(
        endpoint,
        params=context,
        json=_resolution_payload(
            repository.items[current.id],
            idempotency_key=uuid4(),
            expected_revision=0,
            action="corrected",
            corrected_cell=0,
        ),
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "IMAGE_REVIEW_REVISION_CONFLICT"
    assert stale.json()["details"] == {
        "actualRevision": 1,
        "actualStatus": "accepted",
        "conflictScope": "item",
        "expectedRevision": 0,
        "reviewItemId": str(current.id),
    }


def test_resolution_rejects_stale_revision_and_changed_idempotent_command(
    operational_review_context: tuple[
        TestClient,
        MemoryOperationalImageReviewRepository,
        UUID,
        UUID,
    ],
) -> None:
    client, repository, game_id, import_job_id = operational_review_context
    item = next(iter(repository.items.values()))
    endpoint = f"/api/v1/admin/image-review-items/{item.id}/resolution"
    query = {"gameId": str(game_id), "importJobId": str(import_job_id)}
    key = uuid4()
    payload = _resolution_payload(item, idempotency_key=key)
    assert client.post(endpoint, params=query, json=payload).status_code == 200

    stale = _resolution_payload(
        repository.items[item.id],
        idempotency_key=uuid4(),
        expected_revision=0,
        action="corrected",
        corrected_cell=0,
    )
    stale_response = client.post(endpoint, params=query, json=stale)
    assert stale_response.status_code == 409
    assert stale_response.json()["code"] == "IMAGE_REVIEW_REVISION_CONFLICT"

    changed = _resolution_payload(
        repository.items[item.id],
        idempotency_key=key,
        expected_revision=1,
        action="corrected",
        corrected_cell=0,
    )
    changed_response = client.post(endpoint, params=query, json=changed)
    assert changed_response.status_code == 409
    assert changed_response.json()["code"] == "IMAGE_REVIEW_IDEMPOTENCY_CONFLICT"


def test_asset_resolution_is_checksum_bound_and_rejects_traversal(tmp_path: Path) -> None:
    game_id = uuid4()
    import_job_id = uuid4()
    item = _item(
        game_id,
        import_job_id,
        source_order_index=0,
        suggested_sequence_number=1,
    )
    source = tmp_path / "data" / "sources" / "board.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"image-fixture")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    valid = replace(
        item,
        source_relative_path="sources/board.jpg",
        source_checksum_sha256=checksum,
    )
    assert resolve_operational_source_asset(valid, tmp_path).path == source

    with pytest.raises(ImageReviewNotFoundError) as checksum_error:
        resolve_operational_source_asset(
            replace(valid, source_checksum_sha256="0" * 64),
            tmp_path,
        )
    assert checksum_error.value.code == "IMAGE_REVIEW_ASSET_CHECKSUM_DRIFT"

    with pytest.raises(ImageReviewNotFoundError) as path_error:
        resolve_operational_source_asset(
            replace(valid, source_relative_path="../board.jpg"),
            tmp_path,
        )
    assert path_error.value.code == "IMAGE_REVIEW_ASSET_PATH_UNSAFE"
