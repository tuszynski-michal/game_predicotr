"""PostgreSQL adapter for preview-bound cleanup operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.cleanup import CleanupRepository
from game_predictor_api.domain.cleanup import (
    CleanupCount,
    CleanupKind,
    CleanupNotFoundError,
    CleanupResult,
    CleanupSnapshot,
)
from game_predictor_api.storage.models import (
    CleanupOperationModel,
    GameModel,
    MobileReleaseModel,
)


class SqlAlchemyCleanupRepository(CleanupRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def release_snapshot(
        self,
        mobile_release_id: UUID,
        *,
        for_update: bool = False,
    ) -> CleanupSnapshot:
        statement = select(MobileReleaseModel).where(MobileReleaseModel.id == mobile_release_id)
        if for_update:
            statement = statement.with_for_update()
        release = self._session.scalar(statement)
        if release is None:
            raise CleanupNotFoundError(
                "CLEANUP_TARGET_NOT_FOUND",
                "The mobile release selected for cleanup does not exist.",
                details={"mobileReleaseId": str(mobile_release_id)},
            )
        game_count = self._count(
            "SELECT count(*) FROM mobile_release_games WHERE mobile_release_id = :target_id",
            target_id=mobile_release_id,
        )
        artifacts = _release_artifact_directories(
            release.version,
            has_snapshot=release.snapshot_path is not None,
            has_apk=release.apk_path is not None,
        )
        active_build = (
            self._count(
                """
            SELECT count(*)
            FROM jobs
            WHERE id = :job_id AND status IN ('created', 'processing')
            """,
                job_id=release.build_job_id,
            )
            if release.build_job_id is not None
            else 0
        )
        blockers = ("ACTIVE_RELEASE_BUILD",) if active_build else ()
        return CleanupSnapshot(
            kind="mobile_release",
            target_id=release.id,
            target_label=release.version,
            confirmation_target=str(release.id),
            counts=(
                CleanupCount("mobile_releases", 1),
                CleanupCount("mobile_release_games", game_count),
                CleanupCount("build_jobs_preserved", 1 if release.build_job_id else 0),
                CleanupCount("managed_artifacts", len(artifacts)),
            ),
            artifact_paths=artifacts,
            retained_shared_artifact_count=0,
            blockers=blockers,
        )

    def game_snapshot(
        self,
        game_id: UUID,
        *,
        for_update: bool = False,
    ) -> CleanupSnapshot:
        statement = select(GameModel).where(GameModel.id == game_id)
        if for_update:
            statement = statement.with_for_update()
        game = self._session.scalar(statement)
        if game is None:
            raise CleanupNotFoundError(
                "CLEANUP_TARGET_NOT_FOUND",
                "The game selected for cleanup does not exist.",
                details={"gameId": str(game_id)},
            )
        counts = self._game_counts(game_id)
        artifacts, retained_shared = self._game_artifacts(game_id)
        blockers: list[str] = []
        if self._count(
            """
            SELECT count(*) FROM jobs
            WHERE game_id = :game_id AND status IN ('created', 'processing')
            """,
            game_id=game_id,
        ):
            blockers.append("ACTIVE_GAME_JOB")
        if self._count(
            """
            SELECT count(*)
            FROM mobile_releases mr
            JOIN mobile_release_games mrg ON mrg.mobile_release_id = mr.id
            JOIN jobs j ON j.id = mr.build_job_id
            WHERE mrg.game_id = :game_id AND j.status IN ('created', 'processing')
            """,
            game_id=game_id,
        ):
            blockers.append("ACTIVE_RELEASE_BUILD")
        if self._count(
            """
            SELECT count(*) FROM reviewer_access_sessions
            WHERE game_id = :game_id AND revoked_at IS NULL AND expires_at > now()
            """,
            game_id=game_id,
        ):
            blockers.append("ACTIVE_REVIEWER_SESSION")
        if self._count(
            """
            SELECT count(*)
            FROM mobile_release_games target
            WHERE target.game_id = :game_id
              AND EXISTS (
                SELECT 1 FROM mobile_release_games other
                WHERE other.mobile_release_id = target.mobile_release_id
                  AND other.game_id <> :game_id
              )
            """,
            game_id=game_id,
        ):
            blockers.append("SHARED_MULTI_GAME_RELEASE")
        return CleanupSnapshot(
            kind="game_layout_data",
            target_id=game.id,
            target_label=f"{game.name} ({game.code})",
            confirmation_target=str(game.id),
            counts=(*counts, CleanupCount("managed_artifacts", len(artifacts))),
            artifact_paths=artifacts,
            retained_shared_artifact_count=retained_shared,
            blockers=tuple(blockers),
        )

    def completed_result(
        self,
        kind: str,
        target_id: UUID,
        preview_token: str,
    ) -> CleanupResult | None:
        record = self._session.scalar(
            select(CleanupOperationModel).where(
                CleanupOperationModel.operation_type == kind,
                CleanupOperationModel.target_id == target_id,
                CleanupOperationModel.preview_token == preview_token,
            )
        )
        return None if record is None else _result_from_payload(record.result_payload)

    def delete_release(
        self,
        snapshot: CleanupSnapshot,
        result: CleanupResult,
    ) -> None:
        self._session.execute(
            text("DELETE FROM mobile_release_games WHERE mobile_release_id = :target_id"),
            {"target_id": snapshot.target_id},
        )
        deletion_result = self._session.execute(
            text("DELETE FROM mobile_releases WHERE id = :target_id"),
            {"target_id": snapshot.target_id},
        )
        deleted = int(getattr(deletion_result, "rowcount", 0))
        if deleted != 1:
            raise CleanupNotFoundError(
                "CLEANUP_TARGET_NOT_FOUND",
                "The mobile release disappeared before cleanup completed.",
            )
        self._record(result)

    def reset_game(
        self,
        snapshot: CleanupSnapshot,
        result: CleanupResult,
    ) -> None:
        parameters = {"game_id": snapshot.target_id}
        for statement in _GAME_RESET_STATEMENTS:
            self._session.execute(text(statement), parameters)
        self._record(result)

    def _record(self, result: CleanupResult) -> None:
        self._session.add(
            CleanupOperationModel(
                operation_type=result.kind,
                target_id=result.target_id,
                preview_token=result.preview_token,
                result_payload=_result_payload(result),
            )
        )
        self._session.flush()

    def _count(self, statement: str, **parameters: object) -> int:
        return int(self._session.scalar(text(statement), parameters) or 0)

    def _game_counts(self, game_id: UUID) -> tuple[CleanupCount, ...]:
        row = (
            self._session.execute(
                text(_GAME_COUNTS_SQL),
                {"game_id": game_id},
            )
            .mappings()
            .one()
        )
        return tuple(CleanupCount(str(name), int(value or 0)) for name, value in row.items())

    def _game_artifacts(self, game_id: UUID) -> tuple[tuple[str, ...], int]:
        rows = self._session.execute(
            text(_GAME_ARTIFACTS_SQL),
            {"game_id": game_id},
        ).mappings()
        deleted: list[str] = []
        retained = 0
        for row in rows:
            if bool(row["shared"]):
                retained += 1
            else:
                deleted.append(cast(str, row["path"]))
        return tuple(sorted(set(deleted))), retained


def _release_artifact_directories(
    version: str,
    *,
    has_snapshot: bool,
    has_apk: bool,
) -> tuple[str, ...]:
    paths: list[str] = []
    if has_snapshot:
        paths.append(f"snapshots/{version}")
    if has_apk:
        paths.append(f"android-releases/{version}")
    return tuple(paths)


def _result_payload(result: CleanupResult) -> dict[str, object]:
    return {
        "kind": result.kind,
        "targetId": str(result.target_id),
        "targetLabel": result.target_label,
        "previewToken": result.preview_token,
        "deletedCounts": [
            {"name": item.name, "count": item.count} for item in result.deleted_counts
        ],
        "deletedArtifactCount": result.deleted_artifact_count,
        "retainedSharedArtifactCount": result.retained_shared_artifact_count,
    }


def _result_from_payload(payload: dict[str, object]) -> CleanupResult:
    raw_counts = cast(Iterable[dict[str, object]], payload["deletedCounts"])
    return CleanupResult(
        kind=cast(CleanupKind, payload["kind"]),
        target_id=UUID(cast(str, payload["targetId"])),
        target_label=cast(str, payload["targetLabel"]),
        preview_token=cast(str, payload["previewToken"]),
        deleted_counts=tuple(
            CleanupCount(cast(str, item["name"]), int(cast(int, item["count"])))
            for item in raw_counts
        ),
        deleted_artifact_count=int(cast(int, payload["deletedArtifactCount"])),
        retained_shared_artifact_count=int(cast(int, payload["retainedSharedArtifactCount"])),
    )


_GAME_COUNTS_SQL = """
SELECT
  (SELECT count(*) FROM symbols WHERE game_id = :game_id) AS symbols,
  (SELECT count(*) FROM rules_versions WHERE game_id = :game_id) AS rules_versions,
  (SELECT count(*) FROM dataset_versions WHERE game_id = :game_id) AS dataset_versions,
  (SELECT count(*) FROM layouts l JOIN dataset_versions d ON d.id = l.dataset_version_id
    WHERE d.game_id = :game_id) AS layouts,
  (SELECT count(*) FROM layout_payouts p JOIN dataset_versions d ON d.id = p.dataset_version_id
    WHERE d.game_id = :game_id) AS layout_payouts,
  (SELECT count(*) FROM jobs WHERE game_id = :game_id AND job_type = 'import') AS imports,
  (SELECT count(*) FROM source_images s JOIN jobs j ON j.id = s.import_job_id
    WHERE j.game_id = :game_id) AS source_images,
  (SELECT count(*) FROM recognized_boards b JOIN source_images s ON s.id = b.source_image_id
    JOIN jobs j ON j.id = s.import_job_id WHERE j.game_id = :game_id) AS recognized_boards,
  (SELECT count(*) FROM image_review_items r
    JOIN recognized_boards b ON b.id = r.recognized_board_id
    JOIN source_images s ON s.id = b.source_image_id JOIN jobs j ON j.id = s.import_job_id
    WHERE j.game_id = :game_id) AS image_reviews,
  (SELECT count(*) FROM reviewer_access_sessions WHERE game_id = :game_id) AS reviewer_sessions,
  (SELECT count(*) FROM curated_image_import_sources
    WHERE game_id = :game_id) AS curated_import_sources,
  (SELECT count(*) FROM grid_geometry_cohorts
    WHERE game_id = :game_id) AS grid_geometry_cohorts,
  (SELECT count(*) FROM grid_calibration_profiles
    WHERE game_id = :game_id) AS grid_calibration_profiles,
  (SELECT count(DISTINCT mobile_release_id) FROM mobile_release_games
    WHERE game_id = :game_id) AS mobile_releases,
  (SELECT count(*) FROM review_batches WHERE game_id = :game_id) AS review_batches,
  (SELECT count(*) FROM jobs WHERE game_id = :game_id) AS jobs_preserved
"""


_GAME_ARTIFACTS_SQL = """
WITH refs(path, game_id) AS (
  SELECT image_path, game_id FROM symbols WHERE image_path IS NOT NULL
  UNION ALL
  SELECT s.relative_path, j.game_id FROM source_images s JOIN jobs j ON j.id = s.import_job_id
  UNION ALL
  SELECT b.board_relative_path, j.game_id FROM recognized_boards b
    JOIN source_images s ON s.id = b.source_image_id JOIN jobs j ON j.id = s.import_job_id
  UNION ALL
  SELECT c.crop_relative_path, j.game_id FROM cell_observations c
    JOIN recognized_boards b ON b.id = c.recognized_board_id
    JOIN source_images s ON s.id = b.source_image_id JOIN jobs j ON j.id = s.import_job_id
  UNION ALL
  SELECT g.board_relative_path, j.game_id FROM image_board_geometry_revisions g
    JOIN recognized_boards b ON b.id = g.recognized_board_id
    JOIN source_images s ON s.id = b.source_image_id JOIN jobs j ON j.id = s.import_job_id
  UNION ALL
  SELECT crop.value->>'cropRelativePath', j.game_id
    FROM image_board_geometry_revisions g
    CROSS JOIN LATERAL jsonb_array_elements(g.crop_artifacts) crop(value)
    JOIN recognized_boards b ON b.id = g.recognized_board_id
    JOIN source_images s ON s.id = b.source_image_id JOIN jobs j ON j.id = s.import_job_id
  UNION ALL
  SELECT artifact_relative_path, game_id FROM image_verified_cohort_exports
  UNION ALL
  SELECT p.audit_path, d.game_id FROM layout_payouts p
    JOIN dataset_versions d ON d.id = p.dataset_version_id WHERE p.audit_path IS NOT NULL
  UNION ALL
  SELECT 'snapshots/' || mr.version, mrg.game_id FROM mobile_releases mr
    JOIN mobile_release_games mrg ON mrg.mobile_release_id = mr.id
    WHERE mr.snapshot_path IS NOT NULL
  UNION ALL
  SELECT 'android-releases/' || mr.version, mrg.game_id FROM mobile_releases mr
    JOIN mobile_release_games mrg ON mrg.mobile_release_id = mr.id WHERE mr.apk_path IS NOT NULL
  UNION ALL
  SELECT 'data/originals/manifests/' || j.id::text || '.json', j.game_id
    FROM jobs j WHERE j.job_type = 'import'
  UNION ALL
  SELECT 'data/exports/image-jobs/' || j.id::text, j.game_id
    FROM jobs j WHERE j.job_type = 'import'
)
SELECT path, bool_or(game_id <> :game_id) AS shared
FROM refs
WHERE path IS NOT NULL AND path <> ''
  AND path IN (SELECT path FROM refs WHERE game_id = :game_id)
GROUP BY path
HAVING bool_or(game_id = :game_id)
ORDER BY path
"""


_GAME_RESET_STATEMENTS = (
    """WITH target_releases AS (
         SELECT DISTINCT mobile_release_id FROM mobile_release_games WHERE game_id = :game_id
       ), deleted_links AS (
         DELETE FROM mobile_release_games
         WHERE mobile_release_id IN (SELECT mobile_release_id FROM target_releases)
         RETURNING mobile_release_id
       )
       DELETE FROM mobile_releases
       WHERE id IN (SELECT mobile_release_id FROM target_releases)""",
    "DELETE FROM review_feedback_exports WHERE game_id = :game_id",
    """DELETE FROM review_resolutions WHERE review_item_id IN
       (SELECT ri.id FROM review_items ri JOIN review_batches rb ON rb.id = ri.review_batch_id
        WHERE rb.game_id = :game_id)""",
    """DELETE FROM review_items WHERE review_batch_id IN
       (SELECT id FROM review_batches WHERE game_id = :game_id)""",
    "DELETE FROM review_batches WHERE game_id = :game_id",
    """DELETE FROM reviewer_access_audit_events WHERE session_id IN
       (SELECT id FROM reviewer_access_sessions WHERE game_id = :game_id)""",
    "DELETE FROM reviewer_access_sessions WHERE game_id = :game_id",
    "DELETE FROM image_sequence_source_override_events WHERE game_id = :game_id",
    "DELETE FROM image_verified_cohort_exports WHERE game_id = :game_id",
    "DELETE FROM game_grid_profile_activations WHERE game_id = :game_id",
    "DELETE FROM grid_calibration_profiles WHERE game_id = :game_id",
    "DELETE FROM grid_geometry_cohorts WHERE game_id = :game_id",
    """DELETE FROM curated_image_import_batches WHERE source_id IN
       (SELECT id FROM curated_image_import_sources WHERE game_id = :game_id)""",
    "DELETE FROM curated_image_import_sources WHERE game_id = :game_id",
    """DELETE FROM image_layout_staging_rows WHERE import_job_id IN
       (SELECT id FROM jobs WHERE game_id = :game_id)""",
    """DELETE FROM image_board_geometry_revisions WHERE recognized_board_id IN
       (SELECT b.id FROM recognized_boards b JOIN source_images s ON s.id = b.source_image_id
        JOIN jobs j ON j.id = s.import_job_id WHERE j.game_id = :game_id)""",
    """DELETE FROM image_review_resolution_events WHERE review_item_id IN
       (SELECT r.id FROM image_review_items r
        JOIN recognized_boards b ON b.id = r.recognized_board_id
        JOIN source_images s ON s.id = b.source_image_id JOIN jobs j ON j.id = s.import_job_id
        WHERE j.game_id = :game_id)""",
    """DELETE FROM image_review_items WHERE recognized_board_id IN
       (SELECT b.id FROM recognized_boards b JOIN source_images s ON s.id = b.source_image_id
        JOIN jobs j ON j.id = s.import_job_id WHERE j.game_id = :game_id)""",
    """DELETE FROM cell_observations WHERE recognized_board_id IN
       (SELECT b.id FROM recognized_boards b JOIN source_images s ON s.id = b.source_image_id
        JOIN jobs j ON j.id = s.import_job_id WHERE j.game_id = :game_id)""",
    """DELETE FROM recognized_boards WHERE source_image_id IN
       (SELECT s.id FROM source_images s JOIN jobs j ON j.id = s.import_job_id
        WHERE j.game_id = :game_id)""",
    """DELETE FROM source_images WHERE import_job_id IN
       (SELECT id FROM jobs WHERE game_id = :game_id)""",
    """DELETE FROM image_import_job_files WHERE job_id IN
       (SELECT id FROM jobs WHERE game_id = :game_id)""",
    """DELETE FROM layout_import_normalized_rows WHERE validation_job_id IN
       (SELECT id FROM jobs WHERE game_id = :game_id)
       OR import_job_id IN (SELECT id FROM jobs WHERE game_id = :game_id)""",
    """DELETE FROM layout_import_rows WHERE job_id IN
       (SELECT id FROM jobs WHERE game_id = :game_id)""",
    """DELETE FROM layout_payouts WHERE dataset_version_id IN
       (SELECT id FROM dataset_versions WHERE game_id = :game_id)
       OR rules_version_id IN (SELECT id FROM rules_versions WHERE game_id = :game_id)""",
    """DELETE FROM layouts WHERE dataset_version_id IN
       (SELECT id FROM dataset_versions WHERE game_id = :game_id)""",
    "DELETE FROM dataset_versions WHERE game_id = :game_id",
    """DELETE FROM payout_rules WHERE rules_version_id IN
       (SELECT id FROM rules_versions WHERE game_id = :game_id)""",
    """DELETE FROM rules_version_symbols WHERE rules_version_id IN
       (SELECT id FROM rules_versions WHERE game_id = :game_id)""",
    """DELETE FROM paylines WHERE rules_version_id IN
       (SELECT id FROM rules_versions WHERE game_id = :game_id)""",
    "DELETE FROM rules_versions WHERE game_id = :game_id",
    "DELETE FROM symbols WHERE game_id = :game_id",
)


__all__ = ["SqlAlchemyCleanupRepository"]
