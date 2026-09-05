"""SQLAlchemy persistence for cumulative verified training cohorts."""

from __future__ import annotations

import hashlib
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.verified_training_cohorts import (
    VerifiedTrainingCohortRepository,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    canonical_image_review_bytes,
)
from game_predictor_api.domain.verified_training_cohorts import (
    VerifiedTrainingCohort,
    VerifiedTrainingCohortSnapshot,
    VerifiedTrainingCohortSource,
)
from game_predictor_api.storage.models import (
    VerifiedTrainingCohortCellModel,
    VerifiedTrainingCohortItemModel,
    VerifiedTrainingCohortModel,
)


class SqlAlchemyVerifiedTrainingCohortRepository(VerifiedTrainingCohortRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, *, cohort_id: UUID) -> VerifiedTrainingCohort | None:
        record = self._session.get(VerifiedTrainingCohortModel, cohort_id)
        return None if record is None else _to_cohort(record)

    def find_by_idempotency(
        self,
        *,
        game_id: UUID,
        idempotency_key: UUID,
    ) -> tuple[VerifiedTrainingCohort, str] | None:
        record = self._session.scalar(
            select(VerifiedTrainingCohortModel).where(
                VerifiedTrainingCohortModel.game_id == game_id,
                VerifiedTrainingCohortModel.idempotency_key == idempotency_key,
            )
        )
        return None if record is None else (_to_cohort(record), record.command_sha256)

    def latest_snapshot(
        self,
        *,
        game_id: UUID,
    ) -> VerifiedTrainingCohortSnapshot | None:
        record = self._session.scalar(
            select(VerifiedTrainingCohortModel)
            .where(VerifiedTrainingCohortModel.game_id == game_id)
            .order_by(VerifiedTrainingCohortModel.iteration_number.desc())
            .limit(1)
        )
        if record is None:
            return None
        checksum_column = (
            VerifiedTrainingCohortCellModel.sample_checksum_sha256
            if record.dataset_kind == "verified-symbol-cell-training-cohort-v2"
            else VerifiedTrainingCohortItemModel.item_checksum_sha256
        )
        checksum_model = (
            VerifiedTrainingCohortCellModel
            if record.dataset_kind == "verified-symbol-cell-training-cohort-v2"
            else VerifiedTrainingCohortItemModel
        )
        item_checksums = frozenset(
            self._session.scalars(
                select(checksum_column).where(checksum_model.cohort_id == record.id)
            ).all()
        )
        return VerifiedTrainingCohortSnapshot(
            cohort=_to_cohort(record),
            item_checksums=item_checksums,
        )

    def find_by_manifest(
        self,
        *,
        game_id: UUID,
        manifest_checksum_sha256: str,
    ) -> VerifiedTrainingCohort | None:
        record = self._session.scalar(
            select(VerifiedTrainingCohortModel).where(
                VerifiedTrainingCohortModel.game_id == game_id,
                VerifiedTrainingCohortModel.manifest_checksum_sha256 == manifest_checksum_sha256,
            )
        )
        return None if record is None else _to_cohort(record)

    def next_iteration(self, *, game_id: UUID) -> int:
        return (
            int(
                self._session.scalar(
                    select(func.max(VerifiedTrainingCohortModel.iteration_number)).where(
                        VerifiedTrainingCohortModel.game_id == game_id
                    )
                )
                or 0
            )
            + 1
        )

    def save(
        self,
        *,
        source: VerifiedTrainingCohortSource,
        iteration_number: int,
        idempotency_key: UUID,
        command_sha256: str,
        artifact_relative_path: str,
        created_by: str,
    ) -> VerifiedTrainingCohort:
        record = VerifiedTrainingCohortModel(
            game_id=source.game_id,
            iteration_number=iteration_number,
            manifest_schema_version=source.manifest_schema_version,
            dataset_kind=source.dataset_kind,
            manifest_checksum_sha256=source.manifest_checksum_sha256,
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
            resolved_layout_count=source.resolved_layout_count,
            cell_sample_count=source.cell_sample_count,
            source_image_count=source.source_image_count,
            pending_item_count=source.pending_item_count,
            rejected_item_count=source.rejected_item_count,
            incomplete_item_count=source.incomplete_item_count,
            artifact_relative_path=artifact_relative_path,
            created_by=created_by,
        )
        self._session.add(record)
        try:
            self._session.flush()
            for item_order, board in enumerate(source.boards):
                board_manifest = dict(board)
                self._session.add(
                    VerifiedTrainingCohortItemModel(
                        cohort_id=record.id,
                        item_order=item_order,
                        review_item_id=UUID(cast(str, board["reviewItemId"])),
                        recognized_board_id=UUID(cast(str, board["recognizedBoardId"])),
                        source_image_id=UUID(cast(str, board["sourceImageId"])),
                        import_job_id=UUID(cast(str, board["importJobId"])),
                        sequence_number=cast(int, board["sequenceNumber"]),
                        decision_status=cast(str, board["decisionStatus"]),
                        resolution_revision=cast(int, board["resolutionRevision"]),
                        geometry_revision=cast(int, board["geometryRevision"]),
                        source_checksum_sha256=cast(
                            str, cast(dict[str, object], board["source"])["checksumSha256"]
                        ),
                        board_checksum_sha256=cast(
                            str, cast(dict[str, object], board["board"])["checksumSha256"]
                        ),
                        pipeline_fingerprint=cast(str, board["pipelineFingerprint"]),
                        item_checksum_sha256=hashlib.sha256(
                            canonical_image_review_bytes(board_manifest)
                        ).hexdigest(),
                        board_manifest=board_manifest,
                    )
                )
            for sample_order, cell in enumerate(source.cells):
                cell_manifest = dict(cell)
                source_geometry_revision_id = cell.get("sourceGeometryRevisionId")
                self._session.add(
                    VerifiedTrainingCohortCellModel(
                        cohort_id=record.id,
                        sample_order=sample_order,
                        cell_review_id=UUID(cast(str, cell["cellReviewId"])),
                        review_item_id=UUID(cast(str, cell["reviewItemId"])),
                        recognized_board_id=UUID(cast(str, cell["recognizedBoardId"])),
                        source_image_id=UUID(cast(str, cell["sourceImageId"])),
                        sequence_number=cast(int, cell["sequenceNumber"]),
                        cell_index=cast(int, cell["cellIndex"]),
                        symbol_code=cast(str, cell["symbolCode"]),
                        crop_checksum_sha256=cast(str, cell["cropChecksumSha256"]),
                        asset_mode=cast(str, cell.get("assetMode", "legacy_file")),
                        source_geometry_revision_id=(
                            UUID(source_geometry_revision_id)
                            if isinstance(source_geometry_revision_id, str)
                            else None
                        ),
                        logical_cell_key=cast(str | None, cell.get("logicalCellKeySha256")),
                        logical_cell_key_v2=cast(str | None, cell.get("logicalCellKeyV2Sha256")),
                        render_identity_v2_sha256=cast(
                            str | None, cell.get("renderIdentityV2Sha256")
                        ),
                        render_spec=cast(dict[str, object] | None, cell.get("renderSpec")),
                        render_spec_checksum_sha256=cast(
                            str | None, cell.get("renderSpecChecksumSha256")
                        ),
                        rendered_pixel_checksum_sha256=cast(
                            str | None, cell.get("renderedPixelChecksumSha256")
                        ),
                        extractor_version=cast(str | None, cell.get("extractorVersion")),
                        sample_checksum_sha256=hashlib.sha256(
                            canonical_image_review_bytes(cell_manifest)
                        ).hexdigest(),
                        cell_manifest=cell_manifest,
                    )
                )
            self._session.flush()
        except IntegrityError as error:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_WRITE_CONFLICT",
                "The training cohort was frozen concurrently; retry the command.",
            ) from error
        self._session.refresh(record)
        return _to_cohort(record)


def _to_cohort(record: VerifiedTrainingCohortModel) -> VerifiedTrainingCohort:
    return VerifiedTrainingCohort(
        id=record.id,
        game_id=record.game_id,
        iteration_number=record.iteration_number,
        manifest_schema_version=record.manifest_schema_version,
        manifest_checksum_sha256=record.manifest_checksum_sha256,
        resolved_layout_count=record.resolved_layout_count,
        cell_sample_count=record.cell_sample_count,
        source_image_count=record.source_image_count,
        pending_item_count=record.pending_item_count,
        rejected_item_count=record.rejected_item_count,
        incomplete_item_count=record.incomplete_item_count,
        artifact_relative_path=record.artifact_relative_path,
        created_by=record.created_by,
        created_at=record.created_at,
    )


__all__ = ["SqlAlchemyVerifiedTrainingCohortRepository"]
