"""Shared geometry candidate of several games: pre-queue checks (TASK-1006, D-549).

The primary game keeps its run route; each other game's cohort is read, qualified and
pinned in that game's own transaction, then the joint plan of ``grid-shared-candidate-v1``
is computed over all pinned snapshots. The supervisor recomputes the same plan at every
claim. Nothing here trains, publishes, activates or switches a game.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.shared_grid_model_candidate import (
    MAX_SHARED_GAMES,
    SharedCandidateError,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)


class SharedGridCandidateService:
    def __init__(self, session_factory: sessionmaker[Session], artifact_root: Path) -> None:
        self.session_factory, self.artifact_root = session_factory, artifact_root

    def _cohort(
        self, game: UUID, cohort: UUID
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            repository = SqlAlchemyGridTrainingCohortRepository(session, self.artifact_root)
            service = GridTrainingCohortService(repository, self.artifact_root)
            header = service.get(game, cohort)
            row = repository.cohort(game, cohort)
            eligibility = service.eligibility(game, cohort)
            groups: dict[str, str] = {}
            for member in repository.iter_members(game, cohort):
                recording = member.frozen.get("recording")
                if member.frozen.get("used") is True and isinstance(recording, dict):
                    group = recording.get("groupId")
                    if isinstance(group, str):
                        groups[str(member.source_id)] = group
            return {**header, "manifestPath": row.manifest_path}, eligibility, groups

    def prepare(
        self, primary_game: UUID, primary_cohort: UUID, others: Sequence[tuple[UUID, UUID]]
    ) -> dict[str, Any]:
        """Joint plan, the pins of the other games and the summed cohort counts."""
        from game_predictor_worker.images.grid_shared_candidate import plan_for
        from game_predictor_worker.training_core.grid_training_admission import summed_counts

        games = [primary_game, *(game for game, _ in others)]
        if (
            not others
            or len(games) > MAX_SHARED_GAMES
            or len(set(games)) != len(games)
            or len({primary_cohort, *(cohort for _, cohort in others)}) != len(games)
        ):
            raise GridCohortError(
                "GRID_SHARED_SCOPE_INVALID", "Choose one cohort in each other game.", 422
            )
        pinned: list[tuple[Mapping[str, Any], Mapping[str, str]]] = []
        for game, cohort in [(primary_game, primary_cohort), *others]:
            header, eligibility, groups = self._cohort(game, cohort)
            if header["status"] != "frozen":
                raise GridCohortError("GRID_RUN_COHORT_NOT_FROZEN", "Only frozen cohorts train.")
            if eligibility["qualification"] != "eligible":
                reasons = list(eligibility["reasons"])
                raise GridCohortError(
                    reasons[0] if reasons else "GRID_RUN_COHORT_NOT_QUALIFIED",
                    "A shared cohort does not qualify for new training use.",
                )
            pinned.append((header, groups))
        try:
            plan = plan_for(self.artifact_root, str(primary_game), pinned)
        except SharedCandidateError as error:
            raise GridCohortError(error.code, error.message) from error
        return {
            "plan": plan,
            "pins": sorted(
                (
                    {
                        "game_id": str(header["gameId"]),
                        "cohort_id": str(header["id"]),
                        "manifest_sha256": str(header["manifestSha256"]),
                    }
                    for header, _ in pinned[1:]
                ),
                key=lambda pin: pin["game_id"],
            ),
            "counts": summed_counts([header for header, _ in pinned]),
        }
