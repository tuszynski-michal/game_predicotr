"""SQLAlchemy implementation of the mobile release repository port."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.mobile_releases import (
    MobileReleaseRepository,
)
from game_predictor_api.domain.jobs import Job
from game_predictor_api.domain.mobile_releases import (
    MobileRelease,
    MobileReleaseConflictError,
    MobileReleaseDatasetSource,
    MobileReleaseGame,
    MobileReleaseGameInput,
    MobileReleaseGameSource,
    MobileReleaseRulesSource,
    MobileReleaseStatus,
)
from game_predictor_api.storage.job_repository import job_record_from_domain
from game_predictor_api.storage.models import (
    DatasetVersionModel,
    GameModel,
    MobileReleaseGameModel,
    MobileReleaseModel,
    RulesVersionModel,
)


class SqlAlchemyMobileReleaseRepository(MobileReleaseRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_mobile_releases(self) -> list[MobileRelease]:
        records = list(
            self._session.scalars(
                select(MobileReleaseModel).order_by(
                    MobileReleaseModel.created_at.desc(),
                    MobileReleaseModel.id.desc(),
                )
            )
        )
        return self._load_release_games(records)

    def get_mobile_release(
        self,
        mobile_release_id: UUID,
    ) -> MobileRelease | None:
        record = self._session.get(MobileReleaseModel, mobile_release_id)
        if record is None:
            return None
        return self._load_release_games([record])[0]

    def get_mobile_release_for_update(
        self,
        mobile_release_id: UUID,
    ) -> MobileRelease | None:
        record = self._session.scalar(
            select(MobileReleaseModel)
            .where(MobileReleaseModel.id == mobile_release_id)
            .with_for_update()
        )
        if record is None:
            return None
        return self._load_release_games([record])[0]

    def get_mobile_release_by_version(
        self,
        version: str,
    ) -> MobileRelease | None:
        record = self._session.scalar(
            select(MobileReleaseModel).where(MobileReleaseModel.version == version)
        )
        if record is None:
            return None
        return self._load_release_games([record])[0]

    def get_game_source_for_update(
        self,
        selection: MobileReleaseGameInput,
    ) -> MobileReleaseGameSource | None:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == selection.game_id).with_for_update()
        )
        dataset = self._session.scalar(
            select(DatasetVersionModel)
            .where(DatasetVersionModel.id == selection.dataset_version_id)
            .with_for_update()
        )
        rules = self._session.scalar(
            select(RulesVersionModel)
            .where(RulesVersionModel.id == selection.rules_version_id)
            .with_for_update()
        )
        if game is None or dataset is None or rules is None:
            return None
        return MobileReleaseGameSource(
            game_id=game.id,
            game_code=game.code,
            game_status=game.status,
            dataset=MobileReleaseDatasetSource(
                id=dataset.id,
                game_id=dataset.game_id,
                version=dataset.version,
                rows=dataset.rows,
                columns=dataset.columns,
                layout_count=dataset.layout_count,
                status=dataset.status,
            ),
            rules=MobileReleaseRulesSource(
                id=rules.id,
                game_id=rules.game_id,
                version=rules.version,
                rows=rules.rows,
                columns=rules.columns,
                status=rules.status,
            ),
        )

    def add_mobile_release(
        self,
        *,
        version: str,
        algorithm_version: str,
        snapshot_schema_version: int,
        games: Sequence[MobileReleaseGame],
    ) -> MobileRelease:
        record = MobileReleaseModel(
            version=version,
            status=MobileReleaseStatus.DRAFT,
            algorithm_version=algorithm_version,
            snapshot_schema_version=snapshot_schema_version,
        )
        self._session.add(record)
        try:
            self._session.flush()
            self._session.add_all(
                [
                    MobileReleaseGameModel(
                        mobile_release_id=record.id,
                        game_id=game.game_id,
                        dataset_version_id=game.dataset_version_id,
                        rules_version_id=game.rules_version_id,
                        layout_count=game.layout_count,
                    )
                    for game in games
                ]
            )
            self._session.flush()
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            constraint_name = getattr(diagnostic, "constraint_name", None)
            if constraint_name == "uq_mobile_releases_version":
                raise MobileReleaseConflictError(
                    "MOBILE_RELEASE_VERSION_ALREADY_EXISTS",
                    "A mobile release with this version already exists.",
                    details={"version": version},
                ) from error
            raise
        self._session.refresh(record)
        return _to_mobile_release(record, tuple(games))

    def start_mobile_release_build(
        self,
        release: MobileRelease,
        job: Job,
    ) -> Job:
        record = self._session.get(MobileReleaseModel, release.id)
        if record is None:
            raise MobileReleaseConflictError(
                "MOBILE_RELEASE_NOT_FOUND",
                "Mobile release no longer exists.",
                details={"mobileReleaseId": str(release.id)},
            )
        self._session.add(job_record_from_domain(job))
        record.status = release.status
        record.build_job_id = release.build_job_id
        try:
            self._session.flush()
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            constraint_name = getattr(diagnostic, "constraint_name", None)
            if constraint_name in {
                "uq_jobs_input_key",
                "uq_mobile_releases_build_job_id",
            }:
                raise MobileReleaseConflictError(
                    "MOBILE_RELEASE_BUILD_ALREADY_STARTED",
                    "The mobile release already has a build workflow.",
                    details={"mobileReleaseId": str(release.id)},
                ) from error
            raise
        return job

    def _load_release_games(
        self,
        records: Sequence[MobileReleaseModel],
    ) -> list[MobileRelease]:
        if not records:
            return []
        release_ids = [record.id for record in records]
        rows = self._session.execute(
            select(
                MobileReleaseGameModel,
                GameModel,
                DatasetVersionModel,
                RulesVersionModel,
            )
            .join(
                GameModel,
                GameModel.id == MobileReleaseGameModel.game_id,
            )
            .join(
                DatasetVersionModel,
                DatasetVersionModel.id == MobileReleaseGameModel.dataset_version_id,
            )
            .join(
                RulesVersionModel,
                RulesVersionModel.id == MobileReleaseGameModel.rules_version_id,
            )
            .where(MobileReleaseGameModel.mobile_release_id.in_(release_ids))
            .order_by(
                MobileReleaseGameModel.mobile_release_id,
                GameModel.code,
                GameModel.id,
            )
        )
        games_by_release: dict[UUID, list[MobileReleaseGame]] = {
            release_id: [] for release_id in release_ids
        }
        for release_game, game, dataset, rules in rows:
            games_by_release[release_game.mobile_release_id].append(
                MobileReleaseGame(
                    game_id=game.id,
                    game_code=game.code,
                    dataset_version_id=dataset.id,
                    dataset_version=dataset.version,
                    rules_version_id=rules.id,
                    rules_version=rules.version,
                    rows=rules.rows,
                    columns=rules.columns,
                    layout_count=release_game.layout_count,
                )
            )
        return [
            _to_mobile_release(
                record,
                tuple(games_by_release[record.id]),
            )
            for record in records
        ]


def _to_mobile_release(
    record: MobileReleaseModel,
    games: tuple[MobileReleaseGame, ...],
) -> MobileRelease:
    return MobileRelease(
        id=record.id,
        version=record.version,
        status=record.status,
        algorithm_version=record.algorithm_version,
        snapshot_schema_version=record.snapshot_schema_version,
        snapshot_path=record.snapshot_path,
        snapshot_checksum=record.snapshot_checksum,
        apk_path=record.apk_path,
        apk_checksum=record.apk_checksum,
        build_job_id=record.build_job_id,
        created_at=record.created_at,
        ready_at=record.ready_at,
        games=games,
    )
