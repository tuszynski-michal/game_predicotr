"""Transactional persistence for pre-import geometry guard resolutions."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardDecision,
    ImageGeometryGuardDisposition,
    ImageGeometryGuardResolutionManifest,
    ImageGeometryGuardScope,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.storage.models import (
    BrowserSelectionRetentionModel,
    ImageImportGeometryGuardDecisionModel,
    ImageImportGeometryGuardResolutionManifestModel,
    JobModel,
)


class SqlAlchemyImageImportGeometryGuardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_scope(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        guard_job_id: UUID,
    ) -> ImageGeometryGuardScope | None:
        row = self._session.execute(
            select(JobModel, BrowserSelectionRetentionModel)
            .join(
                BrowserSelectionRetentionModel,
                BrowserSelectionRetentionModel.upload_id == browser_selection_id,
            )
            .where(
                JobModel.id == guard_job_id,
                JobModel.game_id == game_id,
                BrowserSelectionRetentionModel.game_id == game_id,
            )
        ).one_or_none()
        if row is None:
            return None
        job, staging = row
        if job.input_payload.get("source_selection_id") != str(browser_selection_id):
            return None
        source_guard_checkpoint = (
            job.checkpoint_payload.get("geometry_systemic_guard")
            if isinstance(job.checkpoint_payload, dict)
            else None
        )
        source_guard_report_checksum = (
            source_guard_checkpoint.get("reportChecksumSha256")
            if isinstance(source_guard_checkpoint, dict)
            else None
        )
        derived_report_checkpoint = None
        reconstruction_jobs = self._session.scalars(
            select(JobModel)
            .where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.VALIDATE,
                JobModel.status == JobStatus.COMPLETED,
            )
            .order_by(JobModel.created_at.desc(), JobModel.id.desc())
        ).all()
        for reconstruction in reconstruction_jobs:
            if (
                reconstruction.input_payload.get("validation_kind")
                != "image_geometry_guard_report_reconstruction"
                or reconstruction.input_payload.get("source_guard_job_id") != str(guard_job_id)
                or reconstruction.input_payload.get("source_selection_id")
                != str(browser_selection_id)
                or reconstruction.input_payload.get("legacy_report_checksum_sha256")
                != source_guard_report_checksum
                or not isinstance(reconstruction.checkpoint_payload, dict)
            ):
                continue
            raw_checkpoint = reconstruction.checkpoint_payload.get(
                "geometry_guard_report_reconstruction"
            )
            if isinstance(raw_checkpoint, dict):
                derived_report_checkpoint = dict(raw_checkpoint)
                break
        return ImageGeometryGuardScope(
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            browser_manifest_checksum_sha256=staging.manifest_checksum_sha256,
            job_input_payload=dict(job.input_payload),
            job_checkpoint_payload=(
                None if job.checkpoint_payload is None else dict(job.checkpoint_payload)
            ),
            derived_report_checkpoint=derived_report_checkpoint,
        )

    def latest_decisions(self, *, guard_job_id: UUID) -> tuple[ImageGeometryGuardDecision, ...]:
        rows = self._session.scalars(
            select(ImageImportGeometryGuardDecisionModel)
            .where(ImageImportGeometryGuardDecisionModel.guard_job_id == guard_job_id)
            .order_by(
                ImageImportGeometryGuardDecisionModel.source_checksum_sha256,
                ImageImportGeometryGuardDecisionModel.position_index,
                ImageImportGeometryGuardDecisionModel.revision.desc(),
            )
        ).all()
        latest: dict[tuple[str, int], ImageGeometryGuardDecision] = {}
        for row in rows:
            key = (row.source_checksum_sha256, row.position_index)
            latest.setdefault(key, _decision(row))
        return tuple(latest[key] for key in sorted(latest))

    def add_decisions(
        self, values: Sequence[ImageGeometryGuardDecision]
    ) -> tuple[ImageGeometryGuardDecision, ...]:
        for value in values:
            self._session.add(
                ImageImportGeometryGuardDecisionModel(
                    id=value.id,
                    game_id=value.game_id,
                    browser_selection_id=value.browser_selection_id,
                    guard_job_id=value.guard_job_id,
                    guard_report_checksum_sha256=value.guard_report_checksum_sha256,
                    source_checksum_sha256=value.source_checksum_sha256,
                    source_relative_path=value.source_relative_path,
                    position_index=value.position_index,
                    sequence_number=value.sequence_number,
                    revision=value.revision,
                    disposition=value.disposition.value,
                    symbol_grid_quad=(
                        None
                        if value.symbol_grid_quad is None
                        else [dict(point) for point in value.symbol_grid_quad]
                    ),
                    unavailable_cell_indices=list(value.unavailable_cell_indices),
                    reason=value.reason,
                    actor=value.actor,
                    decision_checksum_sha256=value.decision_checksum_sha256,
                    created_at=value.created_at,
                )
            )
        self._session.flush()
        return tuple(values)

    def get_manifest_by_checksum(
        self, *, guard_job_id: UUID, manifest_checksum_sha256: str
    ) -> ImageGeometryGuardResolutionManifest | None:
        row = self._session.scalar(
            select(ImageImportGeometryGuardResolutionManifestModel).where(
                ImageImportGeometryGuardResolutionManifestModel.guard_job_id == guard_job_id,
                ImageImportGeometryGuardResolutionManifestModel.manifest_checksum_sha256
                == manifest_checksum_sha256,
            )
        )
        return None if row is None else _manifest(row)

    def get_manifest_by_id(
        self, *, manifest_id: UUID
    ) -> ImageGeometryGuardResolutionManifest | None:
        row = self._session.get(ImageImportGeometryGuardResolutionManifestModel, manifest_id)
        return None if row is None else _manifest(row)

    def add_manifest(
        self, value: ImageGeometryGuardResolutionManifest
    ) -> ImageGeometryGuardResolutionManifest:
        self._session.add(
            ImageImportGeometryGuardResolutionManifestModel(
                id=value.id,
                game_id=value.game_id,
                browser_selection_id=value.browser_selection_id,
                guard_job_id=value.guard_job_id,
                guard_report_checksum_sha256=value.guard_report_checksum_sha256,
                source_manifest_checksum_sha256=value.source_manifest_checksum_sha256,
                page_geometry_manifest_checksum_sha256=(
                    value.page_geometry_manifest_checksum_sha256
                ),
                manifest_relative_path=value.manifest_relative_path,
                manifest_checksum_sha256=value.manifest_checksum_sha256,
                decision_count=value.decision_count,
                sealed_by=value.sealed_by,
                created_at=value.created_at,
            )
        )
        self._session.flush()
        return value


def _decision(row: ImageImportGeometryGuardDecisionModel) -> ImageGeometryGuardDecision:
    return ImageGeometryGuardDecision(
        id=row.id,
        game_id=row.game_id,
        browser_selection_id=row.browser_selection_id,
        guard_job_id=row.guard_job_id,
        guard_report_checksum_sha256=row.guard_report_checksum_sha256,
        source_checksum_sha256=row.source_checksum_sha256,
        source_relative_path=row.source_relative_path,
        position_index=row.position_index,
        sequence_number=row.sequence_number,
        revision=row.revision,
        disposition=ImageGeometryGuardDisposition(row.disposition),
        symbol_grid_quad=(
            None
            if row.symbol_grid_quad is None
            else tuple(dict(point) for point in row.symbol_grid_quad)
        ),
        unavailable_cell_indices=tuple(row.unavailable_cell_indices),
        reason=row.reason,
        actor=row.actor,
        decision_checksum_sha256=row.decision_checksum_sha256,
        created_at=row.created_at,
    )


def _manifest(
    row: ImageImportGeometryGuardResolutionManifestModel,
) -> ImageGeometryGuardResolutionManifest:
    return ImageGeometryGuardResolutionManifest(
        id=row.id,
        game_id=row.game_id,
        browser_selection_id=row.browser_selection_id,
        guard_job_id=row.guard_job_id,
        guard_report_checksum_sha256=row.guard_report_checksum_sha256,
        source_manifest_checksum_sha256=row.source_manifest_checksum_sha256,
        page_geometry_manifest_checksum_sha256=row.page_geometry_manifest_checksum_sha256,
        manifest_relative_path=row.manifest_relative_path,
        manifest_checksum_sha256=row.manifest_checksum_sha256,
        decision_count=row.decision_count,
        sealed_by=row.sealed_by,
        created_at=row.created_at,
    )


__all__ = [
    "SqlAlchemyImageImportGeometryGuardRepository",
]
