"""Managed directory of the frozen grid engine models (TASK-0830).

Files live under ``<ARTIFACT_ROOT>/models/grid-engine/<profile>/<version>/``
and are verified against the in-code registry on every inspection: size and
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

    def require(self, version: GridEngineModelVersion) -> Path:
        """Return the verified model directory or raise; there is no fallback."""

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


__all__ = ["ManagedGridEngineModelStore", "file_sha256", "inspect_model_directory"]
