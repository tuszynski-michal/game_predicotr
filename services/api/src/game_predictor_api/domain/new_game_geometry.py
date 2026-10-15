"""Closed, immutable transfer and protected ancestry contracts (no copied weights)."""

from __future__ import annotations

import json
from typing import Any

from .grid_model_registry import GridModelRegistryError, canonical_json, descriptor_sha256

PROTECTED_ROLES = (
    "VALIDATION",
    "REGRESSION",
    "final_test",
    "unseen_game",
    "Reels",
    "Treasure",
    "declared_holdouts",
)


def verified_json(
    content: str, checksum: str, *, code: str = "GRID_MODEL_REGISTRY_CORRUPT"
) -> dict[str, Any]:
    try:
        value = json.loads(content)
        if (
            not isinstance(value, dict)
            or canonical_json(value) != content
            or descriptor_sha256(value) != checksum
        ):
            raise ValueError("Immutable JSON or checksum differs.")
    except (TypeError, ValueError) as error:
        raise GridModelRegistryError(code, "Immutable JSON or checksum differs.") from error
    return value


def transfer_evidence(
    view: dict[str, Any],
    source_evidence: dict[str, Any],
    *,
    training_family_id: str,
    default_revision: int | None,
    lineage_sha256: str,
) -> dict[str, Any]:
    manifest = view["manifest"]
    return {
        "schemaVersion": "grid-model-transfer-v1",
        "kind": "transfer_bootstrap",
        "sourceVersionId": manifest["versionId"],
        "sourceFamilyId": manifest["familyId"],
        "sourceManifestSha256": view["manifestSha256"],
        "sourceEvidenceKind": source_evidence["kind"],
        "sourceEvidenceSha256": descriptor_sha256(source_evidence),
        "evaluationId": source_evidence.get("evaluationId"),
        "trainingFamilyId": training_family_id,
        "defaultRevision": default_revision,
        "lineageSha256": lineage_sha256,
        "qualityScope": "source-games-only",
    }
