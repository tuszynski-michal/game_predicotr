"""Evaluate the pinned ONNX model on an immutable v19 residual cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import UUID

import numpy as np
from game_predictor_api.config import get_settings
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
    canonical_json_bytes,
)
from game_predictor_worker.images.board_cell_geometry_crops import CROPPER_VERSION
from game_predictor_worker.images.grid_symbol_diagnosis import (
    CellPrediction,
    production_preprocess_rgb,
)
from game_predictor_worker.images.symbol_classifier import load_image_tensor
from game_predictor_worker.images.symbol_model_release import build_symbol_predictions
from game_predictor_worker.images.symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError
from game_predictor_worker.images.v19_symbol_residuals import (
    COHORT_VERSION,
    EvaluatedCell,
    V19SymbolResidualError,
    build_evaluation_document,
    document_checksum_sha256,
)
from PIL import Image, ImageOps, UnidentifiedImageError

DESCRIPTOR_VERSION = "v19-symbol-residual-cohort-descriptor-v1"
SCRIPT_VERSION = "evaluate-v19-symbol-residuals-v1"
DEFAULT_DESCRIPTOR = Path("ai_docs/quality/v19-symbol-residual-cohort.json")
DEFAULT_OUTPUT_ROOT = Path("artifacts/quality/v19-symbol-residuals")
BATCH_SIZE = 512


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--cohort-checksum")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    session = None
    try:
        descriptor = _load_descriptor(arguments.descriptor)
        cohort_checksum = _sha256(
            arguments.cohort_checksum or descriptor["expectedCohortChecksumSha256"]
        )
        cohort_path = arguments.output_root / "cohorts" / f"{cohort_checksum}.json"
        cohort_content = cohort_path.read_bytes()
        if hashlib.sha256(cohort_content).hexdigest() != cohort_checksum:
            raise _error("V19_SYMBOL_EVALUATION_COHORT_DRIFT", "Cohort checksum differs.")
        cohort = json.loads(cohort_content)
        if not isinstance(cohort, Mapping) or cohort.get("version") != COHORT_VERSION:
            raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", "Cohort version is invalid.")
        settings = get_settings()
        session = create_session_factory(create_database_engine(settings))()
        snapshot = SqlAlchemySymbolModelSnapshotResolver(
            session, artifact_root=settings.artifact_root
        ).resolve(game_id=UUID(cast(str, cohort["gameId"])))
        model = _mapping(cohort.get("model"), "model")
        if model.get("inferenceFingerprintSha256") != snapshot.inference_fingerprint:
            raise _error(
                "V19_SYMBOL_EVALUATION_MODEL_DRIFT",
                "The active model differs from the frozen cohort.",
            )
        adapter = _load_adapter(snapshot, settings.artifact_root)
        metadata, tensors, parity = _load_cells(
            cohort,
            output_root=arguments.output_root,
            input_size=snapshot.input_size,
        )
        predictions: list[CellPrediction] = []
        for offset in range(0, len(tensors), BATCH_SIZE):
            batch = np.stack(tensors[offset : offset + BATCH_SIZE]).astype(np.float32)
            result = adapter.infer(batch)
            predictions.extend(
                CellPrediction(value.symbol_code, value.confidence)
                for value in build_symbol_predictions(
                    result.logits,
                    temperature=max(0.50, snapshot.temperature),
                    class_codes=adapter.class_codes,
                    alternative_limit=3,
                )
            )
        if len(predictions) != len(metadata):
            raise _error("V19_SYMBOL_EVALUATION_INCOMPLETE", "Predictions do not align.")
        cells = tuple(
            EvaluatedCell(
                board_id=row["boardId"],
                sequence_number=row["sequenceNumber"],
                cell_index=row["cellIndex"],
                staging_label=row["stagingLabel"],
                source_family=row["sourceFamily"],
                expected_symbol=row["symbolCode"],
                prediction=prediction,
                crop_checksum_sha256=row["cropChecksumSha256"],
                preprocessing_parity=parity[index],
            )
            for index, (row, prediction) in enumerate(zip(metadata, predictions, strict=True))
        )
        report = build_evaluation_document(cohort, cells)
        report["model"] = dict(model)
        report["scriptVersion"] = SCRIPT_VERSION
        checksum = document_checksum_sha256(report)
        content = canonical_json_bytes(report)
        destination = arguments.output_root / "reports" / f"{checksum}.json"
        if arguments.check:
            if descriptor["expectedEvaluationChecksumSha256"] != checksum:
                raise _error(
                    "V19_SYMBOL_EVALUATION_CHECKSUM_DRIFT",
                    "The evaluation differs from the pinned descriptor.",
                )
            _verify(destination, content)
        else:
            _write(destination, content)
        print(
            json.dumps(
                {
                    "check": arguments.check,
                    "checksumSha256": checksum,
                    "decision": report["decision"],
                    "metrics": report["metrics"],
                    "path": destination.as_posix(),
                    "preprocessingParity": report["preprocessingParity"],
                    "residuals": report["residuals"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (
        V19SymbolResidualError,
        SymbolOnnxError,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        code = getattr(error, "code", "V19_SYMBOL_EVALUATION_FAILED")
        print(json.dumps({"code": code, "message": str(error)}), file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


def _load_cells(
    cohort: Mapping[str, object],
    *,
    output_root: Path,
    input_size: int,
) -> tuple[list[dict[str, Any]], list[np.ndarray], list[bool]]:
    if (
        cohort.get("geometryVersion") != BOARD_CELL_GEOMETRY_VERSION
        or cohort.get("cropperVersion") != CROPPER_VERSION
    ):
        raise _error(
            "V19_SYMBOL_EVALUATION_CROP_VERSION_INVALID",
            "Only the pinned v19 geometry and cropper are accepted.",
        )
    raw_boards = cohort.get("boards")
    split = _mapping(cohort.get("split"), "split")
    assignments = _mapping(split.get("assignments"), "split.assignments")
    if not isinstance(raw_boards, Sequence) or isinstance(raw_boards, str | bytes):
        raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", "Cohort boards are invalid.")
    metadata: list[dict[str, Any]] = []
    tensors: list[np.ndarray] = []
    parity: list[bool] = []
    seen_sources: dict[str, str] = {}
    for raw_board in raw_boards:
        board = _mapping(raw_board, "board")
        if (
            board.get("geometryVersion") != BOARD_CELL_GEOMETRY_VERSION
            or board.get("geometryProvenance")
            not in {"persisted_v19", "read_only_estimated_v19"}
            or board.get("decisionStatus") not in {"accepted", "corrected"}
        ):
            raise _error(
                "V19_SYMBOL_EVALUATION_GEOMETRY_UNTRUSTED",
                "A board does not contain verified v19 geometry and human labels.",
            )
        source_family = board.get("sourceFamily")
        board_split = board.get("split")
        if not isinstance(source_family, str) or assignments.get(source_family) != board_split:
            raise _error("V19_SYMBOL_EVALUATION_SPLIT_INVALID", "Board split is invalid.")
        prior = seen_sources.setdefault(source_family, cast(str, board_split))
        if prior != board_split:
            raise _error("V19_SYMBOL_EVALUATION_SPLIT_LEAKAGE", "Source family leaked.")
        raw_cells = board.get("cells")
        if (
            not isinstance(raw_cells, Sequence)
            or isinstance(raw_cells, str | bytes)
            or len(raw_cells) != 15
        ):
            raise _error("V19_SYMBOL_EVALUATION_BOARD_INCOMPLETE", "A board is incomplete.")
        for expected_index, raw_cell in enumerate(raw_cells):
            cell = _mapping(raw_cell, "cell")
            if cell.get("cellIndex") != expected_index:
                raise _error(
                    "V19_SYMBOL_EVALUATION_BOARD_INCOMPLETE", "Cells are not row-major."
                )
            relative = cell.get("cropRelativePath")
            checksum = cell.get("cropChecksumSha256")
            if not isinstance(relative, str) or not isinstance(checksum, str):
                raise _error("V19_SYMBOL_EVALUATION_CROP_INVALID", "Crop metadata is invalid.")
            path = _managed_path(output_root, relative)
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != checksum:
                raise _error("V19_SYMBOL_EVALUATION_CROP_DRIFT", "Crop checksum differs.")
            with Image.open(path) as image:
                rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
            production = production_preprocess_rgb(rgb, input_size=input_size)
            training = load_image_tensor(path, input_size).numpy()
            tensors.append(production)
            parity.append(bool(np.array_equal(production, training)))
            metadata.append(
                {
                    "boardId": cast(str, board["boardId"]),
                    "cellIndex": expected_index,
                    "cropChecksumSha256": checksum,
                    "sequenceNumber": cast(int, board["sequenceNumber"]),
                    "sourceFamily": source_family,
                    "stagingLabel": cast(str, board["stagingLabel"]),
                    "symbolCode": cast(str, cell["symbolCode"]),
                }
            )
    return metadata, tensors, parity


def _load_adapter(snapshot: Any, artifact_root: Path) -> LocalSymbolOnnxAdapter:
    root = artifact_root if snapshot.storage_root.value == "artifact" else Path.cwd()
    path = _managed_path(root, snapshot.onnx_relative_path)
    return LocalSymbolOnnxAdapter(
        path,
        expected_sha256=snapshot.onnx_checksum_sha256,
        class_codes=snapshot.class_codes,
        input_size=snapshot.input_size,
    )


def _load_descriptor(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict) or payload.get("version") != DESCRIPTOR_VERSION:
        raise _error("V19_SYMBOL_EVALUATION_DESCRIPTOR_INVALID", "Descriptor is invalid.")
    return cast(dict[str, object], payload)


def _managed_path(root: Path, relative_value: str) -> Path:
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise _error("V19_SYMBOL_EVALUATION_PATH_UNSAFE", "A managed path is unsafe.")
    resolved_root = root.resolve()
    path = resolved_root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(resolved_root):
        raise _error("V19_SYMBOL_EVALUATION_PATH_UNSAFE", "A path escapes storage.")
    return path


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _error("V19_SYMBOL_EVALUATION_COHORT_INVALID", f"{label} is invalid.")
    return cast(Mapping[str, object], value)


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _verify(path, content)
        return
    descriptor, name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            _verify(path, content)
    finally:
        temporary.unlink(missing_ok=True)


def _verify(path: Path, content: bytes) -> None:
    if not path.is_file() or path.read_bytes() != content:
        raise _error("V19_SYMBOL_EVALUATION_ARTIFACT_DRIFT", "Evaluation artifact differs.")


def _sha256(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise _error("V19_SYMBOL_EVALUATION_DESCRIPTOR_INVALID", "Checksum is invalid.")
    return value


def _error(code: str, message: str) -> V19SymbolResidualError:
    return V19SymbolResidualError(code, message)


if __name__ == "__main__":
    raise SystemExit(main())
