"""SQLAlchemy implementation of immutable review batch storage."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.reviews import ReviewRepository
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.reviews import (
    ReviewBatch,
    ReviewConflictError,
    ReviewFeedbackExport,
    ReviewItem,
    ReviewItemPage,
    ReviewItemStatus,
    ReviewResolution,
    ValidatedReviewResolution,
    ValidatedReviewSelection,
    canonical_review_bytes,
)
from game_predictor_api.storage.models import (
    GameModel,
    ReviewBatchModel,
    ReviewFeedbackExportModel,
    ReviewItemModel,
    ReviewResolutionModel,
    SymbolModel,
)


class SqlAlchemyReviewRepository(ReviewRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_symbol_codes(self, game_id: UUID) -> Sequence[str] | None:
        if self._session.get(GameModel, game_id) is None:
            return None
        return tuple(
            self._session.scalars(
                select(SymbolModel.code)
                .where(
                    SymbolModel.game_id == game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
                .order_by(SymbolModel.mobile_code, SymbolModel.code)
            )
        )

    def list_review_batches(self) -> list[ReviewBatch]:
        return [
            _to_review_batch(record)
            for record in self._session.scalars(
                select(ReviewBatchModel)
                .order_by(
                    ReviewBatchModel.created_at.desc(),
                    ReviewBatchModel.id.desc(),
                )
                .limit(50)
            )
        ]

    def get_review_batch(self, review_batch_id: UUID) -> ReviewBatch | None:
        record = self._session.get(ReviewBatchModel, review_batch_id)
        return _to_review_batch(record) if record is not None else None

    def get_review_batch_by_report(
        self,
        source_report_sha256: str,
    ) -> ReviewBatch | None:
        record = self._session.scalar(
            select(ReviewBatchModel).where(
                ReviewBatchModel.source_report_sha256 == source_report_sha256
            )
        )
        return _to_review_batch(record) if record is not None else None

    def add_review_batch(
        self,
        *,
        game_id: UUID,
        selection: ValidatedReviewSelection,
    ) -> ReviewBatch:
        record = ReviewBatchModel(
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
        )
        self._session.add(record)
        try:
            self._session.flush()
            self._session.add_all(
                [_review_item_record(record.id, snapshot) for snapshot in selection.item_snapshots]
            )
            self._session.flush()
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            constraint_name = getattr(diagnostic, "constraint_name", None)
            if constraint_name == "uq_review_batches_source_report_sha256":
                raise ReviewConflictError(
                    "REVIEW_REPORT_IMPORT_RACE",
                    "The immutable report was imported concurrently; retry the request.",
                    details={
                        "sourceReportSha256": selection.source_report_sha256,
                    },
                ) from error
            raise
        self._session.refresh(record)
        return _to_review_batch(record)

    def list_review_items(
        self,
        *,
        review_batch_id: UUID,
        status: ReviewItemStatus | None,
        after_selection_rank: int,
        limit: int,
    ) -> ReviewItemPage:
        query = select(ReviewItemModel).where(
            ReviewItemModel.review_batch_id == review_batch_id,
            ReviewItemModel.selection_rank > after_selection_rank,
        )
        if status is not None:
            query = query.where(ReviewItemModel.status == status)
        records = list(
            self._session.scalars(query.order_by(ReviewItemModel.selection_rank).limit(limit + 1))
        )
        has_next = len(records) > limit
        visible = records[:limit]
        return ReviewItemPage(
            items=tuple(_to_review_item(record) for record in visible),
            next_after_selection_rank=(
                visible[-1].selection_rank if has_next and visible else None
            ),
        )

    def get_review_item(self, review_item_id: UUID) -> ReviewItem | None:
        record = self._session.get(ReviewItemModel, review_item_id)
        return _to_review_item(record) if record is not None else None

    def save_review_resolution(
        self,
        *,
        review_item_id: UUID,
        idempotency_key: UUID,
        expected_revision: int,
        resolution: ValidatedReviewResolution,
    ) -> tuple[ReviewItem, ReviewResolution, bool]:
        existing = self._session.scalar(
            select(ReviewResolutionModel).where(
                ReviewResolutionModel.review_item_id == review_item_id,
                ReviewResolutionModel.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.command_sha256 != resolution.command_sha256:
                raise ReviewConflictError(
                    "REVIEW_IDEMPOTENCY_KEY_REUSED",
                    "The resolution idempotency key was already used for another payload.",
                )
            current = self._session.get(ReviewItemModel, review_item_id)
            if current is None:
                raise ReviewConflictError(
                    "REVIEW_ITEM_AUDIT_ORPHANED",
                    "The review audit references a missing item.",
                )
            return _to_review_item(current), _to_review_resolution(existing), False

        record = self._session.scalar(
            select(ReviewItemModel)
            .where(ReviewItemModel.id == review_item_id)
            .with_for_update()
        )
        if record is None:
            raise ReviewConflictError(
                "REVIEW_ITEM_NOT_FOUND",
                "Review item does not exist.",
            )
        if record.resolution_revision != expected_revision:
            raise ReviewConflictError(
                "REVIEW_REVISION_CONFLICT",
                "The review item changed after it was loaded.",
                details={
                    "expectedRevision": expected_revision,
                    "actualRevision": record.resolution_revision,
                },
            )
        now = datetime.now(UTC)
        revision = record.resolution_revision + 1
        audit = ReviewResolutionModel(
            review_item_id=record.id,
            revision=revision,
            idempotency_key=idempotency_key,
            action=resolution.action,
            command_sha256=resolution.command_sha256,
            resolved_value=dict(resolution.resolved_value),
            resolved_by=resolution.resolved_by,
            created_at=now,
        )
        record.status = ReviewItemStatus(resolution.action.value)
        record.resolved_value = dict(resolution.resolved_value)
        record.resolved_by = resolution.resolved_by
        record.resolved_at = now
        record.resolution_revision = revision
        self._session.add(audit)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise ReviewConflictError(
                "REVIEW_RESOLUTION_RACE",
                "The review item was resolved concurrently; reload and retry.",
            ) from error
        return _to_review_item(record), _to_review_resolution(audit), True

    def list_review_resolutions(
        self,
        review_item_id: UUID,
    ) -> Sequence[ReviewResolution]:
        return tuple(
            _to_review_resolution(record)
            for record in self._session.scalars(
                select(ReviewResolutionModel)
                .where(ReviewResolutionModel.review_item_id == review_item_id)
                .order_by(ReviewResolutionModel.revision)
            )
        )

    def create_feedback_export(
        self,
        *,
        review_batch_id: UUID,
        created_by: str,
    ) -> tuple[ReviewFeedbackExport, bool]:
        batch = self._session.scalar(
            select(ReviewBatchModel)
            .where(ReviewBatchModel.id == review_batch_id)
            .with_for_update()
        )
        if batch is None:
            raise ReviewConflictError(
                "REVIEW_BATCH_NOT_FOUND",
                "Review batch does not exist.",
            )
        self._session.scalar(
            select(GameModel).where(GameModel.id == batch.game_id).with_for_update()
        )
        items = list(
            self._session.scalars(
                select(ReviewItemModel)
                .where(ReviewItemModel.review_batch_id == review_batch_id)
                .order_by(ReviewItemModel.selection_rank)
                .with_for_update()
            )
        )
        pending = [item.id for item in items if item.status is ReviewItemStatus.PENDING]
        if pending:
            raise ReviewConflictError(
                "REVIEW_FEEDBACK_PENDING_ITEMS",
                "Every item must be resolved before feedback is exported.",
                details={"pendingCount": len(pending)},
            )
        source_state = {
            "reviewBatchId": str(batch.id),
            "items": [
                {
                    "reviewItemId": str(item.id),
                    "revision": item.resolution_revision,
                    "status": item.status.value,
                    "resolvedValue": item.resolved_value,
                }
                for item in items
            ],
        }
        source_state_sha256 = hashlib.sha256(
            canonical_review_bytes(source_state)
        ).hexdigest()
        existing = self._session.scalar(
            select(ReviewFeedbackExportModel).where(
                ReviewFeedbackExportModel.review_batch_id == review_batch_id,
                ReviewFeedbackExportModel.source_state_sha256 == source_state_sha256,
            )
        )
        if existing is not None:
            return _to_feedback_export(existing), False

        version = (
            self._session.scalar(
                select(func.max(ReviewFeedbackExportModel.version)).where(
                    ReviewFeedbackExportModel.game_id == batch.game_id
                )
            )
            or 0
        ) + 1
        samples: list[dict[str, object]] = []
        rejected_item_ids: list[str] = []
        for item in items:
            if item.status is ReviewItemStatus.REJECTED:
                rejected_item_ids.append(str(item.id))
                continue
            resolved = cast(Mapping[str, object], item.resolved_value)
            labels = cast(Sequence[Mapping[str, object]], resolved["cells"])
            snapshot_cells = cast(
                Sequence[Mapping[str, object]],
                item.prediction_snapshot["cells"],
            )
            if len(labels) != 15 or len(snapshot_cells) != 15:
                raise ReviewConflictError(
                    "REVIEW_FEEDBACK_ITEM_INVALID",
                    "A resolved review item does not contain 15 exportable labels.",
                )
            for label, snapshot_cell in zip(labels, snapshot_cells, strict=True):
                samples.append(
                    {
                        "reviewItemId": str(item.id),
                        "boardId": item.board_id,
                        "sequenceNumber": item.sequence_number,
                        "selectionRank": item.selection_rank,
                        "sourceImageChecksumSha256": item.source_image_checksum_sha256,
                        "cellIndex": label["cellIndex"],
                        "rowIndex": snapshot_cell["rowIndex"],
                        "columnIndex": snapshot_cell["columnIndex"],
                        "sampleId": label["sampleId"],
                        "observationId": snapshot_cell["observationId"],
                        "cropRelativePath": snapshot_cell["cropRelativePath"],
                        "symbolCode": label["symbolCode"],
                        "predictedSymbolCode": label["predictedSymbolCode"],
                        "decisionStatus": item.status.value,
                        "resolutionRevision": item.resolution_revision,
                    }
                )
        payload: dict[str, object] = {
            "schemaVersion": 1,
            "datasetKind": "labeled-review-feedback-v1",
            "version": version,
            "gameId": str(batch.game_id),
            "reviewBatchId": str(batch.id),
            "sourceStateSha256": source_state_sha256,
            "sourceReportSha256": batch.source_report_sha256,
            "modelVersion": batch.model_version,
            "modelArtifactSha256": batch.model_artifact_sha256,
            "inventorySha256": batch.inventory_sha256,
            "samples": samples,
            "rejectedReviewItemIds": rejected_item_ids,
        }
        payload_sha256 = hashlib.sha256(canonical_review_bytes(payload)).hexdigest()
        record = ReviewFeedbackExportModel(
            review_batch_id=batch.id,
            game_id=batch.game_id,
            version=version,
            source_state_sha256=source_state_sha256,
            payload_sha256=payload_sha256,
            sample_count=len(samples),
            rejected_item_count=len(rejected_item_ids),
            payload=payload,
            created_by=created_by,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise ReviewConflictError(
                "REVIEW_FEEDBACK_EXPORT_RACE",
                "Feedback was exported concurrently; retry the request.",
            ) from error
        self._session.refresh(record)
        return _to_feedback_export(record), True

    def list_feedback_exports(
        self,
        review_batch_id: UUID,
    ) -> Sequence[ReviewFeedbackExport]:
        return tuple(
            _to_feedback_export(record)
            for record in self._session.scalars(
                select(ReviewFeedbackExportModel)
                .where(ReviewFeedbackExportModel.review_batch_id == review_batch_id)
                .order_by(ReviewFeedbackExportModel.version.desc())
            )
        )

    def get_feedback_export(
        self,
        feedback_export_id: UUID,
    ) -> ReviewFeedbackExport | None:
        record = self._session.get(ReviewFeedbackExportModel, feedback_export_id)
        return _to_feedback_export(record) if record is not None else None


def _review_item_record(
    review_batch_id: UUID,
    snapshot: Mapping[str, object],
) -> ReviewItemModel:
    return ReviewItemModel(
        review_batch_id=review_batch_id,
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
    )


def _to_review_batch(record: ReviewBatchModel) -> ReviewBatch:
    return ReviewBatch(
        id=record.id,
        game_id=record.game_id,
        source_report_sha256=record.source_report_sha256,
        active_learning_version=record.active_learning_version,
        model_version=record.model_version,
        model_artifact_sha256=record.model_artifact_sha256,
        calibration_report_sha256=record.calibration_report_sha256,
        dataset_sha256=record.dataset_sha256,
        split_sha256=record.split_sha256,
        inventory_sha256=record.inventory_sha256,
        temperature=record.temperature,
        item_count=record.item_count,
        source_report=record.source_report,
        created_at=record.created_at,
    )


def _to_review_item(record: ReviewItemModel) -> ReviewItem:
    return ReviewItem(
        id=record.id,
        review_batch_id=record.review_batch_id,
        board_id=record.board_id,
        selection_rank=record.selection_rank,
        sequence_number=record.sequence_number,
        source_image_id=record.source_image_id,
        source_image_checksum_sha256=record.source_image_checksum_sha256,
        source_group=record.source_group,
        board_relative_path=record.board_relative_path,
        status=record.status,
        prediction_snapshot=record.prediction_snapshot,
        created_at=record.created_at,
        resolved_value=record.resolved_value,
        resolved_by=record.resolved_by,
        resolved_at=record.resolved_at,
        resolution_revision=record.resolution_revision,
    )


def _to_review_resolution(record: ReviewResolutionModel) -> ReviewResolution:
    return ReviewResolution(
        id=record.id,
        review_item_id=record.review_item_id,
        revision=record.revision,
        idempotency_key=record.idempotency_key,
        action=record.action,
        command_sha256=record.command_sha256,
        resolved_value=record.resolved_value,
        resolved_by=record.resolved_by,
        created_at=record.created_at,
    )


def _to_feedback_export(record: ReviewFeedbackExportModel) -> ReviewFeedbackExport:
    return ReviewFeedbackExport(
        id=record.id,
        review_batch_id=record.review_batch_id,
        game_id=record.game_id,
        version=record.version,
        source_state_sha256=record.source_state_sha256,
        payload_sha256=record.payload_sha256,
        sample_count=record.sample_count,
        rejected_item_count=record.rejected_item_count,
        payload=record.payload,
        created_by=record.created_by,
        created_at=record.created_at,
    )


__all__ = ["SqlAlchemyReviewRepository"]
