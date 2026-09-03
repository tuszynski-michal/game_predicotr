"""Explicit, pending-only symbol prediction refresh.

The handler never mutates the original cell observations.  It writes an
append-only revision and checks the review row again under a database lock so
that a concurrent human resolution always wins.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.jobs import Job, JobStatus
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageSymbolPredictionRevisionModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.images.normalization import (
    CanonicalSourceFrame,
    CanonicalSourceLoader,
    CanonicalSourceLoadError,
)
from game_predictor_worker.images.symbol_model_release import build_symbol_predictions
from game_predictor_worker.images.symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError
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
                "renderSpec": dict(self.render_spec),
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
                )
                with self._session_factory() as session, session.begin():
                    locked = session.scalar(
                        select(ImageReviewItemModel)
                        .where(ImageReviewItemModel.id == item.id)
                        .with_for_update()
                    )
                    if locked is None or locked.status != "pending":
                        skipped += 1
                    else:
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
                        ImageBoardSearchFastDocumentModel,
                        ImageBoardSearchFastDocumentModel.review_item_id == ImageReviewItemModel.id,
                    )
                    .where(
                        JobModel.game_id == game_id,
                        JobModel.status == JobStatus.WAITING_FOR_REVIEW,
                        ImageReviewItemModel.status == "pending",
                    )
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
    ) -> tuple[list[dict[str, object]], str]:
        with self._session_factory() as session:
            observations = session.scalars(
                select(CellObservationModel)
                .where(CellObservationModel.recognized_board_id == board_id)
                .order_by(CellObservationModel.row_index, CellObservationModel.column_index)
            ).all()
            revised = None
            if geometry_revision > 0:
                revised = session.scalar(
                    select(ImageBoardGeometryRevisionModel).where(
                        ImageBoardGeometryRevisionModel.recognized_board_id == board_id,
                        ImageBoardGeometryRevisionModel.revision == geometry_revision,
                    )
                )
        if len(observations) != 15:
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                "A pending board does not contain 15 immutable crops.",
            )
        virtual_assets = all(
            observation.asset_mode == "virtual_source" for observation in observations
        )
        if virtual_assets:
            crops = self._render_virtual_crops(
                observations=observations,
                revised=revised,
                source=source,
                source_loader=source_loader,
            )
        else:
            crops = self._legacy_crops(observations=observations, revised=revised)
        crops.sort(key=lambda crop: (crop.row_index, crop.column_index))
        if len(crops) != 15:
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                "A pending board does not contain 15 crops.",
            )
        tensors: list[NDArray[np.float32]] = []
        checksums: list[str] = []
        for crop in crops:
            checksums.append(crop.checksum_sha256)
            rgb = crop.rgb
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
            inference = adapter.infer(np.stack(tensors).astype(np.float32))
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

    def _legacy_crops(
        self,
        *,
        observations: list[CellObservationModel],
        revised: ImageBoardGeometryRevisionModel | None,
    ) -> list[_ReinferenceCrop]:
        raw_crops: list[tuple[str, str, int, int]] = []
        if revised is not None:
            revised_crops = revised.crop_artifacts
            if not isinstance(revised_crops, list) or len(revised_crops) != 15:
                raise JobHandlerError(
                    "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                    "A pending board geometry revision does not contain 15 crops.",
                )
            for raw in revised_crops:
                if not isinstance(raw, dict):
                    raise JobHandlerError(
                        "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                        "A pending board geometry revision contains an invalid crop.",
                    )
                raw_crops.append(
                    (
                        str(raw["cropRelativePath"]),
                        str(raw["cropChecksumSha256"]),
                        cast(int, raw["rowIndex"]),
                        cast(int, raw["columnIndex"]),
                    )
                )
        else:
            for observation in observations:
                if observation.crop_relative_path is None:
                    raise JobHandlerError(
                        "IMAGE_SYMBOL_REINFERENCE_VIRTUAL_ASSET_UNAVAILABLE",
                        "Virtual cell assets are not active in the legacy reinference job.",
                    )
                raw_crops.append(
                    (
                        observation.crop_relative_path,
                        observation.crop_checksum_sha256,
                        observation.row_index,
                        observation.column_index,
                    )
                )
        crops: list[_ReinferenceCrop] = []
        for crop_relative_path, crop_checksum, row, column in raw_crops:
            path = _artifact_path(self._artifact_root, crop_relative_path)
            try:
                with Image.open(path) as image:
                    rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
            except (OSError, UnidentifiedImageError) as error:
                raise JobHandlerError(
                    "IMAGE_SYMBOL_REINFERENCE_CROP_UNAVAILABLE",
                    "A pending symbol crop cannot be decoded.",
                ) from error
            crops.append(
                _ReinferenceCrop(
                    row_index=row,
                    column_index=column,
                    checksum_sha256=crop_checksum,
                    rgb=rgb,
                )
            )
        return crops

    def _render_virtual_crops(
        self,
        *,
        observations: list[CellObservationModel],
        revised: ImageBoardGeometryRevisionModel | None,
        source: SourceImageModel,
        source_loader: CanonicalSourceLoader,
    ) -> list[_ReinferenceCrop]:
        records = _virtual_records(observations=observations, revised=revised)
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


def _artifact_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_CROP_PATH_INVALID", "A crop path is unsafe."
        )
    path = (root / "data" / Path(*relative.parts)).resolve()
    if not path.is_relative_to((root / "data").resolve()):
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_CROP_PATH_INVALID", "A crop path escapes storage."
        )
    return path


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
    observations: list[CellObservationModel],
    revised: ImageBoardGeometryRevisionModel | None,
) -> list[_PersistedVirtualCell]:
    raw_records: list[Mapping[str, object]] = []
    extractor_version: str | None = None
    if revised is not None:
        manifest = revised.virtual_render_spec
        raw_cells = None if not isinstance(manifest, Mapping) else manifest.get("cells")
        if (
            revised.asset_mode != "virtual_source"
            or not isinstance(raw_cells, list)
            or len(raw_cells) != 15
        ):
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                "A pending virtual geometry revision does not contain 15 cells.",
            )
        if not all(isinstance(raw, Mapping) for raw in raw_cells):
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_VIRTUAL_PROVENANCE_INVALID",
                "A pending virtual geometry revision contains invalid cell provenance.",
            )
        raw_records = cast(list[Mapping[str, object]], raw_cells)
        extractor_version = revised.cropper_version
    else:
        for index, observation in enumerate(observations):
            if (
                observation.asset_mode != "virtual_source"
                or observation.render_spec is None
                or observation.render_spec_checksum_sha256 is None
                or observation.rendered_pixel_checksum_sha256 is None
                or observation.logical_cell_key is None
                or observation.logical_cell_key_v2 is None
                or observation.extractor_version is None
            ):
                raise JobHandlerError(
                    "IMAGE_SYMBOL_REINFERENCE_VIRTUAL_PROVENANCE_INVALID",
                    "A pending virtual cell has incomplete render provenance.",
                )
            raw_records.append(
                {
                    "cellIndex": index,
                    "cropChecksumSha256": observation.crop_checksum_sha256,
                    "extractorVersion": observation.extractor_version,
                    "logicalCellKeySha256": observation.logical_cell_key,
                    "logicalCellKeyV2Sha256": observation.logical_cell_key_v2,
                    "renderSpec": observation.render_spec,
                    "renderSpecChecksumSha256": observation.render_spec_checksum_sha256,
                    "renderedPixelChecksumSha256": observation.rendered_pixel_checksum_sha256,
                }
            )

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
    if [record.cell_index for record in records] != list(range(15)) or [
        (record.row_index, record.column_index) for record in records
    ] != [(index // 5, index % 5) for index in range(15)]:
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
            "Pending virtual cells are not a complete row-major 3 by 5 grid.",
        )
    return records


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
        iteration = raw.get("iterationId")
        return SymbolModelJobSnapshot(
            iteration_id=None if iteration is None else UUID(str(iteration)),
            model_version=str(raw["modelVersion"]),
            manifest_checksum_sha256=str(raw["manifestChecksumSha256"]),
            onnx_checksum_sha256=str(raw["onnxChecksumSha256"]),
            onnx_relative_path=str(raw["onnxRelativePath"]),
            storage_root=SymbolModelStorageRoot(str(raw["storageRoot"])),
            class_codes=tuple(str(value) for value in cast(list[object], raw["classCodes"])),
            input_size=int(raw["inputSize"]),
            temperature=float(raw["temperature"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise JobHandlerError(
            "IMAGE_SYMBOL_REINFERENCE_MODEL_INVALID", "The model snapshot is invalid."
        ) from error


__all__ = ["PendingSymbolReinferenceHandler"]
