"""Application service and repository port for dataset staging."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Never, Protocol
from uuid import UUID

from game_predictor_api.domain.datasets import (
    DatasetConflictError,
    DatasetGenerationSource,
    DatasetNotFoundError,
    DatasetVersion,
    LayoutDraft,
    generate_mock_layouts,
    signature_cell_width,
    validate_generation_seed,
)


class DatasetRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def list_dataset_versions(
        self,
        game_id: UUID,
    ) -> Sequence[DatasetVersion]: ...

    def get_dataset_version(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion | None: ...

    def get_generation_source(
        self,
        game_id: UUID,
        rules_version_id: UUID,
    ) -> DatasetGenerationSource | None: ...

    def add_mock_dataset(
        self,
        *,
        source: DatasetGenerationSource,
        seed: int,
        signature_width: int,
        layouts: Sequence[LayoutDraft],
    ) -> DatasetVersion | None: ...


class DatasetService:
    def __init__(self, repository: DatasetRepository) -> None:
        self._repository = repository

    def list_dataset_versions(
        self,
        game_id: UUID,
    ) -> Sequence[DatasetVersion]:
        if not self._repository.game_exists(game_id):
            self._raise_game_not_found(game_id)
        return self._repository.list_dataset_versions(game_id)

    def get_dataset_version(self, dataset_version_id: UUID) -> DatasetVersion:
        dataset = self._repository.get_dataset_version(dataset_version_id)
        if dataset is None:
            raise DatasetNotFoundError(
                "DATASET_VERSION_NOT_FOUND",
                "Dataset version does not exist.",
                details={"datasetVersionId": str(dataset_version_id)},
            )
        return dataset

    def generate_mock_dataset(
        self,
        game_id: UUID,
        *,
        rules_version_id: UUID,
        seed: int,
    ) -> DatasetVersion:
        validated_seed = validate_generation_seed(seed)
        source = self._repository.get_generation_source(
            game_id,
            rules_version_id,
        )
        if source is None:
            if not self._repository.game_exists(game_id):
                self._raise_game_not_found(game_id)
            raise DatasetNotFoundError(
                "RULES_VERSION_NOT_FOUND",
                "Rules version does not exist for this game.",
                details={
                    "gameId": str(game_id),
                    "rulesVersionId": str(rules_version_id),
                },
            )
        if source.game_id != game_id:
            raise DatasetConflictError(
                "RULES_VERSION_NOT_IN_GAME",
                "Rules version does not belong to the selected game.",
            )
        layouts = generate_mock_layouts(source, seed=validated_seed)
        saved = self._repository.add_mock_dataset(
            source=source,
            seed=validated_seed,
            signature_width=signature_cell_width(
                source.symbol_mobile_codes
            ),
            layouts=layouts,
        )
        if saved is None:
            self._raise_game_not_found(game_id)
        return saved

    @staticmethod
    def _raise_game_not_found(game_id: UUID) -> Never:
        raise DatasetNotFoundError(
            "GAME_NOT_FOUND",
            "Game does not exist.",
            details={"gameId": str(game_id)},
        )
