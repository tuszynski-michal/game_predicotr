from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.datasets import (
    DatasetRepository,
    DatasetService,
)
from game_predictor_api.domain.datasets import (
    MOCK_DUPLICATE_COUNT,
    MOCK_GENERATOR_VERSION,
    MOCK_LAYOUT_COUNT,
    DatasetConflictError,
    DatasetGenerationSource,
    DatasetVersion,
    DatasetVersionStatus,
    LayoutDraft,
    generate_mock_layouts,
)
from game_predictor_api.domain.rules import RulesVersionStatus


class MemoryDatasetRepository(DatasetRepository):
    def __init__(
        self,
        game_id: UUID,
        source: DatasetGenerationSource | None,
    ) -> None:
        self.game_id = game_id
        self.source = source
        self.items: dict[UUID, DatasetVersion] = {}
        self.layouts: dict[UUID, tuple[LayoutDraft, ...]] = {}

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def list_dataset_versions(self, game_id: UUID) -> list[DatasetVersion]:
        return sorted(
            (
                item
                for item in self.items.values()
                if item.game_id == game_id
            ),
            key=lambda item: item.version,
            reverse=True,
        )

    def get_dataset_version(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion | None:
        return self.items.get(dataset_version_id)

    def get_generation_source(
        self,
        game_id: UUID,
        rules_version_id: UUID,
    ) -> DatasetGenerationSource | None:
        if (
            self.source is None
            or self.source.game_id != game_id
            or self.source.rules_version_id != rules_version_id
        ):
            return None
        return self.source

    def add_mock_dataset(
        self,
        *,
        source: DatasetGenerationSource,
        seed: int,
        signature_width: int,
        layouts: Sequence[LayoutDraft],
    ) -> DatasetVersion | None:
        item = DatasetVersion(
            id=uuid4(),
            game_id=source.game_id,
            version=len(self.items) + 1,
            rows=source.rows,
            columns=source.columns,
            signature_cell_width=signature_width,
            layout_count=len(layouts),
            status=DatasetVersionStatus.STAGING,
            generation_seed=seed,
            generator_version=MOCK_GENERATOR_VERSION,
            source_job_id=None,
            created_at=datetime.now(UTC),
            published_at=None,
        )
        self.items[item.id] = item
        self.layouts[item.id] = tuple(layouts)
        return item


def _source(
    game_id: UUID,
    *,
    status: RulesVersionStatus = RulesVersionStatus.PUBLISHED,
) -> DatasetGenerationSource:
    return DatasetGenerationSource(
        rules_version_id=uuid4(),
        game_id=game_id,
        rows=3,
        columns=5,
        rules_status=status,
        symbol_mobile_codes=(1, 2, 7, 12),
    )


def test_generator_is_deterministic_continuous_and_has_controlled_duplicates() -> None:
    game_id = uuid4()
    source = _source(game_id)

    first = generate_mock_layouts(source, seed=71401)
    second = generate_mock_layouts(source, seed=71401)

    assert first == second
    assert len(first) == MOCK_LAYOUT_COUNT
    assert [item.sequence_number for item in first] == list(
        range(1, MOCK_LAYOUT_COUNT + 1)
    )
    assert all(len(item.cells) == 15 for item in first)
    assert all(len(item.signature) == 30 for item in first)
    assert all(set(item.cells) <= {1, 2, 7, 12} for item in first)
    unique_signatures = {item.signature for item in first}
    assert len(first) - len(unique_signatures) == MOCK_DUPLICATE_COUNT
    assert [first[index - 1].cells for index in range(101, 107)] == [
        item.cells for item in first[-MOCK_DUPLICATE_COUNT:]
    ]


def test_service_creates_new_staging_versions_with_same_logical_data() -> None:
    game_id = uuid4()
    source = _source(game_id)
    repository = MemoryDatasetRepository(game_id, source)
    service = DatasetService(repository)

    first = service.generate_mock_dataset(
        game_id,
        rules_version_id=source.rules_version_id,
        seed=123,
    )
    second = service.generate_mock_dataset(
        game_id,
        rules_version_id=source.rules_version_id,
        seed=123,
    )

    assert first.version == 1
    assert second.version == 2
    assert first.status is DatasetVersionStatus.STAGING
    assert first.layout_count == MOCK_LAYOUT_COUNT
    assert first.signature_cell_width == 2
    assert repository.layouts[first.id] == repository.layouts[second.id]
    assert [item.id for item in service.list_dataset_versions(game_id)] == [
        second.id,
        first.id,
    ]


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (
            DatasetGenerationSource(
                rules_version_id=UUID(int=1),
                game_id=UUID(int=2),
                rows=3,
                columns=5,
                rules_status=RulesVersionStatus.DRAFT,
                symbol_mobile_codes=(1, 2),
            ),
            "RULES_VERSION_NOT_PUBLISHED",
        ),
        (
            DatasetGenerationSource(
                rules_version_id=UUID(int=1),
                game_id=UUID(int=2),
                rows=3,
                columns=5,
                rules_status=RulesVersionStatus.PUBLISHED,
                symbol_mobile_codes=(1,),
            ),
            "INSUFFICIENT_ACTIVE_SYMBOLS",
        ),
    ],
)
def test_generator_rejects_invalid_generation_source(
    source: DatasetGenerationSource,
    code: str,
) -> None:
    with pytest.raises(DatasetConflictError) as error:
        generate_mock_layouts(source, seed=1)

    assert error.value.code == code
