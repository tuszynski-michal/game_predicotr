"""Joint policy of one shared geometry candidate trained on several games (TASK-1006).

One base is fine-tuned on the TRAIN members of one frozen, eligible cohort per game, all
of the same family, base and mode (D-549: no weight averaging, the gate stays per game).
Every game and, within a game, every recording weighs the same in sampling, so a large
game never dominates. A TRAIN photo of any game may share neither its source bytes, its
normalized pixels nor its recording group with a control photo (VALIDATION, REGRESSION)
of any game; the family-level recording registry already refuses such aliases when a
cohort freezes, and this plan proves it again over the pinned snapshots. The plan only
describes one explicit run: it never publishes, activates or switches a game.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from .grid_model_registry import descriptor_sha256

JOINT_POLICY: Final = "grid-shared-candidate-v1"
SHARED_TRAINING_KIND: Final = "grid-shared-training-run-v1"
MAX_SHARED_GAMES: Final = 8
CONTROL_ROLES: Final = frozenset({"VALIDATION", "REGRESSION"})


class SharedCandidateError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.details = code, message, dict(details or {})


@dataclass(frozen=True, slots=True)
class SharedMember:
    """One used snapshot source with its role, recording group and byte/pixel identity."""

    source_id: str
    role: str
    group_id: str
    checksum_sha256: str
    pixel_sha256: str


@dataclass(frozen=True, slots=True)
class SharedCohort:
    game_id: str
    cohort_id: str
    manifest_sha256: str
    family_id: str
    base_version_id: str
    mode: str
    members: tuple[SharedMember, ...]


def _identities(member: SharedMember) -> tuple[tuple[str, str], ...]:
    return (
        ("source", member.checksum_sha256),
        ("pixels", member.pixel_sha256),
        ("recording", member.group_id),
    )


def joint_plan(primary_game_id: str, cohorts: Sequence[SharedCohort]) -> dict[str, Any]:
    """The pinned, deterministic plan of one shared run, or a typed refusal."""
    games = [cohort.game_id for cohort in cohorts]
    if not 2 <= len(cohorts) <= MAX_SHARED_GAMES or len(set(games)) != len(games):
        raise SharedCandidateError(
            "GRID_SHARED_SCOPE_INVALID", "Choose one cohort in each of two or more games."
        )
    distinct = len({cohort.cohort_id for cohort in cohorts}) == len(cohorts)
    if not distinct or primary_game_id not in games:
        raise SharedCandidateError(
            "GRID_SHARED_SCOPE_INVALID", "The primary game must be one of the shared games."
        )
    first = cohorts[0]
    for cohort in cohorts:
        if (cohort.family_id, cohort.base_version_id, cohort.mode) != (
            first.family_id,
            first.base_version_id,
            first.mode,
        ):
            raise SharedCandidateError(
                "GRID_SHARED_COHORT_MISMATCH",
                "Shared cohorts need one family, one base and one mode.",
                {"gameId": cohort.game_id},
            )
        roles = {member.role for member in cohort.members}
        if "TRAIN" not in roles or "VALIDATION" not in roles:
            raise SharedCandidateError(
                "GRID_SHARED_COHORT_EMPTY_ROLE",
                "Every shared cohort needs TRAIN and VALIDATION photos.",
                {"gameId": cohort.game_id},
            )
    group_roles: dict[str, set[str]] = defaultdict(set)
    for cohort in cohorts:
        for member in cohort.members:
            group_roles[member.group_id].add(member.role)
    conflicting = sorted(group for group, roles in group_roles.items() if len(roles) > 1)
    if conflicting:
        raise SharedCandidateError(
            "GRID_SHARED_ROLE_CONFLICT",
            "A recording group has different roles across the shared cohorts.",
            {"groupIds": conflicting[:20]},
        )
    controls: dict[tuple[str, str], str] = {}
    for cohort in cohorts:
        for member in cohort.members:
            if member.role in CONTROL_ROLES:
                for identity in _identities(member):
                    controls.setdefault(identity, cohort.game_id)
    for cohort in cohorts:
        for member in cohort.members:
            if member.role != "TRAIN":
                continue
            for identity in _identities(member):
                if identity in controls:
                    raise SharedCandidateError(
                        "GRID_SHARED_CONTROL_ALIAS",
                        "A control photo of one game is also a TRAIN photo of a shared game.",
                        {
                            "trainGameId": cohort.game_id,
                            "controlGameId": controls[identity],
                            "identity": identity[0],
                        },
                    )
    summary = []
    for cohort in sorted(cohorts, key=lambda item: item.game_id):
        train = [member for member in cohort.members if member.role == "TRAIN"]
        # The sampler strata come from this exact source -> recording assignment.
        assignment = sorted(
            [member.source_id, member.role, member.group_id] for member in cohort.members
        )
        summary.append(
            {
                "gameId": cohort.game_id,
                "cohortId": cohort.cohort_id,
                "manifestSha256": cohort.manifest_sha256,
                "trainPhotos": len(train),
                "trainRecordings": len({member.group_id for member in train}),
                "recordingsSha256": descriptor_sha256(assignment),
            }
        )
    plan = {
        "policy": JOINT_POLICY,
        "primaryGameId": primary_game_id,
        "familyId": first.family_id,
        "baseVersionId": first.base_version_id,
        "mode": first.mode,
        "weighting": {"games": "equal", "recordings": "equal-within-game"},
        "cohorts": summary,
    }
    return {**plan, "sha256": descriptor_sha256(plan)}
