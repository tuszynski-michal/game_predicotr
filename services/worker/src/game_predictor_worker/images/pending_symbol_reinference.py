"""Explicit, pending-only symbol prediction refresh.

The handler never mutates the import predictions.  It writes an
append-only revision and checks the review row again under a database lock so
that a concurrent human resolution always wins.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.geometry_qualification import (
    GEOMETRY_QUALIFICATION_VERSION_V3,
    GeometryQualification,
    GeometryQualificationError,
)
from game_predictor_api.domain.jobs import Job, JobStatus
from game_predictor_api.domain.symbol_model_snapshots import (
    LAB_RGB_SYMBOL_MODEL_VERSION,
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_api.storage.board_render_manifest_reader import (
    CurrentBoardRenderManifest,
    current_render_manifest_from_record,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    ImageReviewItemModel,
    ImageSymbolPredictionRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from numpy.typing import NDArray
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.images.normalization import (
    CanonicalSourceFrame,
    CanonicalSourceLoader,
    CanonicalSourceLoadError,
)
from game_predictor_worker.images.symbol_model_release import build_symbol_predictions
from game_predictor_worker.images.symbol_onnx import (
    LocalSymbolOnnxAdapter,
    SymbolOnnxError,
    preprocess_rgb_batch,
    symbol_onnx_variant_arguments,
)
from game_predictor_worker.images.virtual_cell_extraction import (
    VirtualCellExtractionError,
    render_persisted_virtual_cell_rgb,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


@dataclass(frozen=True, slots=True, eq=False)
class _ReinferenceCrop:
    row_index: int
    column_index: int
    checksum_sha256: str
    rgb: NDArray[np.uint8]
    virtual_provenance: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class _PersistedVirtualCell:
    cell_index: int
    row_index: int
    column_index: int
    crop_checksum_sha256: str
    logical_cell_key_sha256: str
    logical_cell_key_v2_sha256: str
    render_spec: Mapping[str, object]
    render_spec_checksum_sha256: str
    rendered_pixel_checksum_sha256: str
    extractor_version: str

    def render(self, frame: CanonicalSourceFrame) -> _ReinferenceCrop:
        rgb = render_persisted_virtual_cell_rgb(
            frame,
            render_spec=self.render_spec,
            expected_render_spec_checksum_sha256=self.render_spec_checksum_sha256,
            expected_rendered_pixel_checksum_sha256=self.rendered_pixel_checksum_sha256,
            expected_cell_index=self.cell_index,
            expected_row_index=self.row_index,
            expected_column_index=self.column_index,
            expected_logical_cell_key_sha256=self.logical_cell_key_sha256,
            expected_logical_cell_key_v2_sha256=self.logical_cell_key_v2_sha256,
            expected_extractor_version=self.extractor_version,
        )
        return _ReinferenceCrop(
            row_index=self.row_index,
            column_index=self.column_index,
            checksum_sha256=self.crop_checksum_sha256,
            rgb=rgb,
            virtual_provenance={
                "cropChecksumSha256": self.crop_checksum_sha256,
                "extractorVersion": self.extractor_version,
                "logicalCellKeySha256": self.logical_cell_key_sha256,
                "logicalCellKeyV2Sha256": self.logical_cell_key_v2_sha256,
                # Slim shape (D-467 S8, TASK-0794): no renderSpec copy.
                "renderSpecChecksumSha256": self.render_spec_checksum_sha256,
                "renderedPixelChecksumSha256": self.rendered_pixel_checksum_sha256,
            },
        )


class PendingSymbolReinferenceHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        repository_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_root = artifact_root.resolve()
        self._repository_root = repository_root.resolve()

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.game_id is None:
            raise JobHandlerError("IMAGE_SYMBOL_REINFERENCE_GAME_MISSING", "The game is missing.")
        snapshot = _snapshot_from_payload(job)
        adapter = LocalSymbolOnnxAdapter(
            _model_path(snapshot, self._artifact_root, self._repository_root),
            expected_sha256=snapshot.onnx_checksum_sha256,
            class_codes=snapshot.class_codes,
            input_size=snapshot.input_size,
            **symbol_onnx_variant_arguments(snapshot.model_version),
        )
        rows = self._pending_rows(job.game_id)
        total = len(rows)
        if total == 0:
            context.checkpoint(
                checkpoint_payload=_checkpoint_payload(processed=0, skipped=0),
                stage="symbol_reinference",
                current=0,
                total=0,
                success_count=0,
                failure_count=0,
                review_count=0,
            )
            return
        processed = 0
        skipped = 0
        source_loader = CanonicalSourceLoader()
        try:
            for item, board, source in rows:
                predictions, crop_manifest_checksum = self._infer_board(
                    board.id,
                    geometry_revision=board.geometry_revision,
                    source=source,
                    snapshot=snapshot,
                    adapter=adapter,
                    source_loader=source_loader,
                    geometry_qualification=board.geometry_qualification,
                    asset_mode=board.asset_mode,
                    game_id=job.game_id,
                )
                with self._session_factory() as session, session.begin():
                    locked = session.scalar(
                        select(ImageReviewItemModel)
                        .where(ImageReviewItemModel.id == item.id)
                        .with_for_update()
                    )
                    current_board = session.scalar(
                        select(RecognizedBoardModel)
                        .where(RecognizedBoardModel.id == board.id)
                        .with_for_update()
                    )
                    if (
                        locked is None
                        or current_board is None
                        or current_board.geometry_revision != board.geometry_revision
                        or current_board.geometry_qualification != board.geometry_qualification
                    ):
                        skipped += 1
                    else:
                        pending_cell = session.scalar(
                            select(ImageSymbolReviewCellModel.id)
                            .where(
                                ImageSymbolReviewCellModel.game_id == job.game_id,
                                ImageSymbolReviewCellModel.review_item_id == item.id,
                                ImageSymbolReviewCellModel.geometry_revision
                                == current_board.geometry_revision,
                                ImageSymbolReviewCellModel.source_available.is_(True),
                                ImageSymbolReviewCellModel.review_state == "pending",
                            )
                            .limit(1)
                            .with_for_update()
                        )
                        if pending_cell is None:
                            skipped += 1
                            context.checkpoint(
                                checkpoint_payload=_checkpoint_payload(
                                    processed=processed, skipped=skipped
                                ),
                                stage="symbol_reinference",
                                current=processed + skipped,
                                total=total,
                                success_count=processed,
                                failure_count=0,
                                review_count=0,
                            )
                            continue
                        existing = session.scalar(
                            select(ImageSymbolPredictionRevisionModel).where(
                                ImageSymbolPredictionRevisionModel.review_item_id == item.id,
                                ImageSymbolPredictionRevisionModel.model_checksum_sha256
                                == snapshot.onnx_checksum_sha256,
                                ImageSymbolPredictionRevisionModel.crop_manifest_checksum_sha256
                                == crop_manifest_checksum,
                            )
                        )
                        if existing is None:
                            session.add(
                                ImageSymbolPredictionRevisionModel(
                                    game_id=job.game_id,
                                    review_item_id=item.id,
                                    recognized_board_id=board.id,
                                    source_job_id=source.import_job_id,
                                    model_iteration_id=snapshot.iteration_id,
                                    model_version=snapshot.model_version,
                                    model_checksum_sha256=snapshot.onnx_checksum_sha256,
                                    crop_manifest_checksum_sha256=crop_manifest_checksum,
                                    predictions=predictions,
                                )
                            )
                            session.flush()
                            SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(
                                item.id
                            )
                            synchronized = SymbolCellReviewWriteThroughCoordinator(
                                session
                            ).synchronize_after_prediction_refresh(
                                game_id=job.game_id,
                                review_item_id=item.id,
                                actor="system:pending-symbol-reinference",
                            )
                            if not synchronized:
                                raise JobHandlerError(
                                    "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
                                    "The symbol-cell review projection rejected a prediction "
                                    "refresh.",
                                )
                        processed += 1
                context.checkpoint(
                    checkpoint_payload=_checkpoint_payload(processed=processed, skipped=skipped),
                    stage="symbol_reinference",
                    current=processed + skipped,
                    total=total,
                    success_count=processed,
                    failure_count=0,
                    review_count=0,
                )
        finally:
            source_loader.clear()

    def _pending_rows(
        self,
        game_id: UUID,
    ) -> list[tuple[ImageReviewItemModel, RecognizedBoardModel, SourceImageModel]]:
        with self._session_factory() as session:
            return list(
                session.execute(
                    select(ImageReviewItemModel, RecognizedBoardModel, SourceImageModel)
                    .join(
                        RecognizedBoardModel,
                        RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                    )
                    .join(
                        SourceImageModel,
                        SourceImageModel.id == RecognizedBoardModel.source_image_id,
                    )
                    .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                    .join(
                        ImageSymbolReviewCellModel,
                        and_(
                            ImageSymbolReviewCellModel.review_item_id == ImageReviewItemModel.id,
                            ImageSymbolReviewCellModel.recognized_board_id
                            == RecognizedBoardModel.id,
                        ),
                    )
                    .where(
                        ImageSymbolReviewCellModel.game_id == game_id,
                        ImageSymbolReviewCellModel.source_available.is_(True),
                        ImageSymbolReviewCellModel.review_state == "pending",
                        ImageSymbolReviewCellModel.geometry_revision
                        == RecognizedBoardModel.geometry_revision,
                        ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
                        or_(
                            JobModel.status == JobStatus.WAITING_FOR_REVIEW,
                            and_(
                                JobModel.status == JobStatus.COMPLETED,
                                RecognizedBoardModel.geometry_qualification.is_not(None),
                            ),
                        ),
                    )
                    .distinct()
                    .order_by(
                        SourceImageModel.id,
                        ImageReviewItemModel.created_at,
                        ImageReviewItemModel.id,
                    )
                )
                .tuples()
                .all()
            )

    def _infer_board(
        self,
        board_id: UUID,
        geometry_revision: int,
        *,
        source: SourceImageModel,
        snapshot: SymbolModelJobSnapshot,
        adapter: LocalSymbolOnnxAdapter,
        source_loader: CanonicalSourceLoader,
        geometry_qualification: Mapping[str, object] | None = None,
        asset_mode: str,
        game_id: UUID,
    ) -> tuple[list[dict[str, object]], str]:
        if asset_mode != "virtual_source":
            # D-467 S6 (TASK-0796): every board is ``virtual_source``; the
            # former file-crop boards have no cells to re-infer.
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_LEGACY_UNSUPPORTED",
                "Only virtual_source boards can be re-inferred.",
            )
        with self._session_factory() as session:
            # D-467: a board's current cells come from its render manifest.
            record = session.get(BoardRenderManifestModel, (game_id, board_id, geometry_revision))
            render_manifest = (
                None if record is None else current_render_manifest_from_record(record)
            )
        expected_indices = _available_indices(geometry_qualification)
        crops = self._render_virtual_crops(
            render_manifest=render_manifest,
            source=source,
            source_loader=source_loader,
            expected_indices=expected_indices,
        )
        crops.sort(key=lambda crop: (crop.row_index, crop.column_index))
        if [(crop.row_index, crop.column_index) for crop in crops] != [
            (index // 5, index % 5) for index in expected_indices
        ]:
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                "A pending board does not contain 15 crops.",
            )
        if not crops:
            return [], hashlib.sha256(b"[]").hexdigest()
        tensors: list[NDArray[np.float32]] = []
        checksums: list[str] = []
        for crop in crops:
            checksums.append(crop.checksum_sha256)
            rgb = crop.rgb
            if snapshot.model_version == LAB_RGB_SYMBOL_MODEL_VERSION:
                # Current crop identity must already be RGB96. Never silently
                # re-render/rescale pixels approved under a different snapshot.
                continue
            if rgb.shape[:2] != (snapshot.input_size, snapshot.input_size):
                rgb = cast(
                    NDArray[np.uint8],
                    cv2.resize(
                        rgb,
                        (snapshot.input_size, snapshot.input_size),
                        interpolation=cv2.INTER_AREA,
                    ),
                )
            normalized = rgb.astype(np.float32).transpose(2, 0, 1) / 255.0
            tensors.append(((normalized - 0.5) / 0.5).astype(np.float32))
        try:
            inputs = (
                preprocess_rgb_batch(
                    [crop.rgb for crop in crops],
                    input_size=snapshot.input_size,
                    model_version=snapshot.model_version,
                )
                if snapshot.model_version == LAB_RGB_SYMBOL_MODEL_VERSION
                else np.stack(tensors).astype(np.float32)
            )
            inference = adapter.infer(inputs)
        except SymbolOnnxError as error:
            raise JobHandlerError(f"IMAGE_{error.code}", str(error)) from error
        predictions = build_symbol_predictions(
            inference.logits,
            temperature=snapshot.temperature,
            class_codes=snapshot.class_codes,
            alternative_limit=3,
        )
        output = [
            {
                **prediction.to_dict(),
                "rowIndex": crop.row_index,
                "columnIndex": crop.column_index,
                **(
                    {}
                    if crop.virtual_provenance is None
                    else {"virtualCell": dict(crop.virtual_provenance)}
                ),
            }
            for crop, prediction in zip(crops, predictions, strict=True)
        ]
        manifest = json.dumps(checksums, separators=(",", ":"), ensure_ascii=True).encode()
        return output, hashlib.sha256(manifest).hexdigest()

    def _render_virtual_crops(
        self,
        *,
        render_manifest: CurrentBoardRenderManifest | None,
        source: SourceImageModel,
        source_loader: CanonicalSourceLoader,
        expected_indices: tuple[int, ...] = tuple(range(15)),
    ) -> list[_ReinferenceCrop]:
        records = _virtual_records(
            render_manifest=render_manifest, expected_indices=expected_indices
        )
        if not records:
            return []
        source_path = _managed_source_path(self._artifact_root, source.checksum_sha256)
        try:
            frame = source_loader.load(
                source_path,
                expected_source_checksum_sha256=source.checksum_sha256,
            )
            return [record.render(frame) for record in records]
        except (CanonicalSourceLoadError, VirtualCellExtractionError) as error:
            raise JobHandlerError(
                getattr(error, "code", "IMAGE_VIRTUAL_CELL_RENDER_FAILED"), str(error)
            ) from error


def _managed_source_path(root: Path, checksum_sha256: str) -> Path:
    if len(checksum_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in checksum_sha256
    ):
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_SOURCE_CHECKSUM_INVALID",
            "A managed source checksum is invalid.",
        )
    managed_root = (root / "data" / "originals").resolve()
    path = (managed_root / checksum_sha256[:2] / f"{checksum_sha256}.jpg").resolve()
    if not path.is_relative_to(managed_root):
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_SOURCE_PATH_INVALID",
            "A managed source path escapes storage.",
        )
    return path


def _virtual_records(
    *,
    render_manifest: CurrentBoardRenderManifest | None,
    expected_indices: tuple[int, ...] = tuple(range(15)),
) -> list[_PersistedVirtualCell]:
    """Persisted render records of the board's current-revision manifest.

    Every manifest cell carries its real ``cellIndex`` (D-467); the former
    revision-0 observation path numbered cells by ordinal, which differed
    from the real index for a partial board with a masked middle cell.  No
    manifest means no renderable cells (TASK-0757 rule).
    """

    if render_manifest is None:
        if expected_indices:
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                "A pending virtual board has no render manifest for its geometry revision.",
            )
        return []
    raw_records: Sequence[Mapping[str, object]] = render_manifest.cells
    if len(raw_records) != len(expected_indices):
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
            "A pending virtual render manifest does not contain every expected cell.",
        )
    extractor_version = render_manifest.extractor_version

    records: list[_PersistedVirtualCell] = []
    for raw in raw_records:
        render_spec = raw.get("renderSpec")
        cell_index = raw.get("cellIndex")
        if not isinstance(render_spec, Mapping) or not isinstance(cell_index, int):
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_VIRTUAL_PROVENANCE_INVALID",
                "A pending virtual cell has invalid render provenance.",
            )
        row = render_spec.get("rowIndex")
        column = render_spec.get("columnIndex")
        values = {
            "crop": raw.get("cropChecksumSha256", raw.get("renderedPixelChecksumSha256")),
            "logical": raw.get("logicalCellKeySha256"),
            "logical_v2": raw.get("logicalCellKeyV2Sha256"),
            "spec_checksum": raw.get("renderSpecChecksumSha256"),
            "pixel_checksum": raw.get("renderedPixelChecksumSha256"),
            "extractor": raw.get("extractorVersion", extractor_version),
        }
        if (
            isinstance(row, bool)
            or not isinstance(row, int)
            or isinstance(column, bool)
            or not isinstance(column, int)
            or not all(isinstance(value, str) and value for value in values.values())
            or values["crop"] != values["pixel_checksum"]
        ):
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_VIRTUAL_PROVENANCE_INVALID",
                "A pending virtual cell has invalid render provenance.",
            )
        records.append(
            _PersistedVirtualCell(
                cell_index=cell_index,
                row_index=row,
                column_index=column,
                crop_checksum_sha256=cast(str, values["crop"]),
                logical_cell_key_sha256=cast(str, values["logical"]),
                logical_cell_key_v2_sha256=cast(str, values["logical_v2"]),
                render_spec=render_spec,
                render_spec_checksum_sha256=cast(str, values["spec_checksum"]),
                rendered_pixel_checksum_sha256=cast(str, values["pixel_checksum"]),
                extractor_version=cast(str, values["extractor"]),
            )
        )
    records.sort(key=lambda record: record.cell_index)
    if [record.cell_index for record in records] != list(expected_indices) or [
        (record.row_index, record.column_index) for record in records
    ] != [(index // 5, index % 5) for index in expected_indices]:
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
            "Pending virtual cells are not a complete row-major 3 by 5 grid.",
        )
    return records


def _available_indices(raw: Mapping[str, object] | None) -> tuple[int, ...]:
    if raw is None:
        return tuple(range(15))
    try:
        qualification = GeometryQualification.from_dict(raw)
    except GeometryQualificationError as error:
        raise JobHandlerError("IMAGE_GEOMETRY_QUALIFICATION_INVALID", str(error)) from error
    excluded = (
        qualification.fully_unavailable_cell_indices
        if qualification.version == GEOMETRY_QUALIFICATION_VERSION_V3
        else qualification.unavailable_cell_indices
    )
    return tuple(index for index in range(15) if index not in excluded)


def _checkpoint_payload(*, processed: int, skipped: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "pending-symbol-reinference-v1",
        "processed": processed,
        "skippedConcurrentResolution": skipped,
    }


def _model_path(
    snapshot: SymbolModelJobSnapshot, artifact_root: Path, repository_root: Path
) -> Path:
    relative = PurePosixPath(snapshot.onnx_relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_MODEL_PATH_INVALID", "The model path is unsafe."
        )
    root = (
        repository_root
        if snapshot.storage_root is SymbolModelStorageRoot.REPOSITORY
        else artifact_root
    )
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root):
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_MODEL_PATH_INVALID", "The model path escapes storage."
        )
    return path


def _snapshot_from_payload(job: Job) -> SymbolModelJobSnapshot:
    raw = job.input_payload.get("symbol_model")
    if not isinstance(raw, dict):
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_MODEL_MISSING", "The model snapshot is missing."
        )
    try:
        return SymbolModelJobSnapshot.from_payload(raw)
    except (KeyError, TypeError, ValueError) as error:
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_MODEL_INVALID", "The model snapshot is invalid."
        ) from error


__all__ = ["PendingSymbolReinferenceHandler"]
