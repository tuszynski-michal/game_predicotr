"""PostgreSQL adapter for preview-bound cleanup operations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import and_, bindparam, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from game_predictor_api.application.cleanup import CleanupRepository
from game_predictor_api.domain.cleanup import (
    BoardSourceCleanupSelection,
    CleanupConflictError,
    CleanupCount,
    CleanupKind,
    CleanupNotFoundError,
    CleanupResult,
    CleanupSnapshot,
)
from game_predictor_api.storage.models import (
    CleanupOperationModel,
    GameModel,
    ImageSourceGeometryRevisionModel,
    MobileReleaseModel,
    SourceImageModel,
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

    def board_source_snapshot(
        self,
        game_id: UUID,
        selection: BoardSourceCleanupSelection,
        *,
        for_update: bool = False,
    ) -> CleanupSnapshot:
        game_statement = select(GameModel).where(GameModel.id == game_id)
        if for_update:
            game_statement = game_statement.with_for_update()
        game = self._session.scalar(game_statement)
        if game is None:
            raise CleanupNotFoundError(
                "CLEANUP_TARGET_NOT_FOUND",
                "The game selected for source cleanup does not exist.",
                details={"gameId": str(game_id)},
            )

        scope = self._board_source_scope(game_id, selection)
        blockers = self._board_source_blockers(scope)
        warnings = self._board_source_warnings(scope)
        counts = self._board_source_counts(scope)
        ranges = ", ".join(f"{start}-{end}" for start, end in scope.ranges)
        return CleanupSnapshot(
            kind="board_source_ranges",
            target_id=game.id,
            target_label=f"{game.name} ({game.code}) · {ranges}",
            confirmation_target=_range_confirmation_target(game.id, scope.ranges),
            counts=(*counts, CleanupCount("managed_artifacts", len(scope.artifact_paths))),
            artifact_paths=scope.artifact_paths,
            retained_shared_artifact_count=scope.retained_shared_artifact_count,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
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

    def completed_board_source_quarantine_keys(self) -> set[str]:
        return set(
            self._session.scalars(
                select(CleanupOperationModel.preview_token).where(
                    CleanupOperationModel.operation_type == "board_source_ranges"
                )
            )
        )

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

    def delete_board_sources(
        self,
        snapshot: CleanupSnapshot,
        result: CleanupResult,
    ) -> None:
        ranges = _ranges_from_confirmation_target(
            snapshot.target_id,
            snapshot.confirmation_target,
        )
        scope = self._board_source_scope_for_ranges(snapshot.target_id, ranges)
        if self._board_source_blockers(scope):
            raise CleanupConflictError(
                "CLEANUP_BLOCKED",
                "The selected source ranges gained a protected dependency.",
                details={"blockers": self._board_source_blockers(scope)},
            )

        self._delete_board_source_graph(scope)
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
        if any(isinstance(value, tuple) and not value for value in parameters.values()):
            return 0
        return int(
            self._session.scalar(self._bound_statement(statement, parameters), parameters) or 0
        )

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

    def _board_source_scope(
        self,
        game_id: UUID,
        selection: BoardSourceCleanupSelection,
    ) -> _BoardSourceScope:
        range_rows = self._session.execute(
            select(
                ImageSourceGeometryRevisionModel.sequence_range_start,
                ImageSourceGeometryRevisionModel.sequence_range_end,
            )
            .where(
                ImageSourceGeometryRevisionModel.game_id == game_id,
                or_(
                    *(
                        and_(
                            ImageSourceGeometryRevisionModel.sequence_range_start <= number,
                            ImageSourceGeometryRevisionModel.sequence_range_end >= number,
                        )
                        for number in selection.sequence_numbers
                    )
                ),
            )
            .distinct()
        ).all()
        if not range_rows:
            raise CleanupNotFoundError(
                "CLEANUP_SOURCE_RANGE_NOT_FOUND",
                "None of the selected board numbers belongs to a removable image source.",
                details={"sequenceNumbers": list(selection.sequence_numbers)},
            )
        selected_numbers = set(selection.sequence_numbers)
        ranges = tuple(sorted((int(row[0]), int(row[1])) for row in range_rows))
        unmatched_numbers = sorted(
            selected_numbers - {number for start, end in ranges for number in range(start, end + 1)}
        )
        if unmatched_numbers:
            raise CleanupNotFoundError(
                "CLEANUP_SOURCE_RANGE_NOT_FOUND",
                "Some selected board numbers do not belong to a removable image source.",
                details={"sequenceNumbers": unmatched_numbers},
            )
        partial_ranges = [
            (start, end)
            for start, end in ranges
            if not set(range(start, end + 1)).issubset(selected_numbers)
        ]
        if partial_ranges:
            raise CleanupConflictError(
                "CLEANUP_SOURCE_RANGE_PARTIAL_SELECTION",
                "Every board in an image source range must be selected together.",
                details={
                    "partialRanges": [{"start": start, "end": end} for start, end in partial_ranges]
                },
            )
        return self._board_source_scope_for_ranges(game_id, ranges)

    def _board_source_scope_for_ranges(
        self,
        game_id: UUID,
        ranges: tuple[tuple[int, int], ...],
    ) -> _BoardSourceScope:
        range_predicate = or_(
            *(
                and_(
                    ImageSourceGeometryRevisionModel.sequence_range_start == start,
                    ImageSourceGeometryRevisionModel.sequence_range_end == end,
                )
                for start, end in ranges
            )
        )
        source_ids = tuple(
            self._session.scalars(
                select(ImageSourceGeometryRevisionModel.source_image_id)
                .where(
                    ImageSourceGeometryRevisionModel.game_id == game_id,
                    range_predicate,
                )
                .distinct()
            )
        )
        if not source_ids:
            raise CleanupNotFoundError(
                "CLEANUP_SOURCE_RANGE_NOT_FOUND",
                "The selected image sources no longer exist.",
            )
        source_rows = [
            (
                cast(UUID, row[0]),
                cast(str, row[1]),
                cast(str, row[2]),
                cast(str, row[3]),
                cast(UUID, row[4]),
            )
            for row in self._session.execute(
                select(
                    SourceImageModel.id,
                    SourceImageModel.relative_path,
                    SourceImageModel.checksum_sha256,
                    SourceImageModel.file_execution_key,
                    SourceImageModel.import_job_id,
                ).where(SourceImageModel.id.in_(source_ids))
            ).all()
        ]
        board_ids = self._ids(
            "SELECT id FROM recognized_boards WHERE source_image_id IN :source_ids",
            source_ids=source_ids,
        )
        review_item_ids = self._ids(
            "SELECT id FROM image_review_items WHERE recognized_board_id IN :board_ids",
            board_ids=board_ids,
        )
        cell_review_ids = self._ids(
            "SELECT id FROM image_symbol_review_cells WHERE review_item_id IN :review_item_ids",
            review_item_ids=review_item_ids,
        )
        source_geometry_ids = self._ids(
            "SELECT id FROM image_source_geometry_revisions WHERE source_image_id IN :source_ids",
            source_ids=source_ids,
        )
        observation_ids = self._ids(
            "SELECT id FROM cell_observations WHERE recognized_board_id IN :board_ids",
            board_ids=board_ids,
        )
        cohort_ids = tuple(
            sorted(
                set(
                    self._ids(
                        "SELECT DISTINCT cohort_id FROM verified_training_cohort_items "
                        "WHERE source_image_id IN :source_ids",
                        source_ids=source_ids,
                    )
                ).union(
                    self._ids(
                        "SELECT DISTINCT cohort_id FROM verified_training_cohort_cells "
                        "WHERE source_image_id IN :source_ids",
                        source_ids=source_ids,
                    )
                )
            )
        )
        model_ids = self._ids(
            "SELECT id FROM symbol_model_iterations WHERE cohort_id IN :cohort_ids",
            cohort_ids=cohort_ids,
        )
        activation_rows = self._session.execute(
            text(
                "SELECT id, model_iteration_id FROM game_symbol_model_activations "
                "WHERE game_id = :game_id ORDER BY activation_number DESC"
            ),
            {"game_id": game_id},
        ).all()
        active_model_id = activation_rows[0][1] if activation_rows else None
        active_model_affected = active_model_id in set(model_ids)
        if active_model_affected:
            activation_ids = tuple(row[0] for row in activation_rows)
        else:
            activation_ids = self._ids(
                "SELECT id FROM game_symbol_model_activations "
                "WHERE model_iteration_id IN :model_ids "
                "OR previous_model_iteration_id IN :model_ids",
                model_ids=model_ids,
            )
        release_ids = (
            self._ids(
                "SELECT mobile_release_id FROM mobile_release_games WHERE game_id = :game_id",
                game_id=game_id,
            )
            if active_model_affected
            else ()
        )
        import_job_ids = tuple(sorted({row[4] for row in source_rows}))
        verified_export_ids = self._ids(
            "SELECT id FROM image_verified_cohort_exports WHERE import_job_id IN :import_job_ids",
            import_job_ids=import_job_ids,
        )
        selected_sequences = tuple(
            number for start, end in ranges for number in range(start, end + 1)
        )
        source_checksums = tuple(row[2] for row in source_rows)
        execution_keys = tuple(row[3] for row in source_rows)
        artifact_paths = self._board_source_artifact_paths(
            source_ids=source_ids,
            board_ids=board_ids,
            review_item_ids=review_item_ids,
            cohort_ids=cohort_ids,
            model_ids=model_ids,
            release_ids=release_ids,
            verified_export_ids=verified_export_ids,
            source_rows=source_rows,
        )
        return _BoardSourceScope(
            game_id=game_id,
            ranges=ranges,
            source_ids=source_ids,
            board_ids=board_ids,
            review_item_ids=review_item_ids,
            cell_review_ids=cell_review_ids,
            observation_ids=observation_ids,
            source_geometry_ids=source_geometry_ids,
            cohort_ids=cohort_ids,
            model_ids=model_ids,
            verified_export_ids=verified_export_ids,
            activation_ids=activation_ids,
            release_ids=release_ids,
            selected_sequences=selected_sequences,
            source_checksums=source_checksums,
            execution_keys=execution_keys,
            import_job_ids=import_job_ids,
            source_job_execution_pairs=tuple(sorted((row[4], row[3]) for row in source_rows)),
            active_model_affected=active_model_affected,
            active_model_survives=active_model_id is not None and not active_model_affected,
            artifact_paths=artifact_paths,
            retained_shared_artifact_count=0,
        )

    def _board_source_blockers(self, scope: _BoardSourceScope) -> list[str]:
        blockers: list[str] = []
        if self._count(
            """
            SELECT count(*) FROM jobs
            WHERE game_id = :game_id AND status IN ('created', 'processing')
            """,
            game_id=scope.game_id,
        ):
            blockers.append("ACTIVE_GAME_JOB")
        if self._count(
            """
            SELECT count(*) FROM reviewer_access_sessions
            WHERE game_id = :game_id AND revoked_at IS NULL AND expires_at > now()
            """,
            game_id=scope.game_id,
        ):
            blockers.append("ACTIVE_REVIEWER_SESSION")
        if scope.release_ids and self._count(
            """
            SELECT count(*) FROM mobile_release_games target
            WHERE target.mobile_release_id IN :release_ids
              AND target.game_id <> :game_id
            """,
            release_ids=scope.release_ids,
            game_id=scope.game_id,
        ):
            blockers.append("SHARED_MULTI_GAME_RELEASE")
        if scope.release_ids and self._count(
            """
            SELECT count(*) FROM mobile_releases mr
            JOIN jobs j ON j.id = mr.build_job_id
            WHERE mr.id IN :release_ids AND j.status IN ('created', 'processing')
            """,
            release_ids=scope.release_ids,
        ):
            blockers.append("ACTIVE_RELEASE_BUILD")
        return blockers

    def _board_source_warnings(self, scope: _BoardSourceScope) -> list[str]:
        if scope.active_model_survives:
            return []
        exclusion = "AND id NOT IN :model_ids" if scope.model_ids else ""
        candidate_parameters: dict[str, object] = {"game_id": scope.game_id}
        if scope.model_ids:
            candidate_parameters["model_ids"] = scope.model_ids
        surviving_candidate_count = self._count(
            f"""
            SELECT count(*) FROM symbol_model_iterations
            WHERE game_id = :game_id AND status = 'candidate_ready'
              {exclusion}
            """,
            **candidate_parameters,
        )
        if surviving_candidate_count:
            return ["SYMBOL_MODEL_ACTIVATION_REQUIRED"]
        return ["SYMBOL_MODEL_BOOTSTRAP_AVAILABLE"]

    @staticmethod
    def _board_source_counts(scope: _BoardSourceScope) -> tuple[CleanupCount, ...]:
        return (
            CleanupCount("source_images", len(scope.source_ids)),
            CleanupCount("source_geometry_revisions", len(scope.source_geometry_ids)),
            CleanupCount("recognized_boards", len(scope.board_ids)),
            CleanupCount("image_review_items", len(scope.review_item_ids)),
            CleanupCount("cell_observations", len(scope.observation_ids)),
            CleanupCount("symbol_review_cells", len(scope.cell_review_ids)),
            CleanupCount("canonical_sequences", len(scope.selected_sequences)),
            CleanupCount("training_cohorts", len(scope.cohort_ids)),
            CleanupCount("symbol_model_iterations", len(scope.model_ids)),
            CleanupCount("verified_cohort_exports", len(scope.verified_export_ids)),
            CleanupCount("mobile_releases", len(scope.release_ids)),
        )

    def _board_source_artifact_paths(
        self,
        *,
        source_ids: tuple[UUID, ...],
        board_ids: tuple[UUID, ...],
        review_item_ids: tuple[UUID, ...],
        cohort_ids: tuple[UUID, ...],
        model_ids: tuple[UUID, ...],
        release_ids: tuple[UUID, ...],
        verified_export_ids: tuple[UUID, ...],
        source_rows: list[tuple[UUID, str, str, str, UUID]],
    ) -> tuple[str, ...]:
        paths = {str(row[1]) for row in source_rows}
        paths.update(
            self._paths(
                "SELECT artifact_relative_path FROM image_verified_cohort_exports "
                "WHERE id IN :verified_export_ids",
                verified_export_ids=verified_export_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT board_relative_path FROM recognized_boards "
                "WHERE id IN :board_ids AND board_relative_path IS NOT NULL",
                board_ids=board_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT board_relative_path FROM image_board_geometry_revisions "
                "WHERE recognized_board_id IN :board_ids "
                "AND board_relative_path IS NOT NULL",
                board_ids=board_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT crop.value->>'cropRelativePath' "
                "FROM image_board_geometry_revisions geometry "
                "CROSS JOIN LATERAL jsonb_array_elements(geometry.crop_artifacts) crop(value) "
                "WHERE geometry.recognized_board_id IN :board_ids "
                "AND crop.value->>'cropRelativePath' IS NOT NULL",
                board_ids=board_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT crop_relative_path FROM cell_observations "
                "WHERE recognized_board_id IN :board_ids "
                "AND crop_relative_path IS NOT NULL",
                board_ids=board_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT crop_relative_path FROM image_symbol_review_cells "
                "WHERE review_item_id IN :review_item_ids "
                "AND crop_relative_path IS NOT NULL",
                review_item_ids=review_item_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT image_relative_path FROM symbol_reference_images "
                "WHERE source_review_item_id IN :review_item_ids",
                review_item_ids=review_item_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT artifact_relative_path FROM verified_training_cohorts "
                "WHERE id IN :cohort_ids",
                cohort_ids=cohort_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT dataset_manifest_relative_path FROM symbol_model_iterations "
                "WHERE id IN :model_ids AND dataset_manifest_relative_path IS NOT NULL",
                model_ids=model_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT checkpoint_relative_path FROM symbol_model_iterations "
                "WHERE id IN :model_ids AND checkpoint_relative_path IS NOT NULL",
                model_ids=model_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT candidate_manifest_relative_path FROM symbol_model_iterations "
                "WHERE id IN :model_ids AND candidate_manifest_relative_path IS NOT NULL",
                model_ids=model_ids,
            )
        )
        paths.update(
            self._paths(
                "SELECT gate_report_relative_path FROM symbol_model_iterations "
                "WHERE id IN :model_ids AND gate_report_relative_path IS NOT NULL",
                model_ids=model_ids,
            )
        )
        for version in self._paths(
            "SELECT version FROM mobile_releases WHERE id IN :release_ids",
            release_ids=release_ids,
        ):
            paths.add(f"snapshots/{version}")
            paths.add(f"android-releases/{version}")
        return tuple(sorted(path for path in paths if path))

    def _delete_board_source_graph(self, scope: _BoardSourceScope) -> None:
        self._delete(
            "DELETE FROM symbol_reference_images WHERE source_review_item_id IN :review_item_ids",
            review_item_ids=scope.review_item_ids,
        )
        self._delete(
            "DELETE FROM image_symbol_review_bulk_targets WHERE cell_review_id IN :cell_review_ids",
            cell_review_ids=scope.cell_review_ids,
        )
        self._delete(
            "DELETE FROM image_symbol_review_events WHERE cell_review_id IN :cell_review_ids",
            cell_review_ids=scope.cell_review_ids,
        )
        self._delete(
            "UPDATE image_symbol_review_cells SET prediction_revision_id = NULL "
            "WHERE id IN :cell_review_ids",
            cell_review_ids=scope.cell_review_ids,
        )
        if scope.model_ids:
            self._delete(
                "UPDATE image_symbol_review_cells SET prediction_revision_id = NULL "
                "WHERE prediction_revision_id IN ("
                "SELECT id FROM image_symbol_prediction_revisions "
                "WHERE model_iteration_id IN :model_ids"
                ")",
                model_ids=scope.model_ids,
            )
            self._delete(
                "DELETE FROM image_symbol_prediction_revisions "
                "WHERE review_item_id IN :review_item_ids "
                "OR model_iteration_id IN :model_ids",
                review_item_ids=scope.review_item_ids,
                model_ids=scope.model_ids,
            )
        else:
            self._delete(
                "DELETE FROM image_symbol_prediction_revisions "
                "WHERE review_item_id IN :review_item_ids",
                review_item_ids=scope.review_item_ids,
            )
        self._delete(
            "DELETE FROM game_symbol_model_activations WHERE id IN :activation_ids",
            activation_ids=scope.activation_ids,
        )
        self._delete(
            "DELETE FROM symbol_model_iterations WHERE id IN :model_ids", model_ids=scope.model_ids
        )
        self._delete(
            "DELETE FROM verified_training_cohort_cells WHERE cohort_id IN :cohort_ids",
            cohort_ids=scope.cohort_ids,
        )
        self._delete(
            "DELETE FROM verified_training_cohort_items WHERE cohort_id IN :cohort_ids",
            cohort_ids=scope.cohort_ids,
        )
        self._delete(
            "DELETE FROM verified_training_cohorts WHERE id IN :cohort_ids",
            cohort_ids=scope.cohort_ids,
        )
        self._delete(
            "DELETE FROM mobile_release_games WHERE mobile_release_id IN :release_ids",
            release_ids=scope.release_ids,
        )
        self._delete(
            "DELETE FROM mobile_releases WHERE id IN :release_ids", release_ids=scope.release_ids
        )
        self._delete(
            "DELETE FROM image_layout_staging_rows WHERE review_item_id IN :review_item_ids",
            review_item_ids=scope.review_item_ids,
        )
        self._delete(
            "DELETE FROM image_verified_cohort_exports WHERE id IN :verified_export_ids",
            verified_export_ids=scope.verified_export_ids,
        )
        self._delete(
            "DELETE FROM image_sequence_canonical WHERE source_image_id IN :source_ids",
            source_ids=scope.source_ids,
        )
        self._delete(
            "DELETE FROM image_sequence_alternatives "
            "WHERE game_id = :game_id AND sequence_number IN :selected_sequences",
            game_id=scope.game_id,
            selected_sequences=scope.selected_sequences,
        )
        self._delete(
            "DELETE FROM image_sequence_source_override_events "
            "WHERE game_id = :game_id AND sequence_number IN :selected_sequences",
            game_id=scope.game_id,
            selected_sequences=scope.selected_sequences,
        )
        self._delete(
            "DELETE FROM image_review_resolution_events WHERE review_item_id IN :review_item_ids",
            review_item_ids=scope.review_item_ids,
        )
        self._delete(
            "DELETE FROM image_board_geometry_review_events "
            "WHERE recognized_board_id IN :board_ids",
            board_ids=scope.board_ids,
        )
        self._delete(
            "DELETE FROM image_board_geometry_revisions WHERE recognized_board_id IN :board_ids",
            board_ids=scope.board_ids,
        )
        self._delete(
            "DELETE FROM image_board_geometry_pending WHERE source_image_id IN :source_ids",
            source_ids=scope.source_ids,
        )
        self._delete(
            "DELETE FROM image_symbol_review_cells WHERE id IN :cell_review_ids",
            cell_review_ids=scope.cell_review_ids,
        )
        self._delete(
            "DELETE FROM image_review_items WHERE id IN :review_item_ids",
            review_item_ids=scope.review_item_ids,
        )
        self._delete(
            "DELETE FROM cell_observations WHERE id IN :observation_ids",
            observation_ids=scope.observation_ids,
        )
        self._delete(
            "DELETE FROM recognized_boards WHERE id IN :board_ids", board_ids=scope.board_ids
        )
        self._delete(
            "UPDATE image_geometry_rollout_states SET last_source_image_id = NULL "
            "WHERE last_source_image_id IN :source_ids",
            source_ids=scope.source_ids,
        )
        self._delete(
            "DELETE FROM image_page_geometry_overrides "
            "WHERE game_id = :game_id AND source_checksum_sha256 IN :source_checksums",
            game_id=scope.game_id,
            source_checksums=scope.source_checksums,
        )
        self._delete(
            "DELETE FROM image_source_geometry_revisions WHERE id IN :source_geometry_ids",
            source_geometry_ids=scope.source_geometry_ids,
        )
        self._delete(
            "DELETE FROM source_images WHERE id IN :source_ids", source_ids=scope.source_ids
        )
        self._delete(
            "DELETE FROM image_review_queue_states WHERE import_job_id IN :import_job_ids",
            import_job_ids=scope.import_job_ids,
        )
        self._delete(
            "DELETE FROM image_symbol_review_states WHERE game_id = :game_id",
            game_id=scope.game_id,
        )
        self._delete(
            "DELETE FROM image_board_search_projection_states WHERE game_id = :game_id",
            game_id=scope.game_id,
        )
        for job_id, execution_key in scope.source_job_execution_pairs:
            self._session.execute(
                text(
                    "DELETE FROM image_import_job_files "
                    "WHERE job_id = :job_id AND file_execution_key = :execution_key"
                ),
                {"job_id": job_id, "execution_key": execution_key},
            )
        shared_execution_keys = set(
            self._session.scalars(
                self._bound_statement(
                    "SELECT DISTINCT file_execution_key FROM image_import_job_files "
                    "WHERE file_execution_key IN :execution_keys",
                    {"execution_keys": scope.execution_keys},
                ),
                {"execution_keys": scope.execution_keys},
            )
        )
        unshared_execution_keys = tuple(
            key for key in scope.execution_keys if key not in shared_execution_keys
        )
        self._delete(
            "DELETE FROM image_pipeline_stage_results WHERE file_execution_key IN :execution_keys",
            execution_keys=unshared_execution_keys,
        )
        self._delete(
            "DELETE FROM image_pipeline_terminal_manifests "
            "WHERE file_execution_key IN :execution_keys",
            execution_keys=unshared_execution_keys,
        )
        self._delete(
            "DELETE FROM image_file_executions WHERE file_execution_key IN :execution_keys",
            execution_keys=unshared_execution_keys,
        )

    def _ids(self, statement: str, **parameters: object) -> tuple[UUID, ...]:
        if any(isinstance(value, tuple) and not value for value in parameters.values()):
            return ()
        return tuple(
            self._session.scalars(self._bound_statement(statement, parameters), parameters)
        )

    def _paths(self, statement: str, **parameters: object) -> tuple[str, ...]:
        if any(isinstance(value, tuple) and not value for value in parameters.values()):
            return ()
        return tuple(
            str(value)
            for value in self._session.scalars(
                self._bound_statement(statement, parameters), parameters
            )
            if value is not None
        )

    def _delete(self, statement: str, **parameters: object) -> None:
        if any(isinstance(value, tuple) and not value for value in parameters.values()):
            return
        self._session.execute(self._bound_statement(statement, parameters), parameters)

    @staticmethod
    def _bound_statement(statement: str, parameters: dict[str, object]) -> TextClause:
        return text(statement).bindparams(
            *(
                bindparam(name, expanding=True)
                for name, value in parameters.items()
                if isinstance(value, tuple)
            )
        )


@dataclass(frozen=True, slots=True)
class _BoardSourceScope:
    game_id: UUID
    ranges: tuple[tuple[int, int], ...]
    source_ids: tuple[UUID, ...]
    board_ids: tuple[UUID, ...]
    review_item_ids: tuple[UUID, ...]
    cell_review_ids: tuple[UUID, ...]
    observation_ids: tuple[UUID, ...]
    source_geometry_ids: tuple[UUID, ...]
    cohort_ids: tuple[UUID, ...]
    model_ids: tuple[UUID, ...]
    verified_export_ids: tuple[UUID, ...]
    activation_ids: tuple[UUID, ...]
    release_ids: tuple[UUID, ...]
    selected_sequences: tuple[int, ...]
    source_checksums: tuple[str, ...]
    execution_keys: tuple[str, ...]
    import_job_ids: tuple[UUID, ...]
    source_job_execution_pairs: tuple[tuple[UUID, str], ...]
    active_model_affected: bool
    active_model_survives: bool
    artifact_paths: tuple[str, ...]
    retained_shared_artifact_count: int


def _range_confirmation_target(
    game_id: UUID,
    ranges: tuple[tuple[int, int], ...],
) -> str:
    return f"{game_id}:" + ",".join(f"{start}-{end}" for start, end in ranges)


def _ranges_from_confirmation_target(
    game_id: UUID,
    confirmation_target: str,
) -> tuple[tuple[int, int], ...]:
    prefix = f"{game_id}:"
    if not confirmation_target.startswith(prefix):
        raise CleanupConflictError(
            "CLEANUP_CONFIRMATION_MISMATCH",
            "The source-range confirmation target belongs to another game.",
        )
    raw_ranges = confirmation_target.removeprefix(prefix).split(",")
    ranges: list[tuple[int, int]] = []
    try:
        for raw_range in raw_ranges:
            raw_start, raw_end = raw_range.split("-", maxsplit=1)
            start, end = int(raw_start), int(raw_end)
            if start <= 0 or end < start or end - start >= 9:
                raise ValueError
            ranges.append((start, end))
    except ValueError as error:
        raise CleanupConflictError(
            "CLEANUP_CONFIRMATION_MISMATCH",
            "The source-range confirmation target is malformed.",
        ) from error
    canonical = tuple(sorted(set(ranges)))
    if not canonical:
        raise CleanupConflictError(
            "CLEANUP_CONFIRMATION_MISMATCH",
            "The source-range confirmation target is empty.",
        )
    return canonical


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
    payload: dict[str, object] = {
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
    if result.quarantine_key is not None:
        payload["quarantineKey"] = result.quarantine_key
    return payload


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
        quarantine_key=cast(str | None, payload.get("quarantineKey")),
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
