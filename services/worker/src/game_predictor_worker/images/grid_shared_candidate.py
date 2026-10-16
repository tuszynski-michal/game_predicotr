"""Pinned snapshot facts of a shared geometry candidate (TASK-1006).

Reads only snapshot metadata (no pixels) and the frozen recording group of each used
member, then applies the API's pure ``joint_plan``. The API (before queueing) and the
training supervisor (at every claim) call the same code, so the pinned plan SHA proves
that nothing changed in between.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from game_predictor_api.domain.shared_grid_model_candidate import (
    SharedCandidateError,
    SharedCohort,
    SharedMember,
    joint_plan,
)

from .grid_cohort_dataset import GridCohortSnapshot


def snapshot_members(
    snapshot: GridCohortSnapshot, groups: Mapping[str, str]
) -> tuple[SharedMember, ...]:
    members = []
    for source in snapshot.sources():
        if source.get("used") is not True:
            continue
        identity = source.get("sourceIdentity") or {}
        group = groups.get(str(source["sourceId"]))
        if group is None:
            raise SharedCandidateError(
                "GRID_SHARED_RECORDING_UNRESOLVED",
                "A used snapshot source has no pinned recording group.",
                {"sourceId": str(source["sourceId"])},
            )
        members.append(
            SharedMember(
                source_id=str(source["sourceId"]),
                role=str(source["role"]),
                group_id=group,
                checksum_sha256=str(identity.get("checksum_sha256")),
                pixel_sha256=str(identity.get("normalized_pixel_checksum_sha256")),
            )
        )
    return tuple(members)


def shared_cohort(
    artifact_root: Path, header: Mapping[str, Any], groups: Mapping[str, str]
) -> SharedCohort:
    """``header`` is a frozen cohort view with ``manifestPath``; ``groups`` maps sources."""
    snapshot = GridCohortSnapshot(artifact_root, header["manifestPath"], header["manifestSha256"])
    manifest = snapshot.manifest
    if manifest["gameId"] != str(header["gameId"]) or manifest["cohortId"] != str(header["id"]):
        raise SharedCandidateError(
            "GRID_SHARED_COHORT_MISMATCH", "The snapshot belongs to another cohort."
        )
    return SharedCohort(
        game_id=str(header["gameId"]),
        cohort_id=str(header["id"]),
        manifest_sha256=str(header["manifestSha256"]),
        family_id=str(header["familyId"]),
        base_version_id=str(header["baseVersionId"]),
        mode=str(header["mode"]),
        members=snapshot_members(snapshot, groups),
    )


def plan_for(
    artifact_root: Path,
    primary_game_id: str,
    cohorts: Sequence[tuple[Mapping[str, Any], Mapping[str, str]]],
) -> dict[str, Any]:
    return joint_plan(
        primary_game_id,
        [shared_cohort(artifact_root, header, groups) for header, groups in cohorts],
    )
