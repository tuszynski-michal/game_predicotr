from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.reviews import ReviewRepository, ReviewService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.reviews import (
    ReviewBatch,
    ReviewConflictError,
    ReviewError,
    ReviewFeedbackExport,
    ReviewItem,
    ReviewItemPage,
    ReviewItemStatus,
    ReviewResolution,
    ValidatedReviewResolution,
    ValidatedReviewSelection,
    canonical_report_bytes,
    canonical_review_bytes,
    validate_review_selection,
)
from game_predictor_api.main import create_app

ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = ROOT / "ai_docs" / "quality" / "m6-symbol-active-learning-selection.json"


def _report() -> tuple[dict[str, object], str]:
    content = REPORT_PATH.read_bytes()
    value: Any = json.loads(content)
    assert isinstance(value, dict)
    return value, hashlib.sha256(content).hexdigest()


class MemoryReviewRepository(ReviewRepository):
    def __init__(self, game_id: UUID, symbols: Sequence[str]) -> None:
        self.game_id = game_id
        self.symbols = tuple(symbols)
        self.batches: dict[UUID, ReviewBatch] = {}
        self.items: dict[UUID, ReviewItem] = {}
        self.resolutions: dict[UUID, list[ReviewResolution]] = {}
        self.feedback_exports: dict[UUID, ReviewFeedbackExport] = {}

    def get_active_symbol_codes(self, game_id: UUID) -> Sequence[str] | None:
        return self.symbols if game_id == self.game_id else None

    def list_review_batches(self) -> Sequence[ReviewBatch]:
        return sorted(
            self.batches.values(),
            key=lambda batch: (batch.created_at, batch.id),
            reverse=True,
        )

    def get_review_batch(self, review_batch_id: UUID) -> ReviewBatch | None:
        return self.batches.get(review_batch_id)

    def get_review_batch_by_report(
        self,
        source_report_sha256: str,
    ) -> ReviewBatch | None:
        return next(
            (
                batch
                for batch in self.batches.values()
                if batch.source_report_sha256 == source_report_sha256
            ),
            None,
        )

    def add_review_batch(
        self,
        *,
        game_id: UUID,
        selection: ValidatedReviewSelection,
    ) -> ReviewBatch:
        now = datetime.now(UTC)
        batch = ReviewBatch(
            id=uuid4(),
            game_id=game_id,
            source_report_sha256=selection.source_report_sha256,
            active_learning_version=selection.active_learning_version,
            model_version=selection.model_version,
            model_artifact_sha256=selection.model_artifact_sha256,
            calibration_report_sha256=selection.calibration_report_sha256,
            dataset_sha256=selection.dataset_sha256,
            split_sha256=selection.split_sha256,
            inventory_sha256=selection.inventory_sha256,
            temperature=selection.temperature,
            item_count=len(selection.item_snapshots),
            source_report=dict(selection.source_report),
            created_at=now,
        )
        self.batches[batch.id] = batch
        for snapshot in selection.item_snapshots:
            item = ReviewItem(
                id=uuid4(),
                review_batch_id=batch.id,
                board_id=cast(str, snapshot["boardId"]),
                selection_rank=cast(int, snapshot["selectionRank"]),
                sequence_number=cast(int, snapshot["sequenceNumber"]),
                source_image_id=cast(str, snapshot["sourceImageId"]),
                source_image_checksum_sha256=cast(
                    str,
                    snapshot["sourceImageChecksumSha256"],
                ),
                source_group=cast(str, snapshot["sourceGroup"]),
                board_relative_path=cast(str, snapshot["boardRelativePath"]),
                status=ReviewItemStatus.PENDING,
                prediction_snapshot=dict(snapshot),
                created_at=now,
            )
            self.items[item.id] = item
        return batch

    def list_review_items(
        self,
        *,
        review_batch_id: UUID,
        status: ReviewItemStatus | None,
        after_selection_rank: int,
        limit: int,
    ) -> ReviewItemPage:
        candidates = sorted(
            (
                item
                for item in self.items.values()
                if item.review_batch_id == review_batch_id
                and item.selection_rank > after_selection_rank
                and (status is None or item.status is status)
            ),
            key=lambda item: item.selection_rank,
        )
        visible = candidates[:limit]
        return ReviewItemPage(
            items=tuple(visible),
            next_after_selection_rank=(
                visible[-1].selection_rank if len(candidates) > limit else None
            ),
        )

    def get_review_item(self, review_item_id: UUID) -> ReviewItem | None:
        return self.items.get(review_item_id)

    def save_review_resolution(
        self,
        *,
        review_item_id: UUID,
        idempotency_key: UUID,
        expected_revision: int,
        resolution: ValidatedReviewResolution,
    ) -> tuple[ReviewItem, ReviewResolution, bool]:
        history = self.resolutions.setdefault(review_item_id, [])
        for event in history:
            if event.idempotency_key == idempotency_key:
                if event.command_sha256 != resolution.command_sha256:
                    raise ReviewConflictError(
                        "REVIEW_IDEMPOTENCY_KEY_REUSED",
                        "The idempotency key was reused.",
                    )
                return self.items[review_item_id], event, False
        item = self.items[review_item_id]
        if item.resolution_revision != expected_revision:
            raise ReviewConflictError(
                "REVIEW_REVISION_CONFLICT",
                "The review item changed after it was loaded.",
            )
        now = datetime.now(UTC)
        event = ReviewResolution(
            id=uuid4(),
            review_item_id=review_item_id,
            revision=item.resolution_revision + 1,
            idempotency_key=idempotency_key,
            action=resolution.action,
            command_sha256=resolution.command_sha256,
            resolved_value=resolution.resolved_value,
            resolved_by=resolution.resolved_by,
            created_at=now,
        )
        updated = replace(
            item,
            status=ReviewItemStatus(resolution.action.value),
            resolved_value=resolution.resolved_value,
            resolved_by=resolution.resolved_by,
            resolved_at=now,
            resolution_revision=event.revision,
        )
        history.append(event)
        self.items[review_item_id] = updated
        return updated, event, True

    def list_review_resolutions(
        self,
        review_item_id: UUID,
    ) -> Sequence[ReviewResolution]:
        return tuple(self.resolutions.get(review_item_id, ()))

    def create_feedback_export(
        self,
        *,
        review_batch_id: UUID,
        created_by: str,
    ) -> tuple[ReviewFeedbackExport, bool]:
        batch = self.batches[review_batch_id]
        items = sorted(
            (item for item in self.items.values() if item.review_batch_id == review_batch_id),
            key=lambda item: item.selection_rank,
        )
        if any(item.status is ReviewItemStatus.PENDING for item in items):
            raise ReviewConflictError(
                "REVIEW_FEEDBACK_PENDING_ITEMS",
                "Every item must be resolved before export.",
            )
        state = {
            "items": [
                {
                    "id": str(item.id),
                    "revision": item.resolution_revision,
                    "status": item.status.value,
                }
                for item in items
            ]
        }
        state_sha = hashlib.sha256(canonical_review_bytes(state)).hexdigest()
        for feedback_export in self.feedback_exports.values():
            if (
                feedback_export.review_batch_id == review_batch_id
                and feedback_export.source_state_sha256 == state_sha
            ):
                return feedback_export, False
        version = 1 + max(
            (
                feedback_export.version
                for feedback_export in self.feedback_exports.values()
                if feedback_export.game_id == batch.game_id
            ),
            default=0,
        )
        sample_count = sum(15 for item in items if item.status is not ReviewItemStatus.REJECTED)
        rejected_count = sum(item.status is ReviewItemStatus.REJECTED for item in items)
        payload: dict[str, object] = {
            "schemaVersion": 1,
            "version": version,
            "sampleCount": sample_count,
        }
        feedback_export = ReviewFeedbackExport(
            id=uuid4(),
            review_batch_id=review_batch_id,
            game_id=batch.game_id,
            version=version,
            source_state_sha256=state_sha,
            payload_sha256=hashlib.sha256(canonical_review_bytes(payload)).hexdigest(),
            sample_count=sample_count,
            rejected_item_count=rejected_count,
            payload=payload,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self.feedback_exports[feedback_export.id] = feedback_export
        return feedback_export, True

    def list_feedback_exports(
        self,
        review_batch_id: UUID,
    ) -> Sequence[ReviewFeedbackExport]:
        return tuple(
            sorted(
                (
                    feedback_export
                    for feedback_export in self.feedback_exports.values()
                    if feedback_export.review_batch_id == review_batch_id
                ),
                key=lambda feedback_export: feedback_export.version,
                reverse=True,
            )
        )

    def get_feedback_export(
        self,
        feedback_export_id: UUID,
    ) -> ReviewFeedbackExport | None:
        return self.feedback_exports.get(feedback_export_id)


def _client(
    repository: MemoryReviewRepository,
) -> TestClient:
    return TestClient(
        create_app(
            ApiSettings.from_environment({}),
            review_service_dependency=lambda: ReviewService(repository),
        )
    )


def test_real_selection_report_is_canonical_and_valid() -> None:
    report, checksum = _report()
    classes = cast(list[str], report["classes"])

    selection = validate_review_selection(
        report,
        source_report_sha256=checksum,
        active_symbol_codes=classes,
    )

    assert canonical_report_bytes(report) == REPORT_PATH.read_bytes()
    assert selection.temperature == 1.0338382913
    assert len(selection.item_snapshots) == 30
    assert [item["selectionRank"] for item in selection.item_snapshots] == list(range(1, 31))


def test_report_checksum_path_and_symbol_drift_fail_closed() -> None:
    report, checksum = _report()
    classes = cast(list[str], report["classes"])

    with pytest.raises(ReviewConflictError) as checksum_error:
        validate_review_selection(
            report,
            source_report_sha256="0" * 64,
            active_symbol_codes=classes,
        )
    assert checksum_error.value.code == "REVIEW_REPORT_CHECKSUM_MISMATCH"

    unsafe = copy.deepcopy(report)
    cast(dict[str, object], cast(list[object], unsafe["selectedBoards"])[0])[
        "boardRelativePath"
    ] = "../board.png"
    unsafe_checksum = hashlib.sha256(canonical_report_bytes(unsafe)).hexdigest()
    with pytest.raises(ReviewError) as path_error:
        validate_review_selection(
            unsafe,
            source_report_sha256=unsafe_checksum,
            active_symbol_codes=classes,
        )
    assert path_error.value.code == "REVIEW_REPORT_PATH_UNSAFE"

    with pytest.raises(ReviewConflictError) as symbol_error:
        validate_review_selection(
            report,
            source_report_sha256=checksum,
            active_symbol_codes=classes[:-1],
        )
    assert symbol_error.value.code == "REVIEW_REPORT_CONTRACT_UNSUPPORTED"


def test_review_admin_api_import_is_idempotent_and_pages_whole_layouts() -> None:
    report, checksum = _report()
    game_id = uuid4()
    repository = MemoryReviewRepository(
        game_id,
        cast(list[str], report["classes"]),
    )
    payload = {
        "gameId": str(game_id),
        "sourceReportSha256": checksum,
        "report": report,
    }

    with _client(repository) as client:
        first = client.post("/api/v1/admin/review-batches", json=payload)
        second = client.post("/api/v1/admin/review-batches", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["created"] is True
        assert second.json()["created"] is False
        assert second.json()["batch"]["id"] == first.json()["batch"]["id"]
        batch_id = first.json()["batch"]["id"]

        batches = client.get("/api/v1/admin/review-batches")
        detail = client.get(f"/api/v1/admin/review-batches/{batch_id}")
        page = client.get(
            f"/api/v1/admin/review-batches/{batch_id}/items",
            params={"status": "pending", "limit": 10},
        )

        assert batches.status_code == detail.status_code == page.status_code == 200
        assert len(batches.json()) == 1
        assert detail.json()["itemCount"] == 30
        assert len(page.json()["items"]) == 10
        assert page.json()["nextAfterSelectionRank"] == 10
        first_item = page.json()["items"][0]
        assert len(first_item["snapshot"]["cells"]) == 15
        assert first_item["snapshot"]["selectionRank"] == 1

        item = client.get(f"/api/v1/admin/review-items/{first_item['id']}")
        assert item.status_code == 200
        assert item.json() == first_item


def test_review_admin_api_returns_stable_missing_errors() -> None:
    report, checksum = _report()
    game_id = uuid4()
    repository = MemoryReviewRepository(
        game_id,
        cast(list[str], report["classes"]),
    )
    payload = {
        "gameId": str(uuid4()),
        "sourceReportSha256": checksum,
        "report": report,
    }

    with _client(repository) as client:
        missing = client.post("/api/v1/admin/review-batches", json=payload)
        unresolved = client.post(
            f"/api/v1/admin/review-items/{uuid4()}/resolution",
            json={
                "idempotencyKey": str(uuid4()),
                "expectedRevision": 0,
                "action": "accepted",
                "geometryAccepted": True,
                "labels": [],
                "resolvedBy": "local-admin",
            },
        )

    assert missing.status_code == 404
    assert missing.json()["code"] == "REVIEW_GAME_NOT_FOUND"
    assert unresolved.status_code == 404


def _labels(item: Mapping[str, object]) -> list[dict[str, object]]:
    snapshot = cast(Mapping[str, object], item["snapshot"])
    cells = cast(Sequence[Mapping[str, object]], snapshot["cells"])
    return [
        {
            "cellIndex": cell["cellIndex"],
            "sampleId": cell["sampleId"],
            "symbolCode": cell["predictedSymbolCode"],
        }
        for cell in cells
    ]


def test_resolution_is_idempotent_revisioned_and_audited() -> None:
    report, checksum = _report()
    game_id = uuid4()
    repository = MemoryReviewRepository(
        game_id,
        cast(list[str], report["classes"]),
    )
    with _client(repository) as client:
        imported = client.post(
            "/api/v1/admin/review-batches",
            json={
                "gameId": str(game_id),
                "sourceReportSha256": checksum,
                "report": report,
            },
        ).json()
        batch_id = imported["batch"]["id"]
        item = client.get(
            f"/api/v1/admin/review-batches/{batch_id}/items",
            params={"limit": 1},
        ).json()["items"][0]
        idempotency_key = str(uuid4())
        payload = {
            "idempotencyKey": idempotency_key,
            "expectedRevision": 0,
            "action": "accepted",
            "geometryAccepted": True,
            "labels": _labels(item),
            "resolvedBy": "local-admin",
        }

        first = client.post(
            f"/api/v1/admin/review-items/{item['id']}/resolution",
            json=payload,
        )
        retry = client.post(
            f"/api/v1/admin/review-items/{item['id']}/resolution",
            json=payload,
        )
        stale = client.post(
            f"/api/v1/admin/review-items/{item['id']}/resolution",
            json={**payload, "idempotencyKey": str(uuid4())},
        )
        changed_retry = client.post(
            f"/api/v1/admin/review-items/{item['id']}/resolution",
            json={**payload, "resolvedBy": "another-admin"},
        )
        history = client.get(f"/api/v1/admin/review-items/{item['id']}/resolutions")

    assert first.status_code == retry.status_code == 200
    assert first.json()["created"] is True
    assert retry.json()["created"] is False
    assert first.json()["item"]["status"] == "accepted"
    assert first.json()["item"]["resolutionRevision"] == 1
    assert stale.status_code == 409
    assert stale.json()["code"] == "REVIEW_REVISION_CONFLICT"
    assert changed_retry.status_code == 409
    assert changed_retry.json()["code"] == "REVIEW_IDEMPOTENCY_KEY_REUSED"
    assert history.status_code == 200
    assert [event["revision"] for event in history.json()] == [1]


def test_resolution_validates_geometry_corrections_and_rejection() -> None:
    report, checksum = _report()
    game_id = uuid4()
    classes = cast(list[str], report["classes"])
    repository = MemoryReviewRepository(game_id, classes)
    with _client(repository) as client:
        imported = client.post(
            "/api/v1/admin/review-batches",
            json={
                "gameId": str(game_id),
                "sourceReportSha256": checksum,
                "report": report,
            },
        ).json()
        batch_id = imported["batch"]["id"]
        items = client.get(
            f"/api/v1/admin/review-batches/{batch_id}/items",
            params={"limit": 2},
        ).json()["items"]
        labels = _labels(items[0])
        predicted = cast(str, labels[0]["symbolCode"])
        labels[0]["symbolCode"] = next(code for code in classes if code != predicted)

        geometry_error = client.post(
            f"/api/v1/admin/review-items/{items[0]['id']}/resolution",
            json={
                "idempotencyKey": str(uuid4()),
                "expectedRevision": 0,
                "action": "corrected",
                "geometryAccepted": False,
                "labels": labels,
                "resolvedBy": "local-admin",
            },
        )
        corrected = client.post(
            f"/api/v1/admin/review-items/{items[0]['id']}/resolution",
            json={
                "idempotencyKey": str(uuid4()),
                "expectedRevision": 0,
                "action": "corrected",
                "geometryAccepted": True,
                "labels": labels,
                "resolvedBy": "local-admin",
            },
        )
        rejected = client.post(
            f"/api/v1/admin/review-items/{items[1]['id']}/resolution",
            json={
                "idempotencyKey": str(uuid4()),
                "expectedRevision": 0,
                "action": "rejected",
                "geometryAccepted": False,
                "labels": [],
                "rejectionReason": "Niepoprawna geometria planszy.",
                "resolvedBy": "local-admin",
            },
        )

    assert geometry_error.status_code == 409
    assert geometry_error.json()["code"] == "REVIEW_GEOMETRY_NOT_ACCEPTED"
    assert corrected.status_code == 200
    assert corrected.json()["item"]["status"] == "corrected"
    assert corrected.json()["item"]["resolvedValue"]["cells"][0]["corrected"] is True
    assert rejected.status_code == 200
    assert rejected.json()["item"]["status"] == "rejected"
    assert rejected.json()["item"]["resolvedValue"]["cells"] == []


def test_feedback_export_requires_complete_resolution_and_is_versioned() -> None:
    report, checksum = _report()
    game_id = uuid4()
    repository = MemoryReviewRepository(
        game_id,
        cast(list[str], report["classes"]),
    )
    with _client(repository) as client:
        imported = client.post(
            "/api/v1/admin/review-batches",
            json={
                "gameId": str(game_id),
                "sourceReportSha256": checksum,
                "report": report,
            },
        ).json()
        batch_id = imported["batch"]["id"]
        pending_export = client.post(
            f"/api/v1/admin/review-batches/{batch_id}/feedback-exports",
            json={"createdBy": "local-admin"},
        )
        items = client.get(
            f"/api/v1/admin/review-batches/{batch_id}/items",
            params={"limit": 100},
        ).json()["items"]
        for index, item in enumerate(items):
            action = "rejected" if index == 0 else "accepted"
            response = client.post(
                f"/api/v1/admin/review-items/{item['id']}/resolution",
                json={
                    "idempotencyKey": str(uuid4()),
                    "expectedRevision": 0,
                    "action": action,
                    "geometryAccepted": action == "accepted",
                    "labels": _labels(item) if action == "accepted" else [],
                    **(
                        {"rejectionReason": "Niepoprawna obserwacja."}
                        if action == "rejected"
                        else {}
                    ),
                    "resolvedBy": "local-admin",
                },
            )
            assert response.status_code == 200
        first = client.post(
            f"/api/v1/admin/review-batches/{batch_id}/feedback-exports",
            json={"createdBy": "local-admin"},
        )
        retry = client.post(
            f"/api/v1/admin/review-batches/{batch_id}/feedback-exports",
            json={"createdBy": "local-admin"},
        )
        exports = client.get(f"/api/v1/admin/review-batches/{batch_id}/feedback-exports")

    assert pending_export.status_code == 409
    assert pending_export.json()["code"] == "REVIEW_FEEDBACK_PENDING_ITEMS"
    assert first.status_code == retry.status_code == 200
    assert first.json()["created"] is True
    assert retry.json()["created"] is False
    assert first.json()["feedbackExport"]["version"] == 1
    assert first.json()["feedbackExport"]["sampleCount"] == 29 * 15
    assert first.json()["feedbackExport"]["rejectedItemCount"] == 1
    assert len(exports.json()) == 1
