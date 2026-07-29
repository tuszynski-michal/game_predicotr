from __future__ import annotations

import hashlib
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
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewAlternative,
    ImageReviewCell,
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryRevision,
    ImageReviewItem,
    ImageReviewNotFoundError,
    ImageReviewPage,
    ImageReviewResolutionEvent,
    ImageReviewView,
    ValidatedImageReviewGeometryCommand,
    ValidatedImageReviewResolution,
)
from game_predictor_api.main import create_app
from game_predictor_worker.images.manual_geometry_recrop import ManualGeometryRecropper


class MemoryOperationalImageReviewRepository(OperationalImageReviewRepository):
    def __init__(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        items: Sequence[ImageReviewItem],
    ) -> None:
        self.game_id = game_id
        self.import_job_id = import_job_id
        self.items = {item.id: item for item in items}
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
        after_key: tuple[int, int, int, str] | None,
        before_key: tuple[int, int, int, str] | None,
        sequence_number: int | None,
        limit: int,
    ) -> ImageReviewPage:
        self.require_context(game_id=game_id, import_job_id=import_job_id)
        candidates = [
            item
            for item in self.items.values()
            if (
                item.status == "pending"
                if view is ImageReviewView.PENDING
                else item.status in {"accepted", "corrected"}
            )
            and (sequence_number is None or item.queue_sequence_number == sequence_number)
        ]
        candidates.sort(key=lambda item: item.cursor_key)
        if after_key is not None:
            if not any(item.cursor_key == after_key for item in candidates):
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_CURSOR_STALE",
                    "The operational review cursor is stale.",
                )
            candidates = [item for item in candidates if item.cursor_key > after_key]
        if before_key is not None:
            if not any(item.cursor_key == before_key for item in candidates):
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_CURSOR_STALE",
                    "The operational review cursor is stale.",
                )
            candidates = [item for item in candidates if item.cursor_key < before_key]
            visible = candidates[-limit:]
        else:
            visible = candidates[:limit]
        all_for_view = sorted(
            (
                item
                for item in self.items.values()
                if (
                    item.status == "pending"
                    if view is ImageReviewView.PENDING
                    else item.status in {"accepted", "corrected"}
                )
            ),
            key=lambda item: item.cursor_key,
        )
        return ImageReviewPage(
            items=tuple(visible),
            counts=self._counts(),
            has_previous=bool(
                visible and any(item.cursor_key < visible[0].cursor_key for item in all_for_view)
            ),
            has_next=bool(
                visible and any(item.cursor_key > visible[-1].cursor_key for item in all_for_view)
            ),
        )

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
        geometry_recropper=ManualGeometryRecropper(),
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
    assert len(body["geometryRevision"]["cells"]) == 15
    assert all(
        cell["currentSymbolCode"] == cell["predictedSymbolCode"] for cell in body["item"]["cells"]
    )
    assert all(
        revised["cropSampleId"] != previous.crop_sample_id
        for revised, previous in zip(body["item"]["cells"], item.cells, strict=True)
    )
    assert len(list((tmp_path / "data" / "image-review-geometry").rglob("*.png"))) == 16
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
    assert (
        reused_for_other_payload.json()["code"]
        == "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT"
    )

    stale = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-revisions",
        params=query,
        json={**payload, "idempotencyKey": str(uuid4())},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT"

    invalid = client.post(
        f"/api/v1/admin/image-review-items/{item.id}/geometry-preview",
        params=query,
        json={
            "expectedGeometryRevision": 1,
            "expectedResolutionRevision": 2,
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
        "completed": 0,
        "total": 3,
    }
    assert first_body["previousCursor"] is None
    assert first_body["nextCursor"]

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
