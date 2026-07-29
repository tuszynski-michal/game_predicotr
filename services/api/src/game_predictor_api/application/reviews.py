"""Application service and repository port for immutable review batches."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.reviews import (
    MAX_REVIEW_PAGE_SIZE,
    ReviewBatch,
    ReviewConflictError,
    ReviewFeedbackExport,
    ReviewItem,
    ReviewItemPage,
    ReviewItemStatus,
    ReviewNotFoundError,
    ReviewResolution,
    ReviewResolutionAction,
    ValidatedReviewResolution,
    ValidatedReviewSelection,
    validate_review_resolution,
    validate_review_selection,
)


class ReviewRepository(Protocol):
    def get_active_symbol_codes(self, game_id: UUID) -> Sequence[str] | None: ...

    def list_review_batches(self) -> Sequence[ReviewBatch]: ...

    def get_review_batch(self, review_batch_id: UUID) -> ReviewBatch | None: ...

    def get_review_batch_by_report(
        self,
        source_report_sha256: str,
    ) -> ReviewBatch | None: ...

    def add_review_batch(
        self,
        *,
        game_id: UUID,
        selection: ValidatedReviewSelection,
    ) -> ReviewBatch: ...

    def list_review_items(
        self,
        *,
        review_batch_id: UUID,
        status: ReviewItemStatus | None,
        after_selection_rank: int,
        limit: int,
    ) -> ReviewItemPage: ...

    def get_review_item(self, review_item_id: UUID) -> ReviewItem | None: ...

    def save_review_resolution(
        self,
        *,
        review_item_id: UUID,
        idempotency_key: UUID,
        expected_revision: int,
        resolution: ValidatedReviewResolution,
    ) -> tuple[ReviewItem, ReviewResolution, bool]: ...

    def list_review_resolutions(
        self,
        review_item_id: UUID,
    ) -> Sequence[ReviewResolution]: ...

    def create_feedback_export(
        self,
        *,
        review_batch_id: UUID,
        created_by: str,
    ) -> tuple[ReviewFeedbackExport, bool]: ...

    def list_feedback_exports(
        self,
        review_batch_id: UUID,
    ) -> Sequence[ReviewFeedbackExport]: ...

    def get_feedback_export(
        self,
        feedback_export_id: UUID,
    ) -> ReviewFeedbackExport | None: ...


class ReviewService:
    def __init__(self, repository: ReviewRepository) -> None:
        self._repository = repository

    def import_review_batch(
        self,
        *,
        game_id: UUID,
        source_report_sha256: str,
        report: Mapping[str, object],
    ) -> tuple[ReviewBatch, bool]:
        active_symbols = self._repository.get_active_symbol_codes(game_id)
        if active_symbols is None:
            raise ReviewNotFoundError(
                "REVIEW_GAME_NOT_FOUND",
                "The selected review game does not exist.",
                details={"gameId": str(game_id)},
            )
        selection = validate_review_selection(
            report,
            source_report_sha256=source_report_sha256,
            active_symbol_codes=active_symbols,
        )
        existing = self._repository.get_review_batch_by_report(selection.source_report_sha256)
        if existing is not None:
            if existing.game_id != game_id or existing.source_report != selection.source_report:
                raise ReviewConflictError(
                    "REVIEW_REPORT_ALREADY_IMPORTED_DIFFERENTLY",
                    "The report checksum already belongs to a different immutable batch.",
                    details={"sourceReportSha256": selection.source_report_sha256},
                )
            return existing, False
        return (
            self._repository.add_review_batch(
                game_id=game_id,
                selection=selection,
            ),
            True,
        )

    def list_review_batches(self) -> Sequence[ReviewBatch]:
        return self._repository.list_review_batches()

    def get_review_batch(self, review_batch_id: UUID) -> ReviewBatch:
        batch = self._repository.get_review_batch(review_batch_id)
        if batch is None:
            raise ReviewNotFoundError(
                "REVIEW_BATCH_NOT_FOUND",
                "Review batch does not exist.",
                details={"reviewBatchId": str(review_batch_id)},
            )
        return batch

    def list_review_items(
        self,
        *,
        review_batch_id: UUID,
        status: ReviewItemStatus | None,
        after_selection_rank: int,
        limit: int,
    ) -> ReviewItemPage:
        if after_selection_rank < 0 or not 1 <= limit <= MAX_REVIEW_PAGE_SIZE:
            raise ReviewConflictError(
                "INVALID_REVIEW_ITEM_PAGE",
                "Review item cursor or page size is invalid.",
            )
        self.get_review_batch(review_batch_id)
        return self._repository.list_review_items(
            review_batch_id=review_batch_id,
            status=status,
            after_selection_rank=after_selection_rank,
            limit=limit,
        )

    def get_review_item(self, review_item_id: UUID) -> ReviewItem:
        item = self._repository.get_review_item(review_item_id)
        if item is None:
            raise ReviewNotFoundError(
                "REVIEW_ITEM_NOT_FOUND",
                "Review item does not exist.",
                details={"reviewItemId": str(review_item_id)},
            )
        return item

    def resolve_review_item(
        self,
        *,
        review_item_id: UUID,
        idempotency_key: UUID,
        expected_revision: int,
        action: ReviewResolutionAction,
        geometry_accepted: bool,
        labels: Sequence[Mapping[str, object]],
        rejection_reason: str | None,
        resolved_by: str,
    ) -> tuple[ReviewItem, ReviewResolution, bool]:
        if expected_revision < 0:
            raise ReviewConflictError(
                "REVIEW_REVISION_INVALID",
                "The expected resolution revision cannot be negative.",
            )
        item = self.get_review_item(review_item_id)
        batch = self.get_review_batch(item.review_batch_id)
        active_symbols = self._repository.get_active_symbol_codes(batch.game_id)
        if active_symbols is None:
            raise ReviewNotFoundError(
                "REVIEW_GAME_NOT_FOUND",
                "The selected review game does not exist.",
            )
        resolution = validate_review_resolution(
            action=action,
            geometry_accepted=geometry_accepted,
            labels=labels,
            rejection_reason=rejection_reason,
            resolved_by=resolved_by,
            prediction_snapshot=item.prediction_snapshot,
            active_symbol_codes=active_symbols,
        )
        return self._repository.save_review_resolution(
            review_item_id=review_item_id,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            resolution=resolution,
        )

    def list_review_resolutions(
        self,
        review_item_id: UUID,
    ) -> Sequence[ReviewResolution]:
        self.get_review_item(review_item_id)
        return self._repository.list_review_resolutions(review_item_id)

    def create_feedback_export(
        self,
        *,
        review_batch_id: UUID,
        created_by: str,
    ) -> tuple[ReviewFeedbackExport, bool]:
        actor = created_by.strip()
        if not actor or len(actor) > 200:
            raise ReviewConflictError(
                "REVIEW_EXPORT_CREATED_BY_INVALID",
                "createdBy must identify the local administrator.",
            )
        self.get_review_batch(review_batch_id)
        return self._repository.create_feedback_export(
            review_batch_id=review_batch_id,
            created_by=actor,
        )

    def list_feedback_exports(
        self,
        review_batch_id: UUID,
    ) -> Sequence[ReviewFeedbackExport]:
        self.get_review_batch(review_batch_id)
        return self._repository.list_feedback_exports(review_batch_id)

    def get_feedback_export(
        self,
        feedback_export_id: UUID,
    ) -> ReviewFeedbackExport:
        result = self._repository.get_feedback_export(feedback_export_id)
        if result is None:
            raise ReviewNotFoundError(
                "REVIEW_FEEDBACK_EXPORT_NOT_FOUND",
                "Review feedback export does not exist.",
                details={"feedbackExportId": str(feedback_export_id)},
            )
        return result


__all__ = ["ReviewRepository", "ReviewService"]
