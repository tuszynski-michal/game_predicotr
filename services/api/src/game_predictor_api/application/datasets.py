"""Application service and repository port for dataset staging."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Never, Protocol
from uuid import UUID

from game_predictor_api.domain.datasets import (
    MOCK_GENERATOR_VERSION,
    DatasetConflictError,
    DatasetGenerationSource,
    DatasetLayoutPage,
    DatasetNotFoundError,
    DatasetValidationReport,
    DatasetValidationSource,
    DatasetVersion,
    LayoutDraft,
    LayoutValidationRecord,
    archive_dataset_version,
    generate_mock_layouts,
    publish_dataset_version,
    signature_cell_width,
    validate_dataset,
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

    def get_dataset_version_for_update(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion | None: ...

    def get_generation_source(
        self,
        game_id: UUID,
        rules_version_id: UUID,
    ) -> DatasetGenerationSource | None: ...

    def get_validation_source(
        self,
        dataset_version_id: UUID,
    ) -> DatasetValidationSource | None: ...

    def get_locked_validation_source(
        self,
        dataset_version_id: UUID,
    ) -> DatasetValidationSource | None: ...

    def list_layouts(
        self,
        dataset_version_id: UUID,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> Sequence[LayoutValidationRecord]: ...

    def save_dataset_version(
        self,
        dataset_version: DatasetVersion,
    ) -> DatasetVersion: ...

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
            signature_width=signature_cell_width(source.symbol_mobile_codes),
            layouts=layouts,
        )
        if saved is None:
            self._raise_game_not_found(game_id)
        return saved

    def get_validation_report(
        self,
        dataset_version_id: UUID,
    ) -> DatasetValidationReport:
        dataset = self._repository.get_dataset_version(dataset_version_id)
        if dataset is None:
            raise DatasetNotFoundError(
                "DATASET_VERSION_NOT_FOUND",
                "Dataset version does not exist.",
                details={"datasetVersionId": str(dataset_version_id)},
            )
        if dataset.generator_version != MOCK_GENERATOR_VERSION:
            raise DatasetConflictError(
                "DATASET_VALIDATION_REQUIRES_JOB",
                "This dataset must be validated by a worker job.",
                details={"datasetVersionId": str(dataset_version_id)},
            )
        source = self._repository.get_validation_source(dataset_version_id)
        if source is None:
            raise DatasetNotFoundError(
                "DATASET_VERSION_NOT_FOUND",
                "Dataset version does not exist.",
                details={"datasetVersionId": str(dataset_version_id)},
            )
        return validate_dataset(source)

    def list_layouts(
        self,
        dataset_version_id: UUID,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> DatasetLayoutPage:
        dataset = self.get_dataset_version(dataset_version_id)
        records = tuple(
            self._repository.list_layouts(
                dataset_version_id,
                after_sequence_number=after_sequence_number,
                limit=limit + 1,
            )
        )
        has_next_page = len(records) > limit
        items = records[:limit]
        return DatasetLayoutPage(
            dataset_version_id=dataset.id,
            dataset_version=dataset.version,
            rows=dataset.rows,
            columns=dataset.columns,
            items=items,
            next_after_sequence_number=(
                items[-1].sequence_number if has_next_page and items else None
            ),
        )

    def publish_dataset_version(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion:
        source = self._repository.get_locked_validation_source(dataset_version_id)
        if source is None:
            raise DatasetNotFoundError(
                "DATASET_VERSION_NOT_FOUND",
                "Dataset version does not exist.",
                details={"datasetVersionId": str(dataset_version_id)},
            )
        dataset = source.dataset_version
        if dataset.generator_version != MOCK_GENERATOR_VERSION:
            raise DatasetConflictError(
                "DATASET_PUBLICATION_REQUIRES_JOB",
                "This dataset must be validated by a worker job before publication.",
                details={"datasetVersionId": str(dataset_version_id)},
            )
        candidate = publish_dataset_version(dataset)
        report = validate_dataset(source)
        if not report.ready_for_publication:
            raise DatasetConflictError(
                "DATASET_VERSION_NOT_READY",
                "Dataset version has publication blockers.",
                details={
                    "datasetVersionId": str(dataset_version_id),
                    "issues": [
                        {
                            "code": check.code,
                            "message": check.message,
                            "issueCount": check.issue_count,
                            "sequenceNumbers": list(check.sequence_numbers),
                            "mobileCodes": list(check.mobile_codes),
                            "truncated": check.truncated,
                        }
                        for check in report.checks
                        if check.status.value == "blocking"
                    ],
                },
            )
        return self._repository.save_dataset_version(candidate)

    def archive_dataset_version(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion:
        dataset = self._repository.get_dataset_version_for_update(dataset_version_id)
        if dataset is None:
            raise DatasetNotFoundError(
                "DATASET_VERSION_NOT_FOUND",
                "Dataset version does not exist.",
                details={"datasetVersionId": str(dataset_version_id)},
            )
        archived = archive_dataset_version(dataset)
        if archived is dataset:
            return archived
        return self._repository.save_dataset_version(archived)

    @staticmethod
    def _raise_game_not_found(game_id: UUID) -> Never:
        raise DatasetNotFoundError(
            "GAME_NOT_FOUND",
            "Game does not exist.",
            details={"gameId": str(game_id)},
        )
