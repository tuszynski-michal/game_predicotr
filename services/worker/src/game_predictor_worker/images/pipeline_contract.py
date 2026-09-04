"""Canonical, versioned value contract for the local image pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import cast

PIPELINE_MANIFEST_VERSION = "image-pipeline-manifest-v1"
PIPELINE_ENVELOPE_VERSION = "image-pipeline-manifest-envelope-v1"
FILE_EXECUTION_KEY_VERSION = "image-file-execution-v1"
FILE_CHECKPOINT_VERSION = "image-pipeline-file-checkpoint-v1"
REVIEW_BOUNDARY_VERSION = "image-pipeline-review-boundary-v1"
VALIDATION_VERSION = "image-pipeline-validation-v1"
MANUAL_REVIEW_VERSION = "revisioned-whole-board-review-v1"

PIPELINE_STAGES = (
    "discovery",
    "normalization",
    "board_detection",
    "board_crops",
    "sequence_ocr",
    "symbol_inference",
    "manual_review",
    "validation",
)
CURRENT_NORMALIZATION_ADAPTER_VERSION = "image-normalization-v2-in-memory-source-v1"
VIRTUAL_GEOMETRY_ROLLOUT_VERSION = "virtual-geometry-rollout-snapshot-v1"
VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V2 = "virtual-geometry-rollout-snapshot-v2"
VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V3 = "virtual-geometry-rollout-snapshot-v3"
STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_VERSION = "structured-geometry-candidate-snapshot-v1"
STRUCTURED_GEOMETRY_ACTIVATION_SNAPSHOT_VERSION = "structured-geometry-activation-snapshot-v1"
STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION = "structured-opencv-independent-board-refinement-v1"
STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION = (
    "structured-opencv-independent-board-refinement-v2-pinned-preflight-v1"
)
VIRTUAL_CELL_RENDERER_VERSION = "virtual-cell-renderer-source-direct-v1"
SYMBOL_RGB_PREPROCESSING_VERSION = "rgb-resize64-normalize-half-v1"
MANUAL_REVIEW_PREDECESSOR = "symbol_inference"
MODEL_MATURITIES = frozenset(
    {
        "deterministic",
        "manual_review_only",
        "bootstrap_manual_review_only",
    }
)
CHECKPOINT_STATUSES = frozenset({"processing", "waiting_for_review", "completed"})
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ImagePipelineContractError(ValueError):
    """Stable validation error for image-pipeline value contracts."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GeometryRolloutMode(StrEnum):
    LEGACY = "legacy"
    STRUCTURED_SHADOW = "structured_shadow"
    STRUCTURED_REVIEW = "structured_review"
    STRUCTURED_DEFAULT = "structured_default"
    STRUCTURED_LATTICE_V3 = "structured_lattice_v3"


class CellAssetRolloutMode(StrEnum):
    LEGACY_FILES = "legacy_files"
    VIRTUAL_SHADOW = "virtual_shadow"
    VIRTUAL_DEFAULT = "virtual_default"


@dataclass(frozen=True, slots=True)
class StructuredGeometryCandidateSnapshot:
    """Exact measurement-only config pinned to one shadow job."""

    config_version: str
    config_checksum_sha256: str
    canonical_config_json: str

    def __post_init__(self) -> None:
        try:
            config = _object(json.loads(self.canonical_config_json), "candidateGeometry.config")
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ImagePipelineContractError(
                "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_INVALID",
                "The candidate geometry config must be canonical JSON.",
            ) from error
        canonical = canonical_json_bytes(config).decode("utf-8")
        checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if (
            canonical != self.canonical_config_json
            or config.get("configVersion") != self.config_version
            or checksum != self.config_checksum_sha256
            or config.get("maturity") != "experimental_measurement_only"
            or config.get("activationAllowed") is not False
            or config.get("requireDisjointTuningAndEvaluation") is not True
        ):
            raise ImagePipelineContractError(
                "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_INVALID",
                "The candidate geometry config must remain exact and measurement-only.",
            )

    @classmethod
    def from_config_payload(
        cls,
        value: object,
    ) -> StructuredGeometryCandidateSnapshot:
        config = _object(value, "candidateGeometry.config")
        canonical = canonical_json_bytes(config)
        return cls(
            config_version=_text(config.get("configVersion"), "candidateGeometry.configVersion"),
            config_checksum_sha256=hashlib.sha256(canonical).hexdigest(),
            canonical_config_json=canonical.decode("utf-8"),
        )

    @property
    def config_payload(self) -> dict[str, object]:
        return dict(_object(json.loads(self.canonical_config_json), "candidateGeometry.config"))

    def to_payload(self) -> dict[str, object]:
        return {
            "config": self.config_payload,
            "configChecksumSha256": self.config_checksum_sha256,
            "configVersion": self.config_version,
            "schemaVersion": STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_VERSION,
        }

    @classmethod
    def from_payload(cls, value: object) -> StructuredGeometryCandidateSnapshot:
        payload = _object(value, "candidateGeometry")
        if (
            set(payload)
            != {
                "config",
                "configChecksumSha256",
                "configVersion",
                "schemaVersion",
            }
            or payload.get("schemaVersion") != STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_VERSION
        ):
            raise ImagePipelineContractError(
                "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_INVALID",
                "The candidate geometry snapshot schema is unsupported.",
            )
        snapshot = cls.from_config_payload(payload.get("config"))
        if (
            payload.get("configVersion") != snapshot.config_version
            or payload.get("configChecksumSha256") != snapshot.config_checksum_sha256
        ):
            raise ImagePipelineContractError(
                "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_DRIFT",
                "The pinned candidate geometry config changed.",
            )
        return snapshot


@dataclass(frozen=True, slots=True)
class StructuredGeometryActivationSnapshot:
    """Exact accepted-primary config pinned to a new v3 job."""

    config_version: str
    config_checksum_sha256: str
    canonical_config_json: str

    def __post_init__(self) -> None:
        try:
            config = _object(json.loads(self.canonical_config_json), "activeLatticeGeometry.config")
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ImagePipelineContractError(
                "IMAGE_STRUCTURED_GEOMETRY_ACTIVATION_SNAPSHOT_INVALID",
                "The active lattice config must be canonical JSON.",
            ) from error
        canonical = canonical_json_bytes(config).decode("utf-8")
        checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        report_checksum = config.get("acceptanceReportChecksumSha256")
        if (
            canonical != self.canonical_config_json
            or config.get("configVersion") != self.config_version
            or checksum != self.config_checksum_sha256
            or config.get("maturity") != "accepted_primary"
            or config.get("activationAllowed") is not True
            or config.get("requireDisjointTuningAndEvaluation") is not True
            or not isinstance(report_checksum, str)
            or not SHA256_PATTERN.fullmatch(report_checksum)
        ):
            raise ImagePipelineContractError(
                "IMAGE_STRUCTURED_GEOMETRY_ACTIVATION_SNAPSHOT_INVALID",
                "The active lattice config must remain tied to an accepted report.",
            )

    @classmethod
    def from_config_payload(cls, value: object) -> StructuredGeometryActivationSnapshot:
        config = _object(value, "activeLatticeGeometry.config")
        canonical = canonical_json_bytes(config)
        return cls(
            config_version=_text(
                config.get("configVersion"), "activeLatticeGeometry.configVersion"
            ),
            config_checksum_sha256=hashlib.sha256(canonical).hexdigest(),
            canonical_config_json=canonical.decode("utf-8"),
        )

    @property
    def config_payload(self) -> dict[str, object]:
        return dict(_object(json.loads(self.canonical_config_json), "activeLatticeGeometry.config"))

    def to_payload(self) -> dict[str, object]:
        return {
            "config": self.config_payload,
            "configChecksumSha256": self.config_checksum_sha256,
            "configVersion": self.config_version,
            "schemaVersion": STRUCTURED_GEOMETRY_ACTIVATION_SNAPSHOT_VERSION,
        }

    @classmethod
    def from_payload(cls, value: object) -> StructuredGeometryActivationSnapshot:
        payload = _object(value, "activeLatticeGeometry")
        if (
            set(payload) != {"config", "configChecksumSha256", "configVersion", "schemaVersion"}
            or payload.get("schemaVersion") != STRUCTURED_GEOMETRY_ACTIVATION_SNAPSHOT_VERSION
        ):
            raise ImagePipelineContractError(
                "IMAGE_STRUCTURED_GEOMETRY_ACTIVATION_SNAPSHOT_INVALID",
                "The active lattice snapshot schema is unsupported.",
            )
        snapshot = cls.from_config_payload(payload.get("config"))
        if (
            payload.get("configVersion") != snapshot.config_version
            or payload.get("configChecksumSha256") != snapshot.config_checksum_sha256
        ):
            raise ImagePipelineContractError(
                "IMAGE_STRUCTURED_GEOMETRY_ACTIVATION_SNAPSHOT_DRIFT",
                "The pinned active lattice config changed.",
            )
        return snapshot


@dataclass(frozen=True, slots=True)
class GeometryPipelineRolloutSnapshot:
    """Immutable per-job rollout choice for the v0.10 image pipeline."""

    geometry_mode: GeometryRolloutMode
    cell_asset_mode: CellAssetRolloutMode
    rollout_revision: int
    geometry_engine_version: str
    virtual_renderer_version: str
    preprocessing_version: str
    candidate_geometry: StructuredGeometryCandidateSnapshot | None = None
    active_lattice_geometry: StructuredGeometryActivationSnapshot | None = None

    def __post_init__(self) -> None:
        if self.rollout_revision < 0 or any(
            not value.strip()
            for value in (
                self.geometry_engine_version,
                self.virtual_renderer_version,
                self.preprocessing_version,
            )
        ):
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID",
                "The geometry rollout snapshot requires versioned, non-negative provenance.",
            )
        allowed = {
            (GeometryRolloutMode.LEGACY, CellAssetRolloutMode.LEGACY_FILES),
            (GeometryRolloutMode.STRUCTURED_SHADOW, CellAssetRolloutMode.VIRTUAL_SHADOW),
            (GeometryRolloutMode.STRUCTURED_REVIEW, CellAssetRolloutMode.VIRTUAL_SHADOW),
            (GeometryRolloutMode.STRUCTURED_DEFAULT, CellAssetRolloutMode.VIRTUAL_DEFAULT),
            (GeometryRolloutMode.STRUCTURED_LATTICE_V3, CellAssetRolloutMode.VIRTUAL_DEFAULT),
        }
        if (self.geometry_mode, self.cell_asset_mode) not in allowed:
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID",
                "Legacy geometry and legacy files must be selected together.",
            )
        if (
            self.candidate_geometry is not None
            and self.geometry_mode is not GeometryRolloutMode.STRUCTURED_SHADOW
        ):
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID",
                "A measurement-only candidate can be pinned only in structured shadow mode.",
            )
        if (
            self.active_lattice_geometry is not None
            and self.geometry_mode is not GeometryRolloutMode.STRUCTURED_LATTICE_V3
        ):
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID",
                "An accepted lattice config can be pinned only in v3 mode.",
            )
        if (
            self.geometry_mode is GeometryRolloutMode.STRUCTURED_LATTICE_V3
            and self.active_lattice_geometry is None
        ):
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID",
                "Structured lattice v3 requires its accepted config snapshot.",
            )

    @property
    def is_legacy(self) -> bool:
        return (
            self.geometry_mode is GeometryRolloutMode.LEGACY
            and self.cell_asset_mode is CellAssetRolloutMode.LEGACY_FILES
        )

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(self.to_payload(include_checksum=False))
        ).hexdigest()

    def to_payload(self, *, include_checksum: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "cellAssetMode": self.cell_asset_mode.value,
            "geometryEngineVersion": self.geometry_engine_version,
            "geometryMode": self.geometry_mode.value,
            "preprocessingVersion": self.preprocessing_version,
            "rolloutRevision": self.rollout_revision,
            "schemaVersion": (
                VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V3
                if self.active_lattice_geometry is not None
                else VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V2
                if self.candidate_geometry is not None
                else VIRTUAL_GEOMETRY_ROLLOUT_VERSION
            ),
            "virtualRendererVersion": self.virtual_renderer_version,
        }
        if self.candidate_geometry is not None:
            payload["candidateGeometry"] = self.candidate_geometry.to_payload()
        if self.active_lattice_geometry is not None:
            payload["activeLatticeGeometry"] = self.active_lattice_geometry.to_payload()
        if include_checksum:
            payload["checksumSha256"] = self.checksum_sha256
        return payload

    @classmethod
    def from_payload(cls, value: object) -> GeometryPipelineRolloutSnapshot:
        payload = _object(value, "imageGeometryRollout")
        schema_version = payload.get("schemaVersion")
        if schema_version not in {
            VIRTUAL_GEOMETRY_ROLLOUT_VERSION,
            VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V2,
            VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V3,
        }:
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID",
                "The pinned geometry rollout schema is unsupported.",
            )
        candidate_geometry = (
            StructuredGeometryCandidateSnapshot.from_payload(payload.get("candidateGeometry"))
            if schema_version == VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V2
            else None
        )
        active_lattice_geometry = (
            StructuredGeometryActivationSnapshot.from_payload(payload.get("activeLatticeGeometry"))
            if schema_version == VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V3
            else None
        )
        rollout_revision = payload.get("rolloutRevision")
        if not isinstance(rollout_revision, int) or isinstance(rollout_revision, bool):
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID",
                "The pinned geometry rollout revision must be an integer.",
            )
        try:
            snapshot = cls(
                geometry_mode=GeometryRolloutMode(
                    _text(payload.get("geometryMode"), "imageGeometryRollout.geometryMode")
                ),
                cell_asset_mode=CellAssetRolloutMode(
                    _text(payload.get("cellAssetMode"), "imageGeometryRollout.cellAssetMode")
                ),
                rollout_revision=rollout_revision,
                geometry_engine_version=_text(
                    payload.get("geometryEngineVersion"),
                    "imageGeometryRollout.geometryEngineVersion",
                ),
                virtual_renderer_version=_text(
                    payload.get("virtualRendererVersion"),
                    "imageGeometryRollout.virtualRendererVersion",
                ),
                preprocessing_version=_text(
                    payload.get("preprocessingVersion"),
                    "imageGeometryRollout.preprocessingVersion",
                ),
                candidate_geometry=candidate_geometry,
                active_lattice_geometry=active_lattice_geometry,
            )
        except (TypeError, ValueError) as error:
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID",
                "The pinned geometry rollout mode is invalid.",
            ) from error
        if payload.get("checksumSha256") != snapshot.checksum_sha256:
            raise ImagePipelineContractError(
                "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_DRIFT",
                "The pinned geometry rollout snapshot checksum changed.",
            )
        return snapshot


def effective_pipeline_fingerprint(
    legacy_fingerprint: str,
    rollout: GeometryPipelineRolloutSnapshot,
) -> str:
    """Preserve the historical identity unless a v0.10 mode is active."""

    if not SHA256_PATTERN.fullmatch(legacy_fingerprint):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKSUM_INVALID",
            "The source pipeline fingerprint must be a lowercase SHA-256.",
        )
    if rollout.is_legacy:
        return legacy_fingerprint
    return hashlib.sha256(
        f"{legacy_fingerprint}:{rollout.checksum_sha256}".encode("ascii")
    ).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """Return host-independent canonical JSON bytes used by contract hashes."""

    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_MANIFEST_INVALID",
            "The image pipeline contract must contain finite JSON values.",
        ) from error


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_MANIFEST_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _array(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_MANIFEST_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_MANIFEST_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_MANIFEST_INVALID",
            f"{label} must be a boolean.",
        )
    return value


def _sha256(value: object, label: str, *, code: str) -> str:
    checksum = _text(value, label)
    if not SHA256_PATTERN.fullmatch(checksum):
        raise ImagePipelineContractError(code, f"{label} must be a lowercase SHA-256.")
    return checksum


def _relative_posix_path(value: object, label: str) -> str:
    path_text = _text(value, label)
    path = PurePosixPath(path_text)
    if (
        "\\" in path_text
        or path.is_absolute()
        or path_text != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_PATH_UNSAFE",
            f"{label} must be a normalized relative POSIX path.",
        )
    return path_text


def _validate_artifacts(value: object, label: str) -> None:
    artifacts = _array(value, label)
    roles: set[str] = set()
    paths: set[str] = set()
    for index, raw_artifact in enumerate(artifacts):
        artifact = _object(raw_artifact, f"{label}[{index}]")
        if set(artifact) != {"relativePath", "role", "sha256"}:
            raise ImagePipelineContractError(
                "IMAGE_PIPELINE_COMPONENT_INVALID",
                f"{label}[{index}] has unsupported or missing fields.",
            )
        role = _text(artifact.get("role"), f"{label}[{index}].role")
        path = _relative_posix_path(
            artifact.get("relativePath"),
            f"{label}[{index}].relativePath",
        )
        _sha256(
            artifact.get("sha256"),
            f"{label}[{index}].sha256",
            code="IMAGE_PIPELINE_CHECKSUM_INVALID",
        )
        if role in roles or path in paths:
            raise ImagePipelineContractError(
                "IMAGE_PIPELINE_COMPONENT_INVALID",
                f"{label} must not duplicate artifact roles or paths.",
            )
        roles.add(role)
        paths.add(path)


def _validate_component(stage: str, value: object) -> str:
    component = _object(value, f"components.{stage}")
    allowed_fields = {
        "adapterVersion",
        "artifacts",
        "calibrationVersion",
        "confidencePolicyVersion",
        "maturity",
        "modelVersion",
        "preprocessingVersion",
        "runtimeVersion",
    }
    if not set(component).issubset(allowed_fields):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_COMPONENT_INVALID",
            f"components.{stage} contains unsupported fields.",
        )
    required_fields = {"adapterVersion", "artifacts", "maturity"}
    if not required_fields.issubset(component):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_COMPONENT_INVALID",
            f"components.{stage} is missing required fields.",
        )
    _text(component.get("adapterVersion"), f"components.{stage}.adapterVersion")
    maturity = _text(component.get("maturity"), f"components.{stage}.maturity")
    if maturity not in MODEL_MATURITIES:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_COMPONENT_INVALID",
            f"components.{stage}.maturity is unsupported.",
        )
    for field in (
        "calibrationVersion",
        "confidencePolicyVersion",
        "modelVersion",
        "preprocessingVersion",
        "runtimeVersion",
    ):
        if field in component:
            _text(component[field], f"components.{stage}.{field}")
    _validate_artifacts(component.get("artifacts"), f"components.{stage}.artifacts")
    if stage in {"sequence_ocr", "symbol_inference"} and (
        "modelVersion" not in component or not component["artifacts"]
    ):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_COMPONENT_INVALID",
            f"components.{stage} requires a model version and checked artifacts.",
        )
    if stage == "symbol_inference" and not {
        "calibrationVersion",
        "confidencePolicyVersion",
        "preprocessingVersion",
    }.issubset(component):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_COMPONENT_INVALID",
            "components.symbol_inference requires preprocessing, calibration and policy versions.",
        )
    return maturity


def validate_pipeline_manifest(value: object) -> dict[str, object]:
    """Validate a manifest and return an isolated JSON-compatible copy."""

    manifest = _object(value, "manifest")
    required_fields = {
        "components",
        "contractVersion",
        "fileExecutionKeyAlgorithm",
        "fingerprintAlgorithm",
        "policies",
        "schemaVersion",
        "stages",
    }
    if set(manifest) != required_fields:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_MANIFEST_INVALID",
            "The image pipeline manifest has unsupported or missing top-level fields.",
        )
    if manifest.get("schemaVersion") != 1:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_VERSION_UNSUPPORTED",
            "Only image pipeline schemaVersion 1 is supported.",
        )
    if manifest.get("contractVersion") != PIPELINE_MANIFEST_VERSION:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_VERSION_UNSUPPORTED",
            f"Only {PIPELINE_MANIFEST_VERSION} is supported.",
        )
    if manifest.get("fingerprintAlgorithm") != "sha256-canonical-json-v1":
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_VERSION_UNSUPPORTED",
            "The pipeline fingerprint algorithm is unsupported.",
        )
    if manifest.get("fileExecutionKeyAlgorithm") != FILE_EXECUTION_KEY_VERSION:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_VERSION_UNSUPPORTED",
            "The file execution key algorithm is unsupported.",
        )

    stages = tuple(
        _text(stage, f"stages[{index}]")
        for index, stage in enumerate(_array(manifest.get("stages"), "stages"))
    )
    if len(stages) != len(set(stages)) or stages != PIPELINE_STAGES:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_STAGE_ORDER_INVALID",
            "The manifest must contain the complete ordered v1 stage sequence.",
        )

    components = _object(manifest.get("components"), "components")
    if set(components) != set(PIPELINE_STAGES):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_COMPONENT_INVALID",
            "The manifest must define exactly one component for every pipeline stage.",
        )
    maturities = {stage: _validate_component(stage, components[stage]) for stage in PIPELINE_STAGES}

    policies = _object(manifest.get("policies"), "policies")
    if set(policies) != {"reviewBoundary"}:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_REVIEW_BOUNDARY_INVALID",
            "The manifest must define exactly one reviewBoundary policy.",
        )
    review = _object(policies.get("reviewBoundary"), "policies.reviewBoundary")
    expected_review = {
        "autoAcceptEnabled": False,
        "autoRejectEnabled": False,
        "policyVersion": REVIEW_BOUNDARY_VERSION,
        "required": True,
        "resumeStage": "validation",
        "stage": "manual_review",
        "waitingStatus": "waiting_for_review",
    }
    if dict(review) != expected_review:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_REVIEW_BOUNDARY_INVALID",
            "The current OCR and symbol models require the v1 manual-review boundary.",
        )
    if not any("manual_review_only" in maturity for maturity in maturities.values()):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_REVIEW_BOUNDARY_INVALID",
            "The required review boundary must be backed by a manual-review-only component.",
        )
    return deepcopy(dict(manifest))


def pipeline_fingerprint(manifest: object) -> str:
    """Hash the validated manifest without envelope or host-specific data."""

    validated = validate_pipeline_manifest(manifest)
    return hashlib.sha256(canonical_json_bytes(validated)).hexdigest()


def build_pipeline_envelope(manifest: object) -> dict[str, object]:
    """Wrap a validated manifest with its derived fingerprint."""

    validated = validate_pipeline_manifest(manifest)
    return {
        "contractVersion": PIPELINE_ENVELOPE_VERSION,
        "manifest": validated,
        "pipelineFingerprint": pipeline_fingerprint(validated),
        "schemaVersion": 1,
    }


def validate_pipeline_envelope(value: object) -> dict[str, object]:
    """Validate the envelope and reject a stale or forged fingerprint."""

    envelope = _object(value, "envelope")
    if set(envelope) != {
        "contractVersion",
        "manifest",
        "pipelineFingerprint",
        "schemaVersion",
    }:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_MANIFEST_INVALID",
            "The pipeline envelope has unsupported or missing fields.",
        )
    if (
        envelope.get("schemaVersion") != 1
        or envelope.get("contractVersion") != PIPELINE_ENVELOPE_VERSION
    ):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_VERSION_UNSUPPORTED",
            f"Only {PIPELINE_ENVELOPE_VERSION} schemaVersion 1 is supported.",
        )
    manifest = validate_pipeline_manifest(envelope.get("manifest"))
    supplied_fingerprint = _sha256(
        envelope.get("pipelineFingerprint"),
        "pipelineFingerprint",
        code="IMAGE_PIPELINE_FINGERPRINT_MISMATCH",
    )
    expected_fingerprint = pipeline_fingerprint(manifest)
    if supplied_fingerprint != expected_fingerprint:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_FINGERPRINT_MISMATCH",
            "pipelineFingerprint does not match the canonical manifest.",
        )
    return {
        "contractVersion": PIPELINE_ENVELOPE_VERSION,
        "manifest": manifest,
        "pipelineFingerprint": expected_fingerprint,
        "schemaVersion": 1,
    }


def file_execution_key(source_checksum_sha256: str, pipeline_fingerprint_sha256: str) -> str:
    """Identify one source file processed by one immutable pipeline."""

    source_checksum = _sha256(
        source_checksum_sha256,
        "sourceChecksumSha256",
        code="IMAGE_PIPELINE_SOURCE_CHECKSUM_INVALID",
    )
    fingerprint = _sha256(
        pipeline_fingerprint_sha256,
        "pipelineFingerprint",
        code="IMAGE_PIPELINE_FINGERPRINT_MISMATCH",
    )
    identity = f"{FILE_EXECUTION_KEY_VERSION}\0{source_checksum}\0{fingerprint}".encode("ascii")
    return hashlib.sha256(identity).hexdigest()


def _checkpoint_parts(value: object) -> tuple[dict[str, object], tuple[str, ...], str]:
    checkpoint = _object(value, "checkpoint")
    required_fields = {
        "completedStages",
        "contractVersion",
        "fileExecutionKey",
        "nextStage",
        "pipelineFingerprint",
        "schemaVersion",
        "sourceChecksumSha256",
        "status",
    }
    if set(checkpoint) != required_fields:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_INVALID",
            "The file checkpoint has unsupported or missing fields.",
        )
    if (
        checkpoint.get("schemaVersion") != 1
        or checkpoint.get("contractVersion") != FILE_CHECKPOINT_VERSION
    ):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_VERSION_UNSUPPORTED",
            f"Only {FILE_CHECKPOINT_VERSION} schemaVersion 1 is supported.",
        )
    source_checksum = _sha256(
        checkpoint.get("sourceChecksumSha256"),
        "sourceChecksumSha256",
        code="IMAGE_PIPELINE_SOURCE_CHECKSUM_INVALID",
    )
    fingerprint = _sha256(
        checkpoint.get("pipelineFingerprint"),
        "pipelineFingerprint",
        code="IMAGE_PIPELINE_FINGERPRINT_MISMATCH",
    )
    execution_key = _sha256(
        checkpoint.get("fileExecutionKey"),
        "fileExecutionKey",
        code="IMAGE_PIPELINE_CHECKPOINT_PROVENANCE_MISMATCH",
    )
    if execution_key != file_execution_key(source_checksum, fingerprint):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_PROVENANCE_MISMATCH",
            "fileExecutionKey does not match the checkpoint source and pipeline.",
        )
    completed = tuple(
        _text(stage, f"completedStages[{index}]")
        for index, stage in enumerate(_array(checkpoint.get("completedStages"), "completedStages"))
    )
    if completed != PIPELINE_STAGES[: len(completed)]:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_INVALID",
            "completedStages must be a unique ordered prefix of the pipeline.",
        )
    status = _text(checkpoint.get("status"), "status")
    if status not in CHECKPOINT_STATUSES:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_INVALID",
            "The checkpoint status is unsupported.",
        )
    next_stage_raw = checkpoint.get("nextStage")
    next_stage = None if next_stage_raw is None else _text(next_stage_raw, "nextStage")
    expected_next = (
        PIPELINE_STAGES[len(completed)] if len(completed) < len(PIPELINE_STAGES) else None
    )
    if next_stage != expected_next:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_INVALID",
            "nextStage must be the stage immediately after completedStages.",
        )
    review_prefix_length = PIPELINE_STAGES.index(MANUAL_REVIEW_PREDECESSOR) + 1
    if status == "waiting_for_review":
        if len(completed) != review_prefix_length or next_stage != "manual_review":
            raise ImagePipelineContractError(
                "IMAGE_PIPELINE_REVIEW_BOUNDARY_INVALID",
                "waiting_for_review is valid only before the manual_review stage.",
            )
    elif status == "completed":
        if len(completed) != len(PIPELINE_STAGES) or next_stage is not None:
            raise ImagePipelineContractError(
                "IMAGE_PIPELINE_CHECKPOINT_INVALID",
                "A completed checkpoint must contain every pipeline stage.",
            )
    elif next_stage == "manual_review":
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_REVIEW_BOUNDARY_INVALID",
            "The manual review boundary must use waiting_for_review.",
        )
    return deepcopy(dict(checkpoint)), completed, status


def validate_file_checkpoint(value: object) -> dict[str, object]:
    """Validate a persistence-neutral per-file checkpoint value."""

    checkpoint, _, _ = _checkpoint_parts(value)
    return checkpoint


def validate_checkpoint_transition(previous: object, current: object) -> None:
    """Validate an idempotent or one-stage-forward checkpoint transition."""

    previous_value, previous_completed, previous_status = _checkpoint_parts(previous)
    current_value, current_completed, _ = _checkpoint_parts(current)
    provenance_fields = (
        "fileExecutionKey",
        "pipelineFingerprint",
        "sourceChecksumSha256",
    )
    if any(previous_value[field] != current_value[field] for field in provenance_fields):
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_PROVENANCE_MISMATCH",
            "A checkpoint transition cannot change source or pipeline provenance.",
        )
    if previous_status == "completed" and current_value != previous_value:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_INVALID",
            "A completed file checkpoint is immutable.",
        )
    progress = len(current_completed) - len(previous_completed)
    if progress not in {0, 1} or current_completed[: len(previous_completed)] != previous_completed:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_INVALID",
            "A checkpoint transition may be idempotent or complete one next stage.",
        )
    if progress == 0 and current_value != previous_value:
        raise ImagePipelineContractError(
            "IMAGE_PIPELINE_CHECKPOINT_INVALID",
            "A transition without stage progress must be byte-logically idempotent.",
        )


def verify_manifest_artifacts(manifest: object, repository_root: Path) -> None:
    """Fail closed when a checked local artifact is missing or has drifted."""

    validated = validate_pipeline_manifest(manifest)
    components = cast(Mapping[str, object], validated["components"])
    root = repository_root.resolve()
    for stage in PIPELINE_STAGES:
        component = cast(Mapping[str, object], components[stage])
        artifacts = cast(Sequence[object], component["artifacts"])
        for raw_artifact in artifacts:
            artifact = cast(Mapping[str, object], raw_artifact)
            relative_path = cast(str, artifact["relativePath"])
            artifact_path = (root / Path(*PurePosixPath(relative_path).parts)).resolve()
            if root not in artifact_path.parents:
                raise ImagePipelineContractError(
                    "IMAGE_PIPELINE_PATH_UNSAFE",
                    f"{relative_path} resolves outside the repository.",
                )
            if not artifact_path.is_file():
                raise ImagePipelineContractError(
                    "IMAGE_PIPELINE_ARTIFACT_MISSING",
                    f"{relative_path} does not exist.",
                )
            actual_checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if actual_checksum != artifact["sha256"]:
                raise ImagePipelineContractError(
                    "IMAGE_PIPELINE_ARTIFACT_DRIFT",
                    f"{relative_path} does not match its manifest checksum.",
                )


def current_pipeline_manifest() -> dict[str, object]:
    """Build the reviewed M5/M6 pipeline manifest without reading mutable files."""

    return {
        "components": {
            "board_crops": {
                "adapterVersion": "board-cell-crops-v18-source-direct-validated-v1",
                "artifacts": [],
                "maturity": "deterministic",
            },
            "board_detection": {
                "adapterVersion": "page-board-detector-v4-verified-registration-v1",
                "artifacts": [
                    {
                        "relativePath": "ai_docs/quality/m5-image-benchmark-report.json",
                        "role": "geometry-benchmark",
                        "sha256": (
                            "0c2904331a764c5ed3bd5e122afe1380ca83665bfb9441c6d0bb1ea3d7792011"
                        ),
                    }
                ],
                "maturity": "deterministic",
            },
            "discovery": {
                "adapterVersion": "image-discovery-v1",
                "artifacts": [],
                "maturity": "deterministic",
            },
            "manual_review": {
                "adapterVersion": MANUAL_REVIEW_VERSION,
                "artifacts": [],
                "maturity": "deterministic",
            },
            "normalization": {
                "adapterVersion": CURRENT_NORMALIZATION_ADAPTER_VERSION,
                "artifacts": [],
                "maturity": "deterministic",
            },
            "sequence_ocr": {
                "adapterVersion": "sequence-number-ocr-v2-page-continuity-v1",
                "artifacts": [
                    {
                        "relativePath": (
                            "artifacts/m5-models/sequence-number-ocr-v1/inference.json"
                        ),
                        "role": "ocr-model-config",
                        "sha256": (
                            "fd1b6ec722ea841a72d3ba43e527df1d1066d5d7808e0503ee3eec7265188753"
                        ),
                    },
                    {
                        "relativePath": (
                            "artifacts/m5-models/sequence-number-ocr-v1/inference.pdiparams"
                        ),
                        "role": "ocr-model-parameters",
                        "sha256": (
                            "3ec8a97ed6cefe8568d3e2ee90bb193299b566a7661aa4fd52d224b96b59f66b"
                        ),
                    },
                    {
                        "relativePath": (
                            "artifacts/m5-models/sequence-number-ocr-v1/inference.yml"
                        ),
                        "role": "ocr-model-metadata",
                        "sha256": (
                            "27e91d0582f40168aa218303c76e184bc78fa7a5d105aad0cfbad8458b441067"
                        ),
                    },
                    {
                        "relativePath": "ai_docs/quality/m5-sequence-ocr-report.json",
                        "role": "ocr-benchmark",
                        "sha256": (
                            "6c5e17ca1aea9074be60547559e73c137c64e46969e265a079889827b232cd43"
                        ),
                    },
                ],
                "maturity": "manual_review_only",
                "modelVersion": "en_PP-OCRv5_mobile_rec",
                "preprocessingVersion": "bright-component-tight-v1",
                "runtimeVersion": "paddlepaddle-cpu-3.3.1",
            },
            "symbol_inference": {
                "adapterVersion": "local-symbol-onnx-runtime-v1",
                "artifacts": [
                    {
                        "relativePath": (
                            "artifacts/m6-symbol-classifier-onnx/bootstrap-symbol-cnn-v1.onnx"
                        ),
                        "role": "symbol-onnx-model",
                        "sha256": (
                            "e03f66f2ab092b6049920fee6fb2839900a95eb94af42fbd5ef7e35c473b5fb8"
                        ),
                    },
                    {
                        "relativePath": "ai_docs/quality/m6-symbol-classifier-onnx-report.json",
                        "role": "symbol-onnx-report",
                        "sha256": (
                            "6f4596ae8ae938b7e9e89dac05e1a888ac4e53fe1d780dcc9325abfac33ad98c"
                        ),
                    },
                    {
                        "relativePath": (
                            "ai_docs/quality/m6-symbol-confidence-calibration-report.json"
                        ),
                        "role": "symbol-confidence-calibration",
                        "sha256": (
                            "a2359efed1e2dc2d73fc383d9e260c88f4a19838a74af3dd165362692601bff7"
                        ),
                    },
                ],
                "calibrationVersion": "symbol-temperature-calibration-v2-safe-floor-v1",
                "confidencePolicyVersion": "symbol-confidence-policy-v1",
                "maturity": "bootstrap_manual_review_only",
                "modelVersion": "bootstrap-symbol-cnn-onnx-v1",
                "preprocessingVersion": "rgb-resize64-normalize-half-v1",
                "runtimeVersion": "onnxruntime-cpu-1.28.0",
            },
            "validation": {
                "adapterVersion": VALIDATION_VERSION,
                "artifacts": [],
                "maturity": "deterministic",
            },
        },
        "contractVersion": PIPELINE_MANIFEST_VERSION,
        "fileExecutionKeyAlgorithm": FILE_EXECUTION_KEY_VERSION,
        "fingerprintAlgorithm": "sha256-canonical-json-v1",
        "policies": {
            "reviewBoundary": {
                "autoAcceptEnabled": False,
                "autoRejectEnabled": False,
                "policyVersion": REVIEW_BOUNDARY_VERSION,
                "required": True,
                "resumeStage": "validation",
                "stage": "manual_review",
                "waitingStatus": "waiting_for_review",
            }
        },
        "schemaVersion": 1,
        "stages": list(PIPELINE_STAGES),
    }


__all__ = [
    "FILE_CHECKPOINT_VERSION",
    "FILE_EXECUTION_KEY_VERSION",
    "ImagePipelineContractError",
    "PIPELINE_ENVELOPE_VERSION",
    "PIPELINE_MANIFEST_VERSION",
    "PIPELINE_STAGES",
    "STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_VERSION",
    "STRUCTURED_GEOMETRY_ACTIVATION_SNAPSHOT_VERSION",
    "StructuredGeometryActivationSnapshot",
    "StructuredGeometryCandidateSnapshot",
    "VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V2",
    "VIRTUAL_GEOMETRY_ROLLOUT_VERSION_V3",
    "build_pipeline_envelope",
    "canonical_json_bytes",
    "current_pipeline_manifest",
    "file_execution_key",
    "pipeline_fingerprint",
    "validate_checkpoint_transition",
    "validate_file_checkpoint",
    "validate_pipeline_envelope",
    "validate_pipeline_manifest",
    "verify_manifest_artifacts",
]
