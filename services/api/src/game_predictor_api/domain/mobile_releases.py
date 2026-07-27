"""Framework-independent mobile release identity and source validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final
from uuid import UUID

from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus

CURRENT_ALGORITHM_VERSION: Final = "payout-v2"
CURRENT_SNAPSHOT_SCHEMA_VERSION: Final = 2
MAX_RELEASE_GAMES: Final = 15
MAX_RELEASE_VERSION_LENGTH: Final = 100
_RELEASE_VERSION_PATTERN: Final = re.compile(
    rf"^[A-Za-z0-9][A-Za-z0-9._-]{{0,{MAX_RELEASE_VERSION_LENGTH - 1}}}$"
)
_SHA256_PATTERN: Final = re.compile(r"^[a-f0-9]{64}$")


class MobileReleaseStatus(StrEnum):
    DRAFT = "draft"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


class MobileReleaseError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class MobileReleaseNotFoundError(MobileReleaseError):
    """A release or one of its selected sources does not exist."""


class MobileReleaseConflictError(MobileReleaseError):
    """A release cannot be created from the selected source state."""


@dataclass(frozen=True, slots=True)
class MobileReleaseGameInput:
    game_id: UUID
    dataset_version_id: UUID
    rules_version_id: UUID


@dataclass(frozen=True, slots=True)
class MobileReleaseDatasetSource:
    id: UUID
    game_id: UUID
    version: int
    rows: int
    columns: int
    layout_count: int
    status: DatasetVersionStatus


@dataclass(frozen=True, slots=True)
class MobileReleaseRulesSource:
    id: UUID
    game_id: UUID
    version: int
    rows: int
    columns: int
    status: RulesVersionStatus


@dataclass(frozen=True, slots=True)
class MobileReleaseGameSource:
    game_id: UUID
    game_code: str
    game_status: GameStatus
    dataset: MobileReleaseDatasetSource
    rules: MobileReleaseRulesSource


@dataclass(frozen=True, slots=True)
class MobileReleaseGame:
    game_id: UUID
    game_code: str
    dataset_version_id: UUID
    dataset_version: int
    rules_version_id: UUID
    rules_version: int
    rows: int
    columns: int
    layout_count: int


@dataclass(frozen=True, slots=True)
class MobileRelease:
    id: UUID
    version: str
    status: MobileReleaseStatus
    algorithm_version: str
    snapshot_schema_version: int
    snapshot_path: str | None
    snapshot_checksum: str | None
    apk_path: str | None
    apk_checksum: str | None
    build_job_id: UUID | None
    created_at: datetime
    ready_at: datetime | None
    games: tuple[MobileReleaseGame, ...]


def validate_release_version(value: str) -> str:
    if not _RELEASE_VERSION_PATTERN.fullmatch(value):
        raise MobileReleaseError(
            "INVALID_RELEASE_VERSION",
            (
                "version must contain 1-100 ASCII letters, digits, dots, "
                "underscores, or hyphens and start with a letter or digit."
            ),
            details={"field": "version"},
        )
    return value


def validate_release_game_inputs(
    games: tuple[MobileReleaseGameInput, ...],
) -> tuple[MobileReleaseGameInput, ...]:
    if not 1 <= len(games) <= MAX_RELEASE_GAMES:
        raise MobileReleaseError(
            "INVALID_RELEASE_GAME_COUNT",
            "A mobile release must contain between 1 and 15 games.",
            details={"field": "games", "gameCount": len(games)},
        )
    game_ids = [item.game_id for item in games]
    if len(set(game_ids)) != len(game_ids):
        raise MobileReleaseError(
            "DUPLICATE_RELEASE_GAME",
            "Each game can be selected only once in a mobile release.",
            details={"field": "games"},
        )
    return games


def validate_release_game_source(
    selection: MobileReleaseGameInput,
    source: MobileReleaseGameSource,
) -> MobileReleaseGame:
    details: dict[str, object] = {
        "gameId": str(selection.game_id),
        "datasetVersionId": str(selection.dataset_version_id),
        "rulesVersionId": str(selection.rules_version_id),
    }
    if source.game_id != selection.game_id:
        raise MobileReleaseConflictError(
            "RELEASE_SOURCE_GAME_MISMATCH",
            "The selected source does not belong to the requested game.",
            details=details,
        )
    if source.game_status is not GameStatus.ACTIVE:
        raise MobileReleaseConflictError(
            "RELEASE_GAME_NOT_ACTIVE",
            "Only an active game can be included in a new mobile release.",
            details=details,
        )
    if (
        source.dataset.id != selection.dataset_version_id
        or source.dataset.game_id != selection.game_id
        or source.rules.id != selection.rules_version_id
        or source.rules.game_id != selection.game_id
    ):
        raise MobileReleaseConflictError(
            "RELEASE_SOURCE_GAME_MISMATCH",
            "Dataset and rules versions must belong to the selected game.",
            details=details,
        )
    if source.dataset.status is not DatasetVersionStatus.PUBLISHED:
        raise MobileReleaseConflictError(
            "RELEASE_DATASET_NOT_PUBLISHED",
            "A new release requires a published dataset version.",
            details=details,
        )
    if source.rules.status is not RulesVersionStatus.PUBLISHED:
        raise MobileReleaseConflictError(
            "RELEASE_RULES_NOT_PUBLISHED",
            "A new release requires a published rules version.",
            details=details,
        )
    if source.dataset.rows != source.rules.rows or source.dataset.columns != source.rules.columns:
        raise MobileReleaseConflictError(
            "RELEASE_SOURCE_DIMENSIONS_MISMATCH",
            "Dataset and rules versions must have identical dimensions.",
            details=details,
        )
    if source.dataset.layout_count <= 0:
        raise MobileReleaseConflictError(
            "RELEASE_DATASET_EMPTY",
            "A release dataset must contain at least one layout.",
            details=details,
        )
    return MobileReleaseGame(
        game_id=source.game_id,
        game_code=source.game_code,
        dataset_version_id=source.dataset.id,
        dataset_version=source.dataset.version,
        rules_version_id=source.rules.id,
        rules_version=source.rules.version,
        rows=source.rules.rows,
        columns=source.rules.columns,
        layout_count=source.dataset.layout_count,
    )


def start_mobile_release_build(
    release: MobileRelease,
    *,
    build_job_id: UUID,
) -> MobileRelease:
    if (
        release.status is not MobileReleaseStatus.DRAFT
        or release.build_job_id is not None
        or release.snapshot_path is not None
        or release.apk_path is not None
    ):
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_BUILD_ALREADY_STARTED",
            "Only an untouched draft mobile release can start a build.",
            details={
                "mobileReleaseId": str(release.id),
                "status": release.status.value,
                "buildJobId": (None if release.build_job_id is None else str(release.build_job_id)),
            },
        )
    return replace(
        release,
        status=MobileReleaseStatus.BUILDING,
        build_job_id=build_job_id,
    )


def mark_mobile_release_building(
    release: MobileRelease,
    *,
    build_job_id: UUID,
) -> MobileRelease:
    _require_build_job(release, build_job_id)
    if release.status not in {
        MobileReleaseStatus.BUILDING,
        MobileReleaseStatus.FAILED,
    }:
        _raise_release_transition(release, MobileReleaseStatus.BUILDING)
    return replace(
        release,
        status=MobileReleaseStatus.BUILDING,
        ready_at=None,
    )


def record_mobile_release_snapshot(
    release: MobileRelease,
    *,
    build_job_id: UUID,
    relative_path: str,
    checksum: str,
) -> MobileRelease:
    _require_active_build(release, build_job_id)
    path = _validate_artifact(relative_path, checksum, kind="snapshot")
    if release.snapshot_path is not None and (
        release.snapshot_path != path or release.snapshot_checksum != checksum
    ):
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_SNAPSHOT_IMMUTABLE",
            "A release snapshot cannot be replaced by a different artifact.",
            details={"mobileReleaseId": str(release.id)},
        )
    return replace(
        release,
        snapshot_path=path,
        snapshot_checksum=checksum,
    )


def complete_mobile_release(
    release: MobileRelease,
    *,
    build_job_id: UUID,
    apk_relative_path: str,
    apk_checksum: str,
    ready_at: datetime | None = None,
) -> MobileRelease:
    _require_active_build(release, build_job_id)
    if release.snapshot_path is None or release.snapshot_checksum is None:
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_SNAPSHOT_MISSING",
            "A release cannot become ready without a verified snapshot.",
            details={"mobileReleaseId": str(release.id)},
        )
    path = _validate_artifact(apk_relative_path, apk_checksum, kind="apk")
    if release.apk_path is not None and (
        release.apk_path != path or release.apk_checksum != apk_checksum
    ):
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_APK_IMMUTABLE",
            "A release APK cannot be replaced by a different artifact.",
            details={"mobileReleaseId": str(release.id)},
        )
    now = ready_at or datetime.now(UTC)
    return replace(
        release,
        status=MobileReleaseStatus.READY,
        apk_path=path,
        apk_checksum=apk_checksum,
        ready_at=now,
    )


def fail_mobile_release(
    release: MobileRelease,
    *,
    build_job_id: UUID,
) -> MobileRelease:
    _require_build_job(release, build_job_id)
    if release.status is MobileReleaseStatus.READY:
        _raise_release_transition(release, MobileReleaseStatus.FAILED)
    if release.status is MobileReleaseStatus.ARCHIVED:
        _raise_release_transition(release, MobileReleaseStatus.FAILED)
    return replace(
        release,
        status=MobileReleaseStatus.FAILED,
        ready_at=None,
    )


def _require_build_job(release: MobileRelease, build_job_id: UUID) -> None:
    if release.build_job_id != build_job_id:
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_BUILD_JOB_MISMATCH",
            "The job does not own this mobile release build.",
            details={
                "mobileReleaseId": str(release.id),
                "buildJobId": str(build_job_id),
            },
        )


def _require_active_build(
    release: MobileRelease,
    build_job_id: UUID,
) -> None:
    _require_build_job(release, build_job_id)
    if release.status is not MobileReleaseStatus.BUILDING:
        _raise_release_transition(release, MobileReleaseStatus.BUILDING)


def _validate_artifact(
    relative_path: str,
    checksum: str,
    *,
    kind: str,
) -> str:
    path = PurePosixPath(relative_path)
    if (
        not relative_path
        or "\\" in relative_path
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
    ):
        raise MobileReleaseError(
            "INVALID_RELEASE_ARTIFACT_PATH",
            f"The {kind} path must be a safe relative POSIX path.",
            details={"field": f"{kind}Path"},
        )
    if not _SHA256_PATTERN.fullmatch(checksum):
        raise MobileReleaseError(
            "INVALID_RELEASE_ARTIFACT_CHECKSUM",
            f"The {kind} checksum must be a lowercase SHA-256.",
            details={"field": f"{kind}Checksum"},
        )
    return path.as_posix()


def _raise_release_transition(
    release: MobileRelease,
    target: MobileReleaseStatus,
) -> None:
    raise MobileReleaseConflictError(
        "INVALID_MOBILE_RELEASE_STATUS_TRANSITION",
        (f"Mobile release cannot transition from {release.status.value} to {target.value}."),
        details={
            "mobileReleaseId": str(release.id),
            "fromStatus": release.status.value,
            "toStatus": target.value,
        },
    )
