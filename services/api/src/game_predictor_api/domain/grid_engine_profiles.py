"""Registry of the frozen grid engine models behind the game's page format (TASK-0830).

A game's ``shape_geometry_configuration`` may name a grid engine profile
(``grid_profile_777_v2``, ``grid_profile_mumie_v1``). Each profile points to a
frozen ``neural_grid`` export (ONNX screen and board stages, the export bundle
and its preset) copied once into the managed directory
``<ARTIFACT_ROOT>/models/grid-engine/<profile>/<version>/`` by
``scripts/install_grid_engine_models.py``. The repository keeps only this
registry: the SHA-256 and metadata of every file. A missing file, a different
SHA-256 or a manifest that differs from the registry is an explicit error;
there is no fallback to another version, profile or engine.

A newer model of the same game is a new ``GridEngineModelVersion`` of the same
profile (and a new ``current_version``), never a new value of the game field.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final

from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration

GRID_ENGINE_MODELS_RELATIVE_ROOT: Final = PurePosixPath("models/grid-engine")
GRID_ENGINE_MANIFEST_FILE_NAME: Final = "manifest.json"
GRID_ENGINE_MANIFEST_SCHEMA_VERSION: Final = "grid-engine-model-manifest-v1"
NEURAL_GRID_MODEL_KIND: Final = "neural_grid"
_COMPARISON_REPORT: Final = "ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md"


class GridEngineModelStatus(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    CHECKSUM_MISMATCH = "checksum_mismatch"


class GridEngineModelError(RuntimeError):
    """A registered model cannot be used as frozen; never silently replaced."""

    def __init__(self, code: str, message: str, *, details: dict[str, object]) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class GridEngineModelFile:
    name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class GridEngineReportResult:
    """One V3-C comparison result copied verbatim into the manifest."""

    dataset: str
    result: str


@dataclass(frozen=True, slots=True)
class GridEngineModelVersion:
    profile: GameShapeGeometryConfiguration
    version: str
    model_kind: str
    model_version: str
    bundle_format: str
    run_id: str
    export_id: str
    preset_name: str
    preset_fingerprint: str
    weights_sha256: str
    checkpoint_sha256: str
    snapshot_id: str
    frozen_on: str
    selection_reason: str
    report_results: tuple[GridEngineReportResult, ...]
    files: tuple[GridEngineModelFile, ...]

    @property
    def relative_directory(self) -> PurePosixPath:
        return GRID_ENGINE_MODELS_RELATIVE_ROOT / self.profile.value / self.version


@dataclass(frozen=True, slots=True)
class GridEngineProfile:
    configuration: GameShapeGeometryConfiguration
    label: str
    description: str
    current_version: str
    versions: tuple[GridEngineModelVersion, ...]

    @property
    def current(self) -> GridEngineModelVersion:
        for version in self.versions:
            if version.version == self.current_version:
                return version
        raise GridEngineModelError(
            "GRID_ENGINE_PROFILE_VERSION_UNKNOWN",
            "The current version of the grid engine profile is not registered.",
            details={"profile": self.configuration.value, "version": self.current_version},
        )


@dataclass(frozen=True, slots=True)
class GridEngineModelFileState:
    file: GridEngineModelFile
    status: GridEngineModelStatus


@dataclass(frozen=True, slots=True)
class GridEngineModelState:
    """Verified state of one registered model version in the managed directory."""

    version: GridEngineModelVersion
    status: GridEngineModelStatus
    reason_code: str
    message: str
    manifest_status: GridEngineModelStatus
    files: tuple[GridEngineModelFileState, ...]


_NEURAL_GRID_MODEL_VERSION: Final = "neural-grid-v1"
_NEURAL_GRID_BUNDLE_FORMAT: Final = "neural-grid-bundle-v1"
_SNAPSHOT_PRODUCTION_GEOMETRY_SPLIT_V2: Final = (
    "286f2e370aa84437c63fcffe202f01260d6ca13aee317eb8c11cac2ad0f2df59"
)

_PROFILE_777_V2_V1: Final = GridEngineModelVersion(
    profile=GameShapeGeometryConfiguration.GRID_PROFILE_777_V2,
    version="v1",
    model_kind=NEURAL_GRID_MODEL_KIND,
    model_version=_NEURAL_GRID_MODEL_VERSION,
    bundle_format=_NEURAL_GRID_BUNDLE_FORMAT,
    run_id="43933ac8d7d443c8b9079630a83de2e6",
    export_id="2cd19738367121e6-round3",
    preset_name="A",
    preset_fingerprint="027b5db151b7094e06e69f6910d705a944312afe4341d37ebbc72c1782f0701d",
    weights_sha256="19b8d1382d5fe13b7e054b2d4eb846c25f7a91f680fa113b7d1d30571cdc80f9",
    checkpoint_sha256="2cd19738367121e6a36cf0630b4fd7d275d1966fbe25ca73d1329fa979183fe8",
    snapshot_id=_SNAPSHOT_PRODUCTION_GEOMETRY_SPLIT_V2,
    frozen_on="2026-10-04",
    selection_reason=(
        "Run 1, preset A, round 3: chosen on development before any holdout read; "
        "the hybrid_v3 gate thresholds were calibrated for this model (V3-C)."
    ),
    report_results=(
        GridEngineReportResult(
            "development 777 (600 photos)",
            "complete and correct 554/600 = 92.3%; image-macro 0.0029; false boards 0",
        ),
        GridEngineReportResult(
            "gold 777 (459 G boards)",
            "correct G boards 443/459 = 96.5%; all-G photos 21/22",
        ),
        GridEngineReportResult("Reels holdout (final_test)", "correct boards 29/30"),
        GridEngineReportResult("Treasure holdout (unseen_game)", "correct boards 30/30"),
        GridEngineReportResult(
            "Mumie holdout (D-490, 4 photos)",
            "complete and correct 4/4; boards 36/36; NME median 0.0067",
        ),
    ),
    files=(
        GridEngineModelFile(
            "screen.onnx",
            "497fad194a6454d9ceb3edf8a1157d4f46c4676f407474cbfafd513d4608b3b4",
            13_808_279,
        ),
        GridEngineModelFile(
            "board.onnx",
            "0ec72d16a0c666523f1e85b73288e017c3905a79d116331290973093f4576c92",
            13_553_174,
        ),
        GridEngineModelFile(
            "bundle.json",
            "64d815d8af168f79fd53f0dcb9e80823c3006ebae3e08225fc9e25f178c27b7b",
            5_336,
        ),
        GridEngineModelFile(
            "preset.json",
            "77e6b9ce792798b58b4c403d6d482fdfd4be43d16d3455cfe8af1345dd7381d3",
            3_637,
        ),
    ),
)

_PROFILE_MUMIE_V1_V1: Final = GridEngineModelVersion(
    profile=GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1,
    version="v1",
    model_kind=NEURAL_GRID_MODEL_KIND,
    model_version=_NEURAL_GRID_MODEL_VERSION,
    bundle_format=_NEURAL_GRID_BUNDLE_FORMAT,
    run_id="5bc981568c3f42bd96f6f9238e57aedc",
    export_id="iteration03-f896da7196431be2",
    preset_name="D",
    preset_fingerprint="b94a9627df4c2d0886b43776f1a80b406de5d124c36c997ada2b5f93c5d1cbd9",
    weights_sha256="473d773897aae999f2a86774d77c1139f62f36fc9b8eb80a17f68256016613a1",
    checkpoint_sha256="f896da7196431be2d6dc7b863cfa69f6ec27fd63cb3d3e00ff7acd1f2b745138",
    snapshot_id=_SNAPSHOT_PRODUCTION_GEOMETRY_SPLIT_V2,
    frozen_on="2026-10-04",
    selection_reason=(
        "Run 3 Mumie fine-tune (D-490), iteration 3: 79% of the proposals of the last "
        "batch accepted unchanged; Mumie holdout 36/36 (the holdout also selected the "
        "state of every iteration, so it is not an independent test)."
    ),
    report_results=(
        GridEngineReportResult(
            "development 777 (600 photos)",
            "complete and correct 546/600 = 91.0%; image-macro 0.0028; false boards 0",
        ),
        GridEngineReportResult(
            "gold 777 (459 G boards)",
            "correct G boards 446/459 = 97.2%; all-G photos 22/22",
        ),
        GridEngineReportResult("Reels holdout (final_test)", "correct boards 29/30"),
        GridEngineReportResult("Treasure holdout (unseen_game)", "correct boards 30/30"),
        GridEngineReportResult(
            "Mumie holdout (D-490, 4 photos)",
            "complete and correct 4/4; boards 36/36; NME median 0.0029",
        ),
    ),
    files=(
        GridEngineModelFile(
            "screen.onnx",
            "877a2d4502022e4f99e80afe27ce438528864be2351cb3d402ee8daa9d54ca43",
            13_808_279,
        ),
        GridEngineModelFile(
            "board.onnx",
            "3498733a8cc4a5faefa640c3acef21d06086d00d8524d1fb289b02a862bcdd7d",
            13_553_174,
        ),
        GridEngineModelFile(
            "bundle.json",
            "024dc1f0d5bc46515cb4173e04c474ea864d730b4d48abd6f418bacfa9b43566",
            7_243,
        ),
        GridEngineModelFile(
            "preset.json",
            "946b5a6cb75d836c61f2a549d0e338f4175eae1e906d26a211428ec2f6181317",
            5_398,
        ),
    ),
)

GRID_ENGINE_PROFILES: Final[tuple[GridEngineProfile, ...]] = (
    GridEngineProfile(
        configuration=GameShapeGeometryConfiguration.GRID_PROFILE_777_V2,
        label="777 v2",
        description=(
            "Model neural_grid runu 1 (preset A, runda 3), trenowany na 777. "
            "Profil służy także kolejnym wersjom gry 777 (np. 777 v3)."
        ),
        current_version=_PROFILE_777_V2_V1.version,
        versions=(_PROFILE_777_V2_V1,),
    ),
    GridEngineProfile(
        configuration=GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1,
        label="Mumie",
        description=("Model neural_grid doszkolony na Mumiach (run 3, iteracja 3, D-490)."),
        current_version=_PROFILE_MUMIE_V1_V1.version,
        versions=(_PROFILE_MUMIE_V1_V1,),
    ),
)


def grid_engine_profile_for(
    configuration: GameShapeGeometryConfiguration | None,
) -> GridEngineProfile | None:
    for profile in GRID_ENGINE_PROFILES:
        if profile.configuration is configuration:
            return profile
    return None


def grid_engine_manifest(version: GridEngineModelVersion) -> dict[str, object]:
    """The exact manifest stored next to the files; a pure function of the registry."""

    return {
        "schemaVersion": GRID_ENGINE_MANIFEST_SCHEMA_VERSION,
        "profile": version.profile.value,
        "version": version.version,
        "modelKind": version.model_kind,
        "modelVersion": version.model_version,
        "bundleFormat": version.bundle_format,
        "runId": version.run_id,
        "exportId": version.export_id,
        "preset": version.preset_name,
        "presetFingerprint": version.preset_fingerprint,
        "weightsSha256": version.weights_sha256,
        "checkpointSha256": version.checkpoint_sha256,
        "snapshotId": version.snapshot_id,
        "frozenOn": version.frozen_on,
        "selectionReason": version.selection_reason,
        "report": _COMPARISON_REPORT,
        "reportResults": [
            {"dataset": result.dataset, "result": result.result}
            for result in version.report_results
        ],
        "files": [
            {"name": file.name, "sha256": file.sha256, "sizeBytes": file.size_bytes}
            for file in version.files
        ],
    }


__all__ = [
    "GRID_ENGINE_MANIFEST_FILE_NAME",
    "GRID_ENGINE_MANIFEST_SCHEMA_VERSION",
    "GRID_ENGINE_MODELS_RELATIVE_ROOT",
    "GRID_ENGINE_PROFILES",
    "NEURAL_GRID_MODEL_KIND",
    "GridEngineModelError",
    "GridEngineModelFile",
    "GridEngineModelFileState",
    "GridEngineModelState",
    "GridEngineModelStatus",
    "GridEngineModelVersion",
    "GridEngineProfile",
    "GridEngineReportResult",
    "grid_engine_manifest",
    "grid_engine_profile_for",
]
