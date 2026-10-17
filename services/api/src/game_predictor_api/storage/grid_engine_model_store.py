"""Managed directory of the frozen grid engine models (TASK-0830).

Files live under ``<ARTIFACT_ROOT>/models/grid-engine/<profile>/<version>/``
and are verified against the frozen registry or catalogue descriptor: size and
SHA-256 of each file and the exact manifest. ``require`` is the only entry
point for code that will load a model and raises instead of falling back.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from game_predictor_api.domain.grid_engine_profiles import (
    GRID_ENGINE_MANIFEST_FILE_NAME,
    GridEngineModelError,
    GridEngineModelFile,
    GridEngineModelFileState,
    GridEngineModelState,
    GridEngineModelStatus,
    GridEngineModelVersion,
    grid_engine_manifest,
)

_CHUNK_BYTES: Final = 1024 * 1024
TRAINING_RECEIPT: Final = "receipt.json"


def training_base_files(version: GridEngineModelVersion) -> tuple[GridEngineModelFile, ...]:
    """Pinned training state, independent of the unchanged inference manifest."""
    if version.checkpoint_size_bytes <= 0 or version.weights_size_bytes <= 0:
        raise GridEngineModelError(
            "GRID_ENGINE_TRAINING_UNREGISTERED",
            "Training artifacts lack pinned sizes.",
            details={"profile": version.profile.value, "version": version.version},
        )
    return (
        GridEngineModelFile(
            "checkpoint.pt", version.checkpoint_sha256, version.checkpoint_size_bytes
        ),
        GridEngineModelFile("weights.pt", version.weights_sha256, version.weights_size_bytes),
        *(file for file in version.files if file.name in {"bundle.json", "preset.json"}),
    )


def training_base_identity(version: GridEngineModelVersion) -> dict[str, object]:
    return {
        "schemaVersion": "grid-engine-training-base-v1",
        "model": grid_engine_manifest(version),
        "files": [
            {"name": file.name, "sha256": file.sha256, "sizeBytes": file.size_bytes}
            for file in training_base_files(version)
        ],
    }


def receipt_bytes(payload: dict[str, object]) -> bytes:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return (
        json.dumps(
            {"payload": payload, "sha256": hashlib.sha256(encoded).hexdigest()},
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def require_training_directory(version: GridEngineModelVersion, directory: Path) -> Path:
    """Validate receipt lineage and all bytes without consulting original C sources."""
    try:
        if (directory / TRAINING_RECEIPT).is_symlink():
            raise ValueError("linked receipt")
        envelope = json.loads((directory / TRAINING_RECEIPT).read_text("utf-8"))
        payload = envelope["payload"]
        if not isinstance(payload, dict):
            raise ValueError("receipt payload")
        if receipt_bytes(payload) != (directory / TRAINING_RECEIPT).read_bytes():
            raise ValueError("receipt checksum")
        identity = training_base_identity(version)
        if any(payload.get(key) != value for key, value in identity.items()):
            raise ValueError("receipt lineage")
        sources = payload.get("sources")
        names = {file.name for file in training_base_files(version)}
        if (
            not isinstance(sources, dict)
            or sources.keys() != names
            or any(
                not isinstance(value, str) or not Path(value).is_absolute()
                for value in sources.values()
            )
        ):
            raise ValueError("receipt provenance")
        if directory.is_symlink() or directory.is_junction():
            raise ValueError("linked training directory")
        if {path.name for path in directory.iterdir()} != names | {TRAINING_RECEIPT}:
            raise ValueError("unexpected training artifacts")
        for file in training_base_files(version):
            path = directory / file.name
            if path.is_symlink() or _file_status(path, file) is not GridEngineModelStatus.AVAILABLE:
                raise ValueError(file.name)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise GridEngineModelError(
            "GRID_ENGINE_TRAINING_INVALID",
            "Training base is missing or differs from registry.",
            details={"directory": str(directory), "reason": str(error)},
        ) from error
    return directory / "checkpoint.pt"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


class ManagedGridEngineModelStore:
    """Read-only verification of the managed model directory."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    def directory(self, version: GridEngineModelVersion) -> Path:
        return self._artifact_root.joinpath(*version.relative_directory.parts)

    def inspect(self, version: GridEngineModelVersion) -> GridEngineModelState:
        return inspect_model_directory(version, self.directory(version))

    def training_directory(self, version: GridEngineModelVersion) -> Path:
        return self.directory(version) / "training-base"

    def require_training_base(self, version: GridEngineModelVersion) -> Path:
        for path in (self.training_directory(version), *self.training_directory(version).parents):
            if path.is_symlink() or path.is_junction():
                raise GridEngineModelError(
                    "GRID_ENGINE_TRAINING_INVALID",
                    "Linked managed directory refused.",
                    details={"directory": str(path)},
                )
        self.require(version)
        return require_training_directory(version, self.training_directory(version))

    def require(self, version: GridEngineModelVersion) -> Path:
        """Return the verified model directory or raise; there is no fallback."""

        if version.catalogue_manifest_json is not None:
            directory = self.directory(version)
            root = (self._artifact_root / "models" / "grid-engine").resolve()
            targets = (
                directory / GRID_ENGINE_MANIFEST_FILE_NAME,
                *(directory / f.name for f in version.files),
            )
            if any(not target.resolve().is_relative_to(root) for target in targets):
                raise GridEngineModelError(
                    "GRID_MODEL_PATH_INVALID", "Model files escape managed storage.", details={}
                )
        state = self.inspect(version)
        if state.status is GridEngineModelStatus.AVAILABLE:
            return self.directory(version)
        raise GridEngineModelError(
            state.reason_code,
            "The registered grid engine model cannot be used.",
            details={
                "profile": version.profile.value,
                "version": version.version,
                "directory": version.relative_directory.as_posix(),
                "manifest": state.manifest_status.value,
                "files": {item.file.name: item.status.value for item in state.files},
            },
        )


def inspect_model_directory(
    version: GridEngineModelVersion, directory: Path
) -> GridEngineModelState:
    """Verify one directory against the registry entry (also used for a staged install)."""

    files = tuple(
        GridEngineModelFileState(file, _file_status(directory / file.name, file))
        for file in version.files
    )
    manifest_status = _manifest_status(directory / GRID_ENGINE_MANIFEST_FILE_NAME, version)
    statuses = {state.status for state in files} | {manifest_status}
    if GridEngineModelStatus.CHECKSUM_MISMATCH in statuses:
        status = GridEngineModelStatus.CHECKSUM_MISMATCH
        reason_code = "GRID_ENGINE_MODEL_CHECKSUM_MISMATCH"
        message = (
            "Plik modelu albo manifest różni się od rejestru (SHA-256); model nie zostanie użyty."
        )
    elif GridEngineModelStatus.MISSING in statuses:
        status = GridEngineModelStatus.MISSING
        reason_code = "GRID_ENGINE_MODEL_MISSING"
        message = (
            "Brak plików modelu w zarządzanym katalogu; uruchom "
            "scripts/install_grid_engine_models.py."
        )
    else:
        status = GridEngineModelStatus.AVAILABLE
        reason_code = "GRID_ENGINE_MODEL_AVAILABLE"
        message = "Model jest w zarządzanym katalogu i zgadza się z rejestrem."
    return GridEngineModelState(
        version=version,
        status=status,
        reason_code=reason_code,
        message=message,
        manifest_status=manifest_status,
        files=files,
    )


def _file_status(path: Path, expected: GridEngineModelFile) -> GridEngineModelStatus:
    if not path.is_file():
        return GridEngineModelStatus.MISSING
    if path.stat().st_size != expected.size_bytes or file_sha256(path) != expected.sha256:
        return GridEngineModelStatus.CHECKSUM_MISMATCH
    return GridEngineModelStatus.AVAILABLE


def _manifest_status(path: Path, version: GridEngineModelVersion) -> GridEngineModelStatus:
    if not path.is_file():
        return GridEngineModelStatus.MISSING
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return GridEngineModelStatus.CHECKSUM_MISMATCH
    if stored != grid_engine_manifest(version):
        return GridEngineModelStatus.CHECKSUM_MISMATCH
    return GridEngineModelStatus.AVAILABLE


__all__ = [
    "ManagedGridEngineModelStore",
    "file_sha256",
    "inspect_model_directory",
    "training_base_files",
    "training_base_identity",
    "receipt_bytes",
    "require_training_directory",
]
