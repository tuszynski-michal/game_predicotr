"""TASK-0728: preview and apply of the D-462 cell-level data migration.

Preview only reads. Apply takes one board per transaction, re-plans it under
the same locks as a cell mutation and executes the plan only when it equals
the reviewed manifest entry. No cell is ever verified by the migration.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from game_predictor_api.domain.cell_level_verification_migration import (
    MANIFEST_VERSION,
    MIGRATED_STATUSES,
    MIGRATION_ACTOR,
    REOPEN_REASON,
    BoardMigrationPlan,
    CellFingerprint,
    CellLevelMigrationError,
    board_fingerprint,
    build_manifest,
    plan_board_migration,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewState
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
    acquire_image_review_sequence_locks,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
    active_symbol_codes_by_id,
    assess_cell_level_board,
    enter_cell_decision,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    RecognizedBoardModel,
)

DEFAULT_BATCH_SIZE = 500


class CellLevelMigrationInvariantError(CellLevelMigrationError):
    """A board would end with a new verification; the whole run must stop."""


class CellLevelVerificationMigrationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def require_ready_game(self, game_id: UUID) -> None:
        if self._session.get(GameModel, game_id) is None:
            raise CellLevelMigrationError("GAME_NOT_FOUND", "The selected game does not exist.")
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        if state is None or state.status != "ready":
            raise CellLevelMigrationError(
                "CELL_MIGRATION_PROJECTION_NOT_READY",
                "The symbol-cell review projection of this game is not ready.",
            )

    def candidate_review_item_ids(self, game_id: UUID) -> tuple[UUID, ...]:
        """Boards with at least one cell other than a pure model prediction."""

        cell = ImageSymbolReviewCellModel
        statement = (
            select(cell.review_item_id)
            .join(ImageReviewItemModel, ImageReviewItemModel.id == cell.review_item_id)
            .where(
                cell.game_id == game_id,
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.status.in_(sorted(MIGRATED_STATUSES)),
                or_(
                    cell.review_state != SymbolCellReviewState.PENDING.value,
                    cell.assignment_source != "model",
                    cell.quality_issue.is_not(None),
                    cell.source_available.is_(False),
                ),
            )
            .distinct()
        )
        return tuple(sorted(set(self._session.scalars(statement)), key=str))

    def plan_boards(
        self,
        game_id: UUID,
        review_item_ids: Sequence[UUID],
        *,
        symbol_code_by_id: Mapping[UUID, str],
    ) -> tuple[list[BoardMigrationPlan], dict[str, list[str]]]:
        """Plans with at least one action, and boards a closure cannot reach."""

        ids = sorted(set(review_item_ids), key=str)
        if not ids:
            return [], {}
        rows = self._session.execute(
            select(ImageReviewItemModel, RecognizedBoardModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.id.in_(ids),
            )
        ).all()
        cells_by_item: dict[UUID, list[ImageSymbolReviewCellModel]] = defaultdict(list)
        for cell in self._session.scalars(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.review_item_id.in_(ids),
            )
        ):
            cells_by_item[cell.review_item_id].append(cell)
        stale_projection = SqlAlchemyBoardSearchProjectionRepository(
            self._session
        ).stale_review_item_ids(ids)
        plans: list[BoardMigrationPlan] = []
        blockers: dict[str, list[str]] = defaultdict(list)
        for item, board in sorted(rows, key=lambda row: str(row[0].id)):
            if item.status not in MIGRATED_STATUSES:
                continue
            cells = [
                cell for cell in cells_by_item[item.id] if cell.recognized_board_id == board.id
            ]
            assessment = assess_cell_level_board(
                item=item,
                board=board,
                cells=cells,
                symbol_code_by_id=symbol_code_by_id,
            )
            if assessment.blocker is not None and any(
                cell.review_state == SymbolCellReviewState.APPROVED.value for cell in cells
            ):
                blockers[assessment.blocker].append(str(item.id))
            plan = plan_board_migration(
                review_item_id=item.id,
                sequence_number=item.sequence_number,
                status=item.status,
                fingerprint=board_fingerprint(
                    status=item.status,
                    resolution_revision=item.resolution_revision,
                    geometry_revision=board.geometry_revision,
                    cells=(
                        CellFingerprint(
                            cell_index=cell.cell_index,
                            revision=cell.revision,
                            review_state=cell.review_state,
                            crop_checksum_sha256=cell.crop_checksum_sha256,
                            rendered_pixel_checksum_sha256=cell.rendered_pixel_checksum_sha256,
                        )
                        for cell in cells
                    ),
                ),
                changed_pixel_approvals=assessment.changed_pixel_approvals,
                resolution_after_recheck=assessment.resolution_after_recheck,
                projection_stale=item.id in stale_projection,
            )
            if plan.has_actions:
                plans.append(plan)
        return plans, dict(blockers)

    def preview(
        self,
        game_id: UUID,
        *,
        generated_at: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> dict[str, Any]:
        """Read-only manifest of every board action; the caller owns the transaction."""

        if not 1 <= batch_size <= 2000:
            raise CellLevelMigrationError(
                "CELL_MIGRATION_BATCH_INVALID", "The batch size must be between 1 and 2000."
            )
        self.require_ready_game(game_id)
        ids = self.candidate_review_item_ids(game_id)
        symbol_code_by_id = active_symbol_codes_by_id(self._session, game_id)
        plans: list[BoardMigrationPlan] = []
        notes: dict[str, list[str]] = defaultdict(list)
        for start in range(0, len(ids), batch_size):
            batch_plans, batch_notes = self.plan_boards(
                game_id,
                ids[start : start + batch_size],
                symbol_code_by_id=symbol_code_by_id,
            )
            plans.extend(batch_plans)
            for code, values in batch_notes.items():
                notes[code].extend(values)
        return build_manifest(
            game_id=game_id,
            plans=plans,
            scanned=len(ids),
            generated_at=generated_at,
            notes=notes,
        )

    def apply_board(
        self,
        game_id: UUID,
        planned: BoardMigrationPlan,
        *,
        actor: str = MIGRATION_ACTOR,
    ) -> dict[str, Any]:
        """Apply one reviewed board plan in the caller's transaction."""

        review_item_id = planned.review_item_id
        # TASK-0971 (P0-5): ownership lock before the sequence lock.
        enter_cell_decision(self._session, game_id=game_id, review_item_id=review_item_id)
        acquire_image_review_sequence_locks(
            self._session,
            game_id=game_id,
            review_item_id=review_item_id,
            requested_sequence_number=None,
        )
        item = self._session.execute(
            select(ImageReviewItemModel)
            .where(
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.id == review_item_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if item is None:
            return {"reviewItemId": str(review_item_id), "result": "drift", "code": "MISSING"}
        approved_before = self._approved_indices(game_id, review_item_id, lock=True)
        fresh, _blockers = self.plan_boards(
            game_id,
            (review_item_id,),
            symbol_code_by_id=active_symbol_codes_by_id(self._session, game_id),
        )
        current = fresh[0] if fresh else None
        if current is None:
            return {"reviewItemId": str(review_item_id), "result": "already_applied"}
        if current != planned:
            return {
                "reviewItemId": str(review_item_id),
                "result": "drift",
                "planned": planned.to_manifest(),
                "current": current.to_manifest(),
            }
        now = datetime.now(UTC)
        if current.reopen:
            SqlAlchemyOperationalImageReviewRepository(self._session).reopen_for_symbol_cell_issue(
                review_item_id=review_item_id,
                game_id=game_id,
                import_job_id=item.import_job_id,
                idempotency_key=uuid4(),
                command_sha256=hashlib.sha256(
                    f"{MANIFEST_VERSION}:{review_item_id}:{current.fingerprint}".encode()
                ).hexdigest(),
                reopened_by=actor,
                reopened_at=now,
                reason=REOPEN_REASON,
            )
        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        rechecked = 0
        if current.recheck_cell_indices:
            rechecked = coordinator.recheck_changed_pixel_approvals(
                game_id=game_id,
                review_item_id=review_item_id,
                cell_indices=current.recheck_cell_indices,
                actor=actor,
            )
        closed = False
        if current.close_action is not None:
            closed = coordinator.synchronize_board_from_cells(
                game_id=game_id,
                review_item_id=review_item_id,
                actor=actor,
            )
        SqlAlchemyBoardSearchProjectionRepository(self._session).sync_review_item(review_item_id)
        self._session.flush()
        approved_after = self._approved_indices(game_id, review_item_id, lock=False)
        if approved_after != approved_before - set(current.recheck_cell_indices):
            raise CellLevelMigrationInvariantError(
                "CELL_MIGRATION_NEW_VERIFICATION",
                f"Board {review_item_id} would end with approvals other than its reviewed "
                "ones minus the recheck.",
            )
        return {
            "reviewItemId": str(review_item_id),
            "result": "applied",
            "reopened": current.reopen,
            "rechecked": rechecked,
            "closed": closed,
            "expectedClose": current.close_action is not None,
            "refreshedProjection": True,
        }

    def _approved_indices(self, game_id: UUID, review_item_id: UUID, *, lock: bool) -> set[int]:
        statement = select(ImageSymbolReviewCellModel).where(
            ImageSymbolReviewCellModel.game_id == game_id,
            ImageSymbolReviewCellModel.review_item_id == review_item_id,
        )
        if lock:
            statement = statement.with_for_update()
        return {
            cell.cell_index
            for cell in self._session.scalars(statement)
            if cell.review_state == SymbolCellReviewState.APPROVED.value
        }


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "CellLevelMigrationInvariantError",
    "CellLevelVerificationMigrationRepository",
]
