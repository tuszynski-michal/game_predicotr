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
        self.artifact_root = artifact_root
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

    def run_preview(self, game: UUID, cohort: UUID) -> dict[str, Any]:
        """Read-only TASK-1005 preview: presets, cohort cost and API-side blockers.

        GPU, runtime, VRAM and budget are checked by the worker at admission; the preview
        lists them as pending and never reports them as passed.
        """
        from game_predictor_worker.training_core.gpu_lease import GpuLease, lease_path
        from game_predictor_worker.training_core.grid_training_admission import (
            ADMISSION_POLICY,
            PRESETS,
            SMOKE_MAX_SECONDS,
            SMOKE_MAX_STEPS,
            SMOKE_STARTUP_SECONDS,
            SMOKE_TRAIN_SECONDS,
            WORKER_CHECKS,
            CohortCounts,
            cost_view,
            estimate_cohort_cost,
            preset_for_mode,
            preset_view,
        )

        header = self.get(game, cohort)
        eligibility = self.eligibility(game, cohort)
        roles = {item["role"]: item for item in header["summary"]["roles"]}
        train = roles.get("TRAIN", {})
        validation = roles.get("VALIDATION", {})
        regression = roles.get("REGRESSION", {})
        counts = CohortCounts(
            mode=header["mode"],
            train_boards=int(train.get("eligibleBoards", 0)),
            train_photos=int(train.get("eligiblePhotos", 0)),
            train_full_photos=int(train.get("eligibleFullPhotos", 0)),
            validation_boards=int(validation.get("eligibleBoards", 0)),
            validation_photos=int(validation.get("eligiblePhotos", 0)),
            regression_boards=int(regression.get("eligibleBoards", 0)),
            regression_photos=int(regression.get("eligiblePhotos", 0)),
        )
        blockers: list[str] = []
        if header["status"] != "frozen":
            blockers.append("GRID_RUN_COHORT_NOT_FROZEN")
        if eligibility["qualification"] != "eligible":
            blockers.append("GRID_RUN_COHORT_NOT_QUALIFIED")
        preset = preset_for_mode(header["mode"])
        cost = None
        if preset is None:
            blockers.append("GRID_RUN_PRESET_NOT_APPROVED")
        else:
            estimate = estimate_cohort_cost(preset, counts)
            cost = cost_view(estimate)
            if estimate.train_items == 0:
                blockers.append("GRID_RUN_COHORT_EMPTY")
            if not estimate.within_budget:
                blockers.append("GRID_RUN_COHORT_COST_EXCEEDS_BUDGET")
        lease = GpuLease(lease_path(self.artifact_root)).observe()
        if lease.state == "held":
            blockers.append("GRID_RUN_LEASE_BUSY")
        elif lease.state == "unknown":
            blockers.append("GRID_RUN_LEASE_UNKNOWN")
        return {
            "policy": ADMISSION_POLICY,
            "gameId": header["gameId"],
            "cohortId": header["id"],
            "cohortStatus": header["status"],
            "cohortMode": header["mode"],
            "cohortQualification": eligibility["qualification"],
            "cohortReasons": list(eligibility["reasons"]),
            "presets": [preset_view(item) for item in PRESETS.values()],
            "selectedPresetId": None if preset is None else preset.preset_id,
            "cost": cost,
            "apiBlockers": blockers,
            "pendingWorkerChecks": list(WORKER_CHECKS),
            "lease": {
                "state": lease.state,
                "runKind": None if lease.record is None else lease.record.run_kind,
            },
            "smoke": {
                "maxSteps": SMOKE_MAX_STEPS,
                "trainSeconds": SMOKE_TRAIN_SECONDS,
                "startupSeconds": SMOKE_STARTUP_SECONDS,
                "maxSeconds": SMOKE_MAX_SECONDS,
            },
        }
