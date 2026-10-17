"""Shared V3 capability policy and immutable catalogue version adapter."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from .catalog import GameShapeGeometryConfiguration
from .grid_engine_profiles import (
    GridEngineModelFile,
    GridEngineModelVersion,
    GridEngineReportResult,
)
from .grid_model_registry import canonical_json, validate_manifest


def uses_neural_grid(configuration: str | None) -> bool:
    return configuration in {
        GameShapeGeometryConfiguration.NEURAL_GRID_V3.value,
        GameShapeGeometryConfiguration.GRID_PROFILE_777_V2.value,
        GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1.value,
    }


def catalogue_model_version(descriptor: dict[str, Any]) -> GridEngineModelVersion:
    """Adapt a validated frozen descriptor; no lookup of mutable catalogue state."""
    frozen = validate_manifest(descriptor)
    for key in ("familyId", "versionId"):
        if not isinstance(descriptor[key], str):
            raise ValueError("Catalogue family and version identities are required.")
    for key in ("familyId", "versionId", "baseVersionId", "cohortId"):
        if descriptor[key] is not None and (
            not isinstance(descriptor[key], str) or str(UUID(descriptor[key])) != descriptor[key]
        ):
            raise ValueError("Catalogue identity must be a canonical UUID.")
    for file in (*descriptor["files"], *descriptor["trainingArtifacts"]):
        if (
            isinstance(file["sizeBytes"], bool)
            or not isinstance(file["sizeBytes"], int)
            or file["sizeBytes"] <= 0
            or not isinstance(file["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", file["sha256"]) is None
        ):
            raise ValueError("Catalogue artifacts require positive sizes and SHA-256.")
    if descriptor["admission"] not in {"historical_baseline", "not_evaluated"}:
        raise ValueError("Catalogue admission is unsupported.")
    manifest = json.loads(frozen)["inferenceManifest"]
    return GridEngineModelVersion(
        profile=GameShapeGeometryConfiguration.NEURAL_GRID_V3,
        version=manifest["version"],
        model_kind=manifest["modelKind"],
        model_version=manifest["modelVersion"],
        bundle_format=manifest["bundleFormat"],
        run_id=manifest["runId"],
        export_id=manifest["exportId"],
        preset_name=manifest["preset"],
        preset_fingerprint=manifest["presetFingerprint"],
        weights_sha256=manifest["weightsSha256"],
        checkpoint_sha256=manifest["checkpointSha256"],
        snapshot_id=manifest["snapshotId"],
        frozen_on=manifest["frozenOn"],
        selection_reason=manifest["selectionReason"],
        report_results=tuple(GridEngineReportResult(**r) for r in manifest["reportResults"]),
        files=tuple(
            GridEngineModelFile(f["name"], f["sha256"], f["sizeBytes"]) for f in manifest["files"]
        ),
        catalogue_manifest_json=canonical_json(descriptor),
    )
