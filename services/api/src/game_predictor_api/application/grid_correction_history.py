"""Verified publication scope and immutable historical cohorts for corrections.

Dataset labels never establish game identity. Missing legacy scope is explicit;
an invalid or stale explicit proof fails closed instead of becoming empty history.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from game_predictor_api.domain.grid_model_publication import require_evaluation_evidence
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError, descriptor_sha256
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository


def verified_history(
    repository: SqlAlchemyGridModelRegistryRepository, version_id: UUID
) -> dict[str, Any]:
    version = repository.version(version_id)
    publication = repository.publication(version_id)
    if version is None or publication is None:
        raise GridModelRegistryError(
            "GRID_LEARNING_BASE_UNPUBLISHED", "The pinned base must be published."
        )
    manifest = json.loads(version.manifest_json)
    if descriptor_sha256(manifest) != version.manifest_sha256:
        raise GridModelRegistryError("GRID_MODEL_REGISTRY_CORRUPT", "Base identity differs.")
    if publication.evaluation_id is None:
        return {"documented": False, "gameIds": [], "cohorts": [], "reportId": None}
    report, invalidated = repository.evaluation(publication.evaluation_id)
    base = (
        repository.version(UUID(manifest["baseVersionId"])) if manifest["baseVersionId"] else None
    )
    if report is None or base is None:
        raise GridModelRegistryError(
            "GRID_LEARNING_HISTORY_UNAVAILABLE", "The published scope proof is missing."
        )
    proof = require_evaluation_evidence(
        report_id=report.id,
        report_json=report.report_json,
        report_sha256=report.report_sha256,
        producer=report.producer,
        invalidated=invalidated,
        manifest=manifest,
        base_sha256=base.manifest_sha256,
        game_id=None,
    )
    if any(
        item["state"] != "current"
        for item in repository.cohort_currentness(proof.report_id, proof.cohorts)
    ):
        raise GridModelRegistryError(
            "GRID_LEARNING_HISTORY_STALE", "A historical cohort needs a current proof."
        )
    return {
        "documented": True,
        "gameIds": sorted(str(game) for game in proof.games),
        "cohorts": list(proof.cohorts),
        "reportId": str(proof.report_id),
    }


def require_historical_cohort(
    repository: SqlAlchemyGridModelRegistryRepository, base: UUID, header: dict[str, Any]
) -> None:
    """Reuse the original snapshot without rewriting its original training base."""
    history = verified_history(repository, base)
    expected = {
        "gameId": str(header["gameId"]),
        "cohortId": str(header["id"]),
        "manifestSha256": header["manifestSha256"],
    }
    if expected not in history["cohorts"]:
        raise GridModelRegistryError(
            "GRID_LEARNING_HISTORY_COHORT_UNVERIFIED",
            "This historical cohort is not pinned by the base publication.",
        )
    ancestors = repository.lineage(base)["ancestors"]
    if str(header["baseVersionId"]) not in {entry["versionId"] for entry in ancestors}:
        raise GridModelRegistryError(
            "GRID_LEARNING_HISTORY_BASE_MISMATCH", "The cohort base is outside the pinned ancestry."
        )
