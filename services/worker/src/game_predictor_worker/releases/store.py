"""PostgreSQL state transitions for the release workflow."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.domain.mobile_releases import (
    MobileRelease,
    MobileReleaseConflictError,
    MobileReleaseGameInput,
    complete_mobile_release,
    fail_mobile_release,
    mark_mobile_release_building,
    record_mobile_release_snapshot,
    validate_release_game_source,
)
from game_predictor_api.storage.mobile_release_repository import (
    SqlAlchemyMobileReleaseRepository,
)
from game_predictor_api.storage.models import JobModel, MobileReleaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker


class SqlAlchemyReleaseWorkflowStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load_release(self, mobile_release_id: UUID) -> MobileRelease | None:
        with self._session_factory() as session:
            return SqlAlchemyMobileReleaseRepository(session).get_mobile_release(mobile_release_id)

    def require_current_sources(self, release: MobileRelease) -> None:
        with self._session_factory() as session, session.begin():
            repository = SqlAlchemyMobileReleaseRepository(session)
            for game in release.games:
                selection = MobileReleaseGameInput(
                    game_id=game.game_id,
                    dataset_version_id=game.dataset_version_id,
                    rules_version_id=game.rules_version_id,
                )
                source = repository.get_game_source_for_update(selection)
                if source is None:
                    raise MobileReleaseConflictError(
                        "RELEASE_SOURCE_NOT_FOUND",
                        "A selected release source no longer exists.",
                        details={"mobileReleaseId": str(release.id)},
                    )
                if validate_release_game_source(selection, source) != game:
                    raise MobileReleaseConflictError(
                        "MOBILE_RELEASE_SOURCE_CHANGED",
                        "A selected release source changed after build start.",
                        details={
                            "mobileReleaseId": str(release.id),
                            "gameId": str(game.game_id),
                        },
                    )

    def mark_building(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
    ) -> MobileRelease:
        return self._update(
            mobile_release_id,
            build_job_id=build_job_id,
            transition=lambda release: mark_mobile_release_building(
                release,
                build_job_id=build_job_id,
            ),
        )

    def record_snapshot(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
        relative_path: str,
        checksum: str,
    ) -> MobileRelease:
        return self._update(
            mobile_release_id,
            build_job_id=build_job_id,
            transition=lambda release: record_mobile_release_snapshot(
                release,
                build_job_id=build_job_id,
                relative_path=relative_path,
                checksum=checksum,
            ),
        )

    def mark_ready(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
        apk_relative_path: str,
        apk_checksum: str,
    ) -> MobileRelease:
        return self._update(
            mobile_release_id,
            build_job_id=build_job_id,
            require_not_cancelled=True,
            transition=lambda release: complete_mobile_release(
                release,
                build_job_id=build_job_id,
                apk_relative_path=apk_relative_path,
                apk_checksum=apk_checksum,
            ),
        )

    def mark_failed(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
    ) -> MobileRelease:
        return self._update(
            mobile_release_id,
            build_job_id=build_job_id,
            transition=lambda release: fail_mobile_release(
                release,
                build_job_id=build_job_id,
            ),
        )

    def _update(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
        transition: Callable[[MobileRelease], MobileRelease],
        require_not_cancelled: bool = False,
    ) -> MobileRelease:
        with self._session_factory() as session, session.begin():
            record = session.scalar(
                select(MobileReleaseModel)
                .where(MobileReleaseModel.id == mobile_release_id)
                .with_for_update()
            )
            if record is None:
                raise MobileReleaseConflictError(
                    "MOBILE_RELEASE_NOT_FOUND",
                    "Mobile release no longer exists.",
                    details={"mobileReleaseId": str(mobile_release_id)},
                )
            if require_not_cancelled:
                job = session.scalar(
                    select(JobModel).where(JobModel.id == build_job_id).with_for_update()
                )
                if (
                    job is None
                    or job.status is not JobStatus.PROCESSING
                    or job.cancel_requested_at is not None
                ):
                    raise MobileReleaseConflictError(
                        "MOBILE_RELEASE_BUILD_NOT_ACTIVE",
                        "Only the active, non-cancelled build can make a release ready.",
                        details={"mobileReleaseId": str(mobile_release_id)},
                    )
            repository = SqlAlchemyMobileReleaseRepository(session)
            release = repository.get_mobile_release(mobile_release_id)
            if release is None:
                raise RuntimeError("Locked mobile release disappeared.")
            updated = transition(release)
            _apply_release(record, updated)
            session.flush()
            return updated


def _apply_release(
    record: MobileReleaseModel,
    release: MobileRelease,
) -> None:
    record.status = release.status
    record.snapshot_path = release.snapshot_path
    record.snapshot_checksum = release.snapshot_checksum
    record.apk_path = release.apk_path
    record.apk_checksum = release.apk_checksum
    record.build_job_id = release.build_job_id
    record.ready_at = release.ready_at
