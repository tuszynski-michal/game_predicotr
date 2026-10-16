"""Explicit, restart-safe geometry cohort commands; no trainer or inference entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)


class GridTrainingCohortService:
    def __init__(
        self, repository: SqlAlchemyGridTrainingCohortRepository, artifact_root: Path
    ) -> None:
        self.repository = repository
        self.artifacts = GridCohortArtifactStore(artifact_root)

    def list(self, game: UUID, cursor: UUID | None, limit: int) -> dict[str, Any]:
        from sqlalchemy import select

        from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel

        self.repository.bind(game)
        query = select(GridTrainingCohortModel).where(GridTrainingCohortModel.game_id == game)
        if cursor is not None:
            query = query.where(GridTrainingCohortModel.id > cursor)
        rows = list(
            self.repository.session.scalars(
                query.order_by(GridTrainingCohortModel.id).limit(limit + 1)
            )
        )
        return {
            "items": [self.repository.view(row) for row in rows[:limit]],
            "nextCursor": str(rows[limit - 1].id) if len(rows) > limit else None,
        }

    def get(self, game: UUID, cohort: UUID) -> dict[str, Any]:
        self.repository.bind(game)
        return self.repository.view(self.repository.cohort(game, cohort))

    def members(self, game: UUID, cohort: UUID, cursor: int | None, limit: int) -> dict[str, Any]:
        self.repository.bind(game)
        self.repository.cohort(game, cohort)
        rows = self.repository.members(game, cohort, cursor or 0, limit + 1)
        return {
            "items": [
                {
                    "sourceId": str(row.source_id),
                    "ordinal": row.ordinal,
                    "role": row.role,
                    "qualification": row.frozen.get("qualification", "unresolved"),
                    "reasons": row.frozen.get("reasons", ["CAPTURE_REQUIRED"]),
                    "boardEligibleCount": row.frozen.get("boardEligibleCount", 0),
                    "screenEligible": row.frozen.get("screenEligible", False),
                    "metadataMissing": row.frozen.get("metadataMissing", True),
                }
                for row in rows[:limit]
            ],
            "nextCursor": rows[limit - 1].ordinal + 1 if len(rows) > limit else None,
        }

    def prepare(self, game: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]:
        from game_predictor_api.application.grid_training_cohort_commands import prepare

        return prepare(self, game, command, actor)

    def command(
        self, game: UUID, cohort: UUID, kind: str, command: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        from game_predictor_api.application.grid_training_cohort_commands import execute

        return execute(self, game, cohort, kind, command, actor)

    def eligibility(self, game: UUID, cohort: UUID) -> dict[str, Any]:
        from game_predictor_api.storage.grid_training_cohort_currentness import eligibility

        self.repository.bind(game)
        return eligibility(self.repository, self.repository.cohort(game, cohort), self.artifacts)

    def complete_identities(
        self, game: UUID, command: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        from game_predictor_api.application.grid_source_identities import complete

        if not actor:
            raise GridCohortError(
                "GRID_COHORT_ACTOR_REQUIRED", "A trusted human actor is required.", 403
            )
        return complete(self.repository, self.artifacts, game, command, actor)
