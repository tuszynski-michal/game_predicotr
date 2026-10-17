"""Immutable shared geometry catalogue; never shares game-owned symbol data."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid5

from game_predictor_api.domain.grid_engine_profiles import (
    GRID_ENGINE_PROFILES,
    grid_engine_manifest,
)

CATALOGUE_SCHEMA = "grid-model-catalogue-v1"
_NAMESPACE = UUID("1ab40b36-a4a2-4a30-a80d-f3ef16f2bbcc")


class GridModelRegistryError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        self.details: dict[str, object] = {}
        super().__init__(f"{code}: {message}")


def canonical_json(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def descriptor_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def catalogue_id(name: str) -> UUID:
    return uuid5(_NAMESPACE, name)


def validate_manifest(payload: dict[str, Any]) -> str:
    """Validate relationships beyond the closed transport fields; return immutable JSON."""
    expected = {
        "schemaVersion",
        "familyId",
        "familyCode",
        "familyLabel",
        "versionId",
        "version",
        "modelKind",
        "modelVersion",
        "bundleFormat",
        "preprocessingVersion",
        "decodingPolicyVersion",
        "topology",
        "capabilities",
        "baseVersionId",
        "cohortId",
        "admission",
        "provenance",
        "historicalReports",
        "managedDirectory",
        "inferenceManifest",
        "files",
        "trainingArtifacts",
    }
    if (
        payload.keys() != expected
        or payload["schemaVersion"] != CATALOGUE_SCHEMA
        or payload["modelKind"] != "neural_grid"
    ):
        raise GridModelRegistryError(
            "GRID_MODEL_MANIFEST_INVALID", "Catalogue descriptor fields differ."
        )
    manifest = payload["inferenceManifest"]
    inference_keys = {
        "schemaVersion",
        "profile",
        "version",
        "modelKind",
        "modelVersion",
        "bundleFormat",
        "runId",
        "exportId",
        "preset",
        "presetFingerprint",
        "weightsSha256",
        "checkpointSha256",
        "snapshotId",
        "frozenOn",
        "selectionReason",
        "report",
        "reportResults",
        "files",
    }
    if (
        not isinstance(manifest, dict)
        or manifest.keys() != inference_keys
        or manifest["schemaVersion"] != "grid-engine-model-manifest-v1"
    ):
        raise GridModelRegistryError(
            "GRID_MODEL_MANIFEST_INVALID", "Inference descriptor fields differ."
        )
    if payload["provenance"].keys() != {
        "runId",
        "exportId",
        "presetFingerprint",
        "weightsSha256",
        "checkpointSha256",
        "snapshotId",
    }:
        raise GridModelRegistryError("GRID_MODEL_MANIFEST_INVALID", "Provenance fields differ.")
    if any(
        file.keys() != {"name", "sha256", "sizeBytes"}
        for file in (*payload["files"], *payload["trainingArtifacts"])
    ) or any(report.keys() != {"dataset", "result"} for report in payload["historicalReports"]):
        raise GridModelRegistryError(
            "GRID_MODEL_MANIFEST_INVALID", "Artifact or report descriptor fields differ."
        )
    matching = {
        "version": payload["version"],
        "modelKind": "neural_grid",
        "modelVersion": payload["modelVersion"],
        "bundleFormat": payload["bundleFormat"],
    }
    if any(manifest.get(key) != value for key, value in matching.items()):
        raise GridModelRegistryError(
            "GRID_MODEL_MANIFEST_INVALID", "Inference manifest identity differs."
        )
    files = payload["files"]
    if {file["name"] for file in files} != {
        "screen.onnx",
        "board.onnx",
        "bundle.json",
        "preset.json",
    } or len(files) != 4:
        raise GridModelRegistryError(
            "GRID_MODEL_MANIFEST_INVALID", "Artifact names must be unique."
        )
    if manifest.get("files") != files:
        raise GridModelRegistryError("GRID_MODEL_MANIFEST_INVALID", "Artifact manifest differs.")
    training = payload["trainingArtifacts"]
    if {file["name"] for file in training} != {
        "checkpoint.pt",
        "weights.pt",
        "bundle.json",
        "preset.json",
    } or len(training) != 4:
        raise GridModelRegistryError("GRID_MODEL_MANIFEST_INVALID", "Training artifacts differ.")
    training_by_name = {file["name"]: file for file in training}
    for name, key in (("checkpoint.pt", "checkpointSha256"), ("weights.pt", "weightsSha256")):
        if training_by_name[name]["sha256"] != payload["provenance"][key]:
            raise GridModelRegistryError(
                "GRID_MODEL_MANIFEST_INVALID", "Training artifact provenance differs."
            )
    if any(
        training_by_name[file["name"]] != file
        for file in files
        if file["name"] in {"bundle.json", "preset.json"}
    ):
        raise GridModelRegistryError(
            "GRID_MODEL_MANIFEST_INVALID", "Training input contract differs."
        )
    provenance = payload["provenance"]
    for key in (
        "runId",
        "exportId",
        "presetFingerprint",
        "weightsSha256",
        "checkpointSha256",
        "snapshotId",
    ):
        if manifest.get(key) != provenance[key]:
            raise GridModelRegistryError("GRID_MODEL_MANIFEST_INVALID", "Model provenance differs.")
    if manifest.get("reportResults") != payload["historicalReports"]:
        raise GridModelRegistryError("GRID_MODEL_MANIFEST_INVALID", "Historical reports differ.")
    if (
        payload["preprocessingVersion"] != "neural-grid-preprocessing-v1"
        or payload["decodingPolicyVersion"] != "neural-grid-decoding-v1"
    ):
        raise GridModelRegistryError(
            "GRID_MODEL_CONTRACT_UNSUPPORTED", "Unsupported preprocessing or decoding contract."
        )
    if (
        payload["modelVersion"] != "neural-grid-v1"
        or payload["bundleFormat"] != "neural-grid-bundle-v1"
    ):
        raise GridModelRegistryError(
            "GRID_MODEL_CONTRACT_UNSUPPORTED", "Unsupported neural model contract."
        )
    if payload["topology"] != {
        "screenRows": 3,
        "screenColumns": 3,
        "boardRows": 5,
        "boardColumns": 3,
    } or payload["capabilities"] != ["screen_detector", "grid_detector"]:
        raise GridModelRegistryError(
            "GRID_MODEL_TOPOLOGY_UNSUPPORTED", "Unsupported geometry topology or capabilities."
        )
    if payload["admission"] == "historical_baseline" and payload["cohortId"] is not None:
        raise GridModelRegistryError(
            "GRID_MODEL_MANIFEST_INVALID", "Historical registration cannot invent a cohort."
        )
    directory = PurePosixPath(payload["managedDirectory"])
    if (
        directory.is_absolute()
        or ".." in directory.parts
        or directory.parts[:2] != ("models", "grid-engine")
        or "\\" in payload["managedDirectory"]
        or ":" in payload["managedDirectory"]
    ):
        raise GridModelRegistryError(
            "GRID_MODEL_PATH_INVALID", "Artifacts must remain under models/grid-engine."
        )
    for file in files:
        if (
            PurePosixPath(file["name"]).name != file["name"]
            or file["name"] in {".", "..", "manifest.json"}
            or "\\" in file["name"]
            or ":" in file["name"]
        ):
            raise GridModelRegistryError("GRID_MODEL_PATH_INVALID", "Artifact name is unsafe.")
    return canonical_json(payload)


def historical_catalogue() -> tuple[dict[str, Any], ...]:
    result = []
    for profile in GRID_ENGINE_PROFILES:
        # Historical admission is fixed to v1, never the mutable current pointer.
        version = next(version for version in profile.versions if version.version == "v1")
        manifest = grid_engine_manifest(version)
        inference_files = [
            {"name": file.name, "sha256": file.sha256, "sizeBytes": file.size_bytes}
            for file in version.files
        ]
        result.append(
            {
                "schemaVersion": CATALOGUE_SCHEMA,
                "familyId": str(catalogue_id(profile.configuration.value)),
                "familyCode": profile.configuration.value,
                "familyLabel": profile.label,
                "versionId": str(catalogue_id(profile.configuration.value + ":" + version.version)),
                "version": version.version,
                "modelKind": "neural_grid",
                "modelVersion": version.model_version,
                "bundleFormat": version.bundle_format,
                "preprocessingVersion": "neural-grid-preprocessing-v1",
                "decodingPolicyVersion": "neural-grid-decoding-v1",
                "topology": {
                    "screenRows": 3,
                    "screenColumns": 3,
                    "boardRows": 5,
                    "boardColumns": 3,
                },
                "capabilities": ["screen_detector", "grid_detector"],
                "baseVersionId": None,
                "cohortId": None,
                "admission": "historical_baseline",
                "provenance": {
                    key: manifest[key]
                    for key in (
                        "runId",
                        "exportId",
                        "presetFingerprint",
                        "weightsSha256",
                        "checkpointSha256",
                        "snapshotId",
                    )
                },
                "historicalReports": manifest["reportResults"],
                "managedDirectory": version.relative_directory.as_posix(),
                "inferenceManifest": manifest,
                "files": manifest["files"],
                "trainingArtifacts": [
                    {
                        "name": "checkpoint.pt",
                        "sha256": version.checkpoint_sha256,
                        "sizeBytes": version.checkpoint_size_bytes,
                    },
                    {
                        "name": "weights.pt",
                        "sha256": version.weights_sha256,
                        "sizeBytes": version.weights_size_bytes,
                    },
                    *[
                        file
                        for file in inference_files
                        if file["name"] in {"bundle.json", "preset.json"}
                    ],
                ],
            }
        )
    return tuple(result)
