"""Resolve and check the immutable assignment used by a private learning operation."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from uuid import UUID

from game_predictor_api.domain.grid_training_cohorts import GridCohortError

if TYPE_CHECKING:
    from game_predictor_api.application.grid_model_registry import GridModelRegistryRepository


def assignment_pin(registry: "GridModelRegistryRepository", game: UUID) -> dict[str, Any] | None:
    if not registry.game_grid_model_private(game):
        return None
    assignment, _ = registry.assignment(game)
    family = registry.private_family(game)
    if assignment is None or family is None or assignment.training_family_id != family.id:
        raise GridCohortError(
            "GRID_LEARNING_PRIVATE_ASSIGNMENT_REQUIRED", "Assign an admitted base to this game."
        )
    record = registry.version(assignment.version_id)
    if record is None or registry.version_owner_game_id(record.id) not in (None, game):
        raise GridCohortError(
            "GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED", "The assigned base is unavailable."
        )
    return {
        "gameId": str(game),
        "assignmentRevision": assignment.revision,
        "targetFamilyId": str(family.id),
        "baseVersionId": str(record.id),
        "baseManifestSha256": record.manifest_sha256,
    }


def require_learning_pin(
    registry: "GridModelRegistryRepository", game: UUID, expected: Mapping[str, Any] | None
) -> None:
    observed = assignment_pin(registry, game)
    if observed is not None and expected is None:
        raise GridCohortError(
            "GRID_LEARNING_PRIVATE_SCOPE_REQUIRED",
            "Start private learning from the assigned version.",
        )
    if observed != expected:
        raise GridCohortError(
            "GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED",
            "The game assignment changed. Prepare a fresh preview.",
        )
