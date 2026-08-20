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
from typing import cast
from uuid import UUID

import cv2
import numpy as np
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

from .geometry import ClassicalPageBoardDetector, Point, Quad
from .orchestration import ImageBatchHandler, ImageFileRegistration
from .orchestration_store import SqlAlchemyImageBatchStore
from .page_geometry_registration import (
    PAGE_REGISTRATION_VERSION,
    VerifiedPageRegistrar,
    is_complete_ordered_grid,
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
from .source_ingestion import ImageSourceIngestionHandler, ManagedOriginal, ManagedOriginalStore
from .symbol_model_release import build_symbol_predictions
from .symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError

NORMALIZATION_ADAPTER_VERSION = "image-normalization-v1"
DETECTION_ADAPTER_VERSION = "page-board-detector-v4-verified-registration-v1"
CROP_ADAPTER_VERSION = SOURCE_DIRECT_CROPPER_VERSION
SYMBOL_ADAPTER_VERSION = "local-symbol-onnx-runtime-v1"
SEQUENCE_ADAPTER_VERSION = "sequence-number-ocr-v2-page-continuity-v1"


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

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        manifest = self._original_store.load_or_create_manifest(
            job,
            source_directory=_source_directory(job),
        )
        source_count = len(manifest.originals)
        source_context = _ProgressWindowContext(
            context,
            current_offset=0,
            total=source_count * 2,
            stage_prefix="image_source",
        )
        manifest = self._source_handler.ingest(
            cast(JobExecutionContext, source_context),
            job,
        )
        pipeline_originals = _filter_canonical_originals(manifest.originals, job)
        if not pipeline_originals:
            context.checkpoint(
                checkpoint_payload={
                    "checkpoint_kind": "image-canonical-skip-v1",
                    "skipped_source_count": len(manifest.originals),
                    "schema_version": 1,
                },
                stage="image_canonical_skip",
                current=source_count * 2,
                total=source_count * 2,
                success_count=source_count,
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
            page_geometry_manifest=_page_geometry_manifest(job, self._artifact_root),
            image_selection_run_id=_image_selection_run_id(job),
            attested_sequence_ranges=attested_sequence_ranges,
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
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._artifacts = _ManagedImageArtifacts(artifact_root)
        self._repository_root = repository_root
        self._symbol_model_snapshot = symbol_model or bootstrap_symbol_model_snapshot()
        self._grid_profile = dict(grid_profile or {})
        self._page_registration_profile = dict(page_registration_profile or {})
        self._page_geometry_manifest = dict(page_geometry_manifest or {})
        self._image_selection_run_id = image_selection_run_id
        self._attested_sequence_ranges = dict(attested_sequence_ranges or {})
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
        self._ocr: PaddleSequenceNumberRecognizer | None = None
        self._symbol_model: LocalSymbolOnnxAdapter | None = None

    def adapters(self) -> tuple[VersionedImageStageAdapter, ...]:
        return cast(
            tuple[VersionedImageStageAdapter, ...],
            (
                FunctionImageStageAdapter("discovery", "image-discovery-v1", self.discovery),
                FunctionImageStageAdapter(
                    "normalization",
                    NORMALIZATION_ADAPTER_VERSION,
                    self.normalization,
                ),
                FunctionImageStageAdapter(
                    "board_detection",
                    DETECTION_ADAPTER_VERSION,
                    self.board_detection,
                ),
                FunctionImageStageAdapter(
                    "board_crops",
                    CROP_ADAPTER_VERSION,
                    self.board_crops,
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
            ),
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
                oriented = ImageOps.exif_transpose(image).convert("RGB")
                output = io.BytesIO()
                oriented.save(output, format="PNG", optimize=False, compress_level=6)
                content = output.getvalue()
                width, height = oriented.size
        except (OSError, UnidentifiedImageError) as error:
            raise ImagePipelineExecutionError(
                "IMAGE_NORMALIZATION_DECODE_FAILED",
                "The managed source JPEG cannot be normalized.",
            ) from error
        relative = (
            PurePosixPath(
                "working",
                NORMALIZATION_ADAPTER_VERSION,
                context.file_execution_key[:2],
                context.file_execution_key,
            )
            / "normalized.png"
        ).as_posix()
        checksum = self._artifacts.write_immutable(relative, content)
        return {
            "height": height,
            "normalizedChecksumSha256": checksum,
            "normalizedRelativePath": relative,
            "width": width,
        }

    def board_detection(self, context: ImageStageContext) -> Mapping[str, object]:
        normalized = _previous(context, "normalization")
        rgb = self._artifacts.load_rgb(_text(normalized, "normalizedRelativePath"))
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

    def board_crops(self, context: ImageStageContext) -> Mapping[str, object]:
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
        rgb = self._artifacts.load_rgb(_text(normalized, "normalizedRelativePath"))
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

    def sequence_ocr(self, context: ImageStageContext) -> Mapping[str, object]:
        normalized = _previous(context, "normalization")
        detections = _boards(_previous(context, "board_detection"))
        if context.attested_sequence_range is not None:
            return _attested_sequence_payload(
                detections,
                context.attested_sequence_range,
            )
        rgb = self._artifacts.load_rgb(_text(normalized, "normalizedRelativePath"))
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
        if not tensors:
            raise ImagePipelineExecutionError(
                "IMAGE_SYMBOL_INPUT_EMPTY",
                "The image pipeline produced no cell crops for symbol inference.",
            )
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
        iteration_value = value.get("iterationId")
        iteration_id = None if iteration_value is None else UUID(str(iteration_value))
        storage_root = SymbolModelStorageRoot(_text(value, "storageRoot"))
        class_values = _sequence(value.get("classCodes"), "symbol_model.classCodes")
        if not class_values or not all(isinstance(item, str) and item for item in class_values):
            raise ValueError("Invalid class catalog.")
        class_codes = tuple(cast(Sequence[str], class_values))
        if len(set(class_codes)) != len(class_codes):
            raise ValueError("Duplicate class code.")
        input_size = _integer(value, "inputSize")
        temperature_value = value.get("temperature")
        if (
            input_size < 16
            or isinstance(temperature_value, bool)
            or not isinstance(temperature_value, int | float)
            or float(temperature_value) <= 0
        ):
            raise ValueError("Invalid model runtime values.")
        snapshot = SymbolModelJobSnapshot(
            iteration_id=iteration_id,
            model_version=_text(value, "modelVersion"),
            manifest_checksum_sha256=_sha_text(value, "manifestChecksumSha256"),
            onnx_checksum_sha256=_sha_text(value, "onnxChecksumSha256"),
            onnx_relative_path=_text(value, "onnxRelativePath"),
            storage_root=storage_root,
            class_codes=class_codes,
            input_size=input_size,
            temperature=float(temperature_value),
        )
    except (TypeError, ValueError, ImagePipelineExecutionError) as error:
        raise JobHandlerError(
            "IMAGE_SYMBOL_MODEL_SNAPSHOT_INVALID",
            "The pinned symbol model snapshot is invalid.",
        ) from error
    if value.get("inferenceFingerprint") != snapshot.inference_fingerprint:
        raise JobHandlerError(
            "IMAGE_SYMBOL_MODEL_SNAPSHOT_DRIFT",
            "The pinned symbol model inference fingerprint changed.",
        )
    return snapshot


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
) -> dict[str, object]:
    """Assign row-major numbers from a validated ``seq_start-end`` filename.

    The filename is authoritative only when the detector returned exactly the
    declared number of boards. A partial grid remains reviewable, but no
    remaining board is shifted to fill the missing position.
    """

    start, end = sequence_range
    expected_count = end - start + 1
    complete = len(detections) == expected_count and all(
        _integer(board, "positionIndex") == index for index, board in enumerate(detections)
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
