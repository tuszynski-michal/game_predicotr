"""Build a read-only A/B diagnostic from human-resolved v19 board geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import UUID

import numpy as np
from game_predictor_api.config import get_settings
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_worker.images.board_cell_geometry_contract import canonical_json_bytes
from game_predictor_worker.images.grid_symbol_diagnosis import (
    CellPrediction,
    DiagnosticBoard,
    GridSymbolDiagnosisError,
    build_diagnostic_document,
    document_checksum_sha256,
    production_preprocess_rgb,
)
from game_predictor_worker.images.symbol_model_release import build_symbol_predictions
from game_predictor_worker.images.symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

SCRIPT_VERSION = "build-grid-symbol-diagnostic-v1"
V19_CROPPER = "board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/quality/grid-symbol-diagnosis"),
    )
    parser.add_argument("--corrected-by", default="local-admin")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    settings = get_settings()
    factory = create_session_factory(create_database_engine(settings))
    session = factory()
    try:
        snapshot = SqlAlchemySymbolModelSnapshotResolver(
            session,
            artifact_root=settings.artifact_root,
        ).resolve(game_id=arguments.game_id)
        adapter = _load_adapter(snapshot, settings.artifact_root)
        boards, excluded = _collect_boards(
            session,
            game_id=arguments.game_id,
            corrected_by=arguments.corrected_by,
            comparison_fingerprint=snapshot.inference_fingerprint,
            adapter=adapter,
            artifact_root=settings.artifact_root,
            temperature=max(0.50, snapshot.temperature),
        )
        document = build_diagnostic_document(
            boards,
            comparison_model_fingerprint=snapshot.inference_fingerprint,
            excluded_counts=excluded,
        )
        document["comparisonModel"] = {
            "classCodes": list(snapshot.class_codes),
            "inputSize": snapshot.input_size,
            "iterationId": None if snapshot.iteration_id is None else str(snapshot.iteration_id),
            "manifestChecksumSha256": snapshot.manifest_checksum_sha256,
            "modelVersion": snapshot.model_version,
            "onnxChecksumSha256": snapshot.onnx_checksum_sha256,
            "temperatureApplied": max(0.50, snapshot.temperature),
        }
        document["scriptVersion"] = SCRIPT_VERSION
        checksum = document_checksum_sha256(document)
        destination = arguments.output_root / f"{checksum}.json"
        content = canonical_json_bytes(document)
        if arguments.check:
            if not destination.is_file() or destination.read_bytes() != content:
                raise GridSymbolDiagnosisError(
                    "GRID_SYMBOL_DIAGNOSIS_REPORT_MISSING",
                    "The expected immutable diagnostic report is missing or differs.",
                )
        else:
            _write_immutable(destination, content)
        print(
            json.dumps(
                {
                    "boardCount": len(boards),
                    "checksumSha256": checksum,
                    "excludedBoardCounts": dict(sorted(excluded.items())),
                    "reportPath": destination.as_posix(),
                    "summary": document["summary"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (GridSymbolDiagnosisError, SymbolOnnxError, ValueError) as error:
        code = getattr(error, "code", "GRID_SYMBOL_DIAGNOSIS_FAILED")
        print(json.dumps({"code": code, "message": str(error)}), file=sys.stderr)
        return 1
    finally:
        session.close()


def _collect_boards(
    session: Any,
    *,
    game_id: UUID,
    corrected_by: str,
    comparison_fingerprint: str,
    adapter: LocalSymbolOnnxAdapter,
    artifact_root: Path,
    temperature: float,
) -> tuple[tuple[DiagnosticBoard, ...], Counter[str]]:
    rows = session.execute(
        select(
            ImageBoardGeometryRevisionModel,
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            JobModel,
        )
        .join(
            ImageReviewItemModel,
            ImageReviewItemModel.id == ImageBoardGeometryRevisionModel.review_item_id,
        )
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageBoardGeometryRevisionModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
        .where(
            ImageReviewItemModel.status.in_(("accepted", "corrected")),
            ImageBoardGeometryRevisionModel.corrected_by == corrected_by,
            ImageBoardGeometryRevisionModel.cropper_version == V19_CROPPER,
            JobModel.game_id == game_id,
        )
        .order_by(RecognizedBoardModel.sequence_number, RecognizedBoardModel.id)
    ).all()
    prepared: list[
        tuple[
            ImageBoardGeometryRevisionModel,
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            JobModel,
            tuple[CellObservationModel, ...],
            tuple[CellPrediction, ...],
            tuple[str, ...],
            tuple[np.ndarray, ...],
        ]
    ] = []
    excluded: Counter[str] = Counter()
    for geometry, item, board, source, job in rows:
        if geometry.revision != board.geometry_revision:
            excluded["stale_geometry_revision"] += 1
            continue
        if _snapshot_fingerprint(job.input_payload.get("symbol_model")) != comparison_fingerprint:
            excluded["baseline_model_mismatch"] += 1
            continue
        expected = _expected_symbols(item.resolved_value)
        baseline = _baseline_predictions(session, board.id)
        if expected is None:
            excluded["resolved_labels_invalid"] += 1
            continue
        if baseline is None:
            excluded["baseline_predictions_invalid"] += 1
            continue
        try:
            corrected_tensors = _load_corrected_tensors(
                geometry.crop_artifacts,
                artifact_root=artifact_root,
                input_size=adapter.input_size,
            )
        except GridSymbolDiagnosisError as error:
            excluded[error.code.lower()] += 1
            continue
        baseline_cropper_versions = {cell.cropper_version for cell in baseline[0]}
        if len(baseline_cropper_versions) != 1:
            excluded["baseline_cropper_mismatch"] += 1
            continue
        baseline_predictions = baseline[1]
        geometry_payload = cast(Mapping[str, object], geometry.geometry)
        prepared.append(
            (
                geometry,
                item,
                board,
                source,
                job,
                baseline[0],
                baseline_predictions,
                expected,
                corrected_tensors,
            )
        )
    if not prepared:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_NO_COMPARABLE_BOARDS",
            "No current human-corrected v19 boards match the active model snapshot.",
        )
    inference = adapter.infer(
        np.stack([tensor for *_, tensors in prepared for tensor in tensors]).astype(np.float32)
    )
    predictions = build_symbol_predictions(
        inference.logits,
        temperature=temperature,
        class_codes=adapter.class_codes,
        alternative_limit=3,
    )
    included: list[DiagnosticBoard] = []
    for offset, candidate in enumerate(prepared):
        (
            geometry,
            _item,
            board,
            source,
            job,
            baseline_cells,
            baseline_predictions,
            expected,
            _tensors,
        ) = candidate
        geometry_payload = cast(Mapping[str, object], geometry.geometry)
        corrected = tuple(
            CellPrediction(prediction.symbol_code, prediction.confidence)
            for prediction in predictions[offset * 15 : (offset + 1) * 15]
        )
        included.append(
            DiagnosticBoard(
                board_id=str(board.id),
                sequence_number=cast(int, board.sequence_number),
                position_index=board.position_index,
                source_checksum_sha256=source.checksum_sha256,
                source_relative_path=source.relative_path,
                staging_label=_staging_label(job),
                # The board projection has already been replaced by v19 after the
                # manual correction. The pre-v19 quad was not stored as a separate
                # revision, so report the actual historical fixed-partition method
                # instead of falsely attributing v19 to the baseline crop.
                baseline_geometry_version="fixed-5x3-from-board-quad-v18",
                baseline_cropper_version=baseline_cells[0].cropper_version,
                corrected_geometry_version=str(
                    geometry_payload.get("geometryVersion", "manual-board-cell-geometry-v19")
                ),
                corrected_cropper_version=geometry.cropper_version,
                baseline_model_fingerprint=comparison_fingerprint,
                comparison_model_fingerprint=comparison_fingerprint,
                expected_symbols=expected,
                baseline_predictions=baseline_predictions,
                corrected_predictions=corrected,
            )
        )
    return tuple(included), excluded


def _baseline_predictions(
    session: Any,
    board_id: UUID,
) -> tuple[tuple[CellObservationModel, ...], tuple[CellPrediction, ...]] | None:
    cells = tuple(
        session.scalars(
            select(CellObservationModel)
            .where(CellObservationModel.recognized_board_id == board_id)
            .order_by(CellObservationModel.row_index, CellObservationModel.column_index)
        ).all()
    )
    if len(cells) != 15 or [(cell.row_index, cell.column_index) for cell in cells] != [
        (row, column) for row in range(3) for column in range(5)
    ]:
        return None
    predictions: list[CellPrediction] = []
    for cell in cells:
        prediction = cell.prediction
        symbol = prediction.get("symbolCode")
        confidence = prediction.get("confidence")
        if not isinstance(symbol, str) or not isinstance(confidence, int | float):
            return None
        predictions.append(CellPrediction(symbol, float(confidence)))
    return cells, tuple(predictions)


def _expected_symbols(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, Mapping):
        return None
    cells = value.get("cells")
    if not isinstance(cells, Sequence) or isinstance(cells, str | bytes) or len(cells) != 15:
        return None
    indexed: dict[int, str] = {}
    for raw in cells:
        if not isinstance(raw, Mapping):
            return None
        index = raw.get("cellIndex")
        symbol = raw.get("symbolCode")
        if not isinstance(index, int) or isinstance(index, bool) or not isinstance(symbol, str):
            return None
        indexed[index] = symbol
    if set(indexed) != set(range(15)):
        return None
    return tuple(indexed[index] for index in range(15))


def _load_corrected_tensors(
    artifacts: Sequence[Mapping[str, object]],
    *,
    artifact_root: Path,
    input_size: int,
) -> tuple[np.ndarray, ...]:
    ordered = sorted(
        artifacts,
        key=lambda artifact: (
            cast(int, artifact.get("rowIndex")),
            cast(int, artifact.get("columnIndex")),
        ),
    )
    if len(ordered) != 15 or [
        (artifact.get("rowIndex"), artifact.get("columnIndex")) for artifact in ordered
    ] != [(row, column) for row in range(3) for column in range(5)]:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_CORRECTED_CROPS_INVALID",
            "Corrected geometry must expose fifteen row-major crop artifacts.",
        )
    return tuple(_load_crop_tensor(artifact, artifact_root, input_size) for artifact in ordered)


def _load_crop_tensor(
    artifact: Mapping[str, object], artifact_root: Path, input_size: int
) -> np.ndarray:
    relative_value = artifact.get("cropRelativePath")
    expected_checksum = artifact.get("cropChecksumSha256")
    if not isinstance(relative_value, str) or not isinstance(expected_checksum, str):
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_CORRECTED_CROPS_INVALID", "A crop artifact is incomplete."
        )
    relative = PurePosixPath(relative_value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_CROP_PATH_UNSAFE", "A crop artifact path is unsafe."
        )
    root = (artifact_root / "data").resolve()
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root):
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_CROP_PATH_UNSAFE", "A crop artifact path escapes storage."
        )
    try:
        content = path.read_bytes()
        with Image.open(path) as image:
            image.load()
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_CROP_UNAVAILABLE", "A corrected crop cannot be read."
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_CROP_DRIFT", "A corrected crop checksum differs."
        )
    return production_preprocess_rgb(rgb, input_size=input_size)


def _load_adapter(snapshot: Any, artifact_root: Path) -> LocalSymbolOnnxAdapter:
    root = artifact_root if snapshot.storage_root.value == "artifact" else Path.cwd()
    relative = PurePosixPath(snapshot.onnx_relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_MODEL_PATH_UNSAFE", "The active model path is unsafe."
        )
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise GridSymbolDiagnosisError(
            "GRID_SYMBOL_DIAGNOSIS_MODEL_PATH_UNSAFE", "The active model path escapes storage."
        )
    return LocalSymbolOnnxAdapter(
        path,
        expected_sha256=snapshot.onnx_checksum_sha256,
        class_codes=snapshot.class_codes,
        input_size=snapshot.input_size,
    )


def _snapshot_fingerprint(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    fingerprint = value.get("inferenceFingerprint")
    return fingerprint if isinstance(fingerprint, str) and len(fingerprint) == 64 else None


def _staging_label(job: JobModel) -> str:
    value = job.input_payload.get("source_display_name")
    return value if isinstance(value, str) and value else str(job.id)


def _write_immutable(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != content:
            raise GridSymbolDiagnosisError(
                "GRID_SYMBOL_DIAGNOSIS_ARTIFACT_CONFLICT",
                "The content-addressed report path contains different bytes.",
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != content:
                raise GridSymbolDiagnosisError(
                    "GRID_SYMBOL_DIAGNOSIS_ARTIFACT_CONFLICT",
                    "The content-addressed report path contains different bytes.",
                ) from None
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
