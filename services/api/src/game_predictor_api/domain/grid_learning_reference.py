"""Difficulty evidence is separate from the human geometry used as a target."""

from collections.abc import Mapping, Sequence
from typing import Any

from .grid_learning_material import ERROR_CATEGORIES
from .grid_training_cohorts import digest


def baseline_reference(
    label: Mapping[str, Any],
    geometry: Mapping[str, Any] | None,
    producer: Mapping[str, Any] | None,
    base_version_id: str,
    failure_code: str | None = None,
) -> dict[str, Any]:
    """Only verified producer lineage from original_target can establish difficulty.

    A changed lattice proves a correction, not a missing row or neighbor takeover.
    Those diagnoses remain unknown unless separately measured; no shape heuristic
    converts a prediction into human truth.
    """
    snapshot = (producer or {}).get("engineSnapshot") or {}
    descriptor = snapshot.get("catalogueManifest") or snapshot.get("model") or {}
    reference = {
        "positionIndex": label["positionIndex"],
        "baseVersionId": base_version_id,
        "humanLabelSha256": digest(label),
        "state": "unknown",
        "categories": [],
        "categoryState": "unknown",
        "producer": None,
        # A malformed historical proof stays unknown with its explicit reason.
        "reasonCode": failure_code or "BASELINE_REFERENCE_UNAVAILABLE",
    }
    nodes = (geometry or {}).get("latticeNodes")
    if (
        failure_code is None
        and producer
        and descriptor.get("versionId") == base_version_id
        and isinstance(nodes, list)
        and len(nodes) == 24
        and len(label.get("nodes", [])) == 24
        and label.get("approval")
    ):
        changed = nodes != label["nodes"]
        reference.update(
            state="hard" if changed else "unchanged",
            producer={
                key: producer[key]
                for key in (
                    "sourceRevisionId",
                    "sourceRevision",
                    "operationId",
                    "producingImportJobId",
                    "proposalChecksumSha256",
                    "boardId",
                    "reviewItemId",
                    "positionIndex",
                    "sequenceNumber",
                    "geometryRevision",
                )
                if key in producer
            },
            producerSha256=digest(dict(producer)),
            baselineNodesSha256=digest(nodes),
            reasonCode=None,
        )
    return reference


def source_reference(boards: Sequence[Mapping[str, Any]], base: str | None) -> dict[str, Any]:
    states = {board["state"] for board in boards}
    return {
        "baseVersionId": base,
        "state": "hard"
        if "hard" in states
        else "unchanged"
        if states == {"unchanged"} and len(boards) == 9
        else "unknown",
        "boards": list(boards),
        "categoryCounts": {
            category: sum(category in board.get("categories", []) for board in boards)
            for category in ERROR_CATEGORIES
        },
    }
