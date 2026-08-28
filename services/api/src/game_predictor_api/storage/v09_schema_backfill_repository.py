"""Bounded, idempotent backfill for the additive v0.9 board schema."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_symbol_reviews import SymbolCellQualityIssue
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionModel,
    SourceImageModel,
)

_DEFAULT_BATCH_SIZE = 200


class V09SchemaBackfillError(RuntimeError):
    """A controlled inconsistency which must not be repaired heuristically."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        game_id: UUID,
        board_ids: tuple[UUID, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.game_id = game_id
        self.board_ids = board_ids


@dataclass(frozen=True, slots=True)
class V09SchemaBackfillStep:
    game_id: UUID
    topology_rules_version_id: UUID | None
    topology: BoardTopology | None
    processed_board_count: int
    updated_board_count: int
    updated_cell_count: int
    next_board_id: UUID | None
    has_more: bool
    issue_code: str | None = None
    issue_message: str | None = None
    problem_board_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class V09SchemaBackfillValidation:
    game_id: UUID
    topology_rules_version_id: UUID | None
    board_count: int
    cell_count: int
    missing_topology_board_count: int
    missing_geometry_approval_count: int
    inconsistent_quality_count: int
    missing_approved_crop_count: int
    ready: bool


class SqlAlchemyV09SchemaBackfillRepository:
    """Backfill metadata only; image bytes and immutable observations stay untouched."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def pin_existing_game_topology(self, game_id: UUID) -> tuple[UUID | None, BoardTopology | None]:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise V09SchemaBackfillError(
                "GAME_NOT_FOUND",
                "The selected game does not exist.",
                game_id=game_id,
            )
        board_count = self._board_count(game_id)
        if board_count == 0:
            return None, None

        observed = self._observed_legacy_topology(game_id)
        if game.board_topology_rules_version_id is not None:
            pinned = self._session.get(RulesVersionModel, game.board_topology_rules_version_id)
            if pinned is None or (pinned.rows, pinned.columns) != (
                observed.rows,
                observed.columns,
            ):
                raise V09SchemaBackfillError(
                    "GAME_BOARD_TOPOLOGY_INCONSISTENT",
                    "The pinned rules version conflicts with existing board data.",
                    game_id=game_id,
                )
            return pinned.id, BoardTopology(rows=pinned.rows, columns=pinned.columns)

        rules_version = self._session.scalar(
            select(RulesVersionModel)
            .where(
                RulesVersionModel.game_id == game_id,
                RulesVersionModel.rows == observed.rows,
                RulesVersionModel.columns == observed.columns,
            )
            .order_by(RulesVersionModel.version.desc(), RulesVersionModel.id.desc())
            .limit(1)
        )
        if rules_version is None:
            raise V09SchemaBackfillError(
                "GAME_BOARD_TOPOLOGY_RULES_MISMATCH",
                "No rules version matches the topology of existing boards.",
                game_id=game_id,
            )

        game.board_topology_rules_version_id = rules_version.id
        self._session.flush()
        return rules_version.id, observed

    def backfill_next_batch(
        self,
        game_id: UUID,
        *,
        after_board_id: UUID | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> V09SchemaBackfillStep:
        if not 1 <= batch_size <= _DEFAULT_BATCH_SIZE:
            raise ValueError("batch_size must be between 1 and 200")
        rules_version_id, topology = self.pin_existing_game_topology(game_id)
        if topology is None:
            return V09SchemaBackfillStep(
                game_id=game_id,
                topology_rules_version_id=None,
                topology=None,
                processed_board_count=0,
                updated_board_count=0,
                updated_cell_count=0,
                next_board_id=None,
                has_more=False,
            )

        statement = (
            select(RecognizedBoardModel, ImageReviewItemModel)
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .outerjoin(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .where(
                JobModel.game_id == game_id,
                *((RecognizedBoardModel.id > after_board_id,) if after_board_id else ()),
            )
            .order_by(RecognizedBoardModel.id)
            .with_for_update(of=RecognizedBoardModel)
            .limit(batch_size + 1)
        )
        rows = tuple(self._session.execute(statement).tuples())
        visible = rows[:batch_size]
        has_more = len(rows) > batch_size
        board_ids = tuple(board.id for board, _review_item in visible)
        cells_by_board: dict[UUID, list[ImageSymbolReviewCellModel]] = defaultdict(list)
        for cell in self._session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.recognized_board_id.in_(board_ids))
            .order_by(
                ImageSymbolReviewCellModel.recognized_board_id,
                ImageSymbolReviewCellModel.cell_index,
            )
            .with_for_update()
        ):
            cells_by_board[cell.recognized_board_id].append(cell)
        manual_revisions_by_board: dict[UUID, ImageBoardGeometryRevisionModel] = {}
        for revision in self._session.scalars(
            select(ImageBoardGeometryRevisionModel)
            .where(ImageBoardGeometryRevisionModel.recognized_board_id.in_(board_ids))
            .order_by(
                ImageBoardGeometryRevisionModel.recognized_board_id,
                ImageBoardGeometryRevisionModel.revision,
            )
        ):
            manual_revisions_by_board[revision.recognized_board_id] = revision
        updated_board_count = 0
        updated_cell_count = 0
        for board, review_item in visible:
            updated_board, updated_cells = self._backfill_board(
                game_id=game_id,
                board=board,
                review_item=review_item,
                topology=topology,
                cells=tuple(cells_by_board.get(board.id, ())),
                manual_revision=manual_revisions_by_board.get(board.id),
                load_related=False,
            )
            updated_board_count += int(updated_board)
            updated_cell_count += updated_cells
        self._session.flush()
        return V09SchemaBackfillStep(
            game_id=game_id,
            topology_rules_version_id=rules_version_id,
            topology=topology,
            processed_board_count=len(visible),
            updated_board_count=updated_board_count,
            updated_cell_count=updated_cell_count,
            next_board_id=None if not visible else visible[-1][0].id,
            has_more=has_more,
        )

    def validate_game(self, game_id: UUID) -> V09SchemaBackfillValidation:
        game = self._session.get(GameModel, game_id)
        if game is None:
            raise V09SchemaBackfillError(
                "GAME_NOT_FOUND",
                "The selected game does not exist.",
                game_id=game_id,
            )
        board_scope = (
            select(RecognizedBoardModel.id)
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(JobModel.game_id == game_id)
        )
        board_count = int(
            self._session.scalar(select(func.count()).select_from(board_scope.subquery())) or 0
        )
        cell_count = int(
            self._session.scalar(
                select(func.count(ImageSymbolReviewCellModel.id)).where(
                    ImageSymbolReviewCellModel.game_id == game_id
                )
            )
            or 0
        )
        missing_topology = int(
            self._session.scalar(
                select(func.count(RecognizedBoardModel.id)).where(
                    RecognizedBoardModel.id.in_(board_scope),
                    (
                        RecognizedBoardModel.grid_rows.is_(None)
                        | RecognizedBoardModel.grid_columns.is_(None)
                    ),
                )
            )
            or 0
        )
        missing_geometry_approval = int(
            self._session.scalar(
                select(func.count(RecognizedBoardModel.id))
                .join(
                    ImageReviewItemModel,
                    ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
                )
                .where(
                    RecognizedBoardModel.id.in_(board_scope),
                    ImageReviewItemModel.status.in_(("accepted", "corrected")),
                    RecognizedBoardModel.approved_geometry_revision.is_(None),
                )
            )
            or 0
        )
        inconsistent_quality = int(
            self._session.scalar(
                select(func.count(ImageSymbolReviewCellModel.id)).where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    or_(
                        and_(
                            ImageSymbolReviewCellModel.has_grid_issue.is_(True),
                            or_(
                                ImageSymbolReviewCellModel.quality_issue.is_(None),
                                ImageSymbolReviewCellModel.quality_issue != "grid_issue",
                            ),
                        ),
                        and_(
                            ImageSymbolReviewCellModel.has_grid_issue.is_(False),
                            ImageSymbolReviewCellModel.quality_issue == "grid_issue",
                        ),
                    ),
                )
            )
            or 0
        )
        missing_approved_crop = int(
            self._session.scalar(
                select(func.count(ImageSymbolReviewCellModel.id)).where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.review_state == "approved",
                    (
                        ImageSymbolReviewCellModel.approved_crop_sample_id.is_(None)
                        | ImageSymbolReviewCellModel.approved_crop_checksum_sha256.is_(None)
                        | ImageSymbolReviewCellModel.approved_geometry_revision.is_(None)
                    ),
                )
            )
            or 0
        )
        ready = (
            (board_count == 0 or game.board_topology_rules_version_id is not None)
            and missing_topology == 0
            and missing_geometry_approval == 0
            and inconsistent_quality == 0
            and missing_approved_crop == 0
        )
        return V09SchemaBackfillValidation(
            game_id=game_id,
            topology_rules_version_id=game.board_topology_rules_version_id,
            board_count=board_count,
            cell_count=cell_count,
            missing_topology_board_count=missing_topology,
            missing_geometry_approval_count=missing_geometry_approval,
            inconsistent_quality_count=inconsistent_quality,
            missing_approved_crop_count=missing_approved_crop,
            ready=ready,
        )

    def _backfill_board(
        self,
        *,
        game_id: UUID,
        board: RecognizedBoardModel,
        review_item: ImageReviewItemModel | None,
        topology: BoardTopology,
        cells: Sequence[ImageSymbolReviewCellModel] | None = None,
        manual_revision: ImageBoardGeometryRevisionModel | None = None,
        load_related: bool = True,
    ) -> tuple[bool, int]:
        if (board.grid_rows, board.grid_columns) not in {
            (None, None),
            (topology.rows, topology.columns),
        }:
            raise V09SchemaBackfillError(
                "IMAGE_BOARD_TOPOLOGY_INCONSISTENT",
                "A recognized board has a topology conflicting with its game.",
                game_id=game_id,
                board_ids=(board.id,),
            )
        changed = False
        if board.grid_rows is None:
            board.grid_rows = topology.rows
            board.grid_columns = topology.columns
            changed = True

        approval_actor: str | None = None
        approval_time: datetime | None = None
        if review_item is not None and review_item.status in {"accepted", "corrected"}:
            approval_actor = review_item.resolved_by
            approval_time = review_item.resolved_at
        elif board.geometry_revision > 0:
            if load_related:
                manual_revision = self._session.scalar(
                    select(ImageBoardGeometryRevisionModel)
                    .where(
                        ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                        ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
                    )
                    .limit(1)
                )
            elif (
                manual_revision is not None and manual_revision.revision != board.geometry_revision
            ):
                manual_revision = None
            if manual_revision is not None and manual_revision.corrected_by.strip():
                approval_actor = manual_revision.corrected_by
                approval_time = manual_revision.created_at

        if approval_actor is not None and approval_time is not None:
            if board.approved_geometry_revision not in (None, board.geometry_revision):
                raise V09SchemaBackfillError(
                    "IMAGE_BOARD_GEOMETRY_APPROVAL_INCONSISTENT",
                    "A board has an approval for a different geometry revision.",
                    game_id=game_id,
                    board_ids=(board.id,),
                )
            if board.approved_geometry_revision is None:
                board.approved_geometry_revision = board.geometry_revision
                board.geometry_approved_at = approval_time
                board.geometry_approved_by = approval_actor
                changed = True

        updated_cells = 0
        if cells is None:
            cells = self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.recognized_board_id == board.id)
                .with_for_update()
            ).all()
        for cell in cells:
            expected_quality = (
                SymbolCellQualityIssue.GRID_ISSUE.value if cell.has_grid_issue else None
            )
            if cell.quality_issue not in (None, expected_quality):
                raise V09SchemaBackfillError(
                    "SYMBOL_CELL_QUALITY_INCONSISTENT",
                    "A persisted crop has conflicting legacy and v0.9 quality states.",
                    game_id=game_id,
                    board_ids=(board.id,),
                )
            cell_changed = False
            if cell.quality_issue != expected_quality:
                cell.quality_issue = expected_quality
                cell_changed = True
            if cell.review_state == "approved":
                approved_identity = (
                    cell.approved_crop_sample_id,
                    cell.approved_crop_checksum_sha256,
                    cell.approved_geometry_revision,
                )
                if approved_identity == (None, None, None):
                    cell.approved_crop_sample_id = cell.crop_sample_id
                    cell.approved_crop_checksum_sha256 = cell.crop_checksum_sha256
                    cell.approved_geometry_revision = cell.geometry_revision
                    cell_changed = True
                elif approved_identity != (
                    cell.crop_sample_id,
                    cell.crop_checksum_sha256,
                    cell.geometry_revision,
                ):
                    raise V09SchemaBackfillError(
                        "SYMBOL_CELL_APPROVED_CROP_INCONSISTENT",
                        "An approved crop already has conflicting provenance.",
                        game_id=game_id,
                        board_ids=(board.id,),
                    )
            if cell_changed:
                updated_cells += 1
        return changed, updated_cells

    def _board_count(self, game_id: UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count(RecognizedBoardModel.id))
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .where(JobModel.game_id == game_id)
            )
            or 0
        )

    def _observed_legacy_topology(self, game_id: UUID) -> BoardTopology:
        row = self._session.execute(
            select(
                func.count(CellObservationModel.id),
                func.max(CellObservationModel.row_index),
                func.max(CellObservationModel.column_index),
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(JobModel.game_id == game_id)
        ).one()
        observation_count, max_row, max_column = row
        if not observation_count or max_row is None or max_column is None:
            raise V09SchemaBackfillError(
                "GAME_BOARD_TOPOLOGY_EVIDENCE_MISSING",
                "Existing boards do not contain enough cell evidence to pin topology.",
                game_id=game_id,
            )
        topology = BoardTopology(rows=int(max_row) + 1, columns=int(max_column) + 1)
        if topology.cell_count != 15:
            raise V09SchemaBackfillError(
                "GAME_BOARD_TOPOLOGY_INCONSISTENT",
                "Existing pre-0.9 boards do not form the supported legacy 3 by 5 topology.",
                game_id=game_id,
            )
        incomplete_board_ids = tuple(
            self._session.scalars(
                select(RecognizedBoardModel.id)
                .join(
                    SourceImageModel,
                    SourceImageModel.id == RecognizedBoardModel.source_image_id,
                )
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .outerjoin(
                    CellObservationModel,
                    CellObservationModel.recognized_board_id == RecognizedBoardModel.id,
                )
                .where(JobModel.game_id == game_id)
                .group_by(RecognizedBoardModel.id)
                .having(
                    or_(
                        func.count(CellObservationModel.id) != topology.cell_count,
                        func.max(CellObservationModel.row_index) != topology.rows - 1,
                        func.max(CellObservationModel.column_index) != topology.columns - 1,
                    )
                )
                .order_by(RecognizedBoardModel.id)
                .limit(100)
            )
        )
        if incomplete_board_ids:
            raise V09SchemaBackfillError(
                "GAME_BOARD_TOPOLOGY_INCONSISTENT",
                "At least one existing board lacks a complete row-major cell topology.",
                game_id=game_id,
                board_ids=incomplete_board_ids,
            )
        return topology


__all__ = [
    "SqlAlchemyV09SchemaBackfillRepository",
    "V09SchemaBackfillError",
    "V09SchemaBackfillStep",
    "V09SchemaBackfillValidation",
]
