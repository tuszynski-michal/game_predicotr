"""OpenAPI schemas for immutable mobile release selections."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.jobs import Job, JobStatus
from game_predictor_api.domain.mobile_releases import (
    MAX_RELEASE_GAMES,
    MAX_RELEASE_VERSION_LENGTH,
    MobileRelease,
    MobileReleaseStatus,
)
from game_predictor_api.schemas.catalog import ApiModel


class MobileReleaseGameCreate(ApiModel):
    game_id: UUID
    dataset_version_id: UUID
    rules_version_id: UUID


class MobileReleaseCreate(ApiModel):
    version: str = Field(
        min_length=1,
        max_length=MAX_RELEASE_VERSION_LENGTH,
    )
    games: tuple[MobileReleaseGameCreate, ...] = Field(
        min_length=1,
        max_length=MAX_RELEASE_GAMES,
    )


class MobileReleaseGameResponse(ApiModel):
    game_id: UUID
    game_code: str
    dataset_version_id: UUID
    dataset_version: int
    rules_version_id: UUID
    rules_version: int
    rows: int
    columns: int
    layout_count: int


class MobileReleaseSnapshotResponse(ApiModel):
    schema_version: int
    relative_path: str
    checksum: str


class MobileReleaseApkResponse(ApiModel):
    relative_path: str
    checksum: str


class MobileReleaseResponse(ApiModel):
    id: UUID
    version: str
    status: MobileReleaseStatus
    algorithm_version: str
    snapshot_schema_version: int
    snapshot: MobileReleaseSnapshotResponse | None
    apk: MobileReleaseApkResponse | None
    build_job_id: UUID | None
    created_at: datetime
    ready_at: datetime | None
    games: tuple[MobileReleaseGameResponse, ...]


class MobileReleaseBuildResponse(ApiModel):
    job_id: UUID
    status: JobStatus

    @classmethod
    def from_job(cls, job: Job) -> MobileReleaseBuildResponse:
        return cls(job_id=job.id, status=job.status)


def to_mobile_release_response(
    release: MobileRelease,
) -> MobileReleaseResponse:
    snapshot = None
    if release.snapshot_path is not None:
        if release.snapshot_checksum is None:
            raise RuntimeError("Persisted mobile release snapshot is missing its checksum.")
        snapshot = MobileReleaseSnapshotResponse(
            schema_version=release.snapshot_schema_version,
            relative_path=release.snapshot_path,
            checksum=release.snapshot_checksum,
        )
    apk = None
    if release.apk_path is not None:
        if release.apk_checksum is None:
            raise RuntimeError("Persisted mobile release APK is missing its checksum.")
        apk = MobileReleaseApkResponse(
            relative_path=release.apk_path,
            checksum=release.apk_checksum,
        )
    return MobileReleaseResponse(
        id=release.id,
        version=release.version,
        status=release.status,
        algorithm_version=release.algorithm_version,
        snapshot_schema_version=release.snapshot_schema_version,
        snapshot=snapshot,
        apk=apk,
        build_job_id=release.build_job_id,
        created_at=release.created_at,
        ready_at=release.ready_at,
        games=tuple(MobileReleaseGameResponse.model_validate(game) for game in release.games),
    )
