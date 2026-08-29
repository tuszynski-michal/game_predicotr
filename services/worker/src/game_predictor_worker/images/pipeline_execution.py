"""Composable execution of the versioned image pipeline into review staging."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Never, Protocol, cast
from uuid import UUID

from game_predictor_worker.jobs.runtime import JobHandlerError

from .discovery import (
    DISCOVERY_VERSION,
    SourceImage,
    SourceManifest,
    discover_images,
)
from .orchestration import (
    ImageBatchCandidate,
    ImageBatchHandler,
    ImageBatchStore,
    ImageFileExecution,
    ImageFileRegistration,
    ImageStageExecutionResult,
    ImageStageExecutor,
)
from .pipeline_contract import PIPELINE_STAGES, canonical_json_bytes

AUTOMATED_IMAGE_STAGES = PIPELINE_STAGES[:6]
BOARD_CELL_GEOMETRY_STAGE = "board_cell_geometry"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
BOARD_ROWS = 3
BOARD_COLUMNS = 5
BOARD_CELL_COUNT = BOARD_ROWS * BOARD_COLUMNS
IMAGE_REGISTRATION_BATCH_SIZE = 500


class ImagePipelineExecutionError(JobHandlerError):
    """Stable integration error raised before persistence."""


@dataclass(frozen=True, slots=True)
class ImageStageContext:
    job_id: UUID
    file_execution_key: str
    source_checksum_sha256: str
    source_relative_path: str
    pipeline_fingerprint: str
    previous_results: Mapping[str, Mapping[str, object]]
    attested_sequence_range: tuple[int, int] | None = None


class VersionedImageStageAdapter(Protocol):
    """Narrow port implemented by the accepted M5/M6 adapters."""

    stage: str
    version: str

    def execute(self, context: ImageStageContext) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class FunctionImageStageAdapter:
    """Bind an accepted per-image adapter function to a manifest stage."""

    stage: str
    version: str
    runner: Callable[[ImageStageContext], Mapping[str, object]]
    replayer: Callable[[ImageStageContext, Mapping[str, object]], None] | None = None

    def execute(self, context: ImageStageContext) -> Mapping[str, object]:
        return self.runner(context)

    def replay(self, context: ImageStageContext, payload: Mapping[str, object]) -> None:
        if self.replayer is not None:
            self.replayer(context, payload)


class ImageBatchRegistrar(Protocol):
    def register_file(
        self,
        job_id: UUID,
        *,
        source_checksum_sha256: str,
        pipeline_fingerprint: str,
        source_relative_path: str,
        order_index: int,
        registered_at: datetime,
    ) -> ImageFileExecution: ...

    def register_files(
        self,
        job_id: UUID,
        *,
        registrations: Sequence[ImageFileRegistration],
        pipeline_fingerprint: str,
        registered_at: datetime,
    ) -> None: ...


class ImageDirectoryBatchSeeder:
    """Discover one immutable directory manifest and register unique images."""

    def __init__(self, registrar: ImageBatchRegistrar) -> None:
        self._registrar = registrar

    def seed(
        self,
        job_id: UUID,
        *,
        source_root: Path,
        pipeline_fingerprint: str,
        registered_at: datetime,
    ) -> SourceManifest:
        manifest = discover_images(source_root)
        if manifest.issues:
            raise ImagePipelineExecutionError(
                "IMAGE_DISCOVERY_REQUIRES_REVIEW",
                "Image discovery found unsupported or unreadable image sources.",
            )
        if not manifest.images:
            raise ImagePipelineExecutionError(
                "IMAGE_BATCH_EMPTY",
                "The image directory contains no supported source images.",
            )
        registrations: list[ImageFileRegistration] = []
        for order_index, image in enumerate(manifest.images):
            registrations.append(
                ImageFileRegistration(
                    source_checksum_sha256=image.checksum_sha256,
                    source_relative_path=image.files[0].relative_path,
                    order_index=order_index,
                )
            )
            if len(registrations) == IMAGE_REGISTRATION_BATCH_SIZE:
                self._registrar.register_files(
                    job_id,
                    registrations=registrations,
                    pipeline_fingerprint=pipeline_fingerprint,
                    registered_at=registered_at,
                )
                registrations = []
        if registrations:
            self._registrar.register_files(
                job_id,
                registrations=registrations,
                pipeline_fingerprint=pipeline_fingerprint,
                registered_at=registered_at,
            )
        return manifest


class ManifestDiscoveryStageAdapter:
    """Replay attested discovery metadata without rescanning at every stage."""

    stage = "discovery"
    version = DISCOVERY_VERSION

    def __init__(self, manifest: SourceManifest) -> None:
        self._images = {image.checksum_sha256: image for image in manifest.images}

    def execute(self, context: ImageStageContext) -> Mapping[str, object]:
        image = self._images.get(context.source_checksum_sha256)
        if image is None:
            raise ImagePipelineExecutionError(
                "IMAGE_DISCOVERY_SOURCE_NOT_ATTESTED",
                "The source checksum is absent from the discovery manifest.",
            )
        _require_manifest_path(image, context.source_relative_path)
        return {
            "height": image.height,
            "sourceChecksumSha256": image.checksum_sha256,
            "sourceRelativePath": context.source_relative_path,
            "width": image.width,
        }


@dataclass(frozen=True, slots=True)
class StoredImageStageResult:
    adapter_version: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ContinuityIssue:
    code: str
    sequence_number: int | None
    occurrence_count: int


class ImagePipelineProjectionStore(Protocol):
    def stage_results(
        self,
        file_execution_key: str,
    ) -> Mapping[str, StoredImageStageResult]: ...

    def save_stage_result(
        self,
        candidate: ImageBatchCandidate,
        *,
        stage: str,
        adapter_version: str,
        payload: Mapping[str, object],
    ) -> StoredImageStageResult: ...

    def project_source(
        self,
        candidate: ImageBatchCandidate,
        *,
        discovery: Mapping[str, object],
    ) -> None: ...

    def project_recognition(
        self,
        candidate: ImageBatchCandidate,
        *,
        stage_results: Mapping[str, StoredImageStageResult],
    ) -> None: ...

    def pending_review_count(self, candidate: ImageBatchCandidate) -> int: ...

    def materialize_resolved_staging(self, candidate: ImageBatchCandidate) -> int: ...

    def reopen_continuity_conflicts(
        self,
        candidate: ImageBatchCandidate,
    ) -> tuple[ContinuityIssue, ...]: ...


class ImagePipelineStageExecutor(ImageStageExecutor):
    """Run one immutable adapter stage and project review/staging state."""

    def __init__(
        self,
        store: ImagePipelineProjectionStore,
        adapters: Sequence[VersionedImageStageAdapter],
        *,
        attested_sequence_ranges: Mapping[str, tuple[int, int]] | None = None,
    ) -> None:
        self._store = store
        self._adapters = _adapter_registry(adapters)
        self._result_stages = frozenset(self._adapters)
        self._attested_sequence_ranges = dict(attested_sequence_ranges or {})

    def rehydrate(self, candidate: ImageBatchCandidate) -> None:
        """Rebuild only job-local projections from immutable shared stage results."""

        results = dict(self._store.stage_results(candidate.execution.file_execution_key))
        discovery = results.get("discovery")
        if discovery is not None:
            self._store.project_source(candidate, discovery=discovery.payload)
        for stage in (BOARD_CELL_GEOMETRY_STAGE, "board_crops"):
            stored = results.get(stage)
            adapter = self._adapters.get(stage)
            replay = None if adapter is None else getattr(adapter, "replay", None)
            if stored is not None and callable(replay):
                replay(
                    ImageStageContext(
                        job_id=_candidate_job_id(candidate),
                        file_execution_key=candidate.execution.file_execution_key,
                        source_checksum_sha256=candidate.execution.source_checksum_sha256,
                        source_relative_path=candidate.source_relative_path,
                        pipeline_fingerprint=candidate.execution.pipeline_fingerprint,
                        previous_results={
                            key: value.payload for key, value in results.items() if key != stage
                        },
                        attested_sequence_range=self._attested_sequence_ranges.get(
                            candidate.execution.source_checksum_sha256
                        ),
                    ),
                    stored.payload,
                )
        required = {
            "board_detection",
            "board_crops",
            "sequence_ocr",
            "symbol_inference",
        }
        if required.issubset(results):
            self._store.project_recognition(candidate, stage_results=results)

    def execute_stage(
        self,
        candidate: ImageBatchCandidate,
        stage: str,
    ) -> ImageStageExecutionResult:
        job_id = candidate.job_id
        if job_id is None or candidate.lease_token is None or candidate.executed_at is None:
            raise ImagePipelineExecutionError(
                "IMAGE_PIPELINE_EXECUTION_CONTEXT_MISSING",
                "A persisted image stage requires job, lease and timestamp context.",
            )
        if stage in AUTOMATED_IMAGE_STAGES:
            if stage == "board_crops" and BOARD_CELL_GEOMETRY_STAGE in self._adapters:
                self._execute_automated(candidate, BOARD_CELL_GEOMETRY_STAGE, job_id)
            return self._execute_automated(candidate, stage, job_id)
        if stage == "manual_review":
            if self._store.pending_review_count(candidate):
                return ImageStageExecutionResult.WAITING_FOR_REVIEW
            self._store.materialize_resolved_staging(candidate)
            return ImageStageExecutionResult.COMPLETED
        if stage == "validation":
            issues = self._store.reopen_continuity_conflicts(candidate)
            if issues:
                raise ImagePipelineExecutionError(
                    "IMAGE_SEQUENCE_REVIEW_REOPENED",
                    "Sequence conflicts were returned to operational review.",
                )
            return ImageStageExecutionResult.COMPLETED
        raise ImagePipelineExecutionError(
            "IMAGE_PIPELINE_STAGE_UNSUPPORTED",
            f"Image stage {stage!r} is not supported by the pipeline executor.",
        )

    def _execute_automated(
        self,
        candidate: ImageBatchCandidate,
        stage: str,
        job_id: UUID,
    ) -> ImageStageExecutionResult:
        existing = dict(self._store.stage_results(candidate.execution.file_execution_key))
        adapter = self._adapters[stage]
        stored = existing.get(stage)
        if stored is None:
            context = ImageStageContext(
                job_id=job_id,
                file_execution_key=candidate.execution.file_execution_key,
                source_checksum_sha256=candidate.execution.source_checksum_sha256,
                source_relative_path=candidate.source_relative_path,
                pipeline_fingerprint=candidate.execution.pipeline_fingerprint,
                previous_results={
                    key: value.payload
                    for key, value in existing.items()
                    if key in self._result_stages
                },
                attested_sequence_range=self._attested_sequence_ranges.get(
                    candidate.execution.source_checksum_sha256
                ),
            )
            payload = validate_stage_payload(stage, adapter.execute(context), context)
            stored = self._store.save_stage_result(
                candidate,
                stage=stage,
                adapter_version=adapter.version,
                payload=payload,
            )
            existing[stage] = stored
        else:
            if stored.adapter_version != adapter.version:
                raise ImagePipelineExecutionError(
                    "IMAGE_STAGE_ADAPTER_VERSION_CONFLICT",
                    "Stored image stage uses a different adapter version.",
                )
            validate_stage_payload(
                stage,
                stored.payload,
                ImageStageContext(
                    job_id=job_id,
                    file_execution_key=candidate.execution.file_execution_key,
                    source_checksum_sha256=candidate.execution.source_checksum_sha256,
                    source_relative_path=candidate.source_relative_path,
                    pipeline_fingerprint=candidate.execution.pipeline_fingerprint,
                    previous_results={
                        key: value.payload for key, value in existing.items() if key != stage
                    },
                    attested_sequence_range=self._attested_sequence_ranges.get(
                        candidate.execution.source_checksum_sha256
                    ),
                ),
            )
        replay = getattr(adapter, "replay", None)
        if callable(replay):
            replay(
                ImageStageContext(
                    job_id=job_id,
                    file_execution_key=candidate.execution.file_execution_key,
                    source_checksum_sha256=candidate.execution.source_checksum_sha256,
                    source_relative_path=candidate.source_relative_path,
                    pipeline_fingerprint=candidate.execution.pipeline_fingerprint,
                    previous_results={
                        key: value.payload for key, value in existing.items() if key != stage
                    },
                    attested_sequence_range=self._attested_sequence_ranges.get(
                        candidate.execution.source_checksum_sha256
                    ),
                ),
                stored.payload,
            )
        if stage == "discovery":
            self._store.project_source(candidate, discovery=stored.payload)
        if stage == "symbol_inference":
            self._store.project_recognition(candidate, stage_results=existing)
        return ImageStageExecutionResult.COMPLETED


def build_image_pipeline_handler(
    batch_store: ImageBatchStore,
    projection_store: ImagePipelineProjectionStore,
    adapters: Sequence[VersionedImageStageAdapter],
) -> ImageBatchHandler:
    """Connect the durable batch orchestrator to the versioned adapter composer."""

    return ImageBatchHandler(
        batch_store,
        ImagePipelineStageExecutor(projection_store, adapters),
    )


def validate_stage_payload(
    stage: str,
    value: Mapping[str, object],
    context: ImageStageContext,
) -> dict[str, object]:
    payload = dict(value)
    if stage == "discovery":
        _positive_integer(payload.get("width"), "discovery.width")
        _positive_integer(payload.get("height"), "discovery.height")
        _matching_text(
            payload.get("sourceChecksumSha256"),
            context.source_checksum_sha256,
            "discovery.sourceChecksumSha256",
        )
        _matching_text(
            payload.get("sourceRelativePath"),
            context.source_relative_path,
            "discovery.sourceRelativePath",
        )
    elif stage == "normalization":
        if "normalizedRelativePath" in payload:
            _sha256(payload.get("normalizedChecksumSha256"), "normalization checksum")
            _relative_path(payload.get("normalizedRelativePath"), "normalization path")
        else:
            _sha256(
                payload.get("normalizedPixelChecksumSha256"),
                "normalization pixel checksum",
            )
            _matching_text(
                payload.get("sourceChecksumSha256"),
                context.source_checksum_sha256,
                "normalization.sourceChecksumSha256",
            )
            _matching_text(
                payload.get("sourceRelativePath"),
                context.source_relative_path,
                "normalization.sourceRelativePath",
            )
            _positive_integer(payload.get("sourceWidth"), "normalization.sourceWidth")
            _positive_integer(payload.get("sourceHeight"), "normalization.sourceHeight")
        _positive_integer(payload.get("width"), "normalization.width")
        _positive_integer(payload.get("height"), "normalization.height")
    elif stage == "board_detection":
        _boards(payload, require_cells=False, require_sequence=False, require_symbols=False)
    elif stage == BOARD_CELL_GEOMETRY_STAGE:
        _board_cell_geometry(payload, context)
    elif stage == "board_crops":
        boards = _boards(
            payload,
            require_cells=True,
            require_sequence=False,
            require_symbols=False,
            allow_empty=BOARD_CELL_GEOMETRY_STAGE in context.previous_results,
            allow_sparse=BOARD_CELL_GEOMETRY_STAGE in context.previous_results,
        )
        previous_stage = (
            BOARD_CELL_GEOMETRY_STAGE
            if BOARD_CELL_GEOMETRY_STAGE in context.previous_results
            else "board_detection"
        )
        if previous_stage == BOARD_CELL_GEOMETRY_STAGE:
            _v20_crop_positions(context, payload, boards)
        else:
            _same_positions(context, previous_stage, boards)
    elif stage == "sequence_ocr":
        boards = _boards(
            payload,
            require_cells=False,
            require_sequence=True,
            require_symbols=False,
            allow_empty=BOARD_CELL_GEOMETRY_STAGE in context.previous_results,
            allow_sparse=BOARD_CELL_GEOMETRY_STAGE in context.previous_results,
        )
        previous_stage = (
            "board_crops"
            if BOARD_CELL_GEOMETRY_STAGE in context.previous_results
            else "board_detection"
        )
        _same_positions(context, previous_stage, boards)
    elif stage == "symbol_inference":
        boards = _boards(
            payload,
            require_cells=False,
            require_sequence=False,
            require_symbols=True,
            allow_empty=BOARD_CELL_GEOMETRY_STAGE in context.previous_results,
            allow_sparse=BOARD_CELL_GEOMETRY_STAGE in context.previous_results,
        )
        _same_positions(context, "board_crops", boards)
        model_version = payload.get("modelVersion")
        if not isinstance(model_version, str) or not model_version.strip():
            _invalid("symbol_inference.modelVersion must be non-empty.")
        _sha256(
            payload.get("modelManifestChecksumSha256"),
            "symbol_inference.modelManifestChecksumSha256",
        )
        model_iteration_id = payload.get("modelIterationId")
        if model_iteration_id is not None:
            try:
                UUID(str(model_iteration_id))
            except ValueError:
                _invalid("symbol_inference.modelIterationId must be a UUID or null.")
    else:
        _invalid(f"Payload validation is not defined for stage {stage!r}.")
    canonical_json_bytes(payload)
    return payload


def continuity_issues(sequence_numbers: Sequence[int]) -> tuple[ContinuityIssue, ...]:
    """Return deterministic duplicate/gap diagnostics without altering numbers."""

    if not sequence_numbers:
        return (
            ContinuityIssue(
                code="IMAGE_SEQUENCE_EMPTY",
                sequence_number=None,
                occurrence_count=0,
            ),
        )
    counts: dict[int, int] = {}
    for value in sequence_numbers:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            _invalid("Accepted sequence numbers must be positive integers.")
        counts[value] = counts.get(value, 0) + 1
    issues = [
        ContinuityIssue(
            code="IMAGE_SEQUENCE_DUPLICATE",
            sequence_number=value,
            occurrence_count=count,
        )
        for value, count in sorted(counts.items())
        if count > 1
    ]
    minimum = min(counts)
    maximum = max(counts)
    issues.extend(
        ContinuityIssue(
            code="IMAGE_SEQUENCE_GAP",
            sequence_number=value,
            occurrence_count=0,
        )
        for value in range(minimum, maximum + 1)
        if value not in counts
    )
    return tuple(issues)


def _adapter_registry(
    adapters: Sequence[VersionedImageStageAdapter],
) -> dict[str, VersionedImageStageAdapter]:
    result: dict[str, VersionedImageStageAdapter] = {}
    for adapter in adapters:
        if (
            adapter.stage not in {*AUTOMATED_IMAGE_STAGES, BOARD_CELL_GEOMETRY_STAGE}
            or not adapter.version.strip()
            or adapter.stage in result
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_PIPELINE_ADAPTER_REGISTRY_INVALID",
                "Automated image stages require one unique versioned adapter.",
            )
        result[adapter.stage] = adapter
    missing = [stage for stage in AUTOMATED_IMAGE_STAGES if stage not in result]
    if missing:
        raise ImagePipelineExecutionError(
            "IMAGE_PIPELINE_ADAPTER_MISSING",
            f"Missing image stage adapters: {', '.join(missing)}.",
        )
    return result


def _require_manifest_path(image: SourceImage, relative_path: str) -> None:
    if relative_path not in {item.relative_path for item in image.files}:
        raise ImagePipelineExecutionError(
            "IMAGE_DISCOVERY_PATH_NOT_ATTESTED",
            "The source path is absent from its checksum-bound discovery entry.",
        )


def _boards(
    payload: Mapping[str, object],
    *,
    require_cells: bool,
    require_sequence: bool,
    require_symbols: bool,
    allow_empty: bool = False,
    allow_sparse: bool = False,
) -> tuple[Mapping[str, object], ...]:
    raw = payload.get("boards")
    minimum = 0 if allow_empty else 1
    if (
        not isinstance(raw, Sequence)
        or isinstance(raw, str | bytes)
        or not minimum <= len(raw) <= 9
    ):
        _invalid(f"Stage payload must contain {minimum}..9 boards.")
    boards: list[Mapping[str, object]] = []
    positions: list[int] = []
    for index, item in enumerate(cast(Sequence[object], raw)):
        board = _mapping(item, f"boards[{index}]")
        position = _nonnegative_integer(board.get("positionIndex"), "positionIndex")
        if position > 8:
            _invalid("Board positionIndex must be in range 0..8.")
        positions.append(position)
        if require_cells:
            _board_cells(board)
            _relative_path(board.get("boardRelativePath"), "boardRelativePath")
            _sha256(board.get("boardChecksumSha256"), "board checksum")
        elif require_sequence:
            raw_text = board.get("rawText")
            if not isinstance(raw_text, str):
                _invalid("OCR rawText must be a string.")
            normalized = board.get("normalizedNumber")
            if normalized is not None:
                _positive_integer(normalized, "normalizedNumber")
            _confidence(board.get("confidence"), "sequence confidence")
            reasons = board.get("reviewReasons", [])
            if not isinstance(reasons, Sequence) or isinstance(reasons, str | bytes):
                _invalid("OCR reviewReasons must be an array.")
        elif require_symbols:
            _symbol_cells(board)
        else:
            _confidence(board.get("confidence"), "board confidence")
            if not isinstance(board.get("geometry"), Mapping):
                _invalid("Detected board geometry must be an object.")
        boards.append(board)
    if positions != sorted(set(positions)) or (
        not allow_sparse and positions != list(range(len(positions)))
    ):
        _invalid("Board positions must be unique and row-major.")
    return tuple(boards)


def _board_cells(board: Mapping[str, object]) -> None:
    raw_cells = board.get("cells")
    if not isinstance(raw_cells, Sequence) or isinstance(raw_cells, str | bytes):
        _invalid("Board crop cells must be an array.")
    cells = cast(Sequence[object], raw_cells)
    if len(cells) != BOARD_CELL_COUNT:
        _invalid("Every cropped board must contain exactly 15 cells.")
    for index, item in enumerate(cells):
        cell = _mapping(item, f"cells[{index}]")
        row = _nonnegative_integer(cell.get("rowIndex"), "rowIndex")
        column = _nonnegative_integer(cell.get("columnIndex"), "columnIndex")
        if row != index // BOARD_COLUMNS or column != index % BOARD_COLUMNS:
            _invalid("Board cells must be complete and row-major.")
        _relative_path(cell.get("cropRelativePath"), "cropRelativePath")
        _sha256(cell.get("cropChecksumSha256"), "crop checksum")
    cropper = board.get("cropperVersion")
    if not isinstance(cropper, str) or not cropper.strip():
        _invalid("Board cropperVersion must be non-empty.")


def _symbol_cells(board: Mapping[str, object]) -> None:
    raw_cells = board.get("cells")
    if not isinstance(raw_cells, Sequence) or isinstance(raw_cells, str | bytes):
        _invalid("Symbol prediction cells must be an array.")
    cells = cast(Sequence[object], raw_cells)
    if len(cells) != BOARD_CELL_COUNT:
        _invalid("Every symbol prediction must contain exactly 15 cells.")
    for index, item in enumerate(cells):
        cell = _mapping(item, f"cells[{index}]")
        row = _nonnegative_integer(cell.get("rowIndex"), "rowIndex")
        column = _nonnegative_integer(cell.get("columnIndex"), "columnIndex")
        if row != index // BOARD_COLUMNS or column != index % BOARD_COLUMNS:
            _invalid("Symbol predictions must be complete and row-major.")
        code = cell.get("symbolCode")
        if not isinstance(code, str) or not code.strip():
            _invalid("Predicted symbolCode must be non-empty.")
        _confidence(cell.get("confidence"), "symbol confidence")
        alternatives = cell.get("alternatives")
        if (
            not isinstance(alternatives, Sequence)
            or isinstance(alternatives, str | bytes)
            or not 1 <= len(alternatives) <= 3
        ):
            _invalid("Symbol alternatives must contain one to three values.")


def _same_positions(
    context: ImageStageContext,
    previous_stage: str,
    boards: Sequence[Mapping[str, object]],
) -> None:
    previous = context.previous_results.get(previous_stage)
    if previous is None:
        _invalid(f"{previous_stage} must complete before the current stage.")
    raw = previous.get("boards")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        _invalid(f"{previous_stage} has no boards.")
    previous_boards = [_mapping(item, "previous board") for item in raw]
    previous_positions = [item.get("positionIndex") for item in previous_boards]
    current_positions = [item.get("positionIndex") for item in boards]
    if current_positions != previous_positions:
        _invalid("Board positions cannot change between pipeline stages.")


def _board_cell_geometry(
    payload: Mapping[str, object],
    context: ImageStageContext,
) -> None:
    processing_version = payload.get("processingVersion")
    configuration_fingerprint = payload.get("configurationFingerprintSha256")
    if not isinstance(processing_version, str) or not processing_version.strip():
        _invalid("board_cell_geometry.processingVersion must be non-empty.")
    _sha256(configuration_fingerprint, "board_cell_geometry configuration fingerprint")
    boards = _boards(
        payload,
        require_cells=False,
        require_sequence=False,
        require_symbols=False,
    )
    _same_positions(context, "board_detection", boards)
    for board in boards:
        status = board.get("status")
        sequence_number = board.get("sequenceNumber")
        _positive_integer(sequence_number, "board_cell_geometry.sequenceNumber")
        if status == "verified":
            geometry = _mapping(board.get("cellGeometry"), "cellGeometry")
            cells = geometry.get("cells")
            if not isinstance(cells, Sequence) or isinstance(cells, str | bytes):
                _invalid("Verified board-cell geometry must contain cells.")
            if len(cells) != BOARD_CELL_COUNT:
                _invalid("Verified board-cell geometry must contain exactly 15 cells.")
            for index, value in enumerate(cells):
                cell = _mapping(value, "cellGeometry.cell")
                if (
                    _nonnegative_integer(cell.get("rowIndex"), "cellGeometry.rowIndex")
                    != index // BOARD_COLUMNS
                    or _nonnegative_integer(cell.get("columnIndex"), "cellGeometry.columnIndex")
                    != index % BOARD_COLUMNS
                ):
                    _invalid("Verified board-cell geometry must be complete and row-major.")
                quad = cell.get("quad")
                if (
                    not isinstance(quad, Sequence)
                    or isinstance(quad, str | bytes)
                    or len(quad) != 4
                    or any(not isinstance(point, Mapping) for point in quad)
                ):
                    _invalid("Every verified board-cell quad must contain four points.")
        elif status == "deferred":
            if board.get("cellGeometry") is not None:
                _invalid("Deferred board-cell geometry cannot contain synthetic cells.")
            reason = board.get("reasonCode")
            estimator_reason = board.get("estimatorFailureReason")
            if not isinstance(reason, str) or not reason.strip():
                _invalid("Deferred board-cell geometry requires a reasonCode.")
            if not isinstance(estimator_reason, str) or not estimator_reason.strip():
                _invalid("Deferred board-cell geometry requires an estimatorFailureReason.")
        else:
            _invalid("Board-cell geometry status must be verified or deferred.")


def _v20_crop_positions(
    context: ImageStageContext,
    payload: Mapping[str, object],
    boards: Sequence[Mapping[str, object]],
) -> None:
    geometry = context.previous_results.get(BOARD_CELL_GEOMETRY_STAGE)
    if geometry is None:
        _invalid("board_cell_geometry must complete before v19 crops.")
    geometry_boards = _sequence_mappings(geometry.get("boards"), "board_cell_geometry.boards")
    expected = [
        _nonnegative_integer(item.get("positionIndex"), "board_cell_geometry.positionIndex")
        for item in geometry_boards
        if item.get("status") == "verified"
    ]
    deferred = _sequence_mappings(payload.get("deferredBoards", []), "deferredBoards")
    deferred_positions: list[int] = []
    for item in deferred:
        position = _nonnegative_integer(item.get("positionIndex"), "deferredBoards.positionIndex")
        _positive_integer(item.get("sequenceNumber"), "deferredBoards.sequenceNumber")
        if not isinstance(item.get("reasonCode"), str) or not item["reasonCode"]:
            _invalid("A deferred crop requires a reasonCode.")
        deferred_positions.append(position)
    crop_positions = [
        _nonnegative_integer(item.get("positionIndex"), "board_crops.positionIndex")
        for item in boards
    ]
    combined = sorted([*crop_positions, *deferred_positions])
    if combined != expected or len(combined) != len(set(combined)):
        _invalid("v19 crop results must partition every verified geometry position.")


def _sequence_mappings(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        _invalid(f"{label} must be an array.")
    return [_mapping(item, label) for item in cast(Sequence[object], value)]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _invalid(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _positive_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        _invalid(f"{label} must be a positive integer.")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _invalid(f"{label} must be a non-negative integer.")
    return value


def _confidence(value: object, label: str) -> float:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not 0.0 <= float(value) <= 1.0
    ):
        _invalid(f"{label} must be between zero and one.")
    return float(value)


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        _invalid(f"{label} must be a lowercase SHA-256.")
    return value


def _relative_path(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        _invalid(f"{label} must be a safe relative POSIX path.")
    return value


def _matching_text(value: object, expected: str, label: str) -> None:
    if value != expected:
        _invalid(f"{label} differs from the attested execution.")


def _candidate_job_id(candidate: ImageBatchCandidate) -> UUID:
    if candidate.job_id is None:
        raise ImagePipelineExecutionError(
            "IMAGE_PIPELINE_EXECUTION_CONTEXT_MISSING",
            "A persisted image stage requires a job context.",
        )
    return candidate.job_id


def _invalid(message: str) -> Never:
    raise ImagePipelineExecutionError("IMAGE_STAGE_RESULT_INVALID", message)


__all__ = [
    "AUTOMATED_IMAGE_STAGES",
    "BOARD_CELL_COUNT",
    "ContinuityIssue",
    "FunctionImageStageAdapter",
    "ImageBatchRegistrar",
    "ImageDirectoryBatchSeeder",
    "IMAGE_REGISTRATION_BATCH_SIZE",
    "ImagePipelineExecutionError",
    "ImagePipelineProjectionStore",
    "ImagePipelineStageExecutor",
    "ImageStageContext",
    "ManifestDiscoveryStageAdapter",
    "StoredImageStageResult",
    "VersionedImageStageAdapter",
    "build_image_pipeline_handler",
    "continuity_issues",
    "validate_stage_payload",
]
