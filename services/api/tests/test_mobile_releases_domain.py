from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.mobile_releases import (
    MobileReleaseRepository,
    MobileReleaseService,
)
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.domain.mobile_releases import (
    CURRENT_ALGORITHM_VERSION,
    CURRENT_SNAPSHOT_SCHEMA_VERSION,
    MAX_RELEASE_GAMES,
    MobileRelease,
    MobileReleaseConflictError,
    MobileReleaseDatasetSource,
    MobileReleaseError,
    MobileReleaseGame,
    MobileReleaseGameInput,
    MobileReleaseGameSource,
    MobileReleaseRulesSource,
    MobileReleaseStatus,
    complete_mobile_release,
    fail_mobile_release,
    record_mobile_release_snapshot,
    start_mobile_release_build,
)
from game_predictor_api.domain.rules import RulesVersionStatus


class FakeMobileReleaseRepository(MobileReleaseRepository):
    def __init__(self) -> None:
        self.items: list[MobileRelease] = []
        self.sources: dict[UUID, MobileReleaseGameSource] = {}

    def list_mobile_releases(self) -> list[MobileRelease]:
        return list(self.items)

    def get_mobile_release(
        self,
        mobile_release_id: UUID,
    ) -> MobileRelease | None:
        return next(
            (item for item in self.items if item.id == mobile_release_id),
            None,
        )

    def get_mobile_release_for_update(
        self,
        mobile_release_id: UUID,
    ) -> MobileRelease | None:
        return self.get_mobile_release(mobile_release_id)

    def get_mobile_release_by_version(
        self,
        version: str,
    ) -> MobileRelease | None:
        return next(
            (item for item in self.items if item.version == version),
            None,
        )

    def get_game_source_for_update(
        self,
        selection: MobileReleaseGameInput,
    ) -> MobileReleaseGameSource | None:
        return self.sources.get(selection.game_id)

    def add_mobile_release(
        self,
        *,
        version: str,
        algorithm_version: str,
        snapshot_schema_version: int,
        games: tuple[MobileReleaseGame, ...],
    ) -> MobileRelease:
        release = MobileRelease(
            id=uuid4(),
            version=version,
            status=MobileReleaseStatus.DRAFT,
            algorithm_version=algorithm_version,
            snapshot_schema_version=snapshot_schema_version,
            snapshot_path=None,
            snapshot_checksum=None,
            apk_path=None,
            apk_checksum=None,
            build_job_id=None,
            created_at=datetime.now(UTC),
            ready_at=None,
            games=games,
        )
        self.items.append(release)
        return release

    def start_mobile_release_build(
        self,
        release: MobileRelease,
        job: Job,
    ) -> Job:
        self.items = [release if item.id == release.id else item for item in self.items]
        return job


def _source(
    *,
    game_code: str = "game-1",
    game_status: GameStatus = GameStatus.ACTIVE,
    dataset_status: DatasetVersionStatus = DatasetVersionStatus.PUBLISHED,
    rules_status: RulesVersionStatus = RulesVersionStatus.PUBLISHED,
    dataset_rows: int = 3,
    dataset_columns: int = 5,
    rules_rows: int = 3,
    rules_columns: int = 5,
    layout_count: int = 1000,
) -> tuple[MobileReleaseGameInput, MobileReleaseGameSource]:
    game_id = uuid4()
    dataset_id = uuid4()
    rules_id = uuid4()
    selection = MobileReleaseGameInput(
        game_id=game_id,
        dataset_version_id=dataset_id,
        rules_version_id=rules_id,
    )
    return selection, MobileReleaseGameSource(
        game_id=game_id,
        game_code=game_code,
        game_status=game_status,
        dataset=MobileReleaseDatasetSource(
            id=dataset_id,
            game_id=game_id,
            version=7,
            rows=dataset_rows,
            columns=dataset_columns,
            layout_count=layout_count,
            status=dataset_status,
        ),
        rules=MobileReleaseRulesSource(
            id=rules_id,
            game_id=game_id,
            version=5,
            rows=rules_rows,
            columns=rules_columns,
            status=rules_status,
        ),
    )


def test_create_release_uses_server_versions_and_stable_game_order() -> None:
    repository = FakeMobileReleaseRepository()
    second_selection, second_source = _source(game_code="game-z")
    first_selection, first_source = _source(game_code="game-a")
    repository.sources = {
        second_selection.game_id: second_source,
        first_selection.game_id: first_source,
    }

    release = MobileReleaseService(repository).create_mobile_release(
        version="m3.4-test_1",
        games=(second_selection, first_selection),
    )

    assert release.status is MobileReleaseStatus.DRAFT
    assert release.algorithm_version == CURRENT_ALGORITHM_VERSION
    assert release.snapshot_schema_version == CURRENT_SNAPSHOT_SCHEMA_VERSION
    assert [game.game_code for game in release.games] == [
        "game-a",
        "game-z",
    ]
    assert release.snapshot_path is None
    assert release.build_job_id is None


@pytest.mark.parametrize(
    ("source_change", "expected_code"),
    [
        (
            {"game_status": GameStatus.ARCHIVED},
            "RELEASE_GAME_NOT_ACTIVE",
        ),
        (
            {"dataset_status": DatasetVersionStatus.STAGING},
            "RELEASE_DATASET_NOT_PUBLISHED",
        ),
        (
            {"dataset_status": DatasetVersionStatus.ARCHIVED},
            "RELEASE_DATASET_NOT_PUBLISHED",
        ),
        (
            {"rules_status": RulesVersionStatus.DRAFT},
            "RELEASE_RULES_NOT_PUBLISHED",
        ),
        (
            {"rules_status": RulesVersionStatus.ARCHIVED},
            "RELEASE_RULES_NOT_PUBLISHED",
        ),
        (
            {"dataset_rows": 4},
            "RELEASE_SOURCE_DIMENSIONS_MISMATCH",
        ),
        (
            {"layout_count": 0},
            "RELEASE_DATASET_EMPTY",
        ),
    ],
)
def test_release_rejects_ineligible_sources(
    source_change: dict[str, object],
    expected_code: str,
) -> None:
    repository = FakeMobileReleaseRepository()
    selection, source = _source(**source_change)  # type: ignore[arg-type]
    repository.sources[selection.game_id] = source

    with pytest.raises(MobileReleaseConflictError) as error:
        MobileReleaseService(repository).create_mobile_release(
            version="release-1",
            games=(selection,),
        )

    assert error.value.code == expected_code
    assert repository.items == []


@pytest.mark.parametrize(
    ("version", "expected_code"),
    [
        ("", "INVALID_RELEASE_VERSION"),
        (".hidden", "INVALID_RELEASE_VERSION"),
        ("nested/release", "INVALID_RELEASE_VERSION"),
        ("a" * 101, "INVALID_RELEASE_VERSION"),
    ],
)
def test_release_version_is_a_safe_path_segment(
    version: str,
    expected_code: str,
) -> None:
    with pytest.raises(MobileReleaseError) as error:
        MobileReleaseService(FakeMobileReleaseRepository()).create_mobile_release(
            version=version, games=()
        )

    assert error.value.code == expected_code


def test_release_requires_unique_bounded_games_and_version() -> None:
    repository = FakeMobileReleaseRepository()
    selection, source = _source()
    repository.sources[selection.game_id] = source
    service = MobileReleaseService(repository)

    with pytest.raises(MobileReleaseError) as empty_error:
        service.create_mobile_release(version="release-empty", games=())
    assert empty_error.value.code == "INVALID_RELEASE_GAME_COUNT"

    with pytest.raises(MobileReleaseError) as duplicate_error:
        service.create_mobile_release(
            version="release-duplicate",
            games=(selection, selection),
        )
    assert duplicate_error.value.code == "DUPLICATE_RELEASE_GAME"

    too_many = tuple(
        MobileReleaseGameInput(uuid4(), uuid4(), uuid4()) for _ in range(MAX_RELEASE_GAMES + 1)
    )
    with pytest.raises(MobileReleaseError) as count_error:
        service.create_mobile_release(
            version="release-too-many",
            games=too_many,
        )
    assert count_error.value.code == "INVALID_RELEASE_GAME_COUNT"

    service.create_mobile_release(version="release-1", games=(selection,))
    with pytest.raises(MobileReleaseConflictError) as version_error:
        service.create_mobile_release(
            version="release-1",
            games=(selection,),
        )
    assert version_error.value.code == "MOBILE_RELEASE_VERSION_ALREADY_EXISTS"


def test_release_reports_missing_and_cross_game_source() -> None:
    repository = FakeMobileReleaseRepository()
    selection, source = _source()
    service = MobileReleaseService(repository)

    with pytest.raises(MobileReleaseError) as missing:
        service.create_mobile_release(
            version="release-missing",
            games=(selection,),
        )
    assert missing.value.code == "RELEASE_SOURCE_NOT_FOUND"

    repository.sources[selection.game_id] = replace(
        source,
        dataset=replace(source.dataset, game_id=uuid4()),
    )
    with pytest.raises(MobileReleaseConflictError) as mismatch:
        service.create_mobile_release(
            version="release-mismatch",
            games=(selection,),
        )
    assert mismatch.value.code == "RELEASE_SOURCE_GAME_MISMATCH"


def test_release_build_start_is_atomic_and_revalidates_sources() -> None:
    repository = FakeMobileReleaseRepository()
    selection, source = _source()
    repository.sources[selection.game_id] = source
    service = MobileReleaseService(repository)
    release = service.create_mobile_release(
        version="release-build-1",
        games=(selection,),
    )

    job = service.start_mobile_release_build(release.id)

    assert job.job_type is JobType.ANDROID_BUILD
    assert job.input_payload == {
        "schema_version": 1,
        "mobile_release_id": str(release.id),
    }
    assert repository.items[0].status is MobileReleaseStatus.BUILDING
    assert repository.items[0].build_job_id == job.id

    with pytest.raises(MobileReleaseConflictError) as duplicate:
        service.start_mobile_release_build(release.id)
    assert duplicate.value.code == "MOBILE_RELEASE_BUILD_ALREADY_STARTED"


def test_release_build_rejects_source_changed_after_draft() -> None:
    repository = FakeMobileReleaseRepository()
    selection, source = _source()
    repository.sources[selection.game_id] = source
    service = MobileReleaseService(repository)
    release = service.create_mobile_release(
        version="release-build-changed",
        games=(selection,),
    )
    repository.sources[selection.game_id] = replace(
        source,
        dataset=replace(source.dataset, layout_count=source.dataset.layout_count + 1),
    )

    with pytest.raises(MobileReleaseConflictError) as error:
        service.start_mobile_release_build(release.id)

    assert error.value.code == "MOBILE_RELEASE_SOURCE_CHANGED"
    assert repository.items[0].status is MobileReleaseStatus.DRAFT


def test_release_lifecycle_requires_complete_verified_artifacts() -> None:
    repository = FakeMobileReleaseRepository()
    selection, source = _source()
    repository.sources[selection.game_id] = source
    release = MobileReleaseService(repository).create_mobile_release(
        version="release-lifecycle",
        games=(selection,),
    )
    job_id = uuid4()
    building = start_mobile_release_build(release, build_job_id=job_id)

    with pytest.raises(MobileReleaseConflictError) as missing_snapshot:
        complete_mobile_release(
            building,
            build_job_id=job_id,
            apk_relative_path="android-releases/release/app-release.apk",
            apk_checksum="b" * 64,
        )
    assert missing_snapshot.value.code == "MOBILE_RELEASE_SNAPSHOT_MISSING"

    with_snapshot = record_mobile_release_snapshot(
        building,
        build_job_id=job_id,
        relative_path="snapshots/release/checksum/snapshot.db",
        checksum="a" * 64,
    )
    ready = complete_mobile_release(
        with_snapshot,
        build_job_id=job_id,
        apk_relative_path="android-releases/release/checksum/app-release.apk",
        apk_checksum="b" * 64,
    )
    assert ready.status is MobileReleaseStatus.READY
    assert ready.ready_at is not None

    with pytest.raises(MobileReleaseConflictError):
        fail_mobile_release(ready, build_job_id=job_id)
