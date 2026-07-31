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
    DatasetValidationCheckCode,
    DatasetValidationCheckStatus,
    DatasetValidationSource,
    DatasetVersion,
    DatasetVersionStatus,
    LayoutDraft,
    LayoutValidationRecord,
    generate_mock_layouts,
    validate_dataset,
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

    def get_dataset_version_for_update(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion | None:
        return self.get_dataset_version(dataset_version_id)

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

    def get_validation_source(
        self,
        dataset_version_id: UUID,
    ) -> DatasetValidationSource | None:
        item = self.items.get(dataset_version_id)
        if item is None:
            return None
        layouts = self.layouts.get(dataset_version_id, ())
        return DatasetValidationSource(
            dataset_version=item,
            allowed_symbol_mobile_codes=(
                () if self.source is None else self.source.symbol_mobile_codes
            ),
            layouts=tuple(
                LayoutValidationRecord(
                    sequence_number=layout.sequence_number,
                    signature=layout.signature,
                    cells=layout.cells,
                )
                for layout in layouts
            ),
        )

    def get_locked_validation_source(
        self,
        dataset_version_id: UUID,
    ) -> DatasetValidationSource | None:
        return self.get_validation_source(dataset_version_id)

    def list_layouts(
        self,
        dataset_version_id: UUID,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> list[LayoutValidationRecord]:
        return [
            LayoutValidationRecord(
                sequence_number=layout.sequence_number,
                signature=layout.signature,
                cells=layout.cells,
            )
            for layout in self.layouts.get(dataset_version_id, ())
            if layout.sequence_number > after_sequence_number
        ][:limit]

    def save_dataset_version(
        self,
        dataset_version: DatasetVersion,
    ) -> DatasetVersion:
        self.items[dataset_version.id] = dataset_version
        return dataset_version

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
            expected_layout_count=len(layouts),
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


def test_generated_mock_report_is_ready_with_six_duplicate_warnings() -> None:
    game_id = uuid4()
    source = _source(game_id)
    repository = MemoryDatasetRepository(game_id, source)
    service = DatasetService(repository)
    dataset = service.generate_mock_dataset(
        game_id,
        rules_version_id=source.rules_version_id,
        seed=71401,
    )

    report = service.get_validation_report(dataset.id)

    assert report.ready_for_publication
    assert report.declared_layout_count == MOCK_LAYOUT_COUNT
    assert report.actual_layout_count == MOCK_LAYOUT_COUNT
    assert report.min_sequence_number == 1
    assert report.max_sequence_number == MOCK_LAYOUT_COUNT
    assert report.duplicate_signature_group_count == MOCK_DUPLICATE_COUNT
    assert report.duplicate_signature_affected_layout_count == 12
    assert report.duplicate_signature_excess_layout_count == 6
    assert {
        group.sequence_numbers for group in report.duplicate_signatures
    } == {
        (101, 995),
        (102, 996),
        (103, 997),
        (104, 998),
        (105, 999),
        (106, 1000),
    }
    duplicate_check = report.checks[-1]
    assert duplicate_check.code is DatasetValidationCheckCode.DUPLICATE_SIGNATURE
    assert duplicate_check.status is DatasetValidationCheckStatus.WARNING
    assert all(
        check.status is DatasetValidationCheckStatus.PASSED
        for check in report.checks[:-1]
    )


def test_layout_preview_uses_sequence_keyset_without_overlap() -> None:
    game_id = uuid4()
    source = _source(game_id)
    repository = MemoryDatasetRepository(game_id, source)
    service = DatasetService(repository)
    dataset = service.generate_mock_dataset(
        game_id,
        rules_version_id=source.rules_version_id,
        seed=71401,
    )

    first = service.list_layouts(
        dataset.id,
        after_sequence_number=0,
        limit=3,
    )
    second = service.list_layouts(
        dataset.id,
        after_sequence_number=first.next_after_sequence_number or 0,
        limit=3,
    )

    assert [item.sequence_number for item in first.items] == [1, 2, 3]
    assert first.next_after_sequence_number == 3
    assert [item.sequence_number for item in second.items] == [4, 5, 6]
    assert first.rows == 3
    assert first.columns == 5


def test_publish_accepts_duplicate_warning_and_archive_preserves_timestamp() -> None:
    game_id = uuid4()
    source = _source(game_id)
    repository = MemoryDatasetRepository(game_id, source)
    service = DatasetService(repository)
    dataset = service.generate_mock_dataset(
        game_id,
        rules_version_id=source.rules_version_id,
        seed=71401,
    )

    published = service.publish_dataset_version(dataset.id)
    assert published.status is DatasetVersionStatus.PUBLISHED
    assert published.published_at is not None

    archived = service.archive_dataset_version(dataset.id)
    assert archived.status is DatasetVersionStatus.ARCHIVED
    assert archived.published_at == published.published_at
    assert service.archive_dataset_version(dataset.id) == archived
    assert len(repository.layouts[dataset.id]) == MOCK_LAYOUT_COUNT


def test_publish_revalidates_and_keeps_invalid_dataset_staging() -> None:
    game_id = uuid4()
    source = _source(game_id)
    repository = MemoryDatasetRepository(game_id, source)
    service = DatasetService(repository)
    dataset = service.generate_mock_dataset(
        game_id,
        rules_version_id=source.rules_version_id,
        seed=71401,
    )
    repository.layouts[dataset.id] = repository.layouts[dataset.id][1:]

    with pytest.raises(DatasetConflictError) as error:
        service.publish_dataset_version(dataset.id)

    assert error.value.code == "DATASET_VERSION_NOT_READY"
    assert error.value.details["issues"]
    unchanged = repository.items[dataset.id]
    assert unchanged.status is DatasetVersionStatus.STAGING
    assert unchanged.published_at is None


def test_publish_and_archive_enforce_dataset_lifecycle() -> None:
    game_id = uuid4()
    source = _source(game_id)
    repository = MemoryDatasetRepository(game_id, source)
    service = DatasetService(repository)
    dataset = service.generate_mock_dataset(
        game_id,
        rules_version_id=source.rules_version_id,
        seed=71401,
    )

    with pytest.raises(DatasetConflictError) as archive_error:
        service.archive_dataset_version(dataset.id)
    assert archive_error.value.code == "DATASET_VERSION_NOT_PUBLISHED"

    service.publish_dataset_version(dataset.id)
    with pytest.raises(DatasetConflictError) as publish_error:
        service.publish_dataset_version(dataset.id)
    assert publish_error.value.code == "DATASET_VERSION_NOT_STAGING"


def test_validator_reports_every_blocker_and_keeps_duplicate_as_warning() -> None:
    dataset = DatasetVersion(
        id=uuid4(),
        game_id=uuid4(),
        version=3,
        rows=1,
        columns=2,
        signature_cell_width=1,
        expected_layout_count=3,
        layout_count=3,
        status=DatasetVersionStatus.STAGING,
        generation_seed=1,
        generator_version=MOCK_GENERATOR_VERSION,
        source_job_id=None,
        created_at=datetime.now(UTC),
        published_at=None,
    )
    source = DatasetValidationSource(
        dataset_version=dataset,
        allowed_symbol_mobile_codes=(1, 2),
        layouts=(
            LayoutValidationRecord(1, "11", (1, 1)),
            LayoutValidationRecord(1, "11", (1, 1)),
            LayoutValidationRecord(4, "xx", (3,)),
            LayoutValidationRecord(5, "22", (2, 2)),
        ),
    )

    report = validate_dataset(source)
    checks = {check.code: check for check in report.checks}

    assert not report.ready_for_publication
    assert checks[
        DatasetValidationCheckCode.LAYOUT_COUNT_MISMATCH
    ].issue_count == 1
    assert checks[
        DatasetValidationCheckCode.MISSING_SEQUENCE_NUMBER
    ].sequence_numbers == (2, 3)
    assert checks[
        DatasetValidationCheckCode.OUT_OF_RANGE_SEQUENCE_NUMBER
    ].sequence_numbers == (4, 5)
    assert checks[
        DatasetValidationCheckCode.DUPLICATE_SEQUENCE_NUMBER
    ].sequence_numbers == (1,)
    assert checks[
        DatasetValidationCheckCode.INVALID_CELL_COUNT
    ].sequence_numbers == (4,)
    foreign = checks[DatasetValidationCheckCode.FOREIGN_SYMBOL]
    assert foreign.sequence_numbers == (4,)
    assert foreign.mobile_codes == (3,)
    assert checks[
        DatasetValidationCheckCode.SIGNATURE_MISMATCH
    ].sequence_numbers == (4,)
    assert (
        checks[DatasetValidationCheckCode.DUPLICATE_SIGNATURE].status
        is DatasetValidationCheckStatus.WARNING
    )


def test_validation_samples_are_bounded_but_counts_are_exact() -> None:
    dataset = DatasetVersion(
        id=uuid4(),
        game_id=uuid4(),
        version=1,
        rows=1,
        columns=1,
        signature_cell_width=1,
        expected_layout_count=150,
        layout_count=150,
        status=DatasetVersionStatus.STAGING,
        generation_seed=1,
        generator_version=MOCK_GENERATOR_VERSION,
        source_job_id=None,
        created_at=datetime.now(UTC),
        published_at=None,
    )

    report = validate_dataset(
        DatasetValidationSource(dataset, (1,), ())
    )
    missing = next(
        check
        for check in report.checks
        if check.code is DatasetValidationCheckCode.MISSING_SEQUENCE_NUMBER
    )

    assert missing.issue_count == 150
    assert missing.sequence_numbers == tuple(range(1, 101))
    assert missing.truncated


def test_service_requires_worker_for_non_mock_validation() -> None:
    game_id = uuid4()
    source = _source(game_id)
    repository = MemoryDatasetRepository(game_id, source)
    service = DatasetService(repository)
    dataset = service.generate_mock_dataset(
        game_id,
        rules_version_id=source.rules_version_id,
        seed=1,
    )
    repository.items[dataset.id] = DatasetVersion(
        id=dataset.id,
        game_id=dataset.game_id,
        version=dataset.version,
        rows=dataset.rows,
        columns=dataset.columns,
        signature_cell_width=dataset.signature_cell_width,
        expected_layout_count=dataset.expected_layout_count,
        layout_count=dataset.layout_count,
        status=dataset.status,
        generation_seed=dataset.generation_seed,
        generator_version="import-v1",
        source_job_id=uuid4(),
        created_at=dataset.created_at,
        published_at=dataset.published_at,
    )

    with pytest.raises(DatasetConflictError) as error:
        service.get_validation_report(dataset.id)

    assert error.value.code == "DATASET_VALIDATION_REQUIRES_JOB"


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
