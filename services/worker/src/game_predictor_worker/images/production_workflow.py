"""Production image import: managed originals through review-ready projections."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, cast
from uuid import UUID

import numpy as np
from game_predictor_api.application.board_cell_geometry_pending import (
    ManagedBoardCellProcessingManifestStore,
)
from game_predictor_api.application.browser_staging_retention import ManagedOriginalsHandoff
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryPendingReason,
)
from game_predictor_api.domain.board_topology import BoardTopology as DomainBoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    AttestedSequenceRange,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    VirtualCell,
    canonical_json_bytes,
    derive_virtual_cells,
)
from game_predictor_api.domain.jobs import Job
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
    bootstrap_symbol_model_snapshot,
)
from game_predictor_api.storage.browser_staging_retention_repository import (
    SqlAlchemyBrowserStagingRetentionRepository,
)
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .board_cell_geometry_activation import (
    BOARD_CELL_PROCESSING_VERSION,
    BoardCellRecropSnapshotError,
    require_v20_supported_topology,
    validate_board_cell_processing_snapshot,
)
from .board_cell_geometry_contract import (
    BoardCellGeometryEntry,
    BoardCellGeometryEvidence,
    BoardCellQuad,
    BoardCellTopology,
    EvidenceKind,
)
from .board_cell_geometry_contract import (
    Quad as BoardCellContractQuad,
)
from .board_cell_geometry_crops import (
    CROPPER_VERSION as V19_CROPPER_VERSION,
)
from .board_cell_geometry_crops import (
    BoardCellGeometrySourceDirectCropper,
)
from .board_cell_geometry_deferred_writer import BoardCellGeometryDeferredWriter
from .board_cell_geometry_estimator import estimate_board_cell_geometry
from .geometry import ClassicalPageBoardDetector, Point, Quad
from .large_import_geometry_guard import (
    LARGE_IMPORT_GEOMETRY_GUARD_VERSION,
    LARGE_IMPORT_GUARD_SAMPLE_LIMIT,
    LARGE_IMPORT_MIN_BOARD_COUNT,
    LARGE_IMPORT_MIN_READY_RATE,
    LARGE_IMPORT_MIN_SOURCE_COUNT,
    run_large_import_geometry_guard,
)
from .normalization import CanonicalSourceFrame, CanonicalSourceLoader, CanonicalSourceLoadError
from .orchestration import ImageBatchHandler, ImageFileRegistration
from .orchestration_store import SqlAlchemyImageBatchStore
from .page_geometry_registration import (
    PAGE_REGISTRATION_VERSION,
    VerifiedPageRegistrar,
    is_ordered_active_grid,
)
from .pipeline_contract import (
    CURRENT_NORMALIZATION_ADAPTER_VERSION,
    SYMBOL_RGB_PREPROCESSING_VERSION,
    CellAssetRolloutMode,
    GeometryPipelineRolloutSnapshot,
    GeometryRolloutMode,
    ImagePipelineContractError,
)
from .pipeline_execution import (
    FunctionImageStageAdapter,
    ImagePipelineExecutionError,
    ImagePipelineStageExecutor,
    ImageStageContext,
    VersionedImageStageAdapter,
)
from .pipeline_store import SqlAlchemyImagePipelineStore
from .rectification import BoardGeometry, PageGeometry
from .sequence_ocr import (
    PaddleSequenceNumberRecognizer,
    SequenceOcrError,
    extract_sequence_number_crop,
)
from .source_direct_crops import (
    SOURCE_DIRECT_CROPPER_VERSION,
    SourceDirectBoardCellCropper,
)
from .source_ingestion import (
    ImageSourceIngestionHandler,
    ManagedOriginal,
    ManagedOriginalStore,
    ManagedSourceManifest,
)
from .structured_geometry import (
    STRUCTURED_LATTICE_ACTIVE_CONFIG_VERSION,
    STRUCTURED_LATTICE_CANDIDATE_CONFIG_VERSION,
    STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
    STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION,
    BoardGeometryDisposition,
    StructuredGeometryConfigV2,
    StructuredGeometryInitializationRequest,
    StructuredOpenCvGeometryEngine,
    evaluate_structured_geometry_shadow_v2,
    evaluate_structured_lattice_shadow_v3,
    structured_lattice_active_config_payload,
    structured_lattice_candidate_config_payload,
)
from .symbol_model_release import build_symbol_predictions
from .symbol_onnx import (
    LocalSymbolOnnxAdapter,
    SymbolOnnxError,
    preprocess_rgb_batch,
)
from .virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
    VirtualCellExtractionError,
    VirtualCellRender,
    VirtualCellRenderer,
)

NORMALIZATION_ADAPTER_VERSION = CURRENT_NORMALIZATION_ADAPTER_VERSION
LEGACY_NORMALIZATION_ADAPTER_VERSION = "image-normalization-v1"
DETECTION_ADAPTER_VERSION = "page-board-detector-v4-verified-registration-v1"
CROP_ADAPTER_VERSION = SOURCE_DIRECT_CROPPER_VERSION
SYMBOL_ADAPTER_VERSION = "local-symbol-onnx-runtime-v1"
SEQUENCE_ADAPTER_VERSION = "sequence-number-ocr-v2-page-continuity-v1"


def _attach_lattice_candidate_to_detection(
    raw_boards: Sequence[object],
    candidate: Mapping[str, object],
) -> list[dict[str, object]]:
    candidate_boards = {
        _integer(board, "positionIndex"): board
        for board in (
            _mapping(value, "structuredGeometryCandidateV3.board")
            for value in _sequence(candidate.get("boards"), "structuredGeometryCandidateV3.boards")
        )
    }
    projected: list[dict[str, object]] = []
    for value in raw_boards:
        board = dict(_mapping(value, "board"))
        position = _integer(board, "positionIndex")
        measured = candidate_boards.get(position)
        if measured is None:
            projected.append(board)
            continue
        geometry = dict(_mapping(board.get("geometry"), "geometry"))
        for key in (
            "analysisQuad",
            "boardFrameQuad",
            "symbolGridQuad",
            "localLatticeStatus",
            "localLatticeVersion",
            "contentSafety",
        ):
            geometry[key] = measured.get(key)
        geometry["latticeReasonCode"] = measured.get("reasonCode")
        board["geometry"] = geometry
        projected.append(board)
    return projected


def _activate_structured_lattice_v3(
    upstream: Mapping[str, object],
    candidate: Mapping[str, object],
    *,
    active_config_checksum_sha256: str,
) -> dict[str, object]:
    """Promote only proven per-board v3 lattices; never reuse a frame fallback."""

    candidate_boards = {
        _integer(board, "positionIndex"): board
        for board in (
            _mapping(value, "structuredGeometryCandidateV3.board")
            for value in _sequence(candidate.get("boards"), "structuredGeometryCandidateV3.boards")
        )
    }
    boards: list[dict[str, object]] = []
    source_reasons: set[str] = set()
    for value in _sequence(upstream.get("boards"), "structuredGeometry.boards"):
        board = dict(_mapping(value, "structuredGeometry.board"))
        position = _integer(board, "positionIndex")
        refined = candidate_boards.get(position)
        if refined is None:
            reason: str | None = "source_support_incomplete"
            symbol_grid_quad = None
            local_status = "needs_review"
        else:
            local_status = str(refined.get("localLatticeStatus"))
            symbol_grid_quad = refined.get("symbolGridQuad")
            reason_value = refined.get("reasonCode")
            reason = reason_value if isinstance(reason_value, str) and reason_value else None
        automatic = local_status == "estimated" and symbol_grid_quad is not None and reason is None
        reason_codes = [] if automatic else [reason or "insufficient_lattice_evidence"]
        source_reasons.update(reason_codes)
        board.update(
            {
                "analysisQuad": None if refined is None else refined.get("analysisQuad"),
                "boardFrameQuad": None if refined is None else refined.get("boardFrameQuad"),
                "contentSafety": None if refined is None else refined.get("contentSafety"),
                "disposition": (
                    BoardGeometryDisposition.AUTOMATIC.value
                    if automatic
                    else BoardGeometryDisposition.NEEDS_MANUAL_REVIEW.value
                ),
                "finalQuad": symbol_grid_quad if automatic else None,
                "idealToSourceHomography": None,
                "localLatticeStatus": local_status,
                "localLatticeVersion": (
                    None if refined is None else refined.get("localLatticeVersion")
                ),
                "reasonCodes": reason_codes,
                "symbolGridQuad": symbol_grid_quad if automatic else None,
            }
        )
        boards.append(board)
    payload = dict(upstream)
    payload.update(
        {
            "activationReportChecksumSha256": structured_lattice_active_config_payload()[
                "acceptanceReportChecksumSha256"
            ],
            "boards": boards,
            "configChecksumSha256": active_config_checksum_sha256,
            "geometryRolePolicy": "frame_conditioned_symbol_lattice_v1",
            "localLatticeConfigVersion": STRUCTURED_LATTICE_ACTIVE_CONFIG_VERSION,
            "reasonCodes": sorted(source_reasons),
            "schemaVersion": 2,
            "status": "ready" if not source_reasons else "needs_review",
        }
    )
    payload.pop("resultChecksumSha256", None)
    payload["resultChecksumSha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return payload


class BoardCellGeometryDeferrer(Protocol):
    def defer(
        self,
        context: ImageStageContext,
        *,
        position_index: int,
        sequence_number: int,
        reason_code: BoardCellGeometryPendingReason,
        processing_snapshot: Mapping[str, object],
    ) -> None: ...


class ProductionImageImportWorkflow:
    """Run the complete image workflow behind one image import job."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        *,
        repository_root: Path,
        hard_reserve_bytes: int = 30 * 1024**3,
        resume_target_bytes: int = 80 * 1024**3,
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._repository_root = repository_root.resolve()
        self._hard_reserve_bytes = hard_reserve_bytes
        self._resume_target_bytes = resume_target_bytes
        self._original_store = ManagedOriginalStore(self._artifact_root)
        self._source_handler = ImageSourceIngestionHandler(
            self._original_store,
            before_original=self._has_pipeline_capacity,
        )
        self._browser_staging_retention = SqlAlchemyBrowserStagingRetentionRepository(
            session_factory
        )
        self._batch_store = SqlAlchemyImageBatchStore(session_factory)
        self._projection_store = SqlAlchemyImagePipelineStore(session_factory)
        self._board_cell_geometry_deferred_writer = BoardCellGeometryDeferredWriter(
            session_factory,
            ManagedBoardCellProcessingManifestStore(self._artifact_root),
        )

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        manifest = self._original_store.load_or_create_manifest(
            job,
            source_directory=_source_directory(job),
        )
        all_source_count = len(manifest.originals)
        source_context = _ProgressWindowContext(
            context,
            current_offset=0,
            total=max(1, all_source_count),
            stage_prefix="image_source",
            expose_result_counts=False,
        )
        manifest = self._source_handler.ingest(
            cast(JobExecutionContext, source_context),
            job,
        )
        self._record_browser_staging_handoff(job, manifest, completed_at=context.now())
        geometry_manifest = _page_geometry_manifest(
            job,
            self._artifact_root,
            managed_manifest=manifest,
        )
        unresolved_originals = _filter_canonical_originals(manifest.originals, job)
        canonical_skipped_count = len(manifest.originals) - len(unresolved_originals)
        pipeline_originals = unresolved_originals
        pipeline_originals = _filter_registered_geometry_originals(
            pipeline_originals,
            geometry_manifest,
        )
        deferred_geometry_count = len(unresolved_originals) - len(pipeline_originals)
        source_count = len(pipeline_originals)
        if not pipeline_originals:
            context.checkpoint(
                checkpoint_payload={
                    "canonical_skipped_source_count": canonical_skipped_count,
                    "checkpoint_kind": "image-source-filtered-v1",
                    "deferred_geometry_source_count": deferred_geometry_count,
                    "schema_version": 1,
                },
                stage="image_deferred_geometry_skip",
                current=all_source_count,
                total=all_source_count,
                success_count=all_source_count,
                failure_count=0,
                review_count=0,
            )
            return
        registrations = tuple(
            ImageFileRegistration(
                source_checksum_sha256=original.checksum_sha256,
                source_relative_path=_data_relative_path(original.managed_relative_path),
                order_index=index,
            )
            for index, original in enumerate(pipeline_originals)
        )
        attested_sequence_ranges = {
            original.checksum_sha256: (
                original.sequence_range_start,
                original.sequence_range_end,
            )
            for original in pipeline_originals
            if original.sequence_range_start is not None and original.sequence_range_end is not None
        }
        board_cell_processing = _board_cell_processing_snapshot(job)
        geometry_guard_policy = _geometry_systemic_guard_policy(job)
        geometry_guard = None
        if board_cell_processing is not None and geometry_guard_policy is not None:
            guard_suite = ProductionImageStageAdapterSuite(
                self._artifact_root,
                repository_root=self._repository_root,
                symbol_model=_symbol_model_snapshot(job),
                grid_profile=_grid_profile_snapshot(job),
                page_registration_profile=_page_registration_profile_snapshot(job),
                page_geometry_manifest=geometry_manifest,
                image_selection_run_id=_image_selection_run_id(job),
                attested_sequence_ranges=attested_sequence_ranges,
                board_cell_processing=board_cell_processing,
                geometry_rollout=_geometry_rollout_snapshot(job),
                game_id=job.game_id,
                normalization_adapter_version=_normalization_adapter_version(job),
            )
            geometry_guard = run_large_import_geometry_guard(
                artifact_root=self._artifact_root,
                job_id=job.id,
                pipeline_fingerprint_sha256=_pipeline_fingerprint(job),
                source_manifest_checksum_sha256=manifest.checksum_sha256,
                page_geometry_manifest_checksum_sha256=(_page_geometry_manifest_checksum(job)),
                originals=pipeline_originals,
                geometry_entries=geometry_manifest,
                suite=guard_suite,
            )
            if geometry_guard.required:
                context.checkpoint(
                    checkpoint_payload={
                        "checkpoint_kind": "image-geometry-systemic-guard-v1",
                        "geometry_systemic_guard": geometry_guard.checkpoint_payload(),
                        "schema_version": 1,
                    },
                    stage="image_geometry_systemic_guard",
                    current=all_source_count,
                    total=all_source_count + source_count,
                    success_count=job.success_count,
                    failure_count=job.failure_count,
                    review_count=job.review_count,
                )
                if not geometry_guard.passed:
                    ready_rate = geometry_guard.final_cell_grid_ready_rate or 0.0
                    raise JobHandlerError(
                        "IMAGE_GEOMETRY_SYSTEMIC_REGRESSION",
                        (
                            "Representative final 3x5 geometry readiness "
                            f"was {ready_rate:.2%}; at least 98.00% and zero "
                            "geometry invariant violations are required."
                        ),
                    )
        self._batch_store.register_files(
            job.id,
            registrations=registrations,
            pipeline_fingerprint=_pipeline_fingerprint(job),
            registered_at=context.now(),
        )
        adapters = ProductionImageStageAdapterSuite(
            self._artifact_root,
            repository_root=self._repository_root,
            symbol_model=_symbol_model_snapshot(job),
            grid_profile=_grid_profile_snapshot(job),
            page_registration_profile=_page_registration_profile_snapshot(job),
            page_geometry_manifest=geometry_manifest,
            image_selection_run_id=_image_selection_run_id(job),
            attested_sequence_ranges=attested_sequence_ranges,
            board_cell_processing=board_cell_processing,
            geometry_rollout=_geometry_rollout_snapshot(job),
            game_id=job.game_id,
            normalization_adapter_version=_normalization_adapter_version(job),
            board_cell_geometry_deferred_writer=(
                self._board_cell_geometry_deferred_writer
                if board_cell_processing is not None
                else None
            ),
        ).adapters()
        pipeline = ImageBatchHandler(
            self._batch_store,
            ImagePipelineStageExecutor(
                self._projection_store,
                adapters,
                attested_sequence_ranges=attested_sequence_ranges,
            ),
            before_candidate=lambda: self._has_pipeline_capacity(context.job),
        )
        pipeline_context = _ProgressWindowContext(
            context,
            current_offset=all_source_count,
            total=all_source_count + source_count,
            stage_prefix="image_pipeline",
            checkpoint_extras=(
                {"geometry_systemic_guard": geometry_guard.checkpoint_payload()}
                if geometry_guard is not None and geometry_guard.required
                else None
            ),
        )
        pipeline(cast(JobExecutionContext, pipeline_context), job)

    def _has_pipeline_capacity(self, job: Job) -> bool:
        required = (
            self._resume_target_bytes
            if job.stage == "waiting_for_storage"
            else self._hard_reserve_bytes
        )
        return shutil.disk_usage(self._artifact_root).free >= required

    def _record_browser_staging_handoff(
        self,
        job: Job,
        manifest: ManagedSourceManifest,
        *,
        completed_at: datetime,
    ) -> None:
        raw_upload_id = job.input_payload.get("source_selection_id")
        if job.game_id is None or not isinstance(raw_upload_id, str):
            return
        try:
            upload_id = UUID(raw_upload_id)
        except ValueError:
            return
        self._browser_staging_retention.record_ingested(
            ManagedOriginalsHandoff(
                upload_id=upload_id,
                game_id=job.game_id,
                import_job_id=job.id,
                manifest_relative_path=manifest.relative_path,
                manifest_checksum_sha256=manifest.checksum_sha256,
                completed_at=completed_at,
            )
        )


def _filter_canonical_originals(
    originals: Sequence[ManagedOriginal],
    job: Job,
) -> tuple[ManagedOriginal, ...]:
    """Skip whole attested seq_* sources already resolved for this game.

    The API stores a canonical sequence snapshot in the job payload.  Partial
    sources remain in the pipeline so projection can preserve only their
    unresolved boards; only a source whose complete attested range is covered
    is removed before registration and expensive stages.
    """

    raw_numbers = job.input_payload.get("canonical_sequence_numbers")
    if not isinstance(raw_numbers, list):
        return tuple(originals)
    canonical = {int(number) for number in raw_numbers if isinstance(number, int) and number > 0}
    if not canonical:
        return tuple(originals)
    retained: list[ManagedOriginal] = []
    for original in originals:
        start = getattr(original, "sequence_range_start", None)
        end = getattr(original, "sequence_range_end", None)
        if not isinstance(start, int) or not isinstance(end, int):
            retained.append(original)
            continue
        if any(number not in canonical for number in range(start, end + 1)):
            retained.append(original)
    return tuple(retained)


def _filter_registered_geometry_originals(
    originals: Sequence[ManagedOriginal],
    geometry_entries: Mapping[str, object],
) -> tuple[ManagedOriginal, ...]:
    """Keep only sources proven safe by a pinned page-geometry manifest.

    A non-empty manifest is authoritative.  Review-required pages remain in
    that immutable manifest for a later retry/manual pass and must not enter
    crop or symbol inference prematurely.
    """

    if not geometry_entries:
        return tuple(originals)
    return tuple(
        original
        for original in originals
        if isinstance(geometry_entries.get(original.checksum_sha256), Mapping)
        and cast(Mapping[str, object], geometry_entries[original.checksum_sha256]).get("status")
        == "registered"
    )


class _ProgressWindowContext:
    """Map two resumable phases onto one monotonic job progress contract."""

    def __init__(
        self,
        context: JobExecutionContext,
        *,
        current_offset: int,
        total: int,
        stage_prefix: str,
        expose_result_counts: bool = True,
        checkpoint_extras: Mapping[str, object] | None = None,
    ) -> None:
        self._context = context
        self._current_offset = current_offset
        self._total = total
        self._stage_prefix = stage_prefix
        self._expose_result_counts = expose_result_counts
        self._checkpoint_extras = dict(checkpoint_extras or {})

    @property
    def job(self) -> Job:
        return self._context.job

    @property
    def lease_token(self):  # type: ignore[no-untyped-def]
        return self._context.lease_token

    def now(self):  # type: ignore[no-untyped-def]
        return self._context.now()

    def heartbeat(self) -> None:
        self._context.heartbeat()

    def wait_for_review(self) -> None:
        self._context.wait_for_review()

    def wait_for_storage(self, *, checkpoint_payload: dict[str, object]) -> None:
        self._context.wait_for_storage(
            checkpoint_payload={
                **self._checkpoint_extras,
                **checkpoint_payload,
                "workflow_phase": self._stage_prefix,
            }
        )

    def checkpoint(
        self,
        *,
        checkpoint_payload: dict[str, object],
        stage: str,
        current: int,
        total: int | None,
        success_count: int,
        failure_count: int,
        review_count: int,
    ) -> None:
        del total
        previous = self._context.job
        reported_success_count = (
            success_count if self._expose_result_counts else previous.success_count
        )
        reported_failure_count = (
            failure_count if self._expose_result_counts else previous.failure_count
        )
        reported_review_count = (
            review_count if self._expose_result_counts else previous.review_count
        )
        self._context.checkpoint(
            checkpoint_payload={
                **self._checkpoint_extras,
                **checkpoint_payload,
                "workflow_phase": self._stage_prefix,
            },
            stage=f"{self._stage_prefix}:{stage}",
            current=max(previous.progress_current, self._current_offset + current),
            total=max(previous.progress_total or 0, self._total),
            success_count=max(previous.success_count, reported_success_count),
            failure_count=max(previous.failure_count, reported_failure_count),
            review_count=max(previous.review_count, reported_review_count),
        )


class ProductionImageStageAdapterSuite:
    def __init__(
        self,
        artifact_root: Path,
        *,
        repository_root: Path,
        symbol_model: SymbolModelJobSnapshot | None = None,
        grid_profile: Mapping[str, object] | None = None,
        page_registration_profile: Mapping[str, object] | None = None,
        page_geometry_manifest: Mapping[str, object] | None = None,
        image_selection_run_id: str | None = None,
        attested_sequence_ranges: Mapping[str, tuple[int, int]] | None = None,
        board_cell_processing: Mapping[str, object] | None = None,
        board_cell_geometry_deferred_writer: BoardCellGeometryDeferrer | None = None,
        normalization_adapter_version: str = NORMALIZATION_ADAPTER_VERSION,
        geometry_rollout: GeometryPipelineRolloutSnapshot | None = None,
        game_id: UUID | None = None,
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._artifacts = _ManagedImageArtifacts(artifact_root)
        self._normalized_images = _ExecutionScopedNormalizedImageLoader(self._artifacts)
        self._canonical_sources = CanonicalSourceLoader()
        if normalization_adapter_version not in {
            LEGACY_NORMALIZATION_ADAPTER_VERSION,
            NORMALIZATION_ADAPTER_VERSION,
        }:
            raise ImagePipelineExecutionError(
                "IMAGE_NORMALIZATION_ADAPTER_UNSUPPORTED",
                "The pinned normalization adapter is not supported.",
            )
        self._normalization_adapter_version = normalization_adapter_version
        self._repository_root = repository_root
        self._symbol_model_snapshot = symbol_model or bootstrap_symbol_model_snapshot()
        self._grid_profile = dict(grid_profile or {})
        self._page_registration_profile = dict(page_registration_profile or {})
        self._page_geometry_manifest = dict(page_geometry_manifest or {})
        self._image_selection_run_id = image_selection_run_id
        self._attested_sequence_ranges = dict(attested_sequence_ranges or {})
        self._board_cell_processing = dict(board_cell_processing or {})
        self._board_topology = (
            require_v20_supported_topology(self._board_cell_processing)
            if self._board_cell_processing
            else BoardCellTopology(rows=3, columns=5)
        )
        self._board_cell_geometry_deferred_writer = board_cell_geometry_deferred_writer
        self._geometry_rollout = geometry_rollout or _legacy_geometry_rollout_snapshot()
        self._game_id = game_id
        self._detector = ClassicalPageBoardDetector()
        # A pinned preflight manifest is the complete geometry authority for a
        # ``seq_*`` import.  Loading the fallback registration anchors in that
        # case is both unnecessary work and, more importantly, makes a fully
        # verified import depend on artifacts it will never consume.
        registration_profile = (
            {} if self._page_geometry_manifest else self._page_registration_profile
        )
        self._page_registrar = VerifiedPageRegistrar(
            registration_profile,
            load_anchor_rgb=self._load_anchor_rgb,
        )
        self._cropper = SourceDirectBoardCellCropper(
            cell_output_size=self._symbol_model_snapshot.input_size,
        )
        self._v19_cropper = BoardCellGeometrySourceDirectCropper(
            cell_output_size=self._symbol_model_snapshot.input_size,
            topology=(
                self._board_topology
                if self._board_cell_processing.get("topologyRulesVersionId") is not None
                else None
            ),
        )
        self._ocr: PaddleSequenceNumberRecognizer | None = None
        self._symbol_model: LocalSymbolOnnxAdapter | None = None
        self._structured_geometry_engine: StructuredOpenCvGeometryEngine | None = None
        self._virtual_renderer = VirtualCellRenderer()
        self._virtual_render_cache_key: str | None = None
        self._virtual_render_cache: tuple[VirtualCellRender, ...] = ()

    def adapters(self) -> tuple[VersionedImageStageAdapter, ...]:
        stages: list[FunctionImageStageAdapter] = [
            FunctionImageStageAdapter("discovery", "image-discovery-v1", self.discovery),
            FunctionImageStageAdapter(
                "normalization",
                self._normalization_adapter_version,
                self.normalization,
            ),
            FunctionImageStageAdapter(
                "board_detection",
                (
                    DETECTION_ADAPTER_VERSION
                    if self._geometry_rollout.is_legacy
                    else self._geometry_rollout.geometry_engine_version
                ),
                self.board_detection,
            ),
        ]
        if self._board_cell_processing:
            stages.append(
                FunctionImageStageAdapter(
                    "board_cell_geometry",
                    (
                        BOARD_CELL_PROCESSING_VERSION
                        if self._geometry_rollout.is_legacy
                        else self._geometry_rollout.geometry_engine_version
                    ),
                    self.board_cell_geometry,
                    self.persist_board_cell_geometry_deferrals,
                )
            )
        stages.extend(
            [
                FunctionImageStageAdapter(
                    "board_crops",
                    (
                        self._geometry_rollout.virtual_renderer_version
                        if not self._geometry_rollout.is_legacy
                        else (
                            V19_CROPPER_VERSION
                            if self._board_cell_processing
                            else CROP_ADAPTER_VERSION
                        )
                    ),
                    self.board_crops,
                    (self.persist_board_crop_deferrals if self._board_cell_processing else None),
                ),
                FunctionImageStageAdapter(
                    "sequence_ocr",
                    (
                        "sequence-number-from-attested-range-v1"
                        if self._attested_sequence_ranges
                        else SEQUENCE_ADAPTER_VERSION
                    ),
                    self.sequence_ocr,
                ),
                FunctionImageStageAdapter(
                    "symbol_inference",
                    SYMBOL_ADAPTER_VERSION,
                    self.symbol_inference,
                ),
            ]
        )
        return cast(
            tuple[VersionedImageStageAdapter, ...],
            tuple(stages),
        )

    def discovery(self, context: ImageStageContext) -> Mapping[str, object]:
        rgb = self._artifacts.load_rgb(context.source_relative_path)
        return {
            "height": int(rgb.shape[0]),
            "sourceChecksumSha256": context.source_checksum_sha256,
            "sourceRelativePath": context.source_relative_path,
            "width": int(rgb.shape[1]),
        }

    def normalization(self, context: ImageStageContext) -> Mapping[str, object]:
        if not self._geometry_rollout.is_legacy:
            frame = self._canonical_source(context)
            self._normalized_images.remember(context, frame.rgb)
            return {
                "exifOrientation": frame.source.exif_orientation,
                "height": frame.source.height,
                "normalizedPixelChecksumSha256": (frame.source.normalized_pixel_checksum_sha256),
                "orientationAction": frame.orientation_action,
                "sourceChecksumSha256": frame.source.source_checksum_sha256,
                "sourceHeight": frame.raw_height,
                "sourceMode": frame.source_mode,
                "sourceRelativePath": context.source_relative_path,
                "sourceWidth": frame.raw_width,
                "width": frame.source.width,
            }
        source = self._artifacts.path(context.source_relative_path)
        try:
            with Image.open(source) as image:
                image.load()
                source_width, source_height = image.size
                source_mode = image.mode
                orientation_value = image.getexif().get(274)
                oriented = ImageOps.exif_transpose(image).convert("RGB")
                width, height = oriented.size
                rgb = np.ascontiguousarray(np.asarray(oriented, dtype=np.uint8))
        except (OSError, UnidentifiedImageError) as error:
            raise ImagePipelineExecutionError(
                "IMAGE_NORMALIZATION_DECODE_FAILED",
                "The managed source JPEG cannot be normalized.",
            ) from error
        self._normalized_images.remember(context, rgb)
        if self._normalization_adapter_version == LEGACY_NORMALIZATION_ADAPTER_VERSION:
            relative = (
                PurePosixPath(
                    "working",
                    LEGACY_NORMALIZATION_ADAPTER_VERSION,
                    context.file_execution_key[:2],
                    context.file_execution_key,
                )
                / "normalized.png"
            ).as_posix()
            return {
                "height": height,
                "normalizedChecksumSha256": self._artifacts.write_immutable(
                    relative,
                    _encode_rgb_png(rgb),
                ),
                "normalizedRelativePath": relative,
                "width": width,
            }
        return {
            "height": height,
            "normalizedPixelChecksumSha256": _rgb_pixel_checksum(rgb),
            "orientationAction": _orientation_action(orientation_value),
            "sourceChecksumSha256": context.source_checksum_sha256,
            "sourceHeight": source_height,
            "sourceMode": source_mode,
            "sourceRelativePath": context.source_relative_path,
            "sourceWidth": source_width,
            "width": width,
        }

    def board_detection(self, context: ImageStageContext) -> Mapping[str, object]:
        if not self._geometry_rollout.is_legacy:
            structured, candidate_v2, candidate_v3 = self._detect_structured_geometry(context)
            if self._geometry_rollout.geometry_mode is not GeometryRolloutMode.STRUCTURED_SHADOW:
                return {
                    "boards": [
                        {
                            "confidence": board["geometryConfidence"],
                            "geometry": {
                                "quad": board["finalQuad"],
                                "structuredDisposition": board["disposition"],
                            },
                            "positionIndex": board["positionIndex"],
                        }
                        for board in cast(list[dict[str, object]], structured["boards"])
                    ],
                    "structuredGeometry": structured,
                }
            legacy = self._legacy_board_detection(context)
            projected = {**legacy, "structuredGeometry": structured}
            if candidate_v2 is not None:
                projected["structuredGeometryCandidateV2"] = candidate_v2
            if candidate_v3 is not None:
                projected["structuredGeometryCandidateV3"] = candidate_v3
                projected["boards"] = _attach_lattice_candidate_to_detection(
                    cast(Sequence[object], projected["boards"]),
                    candidate_v3,
                )
            return projected
        return self._legacy_board_detection(context)

    def _legacy_board_detection(self, context: ImageStageContext) -> Mapping[str, object]:
        normalized = _previous(context, "normalization")
        rgb = self._normalized_images.load(context, normalized)
        pinned = _registered_page_geometry(
            self._page_geometry_manifest,
            context.source_checksum_sha256,
            image_width=int(rgb.shape[1]),
            image_height=int(rgb.shape[0]),
            expected_board_count=_expected_board_count(context.attested_sequence_range),
        )
        if self._page_geometry_manifest:
            if pinned is None:
                raise ImagePipelineExecutionError(
                    "IMAGE_PAGE_GEOMETRY_REQUIRES_REVIEW",
                    "The pinned geometry preflight has no verified page for this source.",
                )
            return _registered_geometry_payload(pinned)
        # A reviewed page profile is the normal path for ``seq_*`` imports.
        # Every resulting target quad is specific to this source photo; no
        # coordinates are reused directly from another angle.
        if self._page_registrar.available:
            registered = self._page_registrar.register(rgb)
            if registered is None:
                raise ImagePipelineExecutionError(
                    "IMAGE_PAGE_GEOMETRY_REQUIRES_REVIEW",
                    "The page did not pass verified 3x3 geometry registration.",
                )
            return {
                "boards": [
                    {
                        "confidence": registered.board_red_edge_coverages[position],
                        "cropValidity": "verified_page_geometry",
                        "geometry": {
                            "quad": [point.to_dict() for point in quad],
                            "registration": registered.to_payload(),
                        },
                        "geometryValidity": "verified",
                        "positionIndex": position,
                    }
                    for position, quad in enumerate(registered.quads)
                ],
                "geometryValidity": "verified",
                "recoveryMode": "verified_page_registration",
                "registration": registered.to_payload(),
            }

        # Non-seq legacy imports retain a detector fallback, but it is now
        # fail-closed: all nine boards must be physically detected and none may
        # be synthesized/refined from a grid hypothesis.
        result = self._detector.detect(
            rgb,
            allow_grid_recovery=False,
            allow_occluded_grid_recovery=False,
            allow_partial_grid_recovery=False,
        )
        if (
            result.status != "detected"
            or len(result.boards) != 9
            or result.layout_hypotheses
            or any(
                board.refined_from_grid or board.red_border_score <= 0.0 for board in result.boards
            )
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_PAGE_GEOMETRY_REQUIRES_REVIEW",
                "The page has no complete, independently evidenced 3x3 geometry.",
            )
        projected_boards: list[dict[str, object]] = []
        for board in result.boards:
            calibrated = _calibrated_quad(
                board.quad,
                profile=self._grid_profile,
                image_selection_run_id=self._image_selection_run_id,
                position_index=board.position_index,
                image_width=int(rgb.shape[1]),
                image_height=int(rgb.shape[0]),
            )
            projected_boards.append(
                {
                    "confidence": max(0.0, min(1.0, board.red_border_score)),
                    "cropValidity": "verified_detector_geometry",
                    "geometry": {
                        "detectorQuad": [point.to_dict() for point in board.quad],
                        "quad": [point.to_dict() for point in calibrated],
                    },
                    "geometryValidity": "verified",
                    "positionIndex": board.position_index,
                }
            )
        return {
            "boards": projected_boards,
            "geometryValidity": "verified",
            "recoveryMode": "complete_verified_detector",
        }

    def board_cell_geometry(self, context: ImageStageContext) -> Mapping[str, object]:
        """Estimate all nine lattices and persist only fail-closed deferrals."""

        if not self._geometry_rollout.is_legacy:
            if self._geometry_rollout.geometry_mode is GeometryRolloutMode.STRUCTURED_SHADOW:
                legacy = self._legacy_board_cell_geometry(context)
                projected = {
                    **legacy,
                    "structuredGeometry": _mapping(
                        _previous(context, "board_detection").get("structuredGeometry"),
                        "structuredGeometry",
                    ),
                }
                candidate_v2 = _previous(context, "board_detection").get(
                    "structuredGeometryCandidateV2"
                )
                if isinstance(candidate_v2, Mapping):
                    projected["structuredGeometryCandidateV2"] = dict(candidate_v2)
                candidate_v3 = _previous(context, "board_detection").get(
                    "structuredGeometryCandidateV3"
                )
                if isinstance(candidate_v3, Mapping):
                    projected["structuredGeometryCandidateV3"] = dict(candidate_v3)
                return projected
            return self._structured_board_cell_geometry(context)
        return self._legacy_board_cell_geometry(context)

    def _legacy_board_cell_geometry(
        self,
        context: ImageStageContext,
    ) -> Mapping[str, object]:
        if not self._board_cell_processing:
            raise ImagePipelineExecutionError(
                "IMAGE_BOARD_CELL_PROCESSING_NOT_PINNED",
                "The v20 geometry stage requires an explicit job snapshot.",
            )
        sequence_range = context.attested_sequence_range
        if sequence_range is None:
            raise ImagePipelineExecutionError(
                "IMAGE_BOARD_CELL_SEQUENCE_UNATTESTED",
                "The v20 geometry stage requires an attested seq_* range.",
            )
        normalized = _previous(context, "normalization")
        detections = _boards(_previous(context, "board_detection"))
        start, end = sequence_range
        if end - start + 1 != len(detections):
            raise ImagePipelineExecutionError(
                "IMAGE_BOARD_CELL_ATTESTED_RANGE_INVALID",
                "The attested sequence range differs from the verified page geometry.",
            )
        rgb = self._normalized_images.load(context, normalized)
        projected: list[dict[str, object]] = []
        for board in detections:
            position = _integer(board, "positionIndex")
            sequence_number = start + position
            estimate = estimate_board_cell_geometry(
                rgb,
                _quad(_mapping(board.get("geometry"), "geometry")),
            )
            common = {
                "confidence": _number(board, "confidence"),
                "geometry": dict(_mapping(board.get("geometry"), "geometry")),
                "positionIndex": position,
                "sequenceNumber": sequence_number,
            }
            if (
                estimate.status == "estimated"
                and estimate.lattice_bounds_quad is not None
                and estimate.evidence is not None
                and len(estimate.cells) == self._board_topology.cell_count
            ):
                entry = BoardCellGeometryEntry(
                    source_order_index=0,
                    image_id=context.file_execution_key,
                    source_image_checksum_sha256=context.source_checksum_sha256,
                    source_image_relative_path=context.source_relative_path,
                    source_image_width=int(rgb.shape[1]),
                    source_image_height=int(rgb.shape[0]),
                    source_group=str(context.job_id),
                    condition_tags=("production-v20",),
                    sequence_number=sequence_number,
                    position_index=position,
                    lattice_bounds_quad=estimate.lattice_bounds_quad,
                    cells=estimate.cells,
                    evidence=estimate.evidence,
                    topology=self._board_topology,
                )
                projected.append(
                    {
                        **common,
                        "cellGeometry": entry.to_dict(),
                        "status": "verified",
                    }
                )
                continue
            estimator_reason = (
                estimate.fallback_reason or "BOARD_CELL_GEOMETRY_AUTOMATIC_EVIDENCE_INSUFFICIENT"
            )
            reason = _pending_reason(estimator_reason)
            projected.append(
                {
                    **common,
                    "cellGeometry": None,
                    "diagnostics": estimate.to_dict(),
                    "estimatorFailureReason": estimator_reason,
                    "reasonCode": reason.value,
                    "status": "deferred",
                }
            )
        return {
            "boards": projected,
            "configurationFingerprintSha256": self._board_cell_processing[
                "configurationFingerprintSha256"
            ],
            "processingVersion": BOARD_CELL_PROCESSING_VERSION,
            "gridRows": self._board_topology.rows,
            "gridColumns": self._board_topology.columns,
            "topologyRulesVersionId": self._board_topology.rules_version_id,
        }

    def _structured_board_cell_geometry(
        self,
        context: ImageStageContext,
    ) -> Mapping[str, object]:
        structured = _mapping(
            _previous(context, "board_detection").get("structuredGeometry"),
            "structuredGeometry",
        )
        projected: list[dict[str, object]] = []
        review_only = self._geometry_rollout.geometry_mode is GeometryRolloutMode.STRUCTURED_REVIEW
        for raw_board in _sequence(structured.get("boards"), "structuredGeometry.boards"):
            board = _mapping(raw_board, "structuredGeometry.board")
            automatic = board.get("disposition") == BoardGeometryDisposition.AUTOMATIC.value
            final_quad = board.get("finalQuad")
            common = {
                "confidence": board.get("geometryConfidence"),
                "geometry": {
                    "quad": final_quad,
                    "structuredDisposition": board.get("disposition"),
                },
                "positionIndex": board.get("positionIndex"),
                "sequenceNumber": board.get("sequenceNumber"),
            }
            if automatic and final_quad is not None and not review_only:
                projected.append(
                    {
                        **common,
                        "cellGeometry": {
                            "gridQuad": final_quad,
                            "geometryFingerprintSha256": _text(structured, "resultChecksumSha256"),
                        },
                        "status": "verified",
                    }
                )
            else:
                reason_codes = board.get("reasonCodes")
                projected.append(
                    {
                        **common,
                        "cellGeometry": None,
                        "estimatorFailureReason": (
                            "STRUCTURED_GEOMETRY_REVIEW_REQUIRED"
                            if review_only
                            else "STRUCTURED_GEOMETRY_AUTOMATIC_EVIDENCE_INSUFFICIENT"
                        ),
                        "reasonCode": BoardCellGeometryPendingReason.INCOMPLETE_LATTICE.value,
                        "reasonCodes": list(reason_codes) if isinstance(reason_codes, list) else [],
                        "status": "deferred",
                    }
                )
        return {
            "boards": projected,
            "configurationFingerprintSha256": _text(structured, "configChecksumSha256"),
            "gridColumns": self._board_topology.columns,
            "gridRows": self._board_topology.rows,
            "processingVersion": self._geometry_rollout.geometry_engine_version,
            "structuredGeometry": structured,
            "topologyRulesVersionId": self._board_topology.rules_version_id,
        }

    def board_crops(self, context: ImageStageContext) -> Mapping[str, object]:
        if not self._geometry_rollout.is_legacy:
            return self._board_crops_structured(context)
        if self._board_cell_processing:
            return self._board_crops_v19(context)
        normalized = _previous(context, "normalization")
        detection_payload = _previous(context, "board_detection")
        detections = _boards(detection_payload)
        if (
            detection_payload.get("geometryValidity") != "verified"
            or len(detections) != 9
            or any(board.get("geometryValidity") != "verified" for board in detections)
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_BOARD_CROP_GEOMETRY_UNVERIFIED",
                "Cell crops require a complete verified 3x3 page geometry.",
            )
        rgb = self._normalized_images.load(context, normalized)
        geometry = PageGeometry(
            status="detected",
            image_width=int(rgb.shape[1]),
            image_height=int(rgb.shape[0]),
            boards=tuple(
                BoardGeometry(
                    position_index=_integer(board, "positionIndex"),
                    quad=_quad(_mapping(board.get("geometry"), "geometry")),
                )
                for board in detections
            ),
        )
        result = self._cropper.crop(rgb, geometry)
        if result.status != "cropped":
            raise ImagePipelineExecutionError(
                "IMAGE_BOARD_CROP_REQUIRES_REVIEW",
                "The detected boards could not be cropped automatically.",
            )
        projected: list[dict[str, object]] = []
        for board in result.boards:
            root = PurePosixPath(
                "crops",
                "source-direct-v1",
                context.file_execution_key[:2],
                context.file_execution_key,
                f"board-{board.position_index:02d}",
            )
            board_relative = (root / "source-context.png").as_posix()
            board_checksum = self._artifacts.write_rgb(
                board_relative,
                board.context_rgb,
            )
            cells: list[dict[str, object]] = []
            for cell in board.cells:
                relative = (
                    root / "cells" / f"r{cell.row_index:02d}-c{cell.column_index:02d}.png"
                ).as_posix()
                cells.append(
                    {
                        "columnIndex": cell.column_index,
                        "cropChecksumSha256": self._artifacts.write_rgb(relative, cell.rgb),
                        "cropRelativePath": relative,
                        "rowIndex": cell.row_index,
                    }
                )
            projected.append(
                {
                    "boardChecksumSha256": board_checksum,
                    "boardRelativePath": board_relative,
                    "cellOutputSize": self._symbol_model_snapshot.input_size,
                    "cells": cells,
                    "cropperVersion": CROP_ADAPTER_VERSION,
                    "cropValidity": "source_direct_verified_geometry",
                    "displayAssetKind": "source_context",
                    "positionIndex": board.position_index,
                    "sourceContextBounds": board.context_bounds.to_dict(),
                }
            )
        return {"boards": projected}

    def _board_crops_v19(self, context: ImageStageContext) -> Mapping[str, object]:
        normalized = _previous(context, "normalization")
        detection_by_position = {
            _integer(board, "positionIndex"): board
            for board in _boards(_previous(context, "board_detection"))
        }
        geometry_boards = _boards(_previous(context, "board_cell_geometry"))
        rgb = self._normalized_images.load(context, normalized)
        projected: list[dict[str, object]] = []
        deferred: list[dict[str, object]] = []
        for geometry_board in geometry_boards:
            if geometry_board.get("status") != "verified":
                continue
            position = _integer(geometry_board, "positionIndex")
            sequence_number = _integer(geometry_board, "sequenceNumber")
            entry = _board_cell_geometry_entry(
                _mapping(geometry_board.get("cellGeometry"), "cellGeometry")
            )
            cropped = self._v19_cropper.crop(rgb, entry)
            if cropped.status != "cropped" or len(cropped.cells) != self._board_topology.cell_count:
                estimator_reason = (
                    cropped.review_reasons[0]
                    if cropped.review_reasons
                    else "BOARD_CELL_CROP_RESULT_INCOMPLETE"
                )
                reason = _pending_reason(estimator_reason)
                deferred.append(
                    {
                        "estimatorFailureReason": estimator_reason,
                        "positionIndex": position,
                        "reasonCode": reason.value,
                        "sequenceNumber": sequence_number,
                    }
                )
                continue
            detection = detection_by_position[position]
            board_quad = _quad(_mapping(detection.get("geometry"), "geometry"))
            context_rgb, context_bounds = _source_context(rgb, board_quad)
            root = PurePosixPath(
                "crops",
                "source-direct-v19",
                context.file_execution_key[:2],
                context.file_execution_key,
                f"board-{position:02d}",
            )
            board_relative = (root / "source-context.png").as_posix()
            board_checksum = self._artifacts.write_rgb(board_relative, context_rgb)
            cells: list[dict[str, object]] = []
            for cell in cropped.cells:
                relative = (
                    root / "cells" / f"r{cell.row_index:02d}-c{cell.column_index:02d}.png"
                ).as_posix()
                cells.append(
                    {
                        "columnIndex": cell.column_index,
                        "cropChecksumSha256": self._artifacts.write_rgb(relative, cell.rgb),
                        "cropRelativePath": relative,
                        "paddedSourceQuad": _contract_quad_payload(cell.padded_source_quad),
                        "rowIndex": cell.row_index,
                        "sourceQuad": _contract_quad_payload(cell.source_quad),
                    }
                )
            projected.append(
                {
                    "boardChecksumSha256": board_checksum,
                    "boardRelativePath": board_relative,
                    "cellOutputSize": self._symbol_model_snapshot.input_size,
                    "cells": cells,
                    "cropperVersion": V19_CROPPER_VERSION,
                    "cropValidity": "source_direct_verified_v19_geometry",
                    "displayAssetKind": "source_context",
                    "positionIndex": position,
                    "sourceContextBounds": context_bounds,
                    "gridRows": self._board_topology.rows,
                    "gridColumns": self._board_topology.columns,
                    "topologyRulesVersionId": self._board_topology.rules_version_id,
                }
            )
        return {"boards": projected, "deferredBoards": deferred}

    def _board_crops_structured(self, context: ImageStageContext) -> Mapping[str, object]:
        if self._geometry_rollout.geometry_mode is GeometryRolloutMode.STRUCTURED_REVIEW:
            geometry_boards = _boards(_previous(context, "board_cell_geometry"))
            return {
                "assetMode": "virtual_source",
                "boards": [],
                "deferredBoards": [
                    {
                        "positionIndex": board["positionIndex"],
                        "reasonCode": board["reasonCode"],
                        "sequenceNumber": board["sequenceNumber"],
                    }
                    for board in geometry_boards
                ],
            }
        virtual_payload = self._virtual_board_payload(context)
        if self._geometry_rollout.cell_asset_mode is CellAssetRolloutMode.VIRTUAL_DEFAULT:
            return virtual_payload
        legacy = self._board_crops_v19(context)
        return {**legacy, "virtualShadow": virtual_payload}

    def _virtual_board_payload(self, context: ImageStageContext) -> dict[str, object]:
        geometry_stage = _previous(context, "board_cell_geometry")
        structured = _mapping(
            geometry_stage.get("structuredGeometry"),
            "structuredGeometry",
        )
        renders = self._virtual_renders(context)
        by_position: dict[int, list[VirtualCellRender]] = {}
        for render in renders:
            board_slot = render.render_spec.get("boardSlot")
            if not isinstance(board_slot, int):
                raise ImagePipelineExecutionError(
                    "IMAGE_VIRTUAL_CELL_PROVENANCE_INVALID",
                    "A virtual render has no board-slot provenance.",
                )
            by_position.setdefault(board_slot, []).append(render)
        boards: list[dict[str, object]] = []
        for position in sorted(by_position):
            board_renders = sorted(by_position[position], key=lambda value: value.cell_index)
            boards.append(
                {
                    "assetMode": "virtual_source",
                    "cellOutputSize": self._symbol_model_snapshot.input_size,
                    "cells": [
                        {
                            "assetMode": "virtual_source",
                            "columnIndex": render.column_index,
                            "cropChecksumSha256": render.rendered_pixel_checksum_sha256,
                            "extractorVersion": render.extractor_version,
                            "logicalCellKeySha256": render.logical_cell_key_sha256,
                            "logicalCellKeyV2Sha256": render.logical_cell_key_v2_sha256,
                            "renderIdentityV2Sha256": render.render_identity_v2_sha256,
                            "renderSpec": render.render_spec,
                            "renderSpecChecksumSha256": render.render_spec_checksum_sha256,
                            "renderedPixelChecksumSha256": (render.rendered_pixel_checksum_sha256),
                            "rowIndex": render.row_index,
                        }
                        for render in board_renders
                    ],
                    "cropperVersion": self._geometry_rollout.virtual_renderer_version,
                    "geometryChecksumSha256": _text(structured, "resultChecksumSha256"),
                    "geometryEngineName": _text(structured, "engineId"),
                    "geometryEngineVersion": _text(structured, "engineVersion"),
                    "gridColumns": self._board_topology.columns,
                    "gridRows": self._board_topology.rows,
                    "positionIndex": position,
                    "topologyRulesVersionId": self._board_topology.rules_version_id,
                }
            )
        return {
            "assetMode": "virtual_source",
            "boards": boards,
            "deferredBoards": [
                {
                    "positionIndex": board["positionIndex"],
                    "reasonCode": board["reasonCode"],
                    "sequenceNumber": board["sequenceNumber"],
                }
                for board in _boards(geometry_stage)
                if board.get("status") == "deferred"
            ],
            "geometryChecksumSha256": _text(structured, "resultChecksumSha256"),
            "rendererVersion": self._geometry_rollout.virtual_renderer_version,
        }

    def _virtual_renders(self, context: ImageStageContext) -> tuple[VirtualCellRender, ...]:
        if self._virtual_render_cache_key == context.file_execution_key:
            return self._virtual_render_cache
        normalized = _previous(context, "normalization")
        frame = self._canonical_source(context)
        if (
            normalized.get("normalizedPixelChecksumSha256")
            != frame.source.normalized_pixel_checksum_sha256
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_NORMALIZATION_PIXEL_CHECKSUM_MISMATCH",
                "The virtual source differs from its persisted normalization checkpoint.",
            )
        geometry_stage = _previous(context, "board_cell_geometry")
        structured = _mapping(
            geometry_stage.get("structuredGeometry"),
            "structuredGeometry",
        )
        attested = context.attested_sequence_range
        topology_rules_version = self._board_topology.rules_version_id
        if attested is None or topology_rules_version is None:
            raise ImagePipelineExecutionError(
                "IMAGE_VIRTUAL_GEOMETRY_PROVENANCE_INVALID",
                "Virtual cells require an attested range and pinned topology rules.",
            )
        range_value = AttestedSequenceRange(start=attested[0], end=attested[1])
        topology = DomainBoardTopology(
            rows=self._board_topology.rows,
            columns=self._board_topology.columns,
        )
        configuration = DirectCellRenderConfiguration(
            extractor_version=self._geometry_rollout.virtual_renderer_version,
            preprocessing_version=self._geometry_rollout.preprocessing_version,
            interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
            output_width=self._symbol_model_snapshot.input_size,
            output_height=self._symbol_model_snapshot.input_size,
            padding_fraction=0.08,
        )
        cells: list[VirtualCell] = []
        geometry_revision_value = structured.get("geometryRevision", 0)
        if not isinstance(geometry_revision_value, int) or isinstance(
            geometry_revision_value, bool
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_VIRTUAL_GEOMETRY_PROVENANCE_INVALID",
                "The structured geometry revision must be a non-negative integer.",
            )
        geometry_revision = geometry_revision_value
        boards = {
            _integer(_mapping(value, "structured board"), "positionIndex"): _mapping(
                value, "structured board"
            )
            for value in _sequence(structured.get("boards"), "structuredGeometry.boards")
        }
        for geometry_board in _boards(geometry_stage):
            if geometry_board.get("status") != "verified":
                continue
            position = _integer(geometry_board, "positionIndex")
            board = boards[position]
            if board.get("disposition") != BoardGeometryDisposition.AUTOMATIC.value:
                continue
            final_quad = _source_quad(board.get("finalQuad"))
            local_lattice_version = board.get("localLatticeVersion")
            geometry_version = (
                local_lattice_version
                if isinstance(local_lattice_version, str) and local_lattice_version
                else self._geometry_rollout.geometry_engine_version
            )
            virtual_geometry = VirtualBoardGeometry(
                source=frame.source,
                source_occurrence=SourceOccurrence(
                    import_job_id=context.job_id,
                    file_execution_key=context.file_execution_key,
                ),
                slot=range_value.active_slots[position],
                topology=topology,
                topology_rules_version_id=UUID(topology_rules_version),
                geometry_revision=geometry_revision,
                geometry_version=geometry_version,
                engine_kind=GeometryEngineKind.STRUCTURED_OPENCV_V1,
                symbol_grid_quad=final_quad,
            )
            cells.extend(
                derive_virtual_cells(
                    geometry=virtual_geometry,
                    configuration=configuration,
                )
            )
        try:
            rendered = self._virtual_renderer.render(frame, tuple(cells))
        except VirtualCellExtractionError as error:
            raise ImagePipelineExecutionError(error.code, str(error)) from error
        self._virtual_render_cache_key = context.file_execution_key
        self._virtual_render_cache = rendered
        return rendered

    def persist_board_cell_geometry_deferrals(
        self,
        context: ImageStageContext,
        payload: Mapping[str, object],
    ) -> None:
        for board in _boards(payload):
            if board.get("status") != "deferred":
                continue
            self._defer_board_cell_geometry(
                context,
                position_index=_integer(board, "positionIndex"),
                sequence_number=_integer(board, "sequenceNumber"),
                reason=_pending_reason(_text(board, "estimatorFailureReason")),
            )

    def persist_board_crop_deferrals(
        self,
        context: ImageStageContext,
        payload: Mapping[str, object],
    ) -> None:
        # Structured virtual crops carry forward the exact deferrals already
        # persisted by ``board_cell_geometry``.  Replaying them here would both
        # duplicate the durable pending projection and try to interpret the
        # structured ``reasonCode`` as the legacy estimator failure contract.
        if payload.get("assetMode") == "virtual_source":
            return
        for value in _sequence(payload.get("deferredBoards", []), "deferredBoards"):
            board = _mapping(value, "deferredBoard")
            self._defer_board_cell_geometry(
                context,
                position_index=_integer(board, "positionIndex"),
                sequence_number=_integer(board, "sequenceNumber"),
                reason=_pending_reason(_text(board, "estimatorFailureReason")),
            )

    def _defer_board_cell_geometry(
        self,
        context: ImageStageContext,
        *,
        position_index: int,
        sequence_number: int,
        reason: BoardCellGeometryPendingReason,
    ) -> None:
        if self._board_cell_geometry_deferred_writer is None:
            raise ImagePipelineExecutionError(
                "IMAGE_BOARD_CELL_PENDING_WRITER_MISSING",
                "The explicitly pinned v20 job has no durable deferred writer.",
            )
        self._board_cell_geometry_deferred_writer.defer(
            context,
            position_index=position_index,
            sequence_number=sequence_number,
            reason_code=reason,
            processing_snapshot=self._board_cell_processing,
        )

    def _canonical_source(self, context: ImageStageContext) -> CanonicalSourceFrame:
        try:
            return self._canonical_sources.load(
                self._artifacts.path(context.source_relative_path),
                expected_source_checksum_sha256=context.source_checksum_sha256,
            )
        except CanonicalSourceLoadError as error:
            raise ImagePipelineExecutionError(error.code, str(error)) from error

    def _detect_structured_geometry(
        self,
        context: ImageStageContext,
    ) -> tuple[
        dict[str, object],
        dict[str, object] | None,
        dict[str, object] | None,
    ]:
        if context.attested_sequence_range is None or self._board_topology.rules_version_id is None:
            raise ImagePipelineExecutionError(
                "IMAGE_STRUCTURED_GEOMETRY_ATTESTATION_REQUIRED",
                "Structured geometry requires an attested range and pinned topology.",
            )
        frame = self._canonical_source(context)
        topology = DomainBoardTopology(
            rows=self._board_topology.rows,
            columns=self._board_topology.columns,
        )
        attested = AttestedSequenceRange(
            start=context.attested_sequence_range[0],
            end=context.attested_sequence_range[1],
        )
        pinned_initial_quads: tuple[SourceQuad, ...] | None = None
        pinned_geometry_checksum: str | None = None
        geometry_profile: Mapping[str, object] | None = self._page_registration_profile or None
        if (
            self._geometry_rollout.geometry_engine_version
            == STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION
            and self._page_geometry_manifest
        ):
            registered = _registered_page_geometry(
                self._page_geometry_manifest,
                context.source_checksum_sha256,
                image_width=frame.source.width,
                image_height=frame.source.height,
                expected_board_count=attested.board_count,
            )
            if registered is None:
                raise ImagePipelineExecutionError(
                    "IMAGE_PAGE_GEOMETRY_REQUIRES_REVIEW",
                    "The pinned geometry preflight has no verified page for this source.",
                )
            pinned_initial_quads = tuple(
                SourceQuad(
                    corners=cast(
                        tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                        tuple(SourcePoint(x=float(point.x), y=float(point.y)) for point in quad),
                    )
                )
                for quad in cast(Sequence[Quad], registered["quads"])
            )
            pinned_geometry_checksum = _text(
                registered,
                "manifestEntryChecksumSha256",
            )
            geometry_profile = None
        engine = self._structured_engine()
        result = engine.detect(
            frame,
            StructuredGeometryInitializationRequest.for_frame(
                frame,
                topology=topology,
                topology_rules_version_id=UUID(self._board_topology.rules_version_id),
                attested_range=attested,
                geometry_profile=geometry_profile,
                pinned_initial_quads=pinned_initial_quads,
                pinned_geometry_checksum_sha256=pinned_geometry_checksum,
            ),
        )
        payload = result.to_payload()
        payload["rolloutMode"] = self._geometry_rollout.geometry_mode.value
        active_snapshot = self._geometry_rollout.active_lattice_geometry
        if active_snapshot is not None:
            if active_snapshot.config_payload != structured_lattice_active_config_payload():
                raise ImagePipelineExecutionError(
                    "IMAGE_STRUCTURED_GEOMETRY_ACTIVATION_CONFIG_DRIFT",
                    "The pinned accepted Structured Geometry v3 lattice config changed.",
                )
            active_candidate = evaluate_structured_lattice_shadow_v3(
                frame,
                result,
                config_checksum_sha256=active_snapshot.config_checksum_sha256,
                topology=self._board_topology,
            ).to_payload()
            if (
                active_candidate.get("configChecksumSha256")
                != active_snapshot.config_checksum_sha256
                or active_candidate.get("upstreamResultChecksumSha256")
                != _text(payload, "resultChecksumSha256")
                or active_candidate.get("sourceChecksumSha256")
                != _text(payload, "sourceChecksumSha256")
                or active_candidate.get("normalizedPixelChecksumSha256")
                != _text(payload, "normalizedPixelChecksumSha256")
            ):
                raise ImagePipelineExecutionError(
                    "IMAGE_STRUCTURED_GEOMETRY_ACTIVATION_EVIDENCE_DRIFT",
                    "The accepted Structured Geometry v3 evidence differs from its pinned source.",
                )
            return (
                _activate_structured_lattice_v3(
                    payload,
                    active_candidate,
                    active_config_checksum_sha256=active_snapshot.config_checksum_sha256,
                ),
                None,
                None,
            )
        candidate_snapshot = self._geometry_rollout.candidate_geometry
        if candidate_snapshot is None:
            return payload, None, None
        if self._geometry_rollout.geometry_mode is not GeometryRolloutMode.STRUCTURED_SHADOW:
            raise ImagePipelineExecutionError(
                "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_MODE_INVALID",
                "Structured Geometry v2 measurements are allowed only in shadow mode.",
            )
        if candidate_snapshot.config_version == STRUCTURED_LATTICE_CANDIDATE_CONFIG_VERSION:
            if candidate_snapshot.config_payload != structured_lattice_candidate_config_payload():
                raise ImagePipelineExecutionError(
                    "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_CONFIG_DRIFT",
                    "The pinned Structured Geometry v3 lattice config changed.",
                )
            candidate_v3 = evaluate_structured_lattice_shadow_v3(
                frame,
                result,
                config_checksum_sha256=candidate_snapshot.config_checksum_sha256,
                topology=self._board_topology,
            )
            return payload, None, candidate_v3.to_payload()
        try:
            config = StructuredGeometryConfigV2.from_payload(candidate_snapshot.config_payload)
        except ValueError as error:
            raise ImagePipelineExecutionError(
                "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_CONFIG_DRIFT",
                "The pinned Structured Geometry v2 config cannot be replayed.",
            ) from error
        if config.checksum_sha256 != candidate_snapshot.config_checksum_sha256:
            raise ImagePipelineExecutionError(
                "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_CONFIG_DRIFT",
                "The pinned Structured Geometry v2 config checksum changed.",
            )
        candidate_v2 = evaluate_structured_geometry_shadow_v2(
            frame,
            result,
            config=config,
            game_id=self._game_id,
        )
        return payload, candidate_v2.to_payload(), None

    def _structured_engine(self) -> StructuredOpenCvGeometryEngine:
        if self._structured_geometry_engine is None:
            self._structured_geometry_engine = StructuredOpenCvGeometryEngine(
                load_anchor_rgb=self._load_anchor_rgb,
                engine_version=self._geometry_rollout.geometry_engine_version,
            )
        if (
            self._structured_geometry_engine.version
            != self._geometry_rollout.geometry_engine_version
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_STRUCTURED_GEOMETRY_VERSION_DRIFT",
                "The pinned structured geometry engine differs from the worker implementation.",
            )
        return self._structured_geometry_engine

    def sequence_ocr(self, context: ImageStageContext) -> Mapping[str, object]:
        normalized = _previous(context, "normalization")
        detections = _boards(_previous(context, "board_detection"))
        if self._board_cell_processing:
            crop_positions = {
                _integer(board, "positionIndex")
                for board in _boards(_previous(context, "board_crops"))
            }
            detections = tuple(
                board for board in detections if _integer(board, "positionIndex") in crop_positions
            )
        if context.attested_sequence_range is not None:
            return _attested_sequence_payload(
                detections,
                context.attested_sequence_range,
                allow_sparse=self._board_cell_processing is not None,
            )
        rgb = self._normalized_images.load(context, normalized)
        recognizer = self._ocr_recognizer()
        prepared: list[NDArray[np.uint8] | None] = []
        crop_quads: list[list[dict[str, float]] | None] = []
        reason_sets: list[list[str]] = []
        for board in detections:
            reasons = ["SEQUENCE_OCR_MANUAL_REVIEW_REQUIRED"]
            try:
                _raw, processed_crop, detected_crop_quad = extract_sequence_number_crop(
                    rgb,
                    _quad(_mapping(board.get("geometry"), "geometry")),
                )
                prepared.append(processed_crop)
                crop_quads.append(
                    [
                        {"x": round(float(point[0]), 6), "y": round(float(point[1]), 6)}
                        for point in detected_crop_quad
                    ]
                )
            except SequenceOcrError as error:
                reasons.append(error.code)
                prepared.append(None)
                crop_quads.append(None)
            reason_sets.append(reasons)
        recognized = iter(
            recognizer.recognize_many(tuple(item for item in prepared if item is not None))
        )
        raw_results: list[tuple[str, float]] = []
        for prepared_crop in prepared:
            if prepared_crop is None:
                raw_results.append(("", 0.0))
            else:
                recognition = next(recognized)
                raw_results.append((recognition.raw_text, recognition.confidence))
        observed_numbers = tuple(
            int(raw_text) if raw_text.isdigit() and int(raw_text) > 0 else None
            for raw_text, _confidence in raw_results
        )
        positions = tuple(_integer(board, "positionIndex") for board in detections)
        resolved_numbers, continuity_base = _resolve_page_sequence_numbers(
            observed_numbers,
            positions,
        )
        boards: list[dict[str, object]] = []
        for board, prepared_crop, sequence_quad_payload, reasons in zip(
            detections,
            prepared,
            crop_quads,
            reason_sets,
            strict=True,
        ):
            del prepared_crop
            position = _integer(board, "positionIndex")
            raw_text, confidence = raw_results[position]
            observed_number = observed_numbers[position]
            normalized_number = resolved_numbers[position]
            projected_reasons = list(reasons)
            if continuity_base is not None:
                projected_reasons.append("SEQUENCE_OCR_PAGE_CONTINUITY_INFERRED")
            projected: dict[str, object] = {
                "confidence": confidence,
                "normalizedNumber": normalized_number,
                "ocrNormalizedNumber": observed_number,
                "positionIndex": position,
                "rawText": raw_text,
                "reviewReasons": projected_reasons,
            }
            if continuity_base is not None:
                projected["continuityBase"] = continuity_base
            if sequence_quad_payload is not None:
                projected["sequenceLabelQuad"] = sequence_quad_payload
            boards.append(projected)
        return {"boards": boards}

    def symbol_inference(self, context: ImageStageContext) -> Mapping[str, object]:
        cropped_payload = _previous(context, "board_crops")
        cropped_boards = _boards(cropped_payload)
        boards = self._infer_symbol_boards(context, cropped_boards)
        projected: dict[str, object] = {
            "boards": boards,
            "modelIterationId": (
                None
                if self._symbol_model_snapshot.iteration_id is None
                else str(self._symbol_model_snapshot.iteration_id)
            ),
            "modelManifestChecksumSha256": (self._symbol_model_snapshot.manifest_checksum_sha256),
            "modelChecksumSha256": self._symbol_model_snapshot.onnx_checksum_sha256,
            "modelVersion": self._symbol_model_snapshot.model_version,
            "preprocessingVersion": self._geometry_rollout.preprocessing_version,
            "temperatureApplied": max(0.50, self._symbol_model_snapshot.temperature),
        }
        virtual_shadow = cropped_payload.get("virtualShadow")
        if isinstance(virtual_shadow, Mapping):
            projected["virtualShadow"] = {
                "boards": self._infer_symbol_boards(
                    context,
                    _boards(cast(Mapping[str, object], virtual_shadow)),
                    force_virtual=True,
                ),
                "geometryChecksumSha256": virtual_shadow.get("geometryChecksumSha256"),
                "modelVersion": self._symbol_model_snapshot.model_version,
                "modelChecksumSha256": self._symbol_model_snapshot.onnx_checksum_sha256,
            }
        return projected

    def _infer_symbol_boards(
        self,
        context: ImageStageContext,
        cropped_boards: Sequence[Mapping[str, object]],
        *,
        force_virtual: bool = False,
    ) -> list[dict[str, object]]:
        cell_metadata: list[tuple[int, Mapping[str, object]]] = []
        images: list[NDArray[np.uint8]] = []
        virtual_by_key = (
            {render.logical_cell_key_sha256: render for render in self._virtual_renders(context)}
            if force_virtual
            or any(board.get("assetMode") == "virtual_source" for board in cropped_boards)
            else {}
        )
        for board in cropped_boards:
            position = _integer(board, "positionIndex")
            cells = _sequence(board.get("cells"), "cells")
            for value in cells:
                cell = _mapping(value, "cell")
                if force_virtual or cell.get("assetMode") == "virtual_source":
                    key = _text(cell, "logicalCellKeySha256")
                    render = virtual_by_key.get(key)
                    if (
                        render is None
                        or render.render_spec_checksum_sha256
                        != cell.get("renderSpecChecksumSha256")
                        or render.rendered_pixel_checksum_sha256
                        != cell.get("renderedPixelChecksumSha256")
                    ):
                        raise ImagePipelineExecutionError(
                            "IMAGE_VIRTUAL_CELL_CHECKPOINT_DRIFT",
                            "A restarted virtual render differs from the stored checkpoint.",
                        )
                    images.append(render.rgb)
                else:
                    images.append(self._artifacts.load_rgb(_text(cell, "cropRelativePath")))
                cell_metadata.append((position, cell))
        if not images and not self._board_cell_processing:
            raise ImagePipelineExecutionError(
                "IMAGE_SYMBOL_INPUT_EMPTY",
                "The image pipeline produced no cell crops for symbol inference.",
            )
        if images:
            try:
                inference = self._symbol_adapter().infer(
                    preprocess_rgb_batch(
                        images,
                        input_size=self._symbol_model_snapshot.input_size,
                    )
                )
            except SymbolOnnxError as error:
                raise ImagePipelineExecutionError(f"IMAGE_{error.code}", str(error)) from error
            predictions = build_symbol_predictions(
                inference.logits,
                # Historical model snapshots may contain the former 0.05 floor.
                # Never let a legacy calibration turn out-of-distribution crops
                # into synthetic certainty; this is intentionally independent of
                # the geometry validity decision above.
                temperature=max(0.50, self._symbol_model_snapshot.temperature),
                class_codes=self._symbol_model_snapshot.class_codes,
                alternative_limit=3,
            )
        else:
            predictions = ()
        by_position: dict[int, list[dict[str, object]]] = {}
        for (position, cell), prediction in zip(cell_metadata, predictions, strict=True):
            by_position.setdefault(position, []).append(
                {
                    **prediction.to_dict(),
                    "columnIndex": _integer(cell, "columnIndex"),
                    "rowIndex": _integer(cell, "rowIndex"),
                }
            )
        return [
            {
                "cells": by_position[position],
                "positionIndex": position,
            }
            for position in sorted(by_position)
        ]

    def _ocr_recognizer(self) -> PaddleSequenceNumberRecognizer:
        if self._ocr is None:
            self._ocr = PaddleSequenceNumberRecognizer(
                self._repository_root / "artifacts/m5-models/sequence-number-ocr-v1"
            )
        return self._ocr

    def _load_anchor_rgb(self, checksum_sha256: str) -> NDArray[np.uint8]:
        return self._artifacts.load_rgb(f"originals/{checksum_sha256[:2]}/{checksum_sha256}.jpg")

    def _symbol_adapter(self) -> LocalSymbolOnnxAdapter:
        if self._symbol_model is None:
            root = (
                self._repository_root
                if self._symbol_model_snapshot.storage_root is SymbolModelStorageRoot.REPOSITORY
                else self._artifact_root
            )
            relative = PurePosixPath(self._symbol_model_snapshot.onnx_relative_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise ImagePipelineExecutionError(
                    "IMAGE_SYMBOL_MODEL_PATH_INVALID", "Pinned symbol model path is unsafe."
                )
            model_path = root.joinpath(*relative.parts).resolve()
            if not model_path.is_relative_to(root):
                raise ImagePipelineExecutionError(
                    "IMAGE_SYMBOL_MODEL_PATH_INVALID",
                    "Pinned symbol model path escapes its storage root.",
                )
            try:
                self._symbol_model = LocalSymbolOnnxAdapter(
                    model_path,
                    expected_sha256=self._symbol_model_snapshot.onnx_checksum_sha256,
                    class_codes=self._symbol_model_snapshot.class_codes,
                    input_size=self._symbol_model_snapshot.input_size,
                )
            except SymbolOnnxError as error:
                raise ImagePipelineExecutionError(f"IMAGE_{error.code}", str(error)) from error
        return self._symbol_model


def _rgb_pixel_checksum(rgb: NDArray[np.uint8]) -> str:
    contiguous = np.ascontiguousarray(rgb, dtype=np.uint8)
    digest = hashlib.sha256()
    digest.update(b"rgb-uint8-v1\0")
    digest.update(int(contiguous.shape[1]).to_bytes(8, "big"))
    digest.update(int(contiguous.shape[0]).to_bytes(8, "big"))
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _orientation_action(value: object) -> str:
    actions = {
        1: "identity",
        2: "flip_left_right",
        3: "rotate_180",
        4: "flip_top_bottom",
        5: "transpose",
        6: "rotate_90_clockwise",
        7: "transverse",
        8: "rotate_90_counterclockwise",
    }
    return (
        actions.get(value, "none")
        if isinstance(value, int) and not isinstance(value, bool)
        else "none"
    )


def _encode_rgb_png(rgb: NDArray[np.uint8]) -> bytes:
    output = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(
        output,
        format="PNG",
        optimize=False,
        compress_level=6,
    )
    return output.getvalue()


class _ExecutionScopedNormalizedImageLoader:
    """Keep at most one normalized source in memory for sequential stage execution."""

    def __init__(self, artifacts: _ManagedImageArtifacts) -> None:
        self._artifacts = artifacts
        self._cache_key: str | None = None
        self._cache_rgb: NDArray[np.uint8] | None = None

    def remember(self, context: ImageStageContext, rgb: NDArray[np.uint8]) -> None:
        self._cache_key = context.file_execution_key
        self._cache_rgb = rgb

    def load(
        self,
        context: ImageStageContext,
        normalization: Mapping[str, object],
    ) -> NDArray[np.uint8]:
        if self._cache_key == context.file_execution_key and self._cache_rgb is not None:
            return self._cache_rgb
        relative = normalization.get("normalizedRelativePath")
        if isinstance(relative, str) and relative:
            rgb = self._load_or_rebuild_legacy(context, normalization, relative)
        else:
            source_relative = _text(normalization, "sourceRelativePath")
            if source_relative != context.source_relative_path:
                raise ImagePipelineExecutionError(
                    "IMAGE_NORMALIZATION_SOURCE_DRIFT",
                    "The normalization result references a different managed original.",
                )
            rgb = self._artifacts.load_rgb(source_relative)
            expected = _text(normalization, "normalizedPixelChecksumSha256")
            if _rgb_pixel_checksum(rgb) != expected:
                raise ImagePipelineExecutionError(
                    "IMAGE_NORMALIZATION_PIXEL_CHECKSUM_MISMATCH",
                    "Normalized source pixels differ from the persisted stage result.",
                )
        self.remember(context, rgb)
        return rgb

    def _load_or_rebuild_legacy(
        self,
        context: ImageStageContext,
        normalization: Mapping[str, object],
        relative: str,
    ) -> NDArray[np.uint8]:
        path = self._artifacts.path(relative)
        expected = normalization.get("normalizedChecksumSha256")
        if path.exists():
            try:
                content = path.read_bytes()
            except OSError as error:
                raise ImagePipelineExecutionError(
                    "IMAGE_NORMALIZATION_ARTIFACT_UNREADABLE",
                    "The historical normalization bitmap cannot be read.",
                ) from error
            if isinstance(expected, str) and hashlib.sha256(content).hexdigest() != expected:
                raise ImagePipelineExecutionError(
                    "IMAGE_NORMALIZATION_ARTIFACT_CHECKSUM_MISMATCH",
                    "The historical normalization bitmap differs from its stage result.",
                )
            return self._artifacts.load_rgb(relative)

        rgb = self._artifacts.load_rgb(context.source_relative_path)
        content = _encode_rgb_png(rgb)
        checksum = hashlib.sha256(content).hexdigest()
        if not isinstance(expected, str) or checksum != expected:
            raise ImagePipelineExecutionError(
                "IMAGE_NORMALIZATION_REBUILD_CHECKSUM_MISMATCH",
                "The historical normalization bitmap cannot be reproduced exactly.",
            )
        self._artifacts.write_immutable(relative, content)
        return rgb


class _ManagedImageArtifacts:
    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root.resolve() / "data"

    def path(self, relative_path: str) -> Path:
        relative = PurePosixPath(relative_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_ARTIFACT_PATH_INVALID",
                "The managed image artifact path is invalid.",
            )
        path = self._root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(self._root):
            raise ImagePipelineExecutionError(
                "IMAGE_ARTIFACT_PATH_INVALID",
                "The managed image artifact path escapes its root.",
            )
        return path

    def load_rgb(self, relative_path: str) -> NDArray[np.uint8]:
        path = self.path(relative_path)
        try:
            with Image.open(path) as image:
                image.load()
                return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
        except (OSError, UnidentifiedImageError) as error:
            raise ImagePipelineExecutionError(
                "IMAGE_ARTIFACT_DECODE_FAILED",
                "A managed image artifact cannot be decoded.",
            ) from error

    def write_rgb(self, relative_path: str, rgb: NDArray[np.uint8]) -> str:
        output = io.BytesIO()
        Image.fromarray(rgb, mode="RGB").save(
            output,
            format="PNG",
            optimize=False,
            compress_level=6,
        )
        return self.write_immutable(relative_path, output.getvalue())

    def write_immutable(self, relative_path: str, content: bytes) -> str:
        path = self.path(relative_path)
        checksum = hashlib.sha256(content).hexdigest()
        if path.exists():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                raise ImagePipelineExecutionError(
                    "IMAGE_ARTIFACT_COLLISION",
                    "An immutable image artifact already has different content.",
                )
            return checksum
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-image-")
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                if path.read_bytes() != content:
                    raise ImagePipelineExecutionError(
                        "IMAGE_ARTIFACT_COLLISION",
                        "An immutable image artifact already has different content.",
                    ) from error
        finally:
            temporary.unlink(missing_ok=True)
        return checksum


def _resolve_page_sequence_numbers(
    observed_numbers: Sequence[int | None],
    positions: Sequence[int],
) -> tuple[tuple[int | None, ...], int | None]:
    """Resolve a consecutive page from one dominant OCR base without guessing."""

    if len(observed_numbers) != len(positions) or tuple(positions) != tuple(range(len(positions))):
        return tuple(observed_numbers), None
    bases = Counter(
        number - position
        for number, position in zip(observed_numbers, positions, strict=True)
        if number is not None and number - position > 0
    )
    ranked = sorted(bases.items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return tuple(observed_numbers), None
    winning_base, support = ranked[0]
    runner_up_support = ranked[1][1] if len(ranked) > 1 else 0
    if support < 3 or support - runner_up_support < 2:
        return tuple(observed_numbers), None
    return tuple(winning_base + position for position in positions), winning_base


def _source_directory(job: Job) -> Path:
    value = job.input_payload.get("source_directory")
    if not isinstance(value, str) or not value:
        raise JobHandlerError(
            "IMAGE_IMPORT_PAYLOAD_INVALID",
            "The image import source directory is missing.",
        )
    return Path(value)


def _normalization_adapter_version(job: Job) -> str:
    value = job.input_payload.get("normalization_adapter_version")
    if value is None:
        return LEGACY_NORMALIZATION_ADAPTER_VERSION
    if value not in {
        LEGACY_NORMALIZATION_ADAPTER_VERSION,
        NORMALIZATION_ADAPTER_VERSION,
    }:
        raise JobHandlerError(
            "IMAGE_NORMALIZATION_ADAPTER_UNSUPPORTED",
            "The image import pins an unsupported normalization adapter.",
        )
    return str(value)


def _pipeline_fingerprint(job: Job) -> str:
    value = job.input_payload.get("pipeline_fingerprint")
    if not isinstance(value, str) or len(value) != 64:
        raise JobHandlerError(
            "IMAGE_IMPORT_PAYLOAD_INVALID",
            "The image import pipeline fingerprint is missing.",
        )
    return value


def _legacy_geometry_rollout_snapshot() -> GeometryPipelineRolloutSnapshot:
    return GeometryPipelineRolloutSnapshot(
        geometry_mode=GeometryRolloutMode.LEGACY,
        cell_asset_mode=CellAssetRolloutMode.LEGACY_FILES,
        rollout_revision=0,
        geometry_engine_version=STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
        virtual_renderer_version=VIRTUAL_CELL_RENDERER_VERSION,
        preprocessing_version=SYMBOL_RGB_PREPROCESSING_VERSION,
    )


def _geometry_rollout_snapshot(job: Job) -> GeometryPipelineRolloutSnapshot:
    value = job.input_payload.get("image_geometry_rollout")
    if value is None:
        return _legacy_geometry_rollout_snapshot()
    try:
        return GeometryPipelineRolloutSnapshot.from_payload(value)
    except ImagePipelineContractError as error:
        raise JobHandlerError(error.code, str(error)) from error


def _symbol_model_snapshot(job: Job) -> SymbolModelJobSnapshot:
    value = job.input_payload.get("symbol_model")
    schema_version = job.input_payload.get("schema_version", 1)
    if value is None and schema_version == 1:
        return bootstrap_symbol_model_snapshot()
    if not isinstance(value, Mapping):
        raise JobHandlerError(
            "IMAGE_SYMBOL_MODEL_SNAPSHOT_MISSING",
            "The image import has no pinned symbol model snapshot.",
        )
    try:
        snapshot = SymbolModelJobSnapshot.from_payload(value)
    except ValueError as error:
        code = (
            "IMAGE_SYMBOL_MODEL_SNAPSHOT_DRIFT"
            if "fingerprint changed" in str(error)
            else "IMAGE_SYMBOL_MODEL_SNAPSHOT_INVALID"
        )
        raise JobHandlerError(
            code,
            (
                "The pinned symbol model inference fingerprint changed."
                if code == "IMAGE_SYMBOL_MODEL_SNAPSHOT_DRIFT"
                else "The pinned symbol model snapshot is invalid."
            ),
        ) from error
    return snapshot


def _board_cell_processing_snapshot(job: Job) -> dict[str, object] | None:
    value = job.input_payload.get("board_cell_processing")
    if value is None:
        return None
    try:
        snapshot = validate_board_cell_processing_snapshot(
            value,
            cell_output_size=_symbol_model_snapshot(job).input_size,
        )
        require_v20_supported_topology(snapshot)
        return snapshot
    except BoardCellRecropSnapshotError as error:
        code = (
            "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED"
            if str(error).startswith("IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED")
            else "IMAGE_BOARD_CELL_PROCESSING_SNAPSHOT_INVALID"
        )
        raise JobHandlerError(
            code,
            (
                "The active v20 geometry adapter supports only 3x5 boards."
                if code == "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED"
                else "The pinned v20 board-cell processing snapshot is invalid."
            ),
        ) from error


def _grid_profile_snapshot(job: Job) -> Mapping[str, object]:
    value = job.input_payload.get("grid_profile")
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise JobHandlerError(
            "IMAGE_GRID_PROFILE_SNAPSHOT_INVALID",
            "The pinned grid profile snapshot is invalid.",
        )
    fingerprint = value.get("inferenceFingerprint")
    profile_payload = value.get("profilePayload")
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or not isinstance(profile_payload, Mapping)
    ):
        raise JobHandlerError(
            "IMAGE_GRID_PROFILE_SNAPSHOT_INVALID",
            "The pinned grid profile payload is incomplete.",
        )
    canonical_value = dict(value)
    canonical_value.pop("inferenceFingerprint", None)
    canonical = json.dumps(
        canonical_value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    if hashlib.sha256(canonical).hexdigest() != fingerprint:
        raise JobHandlerError(
            "IMAGE_GRID_PROFILE_SNAPSHOT_DRIFT",
            "The pinned grid profile fingerprint changed.",
        )
    profile_id = value.get("profileId")
    checksum = value.get("profileChecksumSha256")
    if profile_id is not None:
        profile_canonical = json.dumps(
            profile_payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        if (
            not isinstance(checksum, str)
            or hashlib.sha256(profile_canonical).hexdigest() != checksum
        ):
            raise JobHandlerError(
                "IMAGE_GRID_PROFILE_SNAPSHOT_DRIFT",
                "The pinned grid profile checksum changed.",
            )
    return cast(Mapping[str, object], profile_payload)


def _page_registration_profile_snapshot(job: Job) -> Mapping[str, object]:
    """Read the separately pinned reviewed-page registration profile.

    It lives beside the active grid calibration profile because its provenance
    is the same immutable reviewed cohort, while the geometry it produces is a
    per-target homography rather than a normalized corner offset.
    """

    grid_snapshot = job.input_payload.get("grid_profile")
    if not isinstance(grid_snapshot, Mapping):
        return {}
    profile = grid_snapshot.get("pageRegistrationProfile")
    if profile is None:
        return {}
    if not isinstance(profile, Mapping):
        raise JobHandlerError(
            "IMAGE_PAGE_REGISTRATION_PROFILE_INVALID",
            "The pinned page registration profile is invalid.",
        )
    if profile.get("policy") != PAGE_REGISTRATION_VERSION:
        raise JobHandlerError(
            "IMAGE_PAGE_REGISTRATION_PROFILE_INVALID",
            "The pinned page registration profile has an unsupported policy.",
        )
    anchors = profile.get("anchors")
    if not isinstance(anchors, Sequence) or isinstance(anchors, str | bytes):
        raise JobHandlerError(
            "IMAGE_PAGE_REGISTRATION_PROFILE_INVALID",
            "The pinned page registration profile has no anchor list.",
        )
    return cast(Mapping[str, object], profile)


def _page_geometry_manifest(
    job: Job,
    artifact_root: Path,
    *,
    managed_manifest: ManagedSourceManifest | None = None,
) -> Mapping[str, object]:
    descriptor = job.input_payload.get("page_geometry_manifest")
    if descriptor is None:
        if job.input_payload.get("schema_version") == 6:
            raise JobHandlerError(
                "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_REQUIRED",
                "Managed v0.10 reprocessing requires an exact page-geometry manifest.",
            )
        return {}
    if not isinstance(descriptor, Mapping):
        raise _page_manifest_error(job, "The pinned page geometry manifest descriptor is invalid.")
    checksum = descriptor.get("checksumSha256")
    relative_path = descriptor.get("relativePath")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or not isinstance(relative_path, str)
        or not relative_path.startswith("data/")
    ):
        raise _page_manifest_error(
            job,
            "The pinned page geometry manifest descriptor is incomplete.",
        )
    path = (artifact_root / Path(*PurePosixPath(relative_path).parts)).resolve()
    data_root = (artifact_root / "data").resolve()
    if not path.is_relative_to(data_root):
        raise _page_manifest_error(job, "The pinned page geometry manifest path is unsafe.")
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        if job.input_payload.get("schema_version") == 6:
            raise _page_manifest_error(
                job,
                "The pinned page geometry manifest cannot be read.",
            ) from error
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_UNAVAILABLE",
            "The pinned page geometry manifest cannot be read.",
        ) from error
    if hashlib.sha256(content).hexdigest() != checksum or not isinstance(value, Mapping):
        if job.input_payload.get("schema_version") == 6:
            raise _page_manifest_error(
                job,
                "The pinned page geometry manifest changed after preflight.",
            )
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_DRIFT",
            "The pinned page geometry manifest changed after preflight.",
        )
    entries = value.get("entries")
    if not isinstance(entries, Mapping):
        raise _page_manifest_error(job, "The pinned page geometry manifest has no source entries.")
    if job.input_payload.get("schema_version") == 6:
        if managed_manifest is None:
            raise _page_manifest_error(job, "The managed source manifest is unavailable.")
        _validate_managed_reprocess_page_manifest(job, value, entries, managed_manifest)
    return cast(Mapping[str, object], entries)


def _page_geometry_manifest_checksum(job: Job) -> str:
    descriptor = job.input_payload.get("page_geometry_manifest")
    checksum = descriptor.get("checksumSha256") if isinstance(descriptor, Mapping) else None
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or any(character not in "0123456789abcdef" for character in checksum)
    ):
        raise JobHandlerError(
            "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_REQUIRED"
            if job.input_payload.get("schema_version") == 6
            else "IMAGE_PAGE_GEOMETRY_MANIFEST_REQUIRED",
            "The v0.10 board-cell pipeline requires an exact page-geometry manifest.",
        )
    return checksum


def _geometry_systemic_guard_policy(job: Job) -> Mapping[str, object] | None:
    value = job.input_payload.get("geometry_systemic_guard_policy")
    if value is None:
        return None
    expected: dict[str, object] = {
        "policyVersion": LARGE_IMPORT_GEOMETRY_GUARD_VERSION,
        "minimumSourceCount": LARGE_IMPORT_MIN_SOURCE_COUNT,
        "minimumActiveBoardCount": LARGE_IMPORT_MIN_BOARD_COUNT,
        "sampleSourceLimit": LARGE_IMPORT_GUARD_SAMPLE_LIMIT,
        "minimumFinalCellGridReadyRate": LARGE_IMPORT_MIN_READY_RATE,
        "requireZeroInvariantViolations": True,
    }
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_POLICY_INVALID",
            "The pinned systemic geometry guard policy is invalid.",
        )
    return value


def _validate_managed_reprocess_page_manifest(
    job: Job,
    manifest: Mapping[str, object],
    entries: Mapping[str, object],
    managed_manifest: ManagedSourceManifest,
) -> None:
    source_selection_id = job.input_payload.get("source_selection_id")
    source_manifest_sha256 = job.input_payload.get("source_manifest_sha256")
    if (
        manifest.get("gameId") != str(job.game_id)
        or manifest.get("sourceSelectionId") != str(source_selection_id)
        or manifest.get("sourceManifestChecksumSha256") != source_manifest_sha256
        or manifest.get("sourceCount") != len(managed_manifest.originals)
        or len(entries) != len(managed_manifest.originals)
    ):
        raise _page_manifest_error(job, "The page geometry does not match the managed source.")
    expected = {original.checksum_sha256: original for original in managed_manifest.originals}
    if len(expected) != len(managed_manifest.originals) or set(entries) != set(expected):
        raise _page_manifest_error(job, "The page geometry source inventory is incompatible.")
    counts = {"registered": 0, "review_required": 0, "skipped_human_resolved": 0}
    for checksum, raw in entries.items():
        original = expected[checksum]
        if not isinstance(raw, Mapping):
            raise _page_manifest_error(job, "A page geometry source entry is invalid.")
        status = raw.get("status")
        if status not in counts or raw.get("sourceRelativePath") != original.source_relative_path:
            raise _page_manifest_error(job, "A page geometry source entry changed provenance.")
        counts[cast(str, status)] += 1
    if counts != {
        "registered": manifest.get("registeredSourceCount"),
        "review_required": manifest.get("reviewRequiredSourceCount"),
        "skipped_human_resolved": manifest.get("skippedHumanResolvedSourceCount"),
    }:
        raise _page_manifest_error(job, "The page geometry disposition counts are inconsistent.")


def _page_manifest_error(job: Job, message: str) -> JobHandlerError:
    return JobHandlerError(
        (
            "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE"
            if job.input_payload.get("schema_version") == 6
            else "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID"
        ),
        message,
    )


def _expected_board_count(attested_range: tuple[int, int] | None) -> int:
    if attested_range is None:
        return 9
    start, end = attested_range
    expected_count = end - start + 1
    if start < 1 or not 1 <= expected_count <= 9:
        raise ImagePipelineExecutionError(
            "IMAGE_ATTESTED_SEQUENCE_RANGE_INVALID",
            "The attested filename range must declare between one and nine boards.",
        )
    return expected_count


def _registered_page_geometry(
    entries: Mapping[str, object],
    source_checksum_sha256: str,
    *,
    image_width: int,
    image_height: int,
    expected_board_count: int,
) -> Mapping[str, object] | None:
    raw = entries.get(source_checksum_sha256)
    if not isinstance(raw, Mapping) or raw.get("status") != "registered":
        return None
    quads = raw.get("quads")
    coverages = raw.get("boardRedEdgeCoverages")
    if (
        not isinstance(quads, Sequence)
        or isinstance(quads, str | bytes)
        or len(quads) != expected_board_count
        or not isinstance(coverages, Sequence)
        or isinstance(coverages, str | bytes)
        or len(coverages) != expected_board_count
    ):
        return None
    parsed: list[Quad] = []
    parsed_coverages: list[float] = []
    for quad_payload, coverage in zip(quads, coverages, strict=True):
        quad = _quad_from_payload(quad_payload)
        if (
            quad is None
            or not isinstance(coverage, int | float)
            or isinstance(coverage, bool)
            or not 0.0 <= float(coverage) <= 1.0
        ):
            return None
        if any(
            point.x < 0 or point.x >= image_width or point.y < 0 or point.y >= image_height
            for point in quad
        ):
            return None
        parsed.append(quad)
        parsed_coverages.append(float(coverage))
    if not is_ordered_active_grid(
        tuple(parsed),
        tuple(range(expected_board_count)),
        image_width,
        image_height,
    ):
        return None
    return {
        "anchorSourceChecksumSha256": raw.get("anchorSourceChecksumSha256"),
        "boardRedEdgeCoverages": parsed_coverages,
        "featureCount": raw.get("featureCount"),
        "featuresVersion": raw.get("featuresVersion"),
        "inlierCount": raw.get("inlierCount"),
        "inlierRatio": raw.get("inlierRatio"),
        "manifestEntryChecksumSha256": hashlib.sha256(canonical_json_bytes(raw)).hexdigest(),
        "meanRedEdgeCoverage": raw.get("meanRedEdgeCoverage"),
        "p95ReprojectionError": raw.get("p95ReprojectionError"),
        "quads": parsed,
        "registrationVersion": raw.get("registrationVersion"),
        "thresholdsVersion": raw.get("thresholdsVersion"),
    }


def _registered_geometry_payload(geometry: Mapping[str, object]) -> dict[str, object]:
    quads = cast(Sequence[Quad], geometry["quads"])
    coverages = cast(Sequence[float], geometry["boardRedEdgeCoverages"])
    registration = {
        key: value
        for key, value in geometry.items()
        if key
        not in {
            "boardRedEdgeCoverages",
            "manifestEntryChecksumSha256",
            "quads",
        }
    }
    registration["quads"] = [[point.to_dict() for point in quad] for quad in quads]
    registration["boardRedEdgeCoverages"] = list(coverages)
    return {
        "boards": [
            {
                "confidence": coverages[position],
                "cropValidity": "verified_page_geometry",
                "geometry": {
                    "quad": [point.to_dict() for point in quad],
                    "registration": registration,
                },
                "geometryValidity": "verified",
                "positionIndex": position,
            }
            for position, quad in enumerate(quads)
        ],
        "geometryValidity": "verified",
        "recoveryMode": "pinned_verified_page_registration",
        "registration": registration,
    }


def _quad_from_payload(value: object) -> Quad | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        return None
    points: list[Point] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            return None
        x, y = raw.get("x"), raw.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            return None
        points.append(Point(int(round(x)), int(round(y))))
    return cast(Quad, tuple(points))


def _image_selection_run_id(job: Job) -> str | None:
    value = job.input_payload.get("image_selection_run_id")
    return value if isinstance(value, str) and value else None


def _calibrated_quad(
    quad: Quad,
    *,
    profile: Mapping[str, object],
    image_selection_run_id: str | None,
    position_index: int,
    image_width: int,
    image_height: int,
) -> Quad:
    offsets = _grid_offsets(
        profile,
        image_selection_run_id=image_selection_run_id,
        position_index=position_index,
    )
    if offsets is None:
        return quad
    adjusted = tuple(
        Point(
            max(0, min(image_width - 1, round(point.x + offsets[index][0] * image_width))),
            max(0, min(image_height - 1, round(point.y + offsets[index][1] * image_height))),
        )
        for index, point in enumerate(quad)
    )
    calibrated = cast(Quad, adjusted)
    if (
        abs(
            sum(
                calibrated[index].x * calibrated[(index + 1) % 4].y
                - calibrated[(index + 1) % 4].x * calibrated[index].y
                for index in range(4)
            )
        )
        <= 2
    ):
        return quad
    return calibrated


def _grid_offsets(
    profile: Mapping[str, object],
    *,
    image_selection_run_id: str | None,
    position_index: int,
) -> tuple[tuple[float, float], ...] | None:
    for key, require_run in (("scopes", True), ("positionFallbacks", False)):
        values = profile.get(key)
        if not isinstance(values, Sequence) or isinstance(values, str | bytes):
            continue
        for raw in values:
            if not isinstance(raw, Mapping) or raw.get("positionIndex") != position_index:
                continue
            if require_run and raw.get("imageSelectionRunId") != image_selection_run_id:
                continue
            corners = raw.get("normalizedCornerOffsets")
            if (
                not isinstance(corners, Sequence)
                or isinstance(corners, str | bytes)
                or len(corners) != 4
            ):
                continue
            parsed: list[tuple[float, float]] = []
            for corner in corners:
                if not isinstance(corner, Mapping):
                    break
                x = corner.get("x")
                y = corner.get("y")
                if (
                    not isinstance(x, int | float)
                    or isinstance(x, bool)
                    or not isinstance(y, int | float)
                    or isinstance(y, bool)
                ):
                    break
                parsed.append((float(x), float(y)))
            if len(parsed) == 4:
                return tuple(parsed)
    return None


def _sha_text(value: Mapping[str, object], key: str) -> str:
    item = _text(value, key)
    if len(item) != 64 or any(character not in "0123456789abcdef" for character in item):
        raise ValueError(f"{key} must be SHA-256.")
    return item


def _data_relative_path(value: str) -> str:
    prefix = "data/"
    if not value.startswith(prefix):
        raise JobHandlerError(
            "IMAGE_ORIGINAL_STORAGE_INVALID",
            "Managed originals must remain below the data namespace.",
        )
    return value[len(prefix) :]


def _attested_sequence_payload(
    detections: Sequence[Mapping[str, object]],
    sequence_range: tuple[int, int],
    *,
    allow_sparse: bool = False,
) -> dict[str, object]:
    """Assign row-major numbers from a validated ``seq_start-end`` filename.

    The filename is authoritative when the detector returned the complete
    declared page. Sparse geometry on a full nine-board page keeps its physical
    position; neither path shifts a remaining board to fill a missing slot.
    """

    start, end = sequence_range
    expected_count = end - start + 1
    positions = [_integer(board, "positionIndex") for board in detections]
    exact_declared_page = len(detections) == expected_count and positions == list(
        range(expected_count)
    )
    sparse_full_page = (
        allow_sparse
        and expected_count == 9
        and bool(positions)
        and positions == sorted(set(positions))
        and all(0 <= position < expected_count for position in positions)
    )
    complete = exact_declared_page or sparse_full_page
    boards: list[dict[str, object]] = []
    for board in detections:
        position = _integer(board, "positionIndex")
        number = start + position if complete else None
        boards.append(
            {
                "confidence": 1.0 if complete else 0.0,
                "normalizedNumber": number,
                "ocrNormalizedNumber": None,
                "positionIndex": position,
                "rawText": "" if number is None else str(number),
                "reviewReasons": (
                    [] if complete else ["SEQUENCE_ATTESTED_RANGE_GEOMETRY_REVIEW_REQUIRED"]
                ),
                "attestedRangeEnd": end,
                "attestedRangeStart": start,
                "sequenceSource": "filename",
            }
        )
    return {
        "attestedRangeEnd": end,
        "attestedRangeStart": start,
        "boards": boards,
        "rangeSource": "filename",
    }


def _previous(context: ImageStageContext, stage: str) -> Mapping[str, object]:
    value = context.previous_results.get(stage)
    if value is None:
        raise ImagePipelineExecutionError(
            "IMAGE_PIPELINE_STAGE_DEPENDENCY_MISSING",
            f"The {stage} stage must complete first.",
        )
    return _mapping(value, stage)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _boards(value: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    return tuple(_mapping(item, "board") for item in _sequence(value.get("boards"), "boards"))


def _board_cell_geometry_entry(value: Mapping[str, object]) -> BoardCellGeometryEntry:
    topology = BoardCellTopology(
        rows=_integer(value, "gridRows") if "gridRows" in value else 3,
        columns=_integer(value, "gridColumns") if "gridColumns" in value else 5,
        rules_version_id=cast(str | None, value.get("topologyRulesVersionId")),
    )
    cells = tuple(
        BoardCellQuad(
            row_index=_integer(cell, "rowIndex"),
            column_index=_integer(cell, "columnIndex"),
            quad=_contract_quad(cell.get("quad")),
        )
        for raw_cell in _sequence(value.get("cells"), "cellGeometry.cells")
        for cell in (_mapping(raw_cell, "cellGeometry.cell"),)
    )
    evidence_value = _mapping(value.get("evidence"), "cellGeometry.evidence")
    slots = tuple(
        (
            _integer(slot, "rowIndex"),
            _integer(slot, "columnIndex"),
        )
        for raw_slot in _sequence(evidence_value.get("inlierSlots"), "evidence.inlierSlots")
        for slot in (_mapping(raw_slot, "evidence.inlierSlot"),)
    )
    residual = evidence_value.get("inlierP95ResidualPx")
    if residual is not None and (
        not isinstance(residual, int | float) or isinstance(residual, bool)
    ):
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            "inlierP95ResidualPx must be numeric or null.",
        )
    evidence_kind = evidence_value.get("kind")
    if evidence_kind not in {"automatic", "human_reviewed", "manual_override"}:
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            "The board-cell evidence kind is invalid.",
        )
    evidence = BoardCellGeometryEvidence(
        kind=cast(EvidenceKind, evidence_kind),
        estimator_version=_text(evidence_value, "estimatorVersion"),
        thresholds_version=_text(evidence_value, "thresholdsVersion"),
        locator_version=cast(str | None, evidence_value.get("locatorVersion")),
        homography_version=cast(str | None, evidence_value.get("homographyVersion")),
        candidate_center_count=_integer(evidence_value, "candidateCenterCount"),
        reliable_center_count=_integer(evidence_value, "reliableCenterCount"),
        inlier_count=_integer(evidence_value, "inlierCount"),
        inlier_slots=slots,
        inlier_p95_residual_px=None if residual is None else float(residual),
        decision_checksum_sha256=cast(str | None, evidence_value.get("decisionChecksumSha256")),
    )
    tags = _sequence(value.get("conditionTags"), "cellGeometry.conditionTags")
    return BoardCellGeometryEntry(
        source_order_index=_integer(value, "sourceOrderIndex"),
        image_id=_text(value, "imageId"),
        source_image_checksum_sha256=_text(value, "sourceImageChecksumSha256"),
        source_image_relative_path=_text(value, "sourceImageRelativePath"),
        source_image_width=_integer(value, "sourceImageWidth"),
        source_image_height=_integer(value, "sourceImageHeight"),
        source_group=_text(value, "sourceGroup"),
        condition_tags=tuple(cast(str, item) for item in tags),
        sequence_number=_integer(value, "sequenceNumber"),
        position_index=_integer(value, "positionIndex"),
        lattice_bounds_quad=_contract_quad(value.get("latticeBoundsQuad")),
        cells=cells,
        evidence=evidence,
        topology=topology,
    )


def _contract_quad(value: object) -> BoardCellContractQuad:
    points: list[tuple[float, float]] = []
    for raw in _sequence(value, "quad"):
        point = _mapping(raw, "quad point")
        x = point.get("x")
        y = point.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_STAGE_RESULT_INVALID",
                "A board-cell quad point must be numeric.",
            )
        points.append((float(x), float(y)))
    if len(points) != 4:
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            "A board-cell quad must contain four points.",
        )
    return cast(BoardCellContractQuad, tuple(points))


def _contract_quad_payload(
    value: tuple[tuple[float, float], ...],
) -> list[dict[str, float]]:
    return [{"x": round(x, 4), "y": round(y, 4)} for x, y in value]


def _source_context(
    rgb: NDArray[np.uint8],
    quad: Quad,
) -> tuple[NDArray[np.uint8], dict[str, int]]:
    xs = [point.x for point in quad]
    ys = [point.y for point in quad]
    height, width = rgb.shape[:2]
    board_width = max(xs) - min(xs)
    board_height = max(ys) - min(ys)
    left = max(0, int(np.floor(min(xs) - board_width * 0.12)))
    right = min(width, int(np.ceil(max(xs) + board_width * 0.12)) + 1)
    top = max(0, int(np.floor(min(ys) - board_height * 0.12)))
    bottom = min(height, int(np.ceil(max(ys) + board_height * 0.50)) + 1)
    bounds = {
        "height": max(1, bottom - top),
        "width": max(1, right - left),
        "x": left,
        "y": top,
    }
    return rgb[top:bottom, left:right].copy(), bounds


def _pending_reason(estimator_reason: str) -> BoardCellGeometryPendingReason:
    if "SOURCE" in estimator_reason and (
        "UNAVAILABLE" in estimator_reason or "DECODE" in estimator_reason
    ):
        return BoardCellGeometryPendingReason.SOURCE_UNAVAILABLE
    if "INSUFFICIENT" in estimator_reason and (
        "CANDIDATE" in estimator_reason or "CENTER" in estimator_reason
    ):
        return BoardCellGeometryPendingReason.INSUFFICIENT_CENTERS
    if (
        "RESIDUAL" in estimator_reason
        or "RANSAC" in estimator_reason
        or "EVIDENCE" in estimator_reason
    ):
        return BoardCellGeometryPendingReason.RESIDUAL_TOO_HIGH
    return BoardCellGeometryPendingReason.INCOMPLETE_LATTICE


def _text(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            f"{key} must be non-empty text.",
        )
    return item


def _integer(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            f"{key} must be a non-negative integer.",
        )
    return item


def _number(value: Mapping[str, object], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, int | float) or isinstance(item, bool):
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            f"{key} must be numeric.",
        )
    return float(item)


def _quad(geometry: Mapping[str, object]) -> Quad:
    points = _sequence(geometry.get("quad"), "geometry.quad")
    if len(points) != 4:
        raise ImagePipelineExecutionError(
            "IMAGE_STAGE_RESULT_INVALID",
            "geometry.quad must contain four points.",
        )
    parsed: list[Point] = []
    for value in points:
        point = _mapping(value, "geometry point")
        parsed.append(Point(_integer(point, "x"), _integer(point, "y")))
    return cast(Quad, tuple(parsed))


def _source_quad(value: object) -> SourceQuad:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        raise ImagePipelineExecutionError(
            "IMAGE_STRUCTURED_GEOMETRY_QUAD_INVALID",
            "Structured geometry requires four source points.",
        )
    points: list[SourcePoint] = []
    for raw in value:
        point = _mapping(raw, "structured geometry point")
        x = point.get("x")
        y = point.get("y")
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, int | float)
            or not isinstance(y, int | float)
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_STRUCTURED_GEOMETRY_QUAD_INVALID",
                "Structured geometry points must be finite numbers.",
            )
        points.append(SourcePoint(float(x), float(y)))
    return SourceQuad(
        cast(tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint], tuple(points))
    )


__all__ = ["ProductionImageImportWorkflow", "ProductionImageStageAdapterSuite"]
