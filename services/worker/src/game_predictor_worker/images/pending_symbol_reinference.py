"""Explicit, pending-only symbol prediction refresh.

The handler never mutates the original cell observations.  It writes an
append-only revision and checks the review row again under a database lock so
that a concurrent human resolution always wins.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.jobs import Job
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryRevisionModel,
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

from game_predictor_worker.images.symbol_model_release import build_symbol_predictions
from game_predictor_worker.images.symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


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
        with self._session_factory() as session:
            rows = list(
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
                    .where(
                        JobModel.game_id == job.game_id,
                        ImageReviewItemModel.status == "pending",
                    )
                    .order_by(ImageReviewItemModel.created_at, ImageReviewItemModel.id)
                )
                .tuples()
                .all()
            )
        total = len(rows)
        if total == 0:
            context.checkpoint(
                checkpoint_payload={"kind": "pending-symbol-reinference-v1", "processed": 0},
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
        for item, board, source in rows:
            predictions, crop_manifest_checksum = self._infer_board(
                board.id,
                geometry_revision=board.geometry_revision,
                snapshot=snapshot,
                adapter=adapter,
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
                    processed += 1
            context.checkpoint(
                checkpoint_payload={
                    "kind": "pending-symbol-reinference-v1",
                    "processed": processed,
                    "skippedConcurrentResolution": skipped,
                },
                stage="symbol_reinference",
                current=processed + skipped,
                total=total,
                success_count=processed,
                failure_count=0,
                review_count=0,
            )

    def _infer_board(
        self,
        board_id: UUID,
        geometry_revision: int,
        *,
        snapshot: SymbolModelJobSnapshot,
        adapter: LocalSymbolOnnxAdapter,
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
        crops: list[tuple[str, str, int, int]] = []
        if revised is not None:
            raw_crops = revised.crop_artifacts
            if not isinstance(raw_crops, list) or len(raw_crops) != 15:
                raise JobHandlerError(
                    "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                    "A pending board geometry revision does not contain 15 crops.",
                )
            for raw in raw_crops:
                if not isinstance(raw, dict):
                    raise JobHandlerError(
                        "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                        "A pending board geometry revision contains an invalid crop.",
                    )
                crops.append(
                    (
                        str(raw["cropRelativePath"]),
                        str(raw["cropChecksumSha256"]),
                        cast(int, raw["rowIndex"]),
                        cast(int, raw["columnIndex"]),
                    )
                )
        else:
            crops = [
                (
                    observation.crop_relative_path,
                    observation.crop_checksum_sha256,
                    observation.row_index,
                    observation.column_index,
                )
                for observation in observations
            ]
        crops.sort(key=lambda crop: (crop[2], crop[3]))
        if len(crops) != 15:
            raise JobHandlerError(
                "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                "A pending board does not contain 15 crops.",
            )
        tensors: list[NDArray[np.float32]] = []
        checksums: list[str] = []
        for crop_relative_path, crop_checksum, _row, _column in crops:
            checksums.append(crop_checksum)
            path = _artifact_path(self._artifact_root, crop_relative_path)
            try:
                with Image.open(path) as image:
                    rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
            except (OSError, UnidentifiedImageError) as error:
                raise JobHandlerError(
                    "IMAGE_SYMBOL_REINFERENCE_CROP_UNAVAILABLE",
                    "A pending symbol crop cannot be decoded.",
                ) from error
            resized_rgb = rgb
            if resized_rgb.shape[:2] != (snapshot.input_size, snapshot.input_size):
                resized_rgb = cast(
                    NDArray[np.uint8],
                    cv2.resize(
                        resized_rgb,
                        (snapshot.input_size, snapshot.input_size),
                        interpolation=cv2.INTER_AREA,
                    ),
                )
            normalized = resized_rgb.astype(np.float32).transpose(2, 0, 1) / 255.0
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
                "rowIndex": crop[2],
                "columnIndex": crop[3],
            }
            for crop, prediction in zip(crops, predictions, strict=True)
        ]
        manifest = json.dumps(checksums, separators=(",", ":"), ensure_ascii=True).encode()
        return output, hashlib.sha256(manifest).hexdigest()


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
