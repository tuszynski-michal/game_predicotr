"""Install the frozen grid engine models into the managed artifacts directory (TASK-0830).

One-time copy of the ``neural_grid`` exports named by the registry
(``game_predictor_api.domain.grid_engine_profiles``) into
``<ARTIFACT_ROOT>/models/grid-engine/<profile>/<version>/``:
``screen.onnx``, ``board.onnx``, ``bundle.json``, ``preset.json`` (the preset
of the bundle, canonical JSON) and ``manifest.json``.

Every source file is checked against the registry SHA-256 before anything is
written; the copy goes to a temporary sibling directory, is verified again and
is then renamed into place. An already installed, intact version is left
untouched. An existing target that differs from the registry is never
overwritten: the script stops and names the difference. The exports are only
read.

The artifact root is resolved like the API does
(``GAME_PREDICTOR_ARTIFACT_ROOT``, default ``artifacts`` relative to the
current directory); ``--artifact-root`` overrides it. Run from the repository
root of the checkout that serves the API, e.g.::

    $runs = '<lab>\\neural-grid-runs'
    .venv\\Scripts\\python.exe scripts/install_grid_engine_models.py `
        --source "grid_profile_777_v2=$runs\\<run 1>\\exports\\2cd19738367121e6-round3" `
        --source "grid_profile_mumie_v1=$runs\\<run 3>\\exports\\iteration03-f896da7196431be2"
    .venv\\Scripts\\python.exe scripts/install_grid_engine_models.py --check

``<run 1>`` is ``43933ac8d7d443c8b9079630a83de2e6`` and ``<run 3>`` is
``5bc981568c3f42bd96f6f9238e57aedc`` (registry ``run_id``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import (
    GRID_ENGINE_MANIFEST_FILE_NAME,
    GRID_ENGINE_PROFILES,
    GridEngineModelError,
    GridEngineModelStatus,
    GridEngineModelVersion,
    grid_engine_manifest,
    grid_engine_profile_for,
)
from game_predictor_api.storage.grid_engine_model_store import (
    ManagedGridEngineModelStore,
    file_sha256,
    inspect_model_directory,
)

COPIED_FILES = ("screen.onnx", "board.onnx", "bundle.json")
PRESET_FILE = "preset.json"


@dataclass(frozen=True, slots=True)
class InstallResult:
    profile: str
    version: str
    directory: Path
    outcome: str  # "installed" | "already_installed"


def preset_bytes(bundle: dict[str, Any]) -> bytes:
    """Canonical serialization of the bundle preset; its SHA-256 is in the registry."""

    return (
        json.dumps(bundle["preset"], indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def manifest_bytes(version: GridEngineModelVersion) -> bytes:
    return (json.dumps(grid_engine_manifest(version), indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _expected(version: GridEngineModelVersion, name: str) -> tuple[str, int]:
    for file in version.files:
        if file.name == name:
            return file.sha256, file.size_bytes
    raise GridEngineModelError(
        "GRID_ENGINE_REGISTRY_FILE_UNKNOWN",
        "The registry does not list this file.",
        details={"profile": version.profile.value, "file": name},
    )


def _verify_source(version: GridEngineModelVersion, source: Path) -> bytes:
    """Check the export against the registry and return the preset bytes to write."""

    if not source.is_dir():
        raise GridEngineModelError(
            "GRID_ENGINE_SOURCE_MISSING",
            "The export directory does not exist.",
            details={"profile": version.profile.value, "source": str(source)},
        )
    for name in COPIED_FILES:
        path = source / name
        expected_sha, expected_size = _expected(version, name)
        if not path.is_file():
            raise GridEngineModelError(
                "GRID_ENGINE_SOURCE_FILE_MISSING",
                "The export lacks a registered file.",
                details={"profile": version.profile.value, "file": str(path)},
            )
        actual = file_sha256(path)
        if actual != expected_sha or path.stat().st_size != expected_size:
            raise GridEngineModelError(
                "GRID_ENGINE_SOURCE_CHECKSUM_MISMATCH",
                "The export file differs from the registry.",
                details={
                    "profile": version.profile.value,
                    "file": str(path),
                    "expectedSha256": expected_sha,
                    "actualSha256": actual,
                },
            )
    bundle = json.loads((source / "bundle.json").read_text(encoding="utf-8"))
    identity = {
        "preset_fingerprint": (bundle.get("preset_fingerprint"), version.preset_fingerprint),
        "weights_sha256": (bundle.get("weights_sha256"), version.weights_sha256),
        "run_id": (bundle.get("provenance", {}).get("run_id"), version.run_id),
        "checkpoint_sha256": (
            bundle.get("provenance", {}).get("checkpoint_sha256"),
            version.checkpoint_sha256,
        ),
        "preset.name": (bundle.get("preset", {}).get("name"), version.preset_name),
    }
    for field, (actual_value, expected_value) in identity.items():
        if actual_value != expected_value:
            raise GridEngineModelError(
                "GRID_ENGINE_SOURCE_IDENTITY_MISMATCH",
                "The export bundle does not describe the registered model.",
                details={
                    "profile": version.profile.value,
                    "field": field,
                    "expected": expected_value,
                    "actual": actual_value,
                },
            )
    preset = preset_bytes(bundle)
    expected_sha, expected_size = _expected(version, PRESET_FILE)
    if hashlib.sha256(preset).hexdigest() != expected_sha or len(preset) != expected_size:
        raise GridEngineModelError(
            "GRID_ENGINE_SOURCE_CHECKSUM_MISMATCH",
            "The canonical preset differs from the registry.",
            details={"profile": version.profile.value, "file": PRESET_FILE},
        )
    return preset


def install_version(
    version: GridEngineModelVersion, source: Path, artifact_root: Path
) -> InstallResult:
    store = ManagedGridEngineModelStore(artifact_root)
    target = store.directory(version)
    if target.exists():
        state = store.inspect(version)
        if state.status is GridEngineModelStatus.AVAILABLE:
            return InstallResult(
                version.profile.value, version.version, target, "already_installed"
            )
        raise GridEngineModelError(
            "GRID_ENGINE_TARGET_CONFLICT",
            "The managed directory exists but differs from the registry; it is not overwritten.",
            details={
                "directory": str(target),
                "status": state.status.value,
                "manifest": state.manifest_status.value,
                "files": {item.file.name: item.status.value for item in state.files},
            },
        )
    preset = _verify_source(version, source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{version.version}.installing-{uuid.uuid4().hex[:12]}"
    staging.mkdir()
    try:
        for name in COPIED_FILES:
            shutil.copyfile(source / name, staging / name)
        (staging / PRESET_FILE).write_bytes(preset)
        (staging / GRID_ENGINE_MANIFEST_FILE_NAME).write_bytes(manifest_bytes(version))
        for name in (*COPIED_FILES, PRESET_FILE):
            with (staging / name).open("rb+") as stream:
                os.fsync(stream.fileno())
        staged = inspect_model_directory(version, staging)
        if staged.status is not GridEngineModelStatus.AVAILABLE:
            raise GridEngineModelError(
                staged.reason_code,
                "The staged copy does not match the registry.",
                details={"files": {item.file.name: item.status.value for item in staged.files}},
            )
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    final = store.inspect(version)
    if final.status is not GridEngineModelStatus.AVAILABLE:
        raise GridEngineModelError(
            final.reason_code,
            "The installed model does not match the registry.",
            details={"directory": str(target)},
        )
    return InstallResult(version.profile.value, version.version, target, "installed")


def resolve_artifact_root(explicit: str | None) -> Path:
    if explicit is not None:
        return Path(explicit).resolve()
    value = os.environ.get("GAME_PREDICTOR_ARTIFACT_ROOT", "artifacts").strip()
    if not value:
        raise SystemExit("GAME_PREDICTOR_ARTIFACT_ROOT cannot be empty.")
    return Path(value).resolve()


def _parse_sources(values: Sequence[str]) -> dict[GameShapeGeometryConfiguration, Path]:
    sources: dict[GameShapeGeometryConfiguration, Path] = {}
    for value in values:
        profile_value, separator, path = value.partition("=")
        if not separator or not path:
            raise SystemExit(f"--source must be <profile>=<export directory>: {value}")
        try:
            configuration = GameShapeGeometryConfiguration(profile_value)
        except ValueError:
            raise SystemExit(f"Unknown grid engine profile: {profile_value}") from None
        if grid_engine_profile_for(configuration) is None:
            raise SystemExit(f"Not a grid engine profile: {profile_value}")
        sources[configuration] = Path(path)
    return sources


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="<profile>=<export directory>; repeat for every profile to install",
    )
    parser.add_argument("--artifact-root", default=None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report the state of every registered model; writes nothing",
    )
    args = parser.parse_args(argv)
    artifact_root = resolve_artifact_root(args.artifact_root)
    store = ManagedGridEngineModelStore(artifact_root)
    print(f"artifact root: {artifact_root}")
    if args.check:
        failed = False
        for profile in GRID_ENGINE_PROFILES:
            state = store.inspect(profile.current)
            failed |= state.status is not GridEngineModelStatus.AVAILABLE
            print(
                f"{profile.configuration.value} {profile.current_version}: {state.status.value} "
                f"({store.directory(profile.current)})"
            )
        return 1 if failed else 0
    sources = _parse_sources(args.source)
    if not sources:
        parser.error("at least one --source is required (or --check)")
    for configuration, source in sources.items():
        selected = grid_engine_profile_for(configuration)
        assert selected is not None
        try:
            result = install_version(selected.current, source, artifact_root)
        except GridEngineModelError as error:
            print(json.dumps({"code": error.code, "details": error.details}, default=str))
            return 2
        print(f"{result.profile} {result.version}: {result.outcome} -> {result.directory}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
