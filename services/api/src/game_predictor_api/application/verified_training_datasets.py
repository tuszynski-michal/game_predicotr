"""Application boundary for deterministic cumulative symbol datasets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from game_predictor_worker.symbols import (
    DEFAULT_TRAINING_DATASET_CONFIG,
    TrainingDatasetArtifact,
    TrainingDatasetBuildError,
    TrainingDatasetConfig,
    TrainingSymbol,
    build_cumulative_training_dataset,
)

from game_predictor_api.domain.verified_training_cohorts import VerifiedTrainingCohort


@dataclass(frozen=True, slots=True)
class TrainingDatasetCatalog:
    game_code: str
    symbols: tuple[TrainingSymbol, ...]


class TrainingDatasetCohortRepository(Protocol):
    def get(self, *, cohort_id: UUID) -> VerifiedTrainingCohort | None: ...


class TrainingDatasetCatalogRepository(Protocol):
    def get(self, *, game_id: UUID) -> TrainingDatasetCatalog | None: ...


class VerifiedTrainingDatasetService:
    """Resolve persisted metadata and delegate the pure file build to the worker."""

    def __init__(
        self,
        cohort_repository: TrainingDatasetCohortRepository,
        catalog_repository: TrainingDatasetCatalogRepository,
        *,
        artifact_root: Path,
    ) -> None:
        self._cohort_repository = cohort_repository
        self._catalog_repository = catalog_repository
        self._artifact_root = artifact_root.resolve()
        self._data_root = self._artifact_root / "data"

    def build(
        self,
        *,
        cohort_id: UUID,
        config: TrainingDatasetConfig = DEFAULT_TRAINING_DATASET_CONFIG,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> TrainingDatasetArtifact:
        cohort = self._cohort_repository.get(cohort_id=cohort_id)
        if cohort is None:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_COHORT_NOT_FOUND",
                "The requested verified-training cohort does not exist.",
            )
        catalog = self._catalog_repository.get(game_id=cohort.game_id)
        if catalog is None:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_GAME_NOT_FOUND",
                "The cohort game and its symbol catalog are unavailable.",
            )
        relative = PurePosixPath(cohort.artifact_relative_path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in cohort.artifact_relative_path
        ):
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_COHORT_PATH_UNSAFE",
                "The persisted cohort path is outside managed storage.",
            )
        cohort_path = self._data_root.joinpath(*relative.parts)
        return build_cumulative_training_dataset(
            cohort_path=cohort_path,
            expected_cohort_checksum_sha256=cohort.manifest_checksum_sha256,
            artifact_root=self._artifact_root,
            game_code=catalog.game_code,
            symbols=catalog.symbols,
            expected_game_id=str(cohort.game_id),
            config=config,
            progress_callback=progress_callback,
        )


__all__ = [
    "TrainingDatasetCatalog",
    "TrainingDatasetCatalogRepository",
    "TrainingDatasetCohortRepository",
    "VerifiedTrainingDatasetService",
]
