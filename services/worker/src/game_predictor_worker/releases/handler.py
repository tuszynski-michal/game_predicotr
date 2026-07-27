"""One resumable owner for payout, snapshot and Android release stages."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import UUID

from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobType,
)
from game_predictor_api.domain.mobile_releases import MobileRelease, MobileReleaseError

from game_predictor_worker.jobs.runtime import (
    JobExecutionContext,
    JobHandlerError,
)
from game_predictor_worker.payouts.handler import PayoutBatchHandler
from game_predictor_worker.payouts.readiness import PayoutReadinessError, PayoutReadinessService
from game_predictor_worker.releases.android import AndroidReleaseError
from game_predictor_worker.releases.contracts import (
    AndroidReleaseBuilder,
    AndroidReleaseBuildSpec,
    ReleaseWorkflowStore,
)
from game_predictor_worker.snapshots import (
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotSpec,
    SnapshotArtifactError,
    SnapshotGameSelection,
)

RELEASE_WORKFLOW: Final = "mobile_release"
RELEASE_CHECKPOINT_VERSION: Final = 1
FIXED_STAGE_COUNT: Final = 3
ANDROID_VERSION_EPOCH = datetime(2020, 1, 1, tzinfo=UTC)


class ReleaseWorkflowHandler:
    def __init__(
        self,
        release_store: ReleaseWorkflowStore,
        payout_handler: PayoutBatchHandler,
        payout_readiness: PayoutReadinessService,
        snapshot_publisher: ProductionSnapshotArtifactPublisher,
        android_builder: AndroidReleaseBuilder,
        artifact_root: Path,
    ) -> None:
        self._release_store = release_store
        self._payout_handler = payout_handler
        self._payout_readiness = payout_readiness
        self._snapshot_publisher = snapshot_publisher
        self._android_builder = android_builder
        self._artifact_root = artifact_root.resolve()

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        release_id = _parse_job(job)
        try:
            release = self._load_release(release_id, job.id)
            release = self._release_store.mark_building(
                release.id,
                build_job_id=job.id,
            )
            self._release_store.require_current_sources(release)
            completed_games, active_game_id, payout_checkpoint = _resume(job, release)
            total_layouts = sum(game.layout_count for game in release.games)
            progress_total = total_layouts + FIXED_STAGE_COUNT
            completed_layouts = sum(
                game.layout_count for game in release.games if str(game.game_id) in completed_games
            )

            for game in release.games:
                game_id = str(game.game_id)
                if game_id in completed_games:
                    continue
                report = self._payout_readiness.assess(
                    game.dataset_version_id,
                    game.rules_version_id,
                    release.algorithm_version,
                )
                if not report.ready:
                    nested_checkpoint = payout_checkpoint if active_game_id == game_id else None
                    payout_job = replace(
                        job,
                        job_type=JobType.PAYOUT,
                        game_id=game.game_id,
                        input_payload={
                            "schema_version": 1,
                            "dataset_version_id": str(game.dataset_version_id),
                            "rules_version_id": str(game.rules_version_id),
                            "algorithm_version": release.algorithm_version,
                        },
                        checkpoint_payload=nested_checkpoint,
                    )
                    adapter = _NestedPayoutContext(
                        context,
                        release=release,
                        completed_games=completed_games,
                        game_id=game_id,
                        completed_layouts=completed_layouts,
                        progress_total=progress_total,
                    )
                    self._payout_handler(adapter, payout_job)  # type: ignore[arg-type]
                    self._payout_readiness.require(
                        game.dataset_version_id,
                        game.rules_version_id,
                        release.algorithm_version,
                    )

                completed_games.add(game_id)
                completed_layouts += game.layout_count
                _checkpoint(
                    context,
                    release=release,
                    stage="payouts_ready",
                    completed_games=completed_games,
                    current=completed_layouts,
                    total=progress_total,
                )

            snapshot = self._snapshot_publisher.publish(
                ProductionSnapshotSpec(
                    release_version=release.version,
                    created_at=release.created_at,
                    games=tuple(
                        SnapshotGameSelection(
                            dataset_version_id=game.dataset_version_id,
                            rules_version_id=game.rules_version_id,
                            algorithm_version=release.algorithm_version,
                        )
                        for game in release.games
                    ),
                )
            )
            snapshot_relative_path = _relative_path(
                snapshot.database_path,
                self._artifact_root,
            )
            release = self._release_store.record_snapshot(
                release.id,
                build_job_id=job.id,
                relative_path=snapshot_relative_path,
                checksum=snapshot.manifest.snapshot_file_sha256,
            )
            _checkpoint(
                context,
                release=release,
                stage="snapshot_verified",
                completed_games=completed_games,
                current=total_layouts + 1,
                total=progress_total,
                snapshot_path=snapshot_relative_path,
                snapshot_checksum=snapshot.manifest.snapshot_file_sha256,
            )

            apk = self._android_builder.build(
                AndroidReleaseBuildSpec(
                    release_version=release.version,
                    version_code=_android_version_code(release),
                    snapshot=snapshot,
                )
            )
            if apk.snapshot_sha256 != release.snapshot_checksum:
                raise JobHandlerError(
                    "ANDROID_SNAPSHOT_MISMATCH",
                    "The APK does not contain the release snapshot.",
                )
            apk_relative_path = _relative_path(
                apk.apk_path,
                self._artifact_root,
            )
            _checkpoint(
                context,
                release=release,
                stage="apk_verified",
                completed_games=completed_games,
                current=progress_total,
                total=progress_total,
                snapshot_path=snapshot_relative_path,
                snapshot_checksum=snapshot.manifest.snapshot_file_sha256,
                apk_path=apk_relative_path,
                apk_checksum=apk.apk_sha256,
            )
            self._release_store.mark_ready(
                release.id,
                build_job_id=job.id,
                apk_relative_path=apk_relative_path,
                apk_checksum=apk.apk_sha256,
            )
        except JobConflictError as error:
            if error.code != "JOB_LEASE_LOST":
                self._mark_failed(release_id, job.id)
            raise
        except (
            AndroidReleaseError,
            MobileReleaseError,
            PayoutReadinessError,
            SnapshotArtifactError,
        ) as error:
            self._mark_failed(release_id, job.id)
            raise JobHandlerError(error.code, error.message) from error
        except Exception:
            self._mark_failed(release_id, job.id)
            raise

    def _load_release(
        self,
        release_id: UUID,
        build_job_id: UUID,
    ) -> MobileRelease:
        release = self._release_store.load_release(release_id)
        if release is None:
            raise JobHandlerError(
                "MOBILE_RELEASE_NOT_FOUND",
                "The mobile release does not exist.",
            )
        if release.build_job_id != build_job_id:
            raise JobHandlerError(
                "MOBILE_RELEASE_BUILD_JOB_MISMATCH",
                "The job does not own this mobile release build.",
            )
        return release

    def _mark_failed(
        self,
        release_id: UUID,
        build_job_id: UUID,
    ) -> None:
        release = self._release_store.load_release(release_id)
        if release is None or release.build_job_id != build_job_id:
            return
        self._release_store.mark_failed(
            release_id,
            build_job_id=build_job_id,
        )


class _NestedPayoutContext:
    def __init__(
        self,
        context: JobExecutionContext,
        *,
        release: MobileRelease,
        completed_games: set[str],
        game_id: str,
        completed_layouts: int,
        progress_total: int,
    ) -> None:
        self._context = context
        self._release = release
        self._completed_games = completed_games
        self._game_id = game_id
        self._completed_layouts = completed_layouts
        self._progress_total = progress_total

    def checkpoint(
        self,
        *,
        checkpoint_payload: dict[str, object],
        stage: str,
        current: int,
        total: int | None,
        success_count: int,
        failure_count: int,
        review_count: int,
    ) -> None:
        del stage, total
        _checkpoint(
            self._context,
            release=self._release,
            stage="calculating_payouts",
            completed_games=self._completed_games,
            current=self._completed_layouts + current,
            total=self._progress_total,
            active_game_id=self._game_id,
            payout_checkpoint=checkpoint_payload,
            failure_count=failure_count,
            review_count=review_count,
        )


def _parse_job(job: Job) -> UUID:
    if job.job_type is not JobType.ANDROID_BUILD:
        raise JobHandlerError(
            "INVALID_RELEASE_JOB_TYPE",
            "The release workflow only accepts android_build jobs.",
        )
    if job.input_payload.get("schema_version") != 1:
        raise JobHandlerError(
            "UNSUPPORTED_RELEASE_PAYLOAD_VERSION",
            "The release workflow requires input schema version 1.",
        )
    try:
        return UUID(str(job.input_payload["mobile_release_id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise JobHandlerError(
            "INVALID_RELEASE_PAYLOAD",
            "The release workflow requires a valid mobile release ID.",
        ) from error


def _resume(
    job: Job,
    release: MobileRelease,
) -> tuple[set[str], str | None, dict[str, object] | None]:
    checkpoint = job.checkpoint_payload
    if checkpoint is None:
        return set(), None, None
    if (
        checkpoint.get("schema_version") != RELEASE_CHECKPOINT_VERSION
        or checkpoint.get("workflow") != RELEASE_WORKFLOW
        or checkpoint.get("mobile_release_id") != str(release.id)
    ):
        raise JobHandlerError(
            "RELEASE_CHECKPOINT_MISMATCH",
            "The release checkpoint does not match the immutable release.",
        )
    raw_completed = checkpoint.get("completed_game_ids")
    if not isinstance(raw_completed, list) or any(
        not isinstance(item, str) for item in raw_completed
    ):
        raise JobHandlerError(
            "INVALID_RELEASE_CHECKPOINT",
            "The release checkpoint has invalid completed games.",
        )
    known = {str(game.game_id) for game in release.games}
    completed = set(raw_completed)
    if not completed <= known:
        raise JobHandlerError(
            "INVALID_RELEASE_CHECKPOINT",
            "The release checkpoint references an unknown game.",
        )
    active = checkpoint.get("active_game_id")
    if active is not None and (not isinstance(active, str) or active not in known):
        raise JobHandlerError(
            "INVALID_RELEASE_CHECKPOINT",
            "The release checkpoint has an invalid active game.",
        )
    payout = checkpoint.get("payout_checkpoint")
    if payout is not None and not isinstance(payout, dict):
        raise JobHandlerError(
            "INVALID_RELEASE_CHECKPOINT",
            "The nested payout checkpoint is invalid.",
        )
    return completed, active, payout


def _checkpoint(
    context: JobExecutionContext,
    *,
    release: MobileRelease,
    stage: str,
    completed_games: set[str],
    current: int,
    total: int,
    active_game_id: str | None = None,
    payout_checkpoint: dict[str, object] | None = None,
    snapshot_path: str | None = None,
    snapshot_checksum: str | None = None,
    apk_path: str | None = None,
    apk_checksum: str | None = None,
    failure_count: int = 0,
    review_count: int = 0,
) -> None:
    payload: dict[str, object] = {
        "schema_version": RELEASE_CHECKPOINT_VERSION,
        "workflow": RELEASE_WORKFLOW,
        "mobile_release_id": str(release.id),
        "completed_game_ids": sorted(completed_games),
        "active_game_id": active_game_id,
        "payout_checkpoint": payout_checkpoint,
        "snapshot_path": snapshot_path,
        "snapshot_checksum": snapshot_checksum,
        "apk_path": apk_path,
        "apk_checksum": apk_checksum,
    }
    context.checkpoint(
        checkpoint_payload=payload,
        stage=stage,
        current=current,
        total=total,
        success_count=current,
        failure_count=failure_count,
        review_count=review_count,
    )


def _relative_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise JobHandlerError(
            "RELEASE_ARTIFACT_PATH_INVALID",
            "A release artifact escaped the configured artifact root.",
        ) from error


def _android_version_code(release: MobileRelease) -> int:
    created_at = release.created_at
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise JobHandlerError(
            "RELEASE_CREATED_AT_INVALID",
            "The release creation time must include a timezone.",
        )
    value = int((created_at.astimezone(UTC) - ANDROID_VERSION_EPOCH).total_seconds())
    if not 1 <= value <= 2_100_000_000:
        raise JobHandlerError(
            "ANDROID_VERSION_CODE_INVALID",
            "The release time cannot be represented as an Android version code.",
        )
    return value
