"""Persistence and resumable backfill for checksum-bound symbol-cell review."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellReviewState,
    map_current_symbol_cell_reviews,
)
from game_predictor_api.storage.image_review_repository import (
    materialize_current_image_review_cells,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageReviewQueueItemModel,
    ImageSymbolPredictionRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)

_ACTIVE_REVIEW_STATUSES = frozenset({"pending", "accepted", "corrected"})
_DEFAULT_BATCH_SIZE = 200
_BACKFILL_ACTOR = "system:symbol-cell-backfill"

BackfillRow = tuple[
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    RecognizedBoardModel,
    SourceImageModel,
    ImageReviewQueueItemModel,
    JobModel,
]


class SymbolCellReviewBackfillError(RuntimeError):
    """Controlled integrity failure preventing a game from becoming ready."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        review_item_ids: Sequence[UUID] = (),
        invalid_crop_count: int = 0,
        invalid_geometry_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.review_item_ids = tuple(review_item_ids)
        self.invalid_crop_count = invalid_crop_count
        self.invalid_geometry_count = invalid_geometry_count


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBackfillReport:
    game_id: UUID
    status: str
    processed_review_item_count: int
    cell_count: int
    missing_sequence_count: int
    invalid_crop_count: int
    invalid_geometry_count: int
    failure_message: str | None
    sample_problem_review_item_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBackfillStep:
    report: SymbolCellReviewBackfillReport
    processed_review_item_count: int
    has_more: bool


class SqlAlchemyImageSymbolReviewRepository:
    """Backfills only selected logical boards and never stores crop bytes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def start_or_resume_backfill(self, game_id: UUID) -> SymbolCellReviewBackfillReport:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_GAME_NOT_FOUND", "The selected game does not exist."
            )
        missing = self._active_review_items_without_sequence(game_id)
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        if state is None:
            state = ImageSymbolReviewStateModel(
                game_id=game_id,
                status="rebuilding",
                processed_review_item_count=0,
                cell_count=0,
                missing_sequence_count=0,
                invalid_crop_count=0,
                invalid_geometry_count=0,
                last_review_item_id=None,
                failure_message=None,
            )
            self._session.add(state)
        elif state.status != "ready":
            state.status = "rebuilding"
            state.failure_message = None

        if missing:
            self._mark_failed(
                state,
                SymbolCellReviewBackfillError(
                    "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING",
                    "An active board has no resolved sequence number; "
                    "symbol-cell review cannot hide it.",
                    review_item_ids=missing,
                ),
            )
        self._session.flush()
        return self._report_from_state(state, sample_problem_review_item_ids=missing)

    def backfill_next_batch(
        self,
        game_id: UUID,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> SymbolCellReviewBackfillStep:
        if not 1 <= batch_size <= 500:
            raise ValueError("batch_size must be between 1 and 500")
        state = self._require_rebuilding_state(game_id)
        rows = self._selected_rows_after(
            game_id=game_id,
            after_review_item_id=state.last_review_item_id,
            limit=batch_size,
        )
        if not rows:
            report = self.finalize_backfill(game_id)
            return SymbolCellReviewBackfillStep(
                report=report,
                processed_review_item_count=0,
                has_more=False,
            )
        try:
            values = self._cell_values(rows)
        except SymbolCellReviewBackfillError as error:
            self._mark_failed(state, error)
            self._session.flush()
            return SymbolCellReviewBackfillStep(
                report=self._report_from_state(
                    state,
                    sample_problem_review_item_ids=error.review_item_ids,
                ),
                processed_review_item_count=0,
                has_more=False,
            )

        if values:
            statement = postgresql_insert(ImageSymbolReviewCellModel).values(values)
            self._session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[
                        ImageSymbolReviewCellModel.review_item_id,
                        ImageSymbolReviewCellModel.cell_index,
                    ]
                )
            )
        state.last_review_item_id = rows[-1][1].id
        state.processed_review_item_count += len(rows)
        state.cell_count = self._current_selected_cell_count(game_id)
        self._session.flush()
        return SymbolCellReviewBackfillStep(
            report=self._report_from_state(state),
            processed_review_item_count=len(rows),
            has_more=len(rows) == batch_size,
        )

    def finalize_backfill(self, game_id: UUID) -> SymbolCellReviewBackfillReport:
        state = self._require_rebuilding_state(game_id)
        missing = self._active_review_items_without_sequence(game_id)
        incomplete = self._selected_items_without_exactly_fifteen_cells(game_id)
        stale_geometry = self._selected_items_with_stale_geometry(game_id)
        stale_base_crop = self._selected_items_with_stale_base_crop(game_id)
        if missing:
            error = SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING",
                "An active board has no resolved sequence number; "
                "symbol-cell review cannot hide it.",
                review_item_ids=missing,
            )
            self._mark_failed(state, error)
            self._session.flush()
            return self._report_from_state(state, sample_problem_review_item_ids=missing)
        if incomplete:
            error = SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_INCOMPLETE",
                "The symbol-cell backfill did not create exactly 15 current crops for every board.",
                review_item_ids=incomplete,
                invalid_crop_count=len(incomplete),
            )
            self._mark_failed(state, error)
            self._session.flush()
            return self._report_from_state(state, sample_problem_review_item_ids=incomplete)
        if stale_geometry or stale_base_crop:
            problem_ids = tuple(dict.fromkeys((*stale_geometry, *stale_base_crop)))
            error = SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_CROP_STALE",
                "Persisted symbol-cell crops no longer match their current geometry or base crop.",
                review_item_ids=problem_ids,
                invalid_crop_count=len(stale_base_crop),
                invalid_geometry_count=len(stale_geometry),
            )
            self._mark_failed(state, error)
            self._session.flush()
            return self._report_from_state(state, sample_problem_review_item_ids=problem_ids)

        state.status = "ready"
        state.cell_count = self._current_selected_cell_count(game_id)
        state.missing_sequence_count = 0
        state.invalid_crop_count = 0
        state.invalid_geometry_count = 0
        state.failure_message = None
        self._session.flush()
        return self._report_from_state(state)

    def mark_backfill_failed(
        self,
        game_id: UUID,
        error: Exception,
    ) -> SymbolCellReviewBackfillReport:
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        if state is None:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_NOT_STARTED",
                "Start the symbol-cell review backfill before marking it failed.",
            )
        controlled = (
            error
            if isinstance(error, SymbolCellReviewBackfillError)
            else SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_FAILED",
                str(error) or "Symbol-cell review backfill failed.",
            )
        )
        self._mark_failed(state, controlled)
        self._session.flush()
        return self._report_from_state(
            state,
            sample_problem_review_item_ids=controlled.review_item_ids,
        )

    def state_for_game(self, game_id: UUID) -> SymbolCellReviewBackfillReport | None:
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        return None if state is None else self._report_from_state(state)

    def _require_rebuilding_state(self, game_id: UUID) -> ImageSymbolReviewStateModel:
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        if state is None:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_NOT_STARTED",
                "Start the symbol-cell review backfill before processing a batch.",
            )
        if state.status != "rebuilding":
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_NOT_REBUILDING",
                "The symbol-cell review backfill is not currently rebuilding.",
            )
        return state

    def _selected_rows_after(
        self,
        *,
        game_id: UUID,
        after_review_item_id: UUID | None,
        limit: int,
    ) -> tuple[BackfillRow, ...]:
        statement = (
            select(
                ImageBoardSearchFastDocumentModel,
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImageReviewQueueItemModel,
                JobModel,
            )
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.id == ImageBoardSearchFastDocumentModel.review_item_id,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(
                ImageReviewQueueItemModel,
                and_(
                    ImageReviewQueueItemModel.review_item_id == ImageReviewItemModel.id,
                    ImageReviewQueueItemModel.import_job_id == SourceImageModel.import_job_id,
                ),
            )
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                ImageBoardSearchFastDocumentModel.game_id == game_id,
                ImageReviewItemModel.status.in_(_ACTIVE_REVIEW_STATUSES),
                *(
                    ()
                    if after_review_item_id is None
                    else (ImageReviewItemModel.id > after_review_item_id,)
                ),
            )
            .order_by(ImageReviewItemModel.id)
            .limit(limit)
        )
        return tuple(cast(BackfillRow, row) for row in self._session.execute(statement).tuples())

    def _cell_values(self, rows: Sequence[BackfillRow]) -> list[dict[str, object]]:
        board_ids = [board.id for _document, _item, board, _source, _queue, _job in rows]
        item_ids = [item.id for _document, item, _board, _source, _queue, _job in rows]
        observations_by_board: dict[UUID, list[CellObservationModel]] = defaultdict(list)
        for observation in self._session.scalars(
            select(CellObservationModel)
            .where(CellObservationModel.recognized_board_id.in_(board_ids))
            .order_by(
                CellObservationModel.recognized_board_id,
                CellObservationModel.row_index,
                CellObservationModel.column_index,
            )
        ):
            observations_by_board[observation.recognized_board_id].append(observation)
        revisions_by_board: dict[UUID, ImageBoardGeometryRevisionModel] = {}
        for geometry in self._session.scalars(
            select(ImageBoardGeometryRevisionModel)
            .where(ImageBoardGeometryRevisionModel.recognized_board_id.in_(board_ids))
            .order_by(
                ImageBoardGeometryRevisionModel.recognized_board_id,
                ImageBoardGeometryRevisionModel.revision,
            )
        ):
            revisions_by_board[geometry.recognized_board_id] = geometry
        prediction_by_item: dict[UUID, ImageSymbolPredictionRevisionModel] = {}
        for prediction in self._session.scalars(
            select(ImageSymbolPredictionRevisionModel)
            .where(ImageSymbolPredictionRevisionModel.review_item_id.in_(item_ids))
            .order_by(
                ImageSymbolPredictionRevisionModel.review_item_id,
                ImageSymbolPredictionRevisionModel.created_at,
                ImageSymbolPredictionRevisionModel.id,
            )
        ):
            prediction_by_item[prediction.review_item_id] = prediction
        active_symbol_ids = {
            code: symbol_id
            for symbol_id, code in self._session.execute(
                select(SymbolModel.id, SymbolModel.code).where(
                    SymbolModel.game_id == rows[0][0].game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
            )
        }

        values: list[dict[str, object]] = []
        for document, item, board, source, queue_item, job in rows:
            prediction_revision = prediction_by_item.get(item.id)
            prediction_override = (
                None if prediction_revision is None else list(prediction_revision.predictions)
            )
            geometry = revisions_by_board.get(board.id)
            observations = observations_by_board[board.id]
            try:
                current_cells = materialize_current_image_review_cells(
                    item=item,
                    board=board,
                    source=source,
                    queue_item=queue_item,
                    job=job,
                    observations=observations,
                    geometry_revision=geometry,
                    prediction_override=prediction_override,
                )
                cropper_version = _current_cropper_version(
                    board=board,
                    observations=observations,
                    geometry=geometry,
                )
                mapped = map_current_symbol_cell_reviews(
                    cells=current_cells,
                    geometry_revision=board.geometry_revision,
                    cropper_version=cropper_version,
                    assignment_source=(
                        SymbolCellAssignmentSource.BOARD_DECISION
                        if item.status in {"accepted", "corrected"}
                        else SymbolCellAssignmentSource.BACKFILL
                    ),
                )
            except Exception as error:
                if isinstance(error, SymbolCellReviewBackfillError):
                    raise
                geometry_error = getattr(error, "code", "") in {
                    "IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID",
                    "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID",
                }
                raise SymbolCellReviewBackfillError(
                    "SYMBOL_CELL_REVIEW_BACKFILL_CROP_INVALID",
                    "The current crop projection is incomplete or invalid for a selected board.",
                    review_item_ids=(item.id,),
                    invalid_crop_count=0 if geometry_error else 1,
                    invalid_geometry_count=1 if geometry_error else 0,
                ) from error

            for review in mapped:
                approved = item.status in {"accepted", "corrected"}
                symbol_code = review.assigned_symbol_code
                symbol_id = active_symbol_ids.get(symbol_code) if symbol_code is not None else None
                if approved and symbol_id is None:
                    raise SymbolCellReviewBackfillError(
                        "SYMBOL_CELL_REVIEW_BACKFILL_RESOLUTION_INVALID",
                        "A resolved board contains an unknown or inactive symbol assignment.",
                        review_item_ids=(item.id,),
                        invalid_crop_count=1,
                    )
                values.append(
                    {
                        "id": uuid4(),
                        "game_id": document.game_id,
                        "import_job_id": source.import_job_id,
                        "review_item_id": item.id,
                        "recognized_board_id": board.id,
                        "sequence_number": document.sequence_number,
                        "cell_index": review.cell_index,
                        "row_index": review.cell_index // 5,
                        "column_index": review.cell_index % 5,
                        "crop_sample_id": review.crop.crop_sample_id,
                        "crop_relative_path": review.crop.crop_relative_path,
                        "crop_checksum_sha256": review.crop.crop_checksum_sha256,
                        "geometry_revision": review.crop.geometry_revision,
                        "cropper_version": review.crop.cropper_version,
                        "prediction_symbol_code": review.predicted_symbol_code,
                        "prediction_revision_id": (
                            None if prediction_revision is None else prediction_revision.id
                        ),
                        "assigned_symbol_id": symbol_id,
                        "review_state": (
                            SymbolCellReviewState.APPROVED.value
                            if approved
                            else SymbolCellReviewState.PENDING.value
                        ),
                        "has_grid_issue": False,
                        "assignment_source": (
                            SymbolCellAssignmentSource.BOARD_DECISION.value
                            if approved
                            else SymbolCellAssignmentSource.BACKFILL.value
                        ),
                        "revision": 0,
                        "last_reviewed_by": _BACKFILL_ACTOR,
                    }
                )
        return values

    def _active_review_items_without_sequence(self, game_id: UUID) -> tuple[UUID, ...]:
        rows = self._session.execute(
            select(
                ImageReviewItemModel.id,
                ImageReviewItemModel.status,
                ImageReviewItemModel.resolved_value,
                RecognizedBoardModel.sequence_number,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                ImageReviewItemModel.status.in_(_ACTIVE_REVIEW_STATUSES),
            )
            .order_by(ImageReviewItemModel.id)
        ).all()
        missing: list[UUID] = []
        for review_item_id, status, resolved_value, board_sequence_number in rows:
            sequence_value: object = board_sequence_number
            if status in {"accepted", "corrected"} and isinstance(resolved_value, Mapping):
                sequence_value = resolved_value.get("sequenceNumber")
            if (
                not isinstance(sequence_value, int)
                or isinstance(sequence_value, bool)
                or sequence_value < 1
            ):
                missing.append(cast(UUID, review_item_id))
        return tuple(missing)

    def _selected_items_without_exactly_fifteen_cells(self, game_id: UUID) -> tuple[UUID, ...]:
        counts = (
            select(
                ImageBoardSearchFastDocumentModel.review_item_id.label("review_item_id"),
                func.count(ImageSymbolReviewCellModel.id).label("cell_count"),
            )
            .outerjoin(
                ImageSymbolReviewCellModel,
                ImageSymbolReviewCellModel.review_item_id
                == ImageBoardSearchFastDocumentModel.review_item_id,
            )
            .where(ImageBoardSearchFastDocumentModel.game_id == game_id)
            .group_by(ImageBoardSearchFastDocumentModel.review_item_id)
            .having(func.count(ImageSymbolReviewCellModel.id) != 15)
            .order_by(ImageBoardSearchFastDocumentModel.review_item_id)
        )
        return tuple(cast(UUID, value) for value in self._session.scalars(counts))

    def _selected_items_with_stale_geometry(self, game_id: UUID) -> tuple[UUID, ...]:
        statement = (
            select(ImageSymbolReviewCellModel.review_item_id)
            .join(
                ImageBoardSearchFastDocumentModel,
                ImageBoardSearchFastDocumentModel.review_item_id
                == ImageSymbolReviewCellModel.review_item_id,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .where(
                ImageBoardSearchFastDocumentModel.game_id == game_id,
                ImageSymbolReviewCellModel.geometry_revision
                != RecognizedBoardModel.geometry_revision,
            )
            .distinct()
            .order_by(ImageSymbolReviewCellModel.review_item_id)
        )
        return tuple(cast(UUID, value) for value in self._session.scalars(statement))

    def _selected_items_with_stale_base_crop(self, game_id: UUID) -> tuple[UUID, ...]:
        statement = (
            select(ImageSymbolReviewCellModel.review_item_id)
            .join(
                ImageBoardSearchFastDocumentModel,
                ImageBoardSearchFastDocumentModel.review_item_id
                == ImageSymbolReviewCellModel.review_item_id,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .outerjoin(
                CellObservationModel,
                and_(
                    CellObservationModel.recognized_board_id
                    == ImageSymbolReviewCellModel.recognized_board_id,
                    CellObservationModel.row_index == ImageSymbolReviewCellModel.row_index,
                    CellObservationModel.column_index == ImageSymbolReviewCellModel.column_index,
                ),
            )
            .where(
                ImageBoardSearchFastDocumentModel.game_id == game_id,
                RecognizedBoardModel.geometry_revision == 0,
                or_(
                    CellObservationModel.id.is_(None),
                    CellObservationModel.crop_checksum_sha256
                    != ImageSymbolReviewCellModel.crop_checksum_sha256,
                    CellObservationModel.crop_relative_path
                    != ImageSymbolReviewCellModel.crop_relative_path,
                    CellObservationModel.cropper_version
                    != ImageSymbolReviewCellModel.cropper_version,
                ),
            )
            .distinct()
            .order_by(ImageSymbolReviewCellModel.review_item_id)
        )
        return tuple(cast(UUID, value) for value in self._session.scalars(statement))

    def _current_selected_cell_count(self, game_id: UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count(ImageSymbolReviewCellModel.id))
                .join(
                    ImageBoardSearchFastDocumentModel,
                    ImageBoardSearchFastDocumentModel.review_item_id
                    == ImageSymbolReviewCellModel.review_item_id,
                )
                .where(ImageBoardSearchFastDocumentModel.game_id == game_id)
            )
            or 0
        )

    @staticmethod
    def _mark_failed(
        state: ImageSymbolReviewStateModel,
        error: SymbolCellReviewBackfillError,
    ) -> None:
        state.status = "failed"
        state.missing_sequence_count = (
            len(error.review_item_ids) if error.code == "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING" else 0
        )
        state.invalid_crop_count = error.invalid_crop_count
        state.invalid_geometry_count = error.invalid_geometry_count
        state.failure_message = f"{error.code}: {error.message}"[:500]

    @staticmethod
    def _report_from_state(
        state: ImageSymbolReviewStateModel,
        *,
        sample_problem_review_item_ids: Sequence[UUID] = (),
    ) -> SymbolCellReviewBackfillReport:
        return SymbolCellReviewBackfillReport(
            game_id=state.game_id,
            status=state.status,
            processed_review_item_count=int(state.processed_review_item_count),
            cell_count=int(state.cell_count),
            missing_sequence_count=int(state.missing_sequence_count),
            invalid_crop_count=int(state.invalid_crop_count),
            invalid_geometry_count=int(state.invalid_geometry_count),
            failure_message=state.failure_message,
            sample_problem_review_item_ids=tuple(sample_problem_review_item_ids[:100]),
        )


def _current_cropper_version(
    *,
    board: RecognizedBoardModel,
    observations: Sequence[CellObservationModel],
    geometry: ImageBoardGeometryRevisionModel | None,
) -> str:
    if board.geometry_revision > 0:
        if geometry is None or geometry.revision != board.geometry_revision:
            raise SymbolCellReviewBackfillError(
                "SYMBOL_CELL_REVIEW_BACKFILL_GEOMETRY_INVALID",
                "The current board geometry revision is missing.",
                invalid_geometry_count=1,
            )
        return cast(str, geometry.cropper_version)
    versions = {observation.cropper_version for observation in observations}
    if len(versions) != 1:
        raise SymbolCellReviewBackfillError(
            "SYMBOL_CELL_REVIEW_BACKFILL_CROP_INVALID",
            "The base board observations do not have one current cropper version.",
            invalid_crop_count=1,
        )
    return cast(str, next(iter(versions)))


__all__ = [
    "SqlAlchemyImageSymbolReviewRepository",
    "SymbolCellReviewBackfillError",
    "SymbolCellReviewBackfillReport",
    "SymbolCellReviewBackfillStep",
]
