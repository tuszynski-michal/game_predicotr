"""Auditable board-level reconstruction for immutable legacy guard reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

from game_predictor_api.domain.image_import_geometry_guard import payload_checksum
from game_predictor_api.domain.jobs import Job, JobStatus, JobType
from game_predictor_api.storage.job_repository import job_from_record
from game_predictor_api.storage.models import JobModel
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .large_import_geometry_guard import reconstruct_board_level_guard_report_from_legacy
from .production_workflow import (
    ProductionImageStageAdapterSuite,
    _board_cell_processing_snapshot,
    _filter_canonical_originals,
    _filter_registered_geometry_originals,
    _geometry_rollout_snapshot,
    _grid_profile_snapshot,
    _image_selection_run_id,
    _normalization_adapter_version,
    _page_geometry_manifest,
    _page_geometry_manifest_checksum,
    _page_registration_profile_snapshot,
    _pipeline_fingerprint,
    _symbol_model_snapshot,
)
from .source_ingestion import ManagedOriginalStore


class GeometryGuardReportReconstructionHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        *,
        repository_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_root = artifact_root.resolve()
        self._repository_root = repository_root.resolve()
        self._original_store = ManagedOriginalStore(self._artifact_root)

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        source = self._source_job(job)
        legacy_report, legacy_checksum = self._legacy_report(source, job)
        managed_manifest = self._original_store.load_existing_manifest(source)
        if source.input_payload.get("source_manifest_sha256") != job.input_payload.get(
            "source_manifest_checksum_sha256"
        ) or managed_manifest.checksum_sha256 != legacy_report.get("sourceManifestChecksumSha256"):
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The source manifests differ from the immutable legacy guard report.",
            )
        if _page_geometry_manifest_checksum(source) != job.input_payload.get(
            "page_geometry_manifest_checksum_sha256"
        ) or legacy_report.get(
            "pageGeometryManifestChecksumSha256"
        ) != _page_geometry_manifest_checksum(source):
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The page geometry manifest differs from the immutable legacy guard report.",
            )
        geometry_manifest = _page_geometry_manifest(
            source,
            self._artifact_root,
            managed_manifest=managed_manifest,
        )
        originals = _filter_registered_geometry_originals(
            _filter_canonical_originals(managed_manifest.originals, source),
            geometry_manifest,
        )
        ranges = {
            item.checksum_sha256: (item.sequence_range_start, item.sequence_range_end)
            for item in originals
            if item.sequence_range_start is not None and item.sequence_range_end is not None
        }
        processing = _board_cell_processing_snapshot(source)
        if processing is None:
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_RECONSTRUCTION_SNAPSHOT_INVALID",
                "The legacy guard job has no pinned board-cell processing snapshot.",
            )
        suite = ProductionImageStageAdapterSuite(
            self._artifact_root,
            repository_root=self._repository_root,
            symbol_model=_symbol_model_snapshot(source),
            grid_profile=_grid_profile_snapshot(source),
            page_registration_profile=_page_registration_profile_snapshot(source),
            page_geometry_manifest=geometry_manifest,
            image_selection_run_id=_image_selection_run_id(source),
            attested_sequence_ranges=ranges,
            board_cell_processing=processing,
            geometry_rollout=_geometry_rollout_snapshot(source),
            game_id=source.game_id,
            normalization_adapter_version=_normalization_adapter_version(source),
        )
        result = reconstruct_board_level_guard_report_from_legacy(
            artifact_root=self._artifact_root,
            source_job_id=source.id,
            pipeline_fingerprint_sha256=_pipeline_fingerprint(source),
            legacy_report=legacy_report,
            legacy_report_checksum_sha256=legacy_checksum,
            originals=originals,
            geometry_entries=geometry_manifest,
            suite=suite,
        )
        context.checkpoint(
            checkpoint_payload={
                "checkpoint_kind": "image-geometry-guard-report-reconstruction-v1",
                "geometry_guard_report_reconstruction": {
                    "sourceGuardJobId": str(source.id),
                    "legacyReportChecksumSha256": legacy_checksum,
                    "sourceManifestChecksumSha256": job.input_payload.get(
                        "source_manifest_checksum_sha256"
                    ),
                    "pageGeometryManifestChecksumSha256": job.input_payload.get(
                        "page_geometry_manifest_checksum_sha256"
                    ),
                    "reportChecksumSha256": result.report_checksum_sha256,
                    "reportRelativePath": result.report_relative_path,
                },
                "schema_version": 1,
            },
            stage="image_geometry_guard_report_reconstruction",
            current=result.source_count,
            total=result.source_count,
            success_count=result.board_count,
            failure_count=0,
            review_count=0,
        )

    def _source_job(self, reconstruction_job: Job) -> Job:
        if (
            reconstruction_job.job_type is not JobType.VALIDATE
            or reconstruction_job.game_id is None
            or reconstruction_job.input_payload.get("validation_kind")
            != "image_geometry_guard_report_reconstruction"
        ):
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_RECONSTRUCTION_JOB_INVALID",
                "The report reconstruction handler received another job contract.",
            )
        try:
            source_id = UUID(str(reconstruction_job.input_payload.get("source_guard_job_id")))
        except (TypeError, ValueError) as error:
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_RECONSTRUCTION_JOB_INVALID",
                "The source guard job identifier is invalid.",
            ) from error
        with self._session_factory() as session:
            record = session.get(JobModel, source_id)
            source = None if record is None else job_from_record(record)
        if (
            source is None
            or source.job_type is not JobType.IMPORT
            or source.status is not JobStatus.FAILED
            or source.game_id != reconstruction_job.game_id
            or source.input_payload.get("source_selection_id")
            != reconstruction_job.input_payload.get("source_selection_id")
        ):
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_RECONSTRUCTION_SOURCE_INVALID",
                "The reconstruction source is not the pinned failed import.",
            )
        return source

    def _legacy_report(
        self,
        source: Job,
        reconstruction_job: Job,
    ) -> tuple[dict[str, object], str]:
        checkpoint = source.checkpoint_payload
        guard = None if checkpoint is None else checkpoint.get("geometry_systemic_guard")
        if not isinstance(guard, Mapping):
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_REPORT_UNAVAILABLE",
                "The source import has no immutable geometry guard report.",
            )
        relative = guard.get("reportRelativePath")
        expected = guard.get("reportChecksumSha256")
        if (
            not isinstance(relative, str)
            or not isinstance(expected, str)
            or expected != reconstruction_job.input_payload.get("legacy_report_checksum_sha256")
        ):
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The source guard checkpoint differs from the reconstruction job.",
            )
        pure = PurePosixPath(relative)
        path = self._artifact_root.joinpath(*pure.parts).resolve()
        allowed = (self._artifact_root / "data" / "image-geometry-guards").resolve()
        if not path.is_relative_to(allowed) or not path.is_file():
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_REPORT_UNAVAILABLE",
                "The immutable legacy guard report is unavailable.",
            )
        try:
            envelope = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_REPORT_UNAVAILABLE",
                "The immutable legacy guard report cannot be decoded.",
            ) from error
        report = envelope.get("report") if isinstance(envelope, Mapping) else None
        if (
            not isinstance(report, Mapping)
            or envelope.get("reportChecksumSha256") != expected
            or payload_checksum(report) != expected
            or report.get("schemaVersion") == "image-geometry-systemic-guard-report-v2"
            or report.get("jobId") != str(source.id)
        ):
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The legacy guard report content changed or is not legacy.",
            )
        return dict(cast(Mapping[str, object], report)), expected


__all__ = ["GeometryGuardReportReconstructionHandler"]
