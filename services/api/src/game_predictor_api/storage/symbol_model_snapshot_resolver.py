"""Resolve and verify the exact active symbol model pinned to a new image import."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.application.jobs import SymbolModelSnapshotResolver
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
    bootstrap_symbol_model_snapshot,
)
from game_predictor_api.storage.models import (
    GameSymbolModelActivationModel,
    SymbolModel,
    SymbolModelIterationModel,
)


class SqlAlchemySymbolModelSnapshotResolver(SymbolModelSnapshotResolver):
    def __init__(self, session: Session, *, artifact_root: Path) -> None:
        self._session = session
        self._artifact_root = artifact_root.resolve()

    def resolve(self, *, game_id: UUID) -> SymbolModelJobSnapshot:
        active_catalog_codes = tuple(
            self._session.scalars(
                select(SymbolModel.code)
                .where(
                    SymbolModel.game_id == game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
                .order_by(SymbolModel.code)
            )
        )
        activation = self._session.scalar(
            select(GameSymbolModelActivationModel)
            .where(GameSymbolModelActivationModel.game_id == game_id)
            .order_by(
                GameSymbolModelActivationModel.activation_number.desc(),
            )
            .limit(1)
        )
        if activation is None:
            ready_candidate_id = self._session.scalar(
                select(SymbolModelIterationModel.id)
                .where(
                    SymbolModelIterationModel.game_id == game_id,
                    SymbolModelIterationModel.status == "candidate_ready",
                )
                .order_by(SymbolModelIterationModel.iteration_number.desc())
                .limit(1)
            )
            if ready_candidate_id is not None:
                raise JobConflictError(
                    "SYMBOL_MODEL_ACTIVATION_REQUIRED",
                    "A verified symbol model candidate is ready for this game. "
                    "Activate it before starting a new inference job.",
                )
            bootstrap = bootstrap_symbol_model_snapshot()
            if tuple(sorted(bootstrap.class_codes)) != active_catalog_codes:
                raise JobConflictError(
                    "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED",
                    "The bootstrap symbol model does not match this game's active symbol "
                    "catalog. Train and activate a game-specific model before starting "
                    "inference.",
                )
            return bootstrap
        iteration = self._session.get(SymbolModelIterationModel, activation.model_iteration_id)
        if iteration is None or iteration.game_id != game_id:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_ITERATION_MISSING",
                "The active symbol model iteration is unavailable.",
            )
        manifest_path = self._managed_path(iteration.candidate_manifest_relative_path)
        manifest = self._verified_json(
            manifest_path,
            iteration.candidate_manifest_checksum_sha256,
            "SYMBOL_MODEL_ACTIVE_MANIFEST_INVALID",
        )
        artifacts = _mapping(manifest.get("artifacts"), "artifacts")
        onnx = _mapping(artifacts.get("onnx"), "onnx")
        classes = _mapping(artifacts.get("classes"), "classes")
        calibration = _mapping(artifacts.get("calibration"), "calibration")
        onnx_path, onnx_checksum = self._verified_artifact(onnx)
        classes_path, _classes_checksum = self._verified_artifact(classes)
        calibration_path, _calibration_checksum = self._verified_artifact(calibration)
        class_payload = self._read_json(classes_path, "SYMBOL_MODEL_ACTIVE_CLASSES_INVALID")
        calibration_payload = self._read_json(
            calibration_path, "SYMBOL_MODEL_ACTIVE_CALIBRATION_INVALID"
        )
        class_codes_value = class_payload.get("classCodes")
        if (
            not isinstance(class_codes_value, list)
            or not class_codes_value
            or not all(isinstance(value, str) and value for value in class_codes_value)
            or len(set(class_codes_value)) != len(class_codes_value)
        ):
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_CLASSES_INVALID", "Active model class catalog is invalid."
            )
        temperature = calibration_payload.get("temperature")
        input_size = iteration.configuration_payload.get("inputSize")
        if (
            not isinstance(temperature, int | float)
            or isinstance(temperature, bool)
            or float(temperature) <= 0
            or not isinstance(input_size, int)
            or isinstance(input_size, bool)
            or input_size < 16
        ):
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_RUNTIME_INVALID",
                "Active model calibration or input contract is invalid.",
            )
        manifest_codes = manifest.get("classCodes")
        if manifest_codes != class_codes_value:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_CLASSES_DRIFT",
                "Active model manifest and class catalog differ.",
            )
        if tuple(sorted(cast(list[str], class_codes_value))) != active_catalog_codes:
            raise JobConflictError(
                "SYMBOL_MODEL_CLASS_CATALOG_MISMATCH",
                "The active symbol model classes do not match the active game catalog.",
            )
        return SymbolModelJobSnapshot(
            iteration_id=iteration.id,
            model_version="spatial-symbol-cnn-onnx-v1",
            manifest_checksum_sha256=cast(str, iteration.candidate_manifest_checksum_sha256),
            onnx_checksum_sha256=onnx_checksum,
            onnx_relative_path=onnx_path.relative_to(self._artifact_root).as_posix(),
            storage_root=SymbolModelStorageRoot.ARTIFACT,
            class_codes=tuple(cast(list[str], class_codes_value)),
            input_size=input_size,
            temperature=float(temperature),
        )

    def _managed_path(self, relative_path: str | None) -> Path:
        if relative_path is None:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_MANIFEST_MISSING", "Active model manifest is missing."
            )
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_PATH_INVALID", "Active model artifact path is unsafe."
            )
        path = self._artifact_root.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(self._artifact_root):
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_PATH_INVALID", "Active model artifact escapes storage."
            )
        return path

    def _verified_json(
        self, path: Path, expected_checksum: str | None, error_code: str
    ) -> dict[str, object]:
        if expected_checksum is None:
            raise JobConflictError(error_code, "Active model checksum is missing.")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise JobConflictError(error_code, "Active model artifact is unavailable.") from error
        if hashlib.sha256(content).hexdigest() != expected_checksum:
            raise JobConflictError(error_code, "Active model artifact checksum changed.")
        return self._decode_json(content, error_code)

    def _verified_artifact(self, value: dict[str, object]) -> tuple[Path, str]:
        relative_path = value.get("relativePath")
        checksum = value.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(checksum, str):
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_MANIFEST_INVALID", "Active model artifact entry is invalid."
            )
        path = self._managed_path(relative_path)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_ARTIFACT_MISSING", "Active model artifact is unavailable."
            ) from error
        if hashlib.sha256(content).hexdigest() != checksum:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVE_ARTIFACT_DRIFT", "Active model artifact checksum changed."
            )
        return path, checksum

    def _read_json(self, path: Path, error_code: str) -> dict[str, object]:
        try:
            return self._decode_json(path.read_bytes(), error_code)
        except OSError as error:
            raise JobConflictError(error_code, "Active model metadata is unavailable.") from error

    @staticmethod
    def _decode_json(content: bytes, error_code: str) -> dict[str, object]:
        try:
            value = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise JobConflictError(error_code, "Active model JSON metadata is invalid.") from error
        if not isinstance(value, dict):
            raise JobConflictError(error_code, "Active model JSON metadata must be an object.")
        return cast(dict[str, object], value)


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise JobConflictError(
            "SYMBOL_MODEL_ACTIVE_MANIFEST_INVALID", f"Active model {name} is invalid."
        )
    return cast(dict[str, object], value)


__all__ = ["SqlAlchemySymbolModelSnapshotResolver", "SymbolModelSnapshotResolver"]
