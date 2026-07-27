"""Application service and repository port for immutable mobile releases."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.domain.mobile_releases import (
    CURRENT_ALGORITHM_VERSION,
    CURRENT_SNAPSHOT_SCHEMA_VERSION,
    MobileRelease,
    MobileReleaseConflictError,
    MobileReleaseGame,
    MobileReleaseGameInput,
    MobileReleaseGameSource,
    MobileReleaseNotFoundError,
    start_mobile_release_build,
    validate_release_game_inputs,
    validate_release_game_source,
    validate_release_version,
)


class MobileReleaseRepository(Protocol):
    def list_mobile_releases(self) -> Sequence[MobileRelease]: ...

    def get_mobile_release(
        self,
        mobile_release_id: UUID,
    ) -> MobileRelease | None: ...

    def get_mobile_release_for_update(
        self,
        mobile_release_id: UUID,
    ) -> MobileRelease | None: ...

    def get_mobile_release_by_version(
        self,
        version: str,
    ) -> MobileRelease | None: ...

    def get_game_source_for_update(
        self,
        selection: MobileReleaseGameInput,
    ) -> MobileReleaseGameSource | None: ...

    def add_mobile_release(
        self,
        *,
        version: str,
        algorithm_version: str,
        snapshot_schema_version: int,
        games: Sequence[MobileReleaseGame],
    ) -> MobileRelease: ...

    def start_mobile_release_build(
        self,
        release: MobileRelease,
        job: Job,
    ) -> Job: ...


class MobileReleaseService:
    def __init__(self, repository: MobileReleaseRepository) -> None:
        self._repository = repository

    def list_mobile_releases(self) -> Sequence[MobileRelease]:
        return self._repository.list_mobile_releases()

    def get_mobile_release(self, mobile_release_id: UUID) -> MobileRelease:
        release = self._repository.get_mobile_release(mobile_release_id)
        if release is None:
            raise MobileReleaseNotFoundError(
                "MOBILE_RELEASE_NOT_FOUND",
                "Mobile release does not exist.",
                details={"mobileReleaseId": str(mobile_release_id)},
            )
        return release

    def create_mobile_release(
        self,
        *,
        version: str,
        games: tuple[MobileReleaseGameInput, ...],
    ) -> MobileRelease:
        validated_version = validate_release_version(version)
        selections = validate_release_game_inputs(games)
        if self._repository.get_mobile_release_by_version(validated_version):
            raise MobileReleaseConflictError(
                "MOBILE_RELEASE_VERSION_ALREADY_EXISTS",
                "A mobile release with this version already exists.",
                details={"version": validated_version},
            )

        validated_games: list[MobileReleaseGame] = []
        for selection in selections:
            source = self._repository.get_game_source_for_update(selection)
            if source is None:
                raise MobileReleaseNotFoundError(
                    "RELEASE_SOURCE_NOT_FOUND",
                    "A selected game, dataset version, or rules version does not exist.",
                    details={
                        "gameId": str(selection.game_id),
                        "datasetVersionId": str(selection.dataset_version_id),
                        "rulesVersionId": str(selection.rules_version_id),
                    },
                )
            validated_games.append(validate_release_game_source(selection, source))

        return self._repository.add_mobile_release(
            version=validated_version,
            algorithm_version=CURRENT_ALGORITHM_VERSION,
            snapshot_schema_version=CURRENT_SNAPSHOT_SCHEMA_VERSION,
            games=tuple(sorted(validated_games, key=lambda item: item.game_code)),
        )

    def start_mobile_release_build(self, mobile_release_id: UUID) -> Job:
        release = self._repository.get_mobile_release_for_update(mobile_release_id)
        if release is None:
            raise MobileReleaseNotFoundError(
                "MOBILE_RELEASE_NOT_FOUND",
                "Mobile release does not exist.",
                details={"mobileReleaseId": str(mobile_release_id)},
            )

        for game in release.games:
            selection = MobileReleaseGameInput(
                game_id=game.game_id,
                dataset_version_id=game.dataset_version_id,
                rules_version_id=game.rules_version_id,
            )
            source = self._repository.get_game_source_for_update(selection)
            if source is None:
                raise MobileReleaseNotFoundError(
                    "RELEASE_SOURCE_NOT_FOUND",
                    "A selected release source no longer exists.",
                    details={"mobileReleaseId": str(mobile_release_id)},
                )
            current = validate_release_game_source(selection, source)
            if current != game:
                raise MobileReleaseConflictError(
                    "MOBILE_RELEASE_SOURCE_CHANGED",
                    "A selected release source changed after the draft was created.",
                    details={
                        "mobileReleaseId": str(mobile_release_id),
                        "gameId": str(game.game_id),
                    },
                )

        job = create_job(
            JobType.ANDROID_BUILD,
            game_id=None,
            input_payload={
                "schema_version": 1,
                "mobile_release_id": str(release.id),
            },
        )
        started = start_mobile_release_build(
            release,
            build_job_id=job.id,
        )
        return self._repository.start_mobile_release_build(started, job)
