"""Production image import: managed originals through review-ready projections."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Protocol, cast

import cv2
import numpy as np
from game_predictor_api.application.board_cell_geometry_pending import (
    ManagedBoardCellProcessingManifestStore,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryPendingReason,
)
from game_predictor_api.domain.jobs import Job
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
    bootstrap_symbol_model_snapshot,
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
from .orchestration import ImageBatchHandler, ImageFileRegistration
from .orchestration_store import SqlAlchemyImageBatchStore
from .page_geometry_registration import (
    PAGE_REGISTRATION_VERSION,
    VerifiedPageRegistrar,
    is_complete_ordered_grid,
)
from .pipeline_contract import CURRENT_NORMALIZATION_ADAPTER_VERSION
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
from .source_ingestion import ImageSourceIngestionHandler, ManagedOriginal, ManagedOriginalStore
from .symbol_model_release import build_symbol_predictions
from .symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError

NORMALIZATION_ADAPTER_VERSION = CURRENT_NORMALIZATION_ADAPTER_VERSION
LEGACY_NORMALIZATION_ADAPTER_VERSION = "image-normalization-v1"
DETECTION_ADAPTER_VERSION = "page-board-detector-v4-verified-registration-v1"
CROP_ADAPTER_VERSION = SOURCE_DIRECT_CROPPER_VERSION
SYMBOL_ADAPTER_VERSION = "local-symbol-onnx-runtime-v1"
SEQUENCE_ADAPTER_VERSION = "sequence-number-ocr-v2-page-continuity-v1"


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
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._repository_root = repository_root.resolve()
        self._original_store = ManagedOriginalStore(self._artifact_root)
        self._source_handler = ImageSourceIngestionHandler(self._original_store)
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
        geometry_manifest = _page_geometry_manifest(job, self._artifact_root)
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
                current=0,
                total=0,
                success_count=0,
                failure_count=0,
                review_count=0,
            )
            return
        source_context = _ProgressWindowContext(
            context,
            current_offset=0,
            total=source_count * 2,
            stage_prefix="image_source",
        )
        manifest = self._source_handler.ingest(
            cast(JobExecutionContext, source_context),
            job,
            originals=pipeline_originals,
        )
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
        self._batch_store.register_files(
            job.id,
            registrations=registrations,
            pipeline_fingerprint=_pipeline_fingerprint(job),
            registered_at=context.now(),
        )
        board_cell_processing = _board_cell_processing_snapshot(job)
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
        )
        pipeline_context = _ProgressWindowContext(
            context,
            current_offset=source_count,
            total=source_count * 2,
            stage_prefix="image_pipeline",
            success_offset=source_count,
        )
        pipeline(cast(JobExecutionContext, pipeline_context), job)


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
        success_offset: int = 0,
    ) -> None:
        self._context = context
        self._current_offset = current_offset
        self._total = total
        self._stage_prefix = stage_prefix
        self._success_offset = success_offset

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
        self._context.checkpoint(
            checkpoint_payload={
                **checkpoint_payload,
                "workflow_phase": self._stage_prefix,
            },
            stage=f"{self._stage_prefix}:{stage}",
            current=max(previous.progress_current, self._current_offset + current),
            total=max(previous.progress_total or 0, self._total),
            success_count=max(
                previous.success_count,
                self._success_offset + success_count,
            ),
            failure_count=max(previous.failure_count, failure_count),
            review_count=max(previous.review_count, review_count),
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
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._artifacts = _ManagedImageArtifacts(artifact_root)
        self._normalized_images = _ExecutionScopedNormalizedImageLoader(self._artifacts)
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
                DETECTION_ADAPTER_VERSION,
                self.board_detection,
            ),
        ]
        if self._board_cell_processing:
            stages.append(
                FunctionImageStageAdapter(
                    "board_cell_geometry",
                    BOARD_CELL_PROCESSING_VERSION,
                    self.board_cell_geometry,
                    self.persist_board_cell_geometry_deferrals,
                )
            )
        stages.extend(
            [
                FunctionImageStageAdapter(
                    "board_crops",
                    V19_CROPPER_VERSION if self._board_cell_processing else CROP_ADAPTER_VERSION,
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
        normalized = _previous(context, "normalization")
        rgb = self._normalized_images.load(context, normalized)
        pinned = _registered_page_geometry(
            self._page_geometry_manifest,
            context.source_checksum_sha256,
            image_width=int(rgb.shape[1]),
            image_height=int(rgb.shape[0]),
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

    def board_crops(self, context: ImageStageContext) -> Mapping[str, object]:
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
        cropped_boards = _boards(_previous(context, "board_crops"))
        cell_metadata: list[tuple[int, Mapping[str, object]]] = []
        tensors: list[NDArray[np.float32]] = []
        for board in cropped_boards:
            position = _integer(board, "positionIndex")
            cells = _sequence(board.get("cells"), "cells")
            for value in cells:
                cell = _mapping(value, "cell")
                rgb = self._artifacts.load_rgb(_text(cell, "cropRelativePath"))
                input_size = self._symbol_model_snapshot.input_size
                model_rgb = (
                    rgb
                    if rgb.shape[:2] == (input_size, input_size)
                    else cv2.resize(
                        rgb,
                        (input_size, input_size),
                        interpolation=cv2.INTER_AREA,
                    )
                )
                normalized = model_rgb.astype(np.float32).transpose(2, 0, 1) / 255.0
                tensors.append(((normalized - 0.5) / 0.5).astype(np.float32))
                cell_metadata.append((position, cell))
        if not tensors and not self._board_cell_processing:
            raise ImagePipelineExecutionError(
                "IMAGE_SYMBOL_INPUT_EMPTY",
                "The image pipeline produced no cell crops for symbol inference.",
            )
        if tensors:
            try:
                inference = self._symbol_adapter().infer(np.stack(tensors).astype(np.float32))
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
        return {
            "boards": [
                {
                    "cells": by_position[position],
                    "positionIndex": position,
                }
                for position in sorted(by_position)
            ],
            "modelIterationId": (
                None
                if self._symbol_model_snapshot.iteration_id is None
                else str(self._symbol_model_snapshot.iteration_id)
            ),
            "modelManifestChecksumSha256": (self._symbol_model_snapshot.manifest_checksum_sha256),
            "modelVersion": self._symbol_model_snapshot.model_version,
            "temperatureApplied": max(0.50, self._symbol_model_snapshot.temperature),
        }

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
    return actions.get(value, "none")


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


def _page_geometry_manifest(job: Job, artifact_root: Path) -> Mapping[str, object]:
    descriptor = job.input_payload.get("page_geometry_manifest")
    if descriptor is None:
        return {}
    if not isinstance(descriptor, Mapping):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The pinned page geometry manifest descriptor is invalid.",
        )
    checksum = descriptor.get("checksumSha256")
    relative_path = descriptor.get("relativePath")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or not isinstance(relative_path, str)
        or not relative_path.startswith("data/")
    ):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The pinned page geometry manifest descriptor is incomplete.",
        )
    path = (artifact_root / Path(*PurePosixPath(relative_path).parts)).resolve()
    data_root = (artifact_root / "data").resolve()
    if not path.is_relative_to(data_root):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The pinned page geometry manifest path is unsafe.",
        )
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_UNAVAILABLE",
            "The pinned page geometry manifest cannot be read.",
        ) from error
    if hashlib.sha256(content).hexdigest() != checksum or not isinstance(value, Mapping):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_DRIFT",
            "The pinned page geometry manifest changed after preflight.",
        )
    entries = value.get("entries")
    if not isinstance(entries, Mapping):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The pinned page geometry manifest has no source entries.",
        )
    return cast(Mapping[str, object], entries)


def _registered_page_geometry(
    entries: Mapping[str, object],
    source_checksum_sha256: str,
    *,
    image_width: int,
    image_height: int,
) -> Mapping[str, object] | None:
    raw = entries.get(source_checksum_sha256)
    if not isinstance(raw, Mapping) or raw.get("status") != "registered":
        return None
    quads = raw.get("quads")
    coverages = raw.get("boardRedEdgeCoverages")
    if (
        not isinstance(quads, Sequence)
        or isinstance(quads, str | bytes)
        or len(quads) != 9
        or not isinstance(coverages, Sequence)
        or isinstance(coverages, str | bytes)
        or len(coverages) != 9
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
    if not is_complete_ordered_grid(tuple(parsed), image_width, image_height):
        return None
    return {
        "anchorSourceChecksumSha256": raw.get("anchorSourceChecksumSha256"),
        "boardRedEdgeCoverages": parsed_coverages,
        "featureCount": raw.get("featureCount"),
        "featuresVersion": raw.get("featuresVersion"),
        "inlierCount": raw.get("inlierCount"),
        "inlierRatio": raw.get("inlierRatio"),
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
        if key not in {"quads", "boardRedEdgeCoverages"}
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

    The filename is authoritative only when the detector returned exactly the
    declared number of boards. A partial grid remains reviewable, but no
    remaining board is shifted to fill the missing position.
    """

    start, end = sequence_range
    expected_count = end - start + 1
    positions = [_integer(board, "positionIndex") for board in detections]
    complete = (
        expected_count == 9
        and positions == sorted(set(positions))
        and all(position < expected_count for position in positions)
        if allow_sparse
        else len(detections) == expected_count
        and all(position == index for index, position in enumerate(positions))
    )
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


__all__ = ["ProductionImageImportWorkflow", "ProductionImageStageAdapterSuite"]
