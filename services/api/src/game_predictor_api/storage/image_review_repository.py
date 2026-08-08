"""SQLAlchemy repository for the operational image review queue."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import BigInteger, String, and_, delete, func, literal, null, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from game_predictor_api.application.image_reviews import (
    OperationalImageReviewRepository,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.image_reviews import (
    MAX_IMAGE_REVIEW_ALTERNATIVES,
    ImageDatasetCompleteness,
    ImageReviewAlternative,
    ImageReviewCell,
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    ImageReviewGeometryRevision,
    ImageReviewItem,
    ImageReviewNotFoundError,
    ImageReviewPage,
    ImageReviewResolutionEvent,
    ImageReviewView,
    ImageSequenceSourceCandidate,
    ImageSequenceSourceSelection,
    ValidatedImageReviewGeometryCommand,
    ValidatedImageReviewResolution,
    crop_sample_id,
    validate_image_review_resolution,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.verified_training_cohorts import (
    require_pending_model_prediction_target,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryRevisionModel,
    ImageImportJobFileModel,
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    ImageSequenceSourceOverrideEventModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)

ReviewRow = tuple[
    ImageReviewItemModel,
    RecognizedBoardModel,
    SourceImageModel,
    ImageImportJobFileModel,
    JobModel,
]
OrderKey = tuple[int, int, int, str]


class SqlAlchemyOperationalImageReviewRepository(OperationalImageReviewRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def require_context(self, *, game_id: UUID, import_job_id: UUID) -> None:
        if self._session.get(GameModel, game_id) is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_GAME_NOT_FOUND",
                "The selected operational review game does not exist.",
                details={"gameId": str(game_id)},
            )
        job = self._session.get(JobModel, import_job_id)
        if job is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_JOB_NOT_FOUND",
                "The selected operational review import job does not exist.",
                details={"importJobId": str(import_job_id)},
            )
        if (
            job.game_id != game_id
            or job.job_type is not JobType.IMPORT
            or job.input_payload.get("import_kind") != "image_directory"
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_CONTEXT_INVALID",
                "The import job does not belong to this game or image workflow.",
            )

    def expected_layout_count(self, game_id: UUID) -> int | None:
        value = self._session.scalar(
            select(GameModel.expected_layout_count).where(GameModel.id == game_id)
        )
        return None if value is None else int(value)

    def dataset_completeness(self, game_id: UUID) -> ImageDatasetCompleteness | None:
        expected = self.expected_layout_count(game_id)
        if expected is None:
            return None
        accepted = (
            select(ImageLayoutStagingRowModel.sequence_number.label("sequence_number"))
            .join(JobModel, JobModel.id == ImageLayoutStagingRowModel.import_job_id)
            .where(JobModel.game_id == game_id)
        ).subquery()
        accepted_count = int(self._session.scalar(select(func.count()).select_from(accepted)) or 0)
        in_range = (
            select(accepted.c.sequence_number)
            .where(accepted.c.sequence_number.between(1, expected))
            .distinct()
        ).subquery()
        unique_count = int(self._session.scalar(select(func.count()).select_from(in_range)) or 0)
        out_of_range_count = int(
            self._session.scalar(
                select(func.count(func.distinct(accepted.c.sequence_number))).where(
                    ~accepted.c.sequence_number.between(1, expected)
                )
            )
            or 0
        )
        duplicate_groups = (
            select(accepted.c.sequence_number)
            .where(accepted.c.sequence_number.between(1, expected))
            .group_by(accepted.c.sequence_number)
            .having(func.count() > 1)
        ).subquery()
        duplicate_count = int(
            self._session.scalar(select(func.count()).select_from(duplicate_groups)) or 0
        )
        ordered = select(
            in_range.c.sequence_number,
            func.lag(in_range.c.sequence_number)
            .over(order_by=in_range.c.sequence_number)
            .label("previous_number"),
        ).subquery()
        gap_rows = self._session.execute(
            select(ordered.c.sequence_number, ordered.c.previous_number)
            .where(
                or_(
                    and_(ordered.c.previous_number.is_(None), ordered.c.sequence_number > 1),
                    ordered.c.sequence_number - ordered.c.previous_number > 1,
                )
            )
            .order_by(ordered.c.sequence_number)
            .limit(101)
        ).all()
        missing: list[int] = []
        for number, previous in gap_rows:
            start = 1 if previous is None else int(previous) + 1
            stop = int(number)
            missing.extend(range(start, min(stop, start + 100 - len(missing))))
            if len(missing) >= 100:
                break
        maximum = self._session.scalar(select(func.max(in_range.c.sequence_number)))
        if len(missing) < 100 and (maximum is None or int(maximum) < expected):
            start = 1 if maximum is None else int(maximum) + 1
            missing.extend(range(start, min(expected + 1, start + 100 - len(missing))))
        override_latest = (
            select(
                ImageSequenceSourceOverrideEventModel.sequence_number,
                func.max(ImageSequenceSourceOverrideEventModel.revision).label("revision"),
            )
            .where(ImageSequenceSourceOverrideEventModel.game_id == game_id)
            .group_by(ImageSequenceSourceOverrideEventModel.sequence_number)
        ).subquery()
        override_count = int(
            self._session.scalar(
                select(func.count())
                .select_from(ImageSequenceSourceOverrideEventModel)
                .join(
                    override_latest,
                    and_(
                        override_latest.c.sequence_number
                        == ImageSequenceSourceOverrideEventModel.sequence_number,
                        override_latest.c.revision
                        == ImageSequenceSourceOverrideEventModel.revision,
                    ),
                )
                .where(
                    ImageSequenceSourceOverrideEventModel.game_id == game_id,
                    ImageSequenceSourceOverrideEventModel.selected_review_item_id.is_not(None),
                )
            )
            or 0
        )
        missing_count = expected - unique_count
        return ImageDatasetCompleteness(
            game_id=game_id,
            expected_layout_count=expected,
            accepted_board_count=accepted_count,
            unique_sequence_count=unique_count,
            missing_sequence_count=missing_count,
            duplicate_sequence_count=duplicate_count,
            out_of_range_sequence_count=out_of_range_count,
            missing_sequence_numbers=tuple(missing),
            missing_sequence_numbers_truncated=missing_count > len(missing),
            manual_override_count=override_count,
        )

    def sequence_source_selection(
        self,
        game_id: UUID,
        sequence_number: int,
    ) -> ImageSequenceSourceSelection | None:
        rows = self._session.execute(
            select(
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImageLayoutStagingRowModel,
            )
            .join(
                ImageLayoutStagingRowModel,
                ImageLayoutStagingRowModel.review_item_id == ImageReviewItemModel.id,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == ImageLayoutStagingRowModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                ImageLayoutStagingRowModel.sequence_number == sequence_number,
                ImageReviewItemModel.status.in_(("accepted", "corrected")),
            )
            .order_by(
                RecognizedBoardModel.board_confidence.desc(),
                RecognizedBoardModel.sequence_confidence.desc(),
                (SourceImageModel.width * SourceImageModel.height).desc(),
                ImageReviewItemModel.id,
            )
        ).all()
        if not rows:
            return None
        override = self._session.scalar(
            select(ImageSequenceSourceOverrideEventModel)
            .where(
                ImageSequenceSourceOverrideEventModel.game_id == game_id,
                ImageSequenceSourceOverrideEventModel.sequence_number == sequence_number,
            )
            .order_by(ImageSequenceSourceOverrideEventModel.revision.desc())
            .limit(1)
        )
        manual_id = None if override is None else override.selected_review_item_id
        selected_id = manual_id or rows[0][0].id
        candidates = tuple(
            ImageSequenceSourceCandidate(
                review_item_id=item.id,
                recognized_board_id=board.id,
                import_job_id=staging.import_job_id,
                sequence_number=sequence_number,
                source_checksum_sha256=source.checksum_sha256,
                source_relative_path=source.relative_path,
                width=source.width,
                height=source.height,
                board_confidence=board.board_confidence,
                sequence_confidence=board.sequence_confidence,
                geometry_revision=board.geometry_revision,
                automatic_rank=index,
                quality_score=round(
                    board.board_confidence * 0.45
                    + board.sequence_confidence * 0.35
                    + min(source.width * source.height / 2_073_600, 1.0) * 0.20,
                    6,
                ),
                selected=item.id == selected_id,
                selected_manually=manual_id is not None and item.id == manual_id,
            )
            for index, (item, board, source, staging) in enumerate(rows, start=1)
        )
        return ImageSequenceSourceSelection(
            game_id=game_id,
            sequence_number=sequence_number,
            candidates=candidates,
            manual_override_review_item_id=manual_id,
            override_revision=0 if override is None else override.revision,
        )

    def append_source_override(
        self,
        *,
        game_id: UUID,
        sequence_number: int,
        review_item_id: UUID | None,
        selected_by: str,
    ) -> None:
        latest = self._session.scalar(
            select(func.max(ImageSequenceSourceOverrideEventModel.revision)).where(
                ImageSequenceSourceOverrideEventModel.game_id == game_id,
                ImageSequenceSourceOverrideEventModel.sequence_number == sequence_number,
            )
        )
        self._session.add(
            ImageSequenceSourceOverrideEventModel(
                game_id=game_id,
                sequence_number=sequence_number,
                revision=int(latest or 0) + 1,
                selected_review_item_id=review_item_id,
                selected_by=selected_by,
                created_at=datetime.now(UTC),
            )
        )
        self._session.flush()

    def list_items(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        after_key: OrderKey | None,
        before_key: OrderKey | None,
        sequence_number: int | None,
        resume_at_first_pending: bool,
        limit: int,
    ) -> ImageReviewPage:
        self.require_context(game_id=game_id, import_job_id=import_job_id)
        order = _order_expressions(view)
        query = _base_query(game_id, import_job_id, view)
        cursor = after_key or before_key
        if cursor is not None and not self._cursor_exists(
            query,
            order,
            cursor,
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_CURSOR_STALE",
                "The operational review cursor is stale; reload the queue.",
            )
        if after_key is not None:
            query = query.where(_lexicographic_after(order, after_key))
        elif before_key is not None:
            query = query.where(_lexicographic_before(order, before_key))
        if sequence_number is not None:
            query = query.where(_sequence_expression(view) == sequence_number)
        elif resume_at_first_pending:
            pending_row = (
                self._session.execute(
                    _base_query(game_id, import_job_id, ImageReviewView.PENDING)
                    .order_by(*[expression.asc() for expression in order])
                    .limit(1)
                )
                .tuples()
                .first()
            )
            if pending_row is not None:
                pending_item, pending_board, _source, pending_association, _job = pending_row
                pending_key: OrderKey = (
                    0,
                    pending_association.order_index,
                    pending_board.position_index,
                    str(pending_item.id),
                )
                query = query.where(
                    or_(
                        _lexicographic_equal(order, pending_key),
                        _lexicographic_after(order, pending_key),
                    )
                )
        descending = before_key is not None
        ordered = [expression.desc() if descending else expression.asc() for expression in order]
        rows = list(self._session.execute(query.order_by(*ordered).limit(limit + 1)).tuples().all())
        extra = len(rows) > limit
        visible_rows = rows[:limit]
        if descending:
            visible_rows.reverse()
        items = self._items_from_rows(visible_rows)
        if items:
            has_previous = (
                extra
                if descending
                else self._exists_before(
                    game_id,
                    import_job_id,
                    view,
                    items[0].cursor_key_for(view),
                )
            )
            has_next = (
                self._exists_after(
                    game_id,
                    import_job_id,
                    view,
                    items[-1].cursor_key_for(view),
                )
                if descending
                else extra
            )
        else:
            has_previous = False
            has_next = False
        return ImageReviewPage(
            items=items,
            counts=self._counts(game_id, import_job_id),
            has_previous=has_previous,
            has_next=has_next,
        )

    def get_item(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        for_update: bool = False,
    ) -> ImageReviewItem | None:
        query = _base_query(game_id, import_job_id, None).where(
            ImageReviewItemModel.id == review_item_id
        )
        if for_update:
            query = query.with_for_update()
        row = self._session.execute(query).tuples().one_or_none()
        if row is None:
            return None
        return self._items_from_rows([row])[0]

    def active_symbol_codes(self, game_id: UUID) -> Sequence[str]:
        return tuple(
            self._session.scalars(
                select(SymbolModel.code)
                .where(
                    SymbolModel.game_id == game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
                .order_by(SymbolModel.display_order, SymbolModel.code)
            ).all()
        )

    def has_active_heavy_job(self, *, game_id: UUID) -> bool:
        return bool(
            self._session.scalar(
                select(
                    select(JobModel.id)
                    .where(
                        JobModel.game_id == game_id,
                        JobModel.status.in_((JobStatus.CREATED, JobStatus.PROCESSING)),
                    )
                    .exists()
                )
            )
        )

    def lock_verified_snapshot(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> tuple[Sequence[ImageReviewItem], ImageReviewCounts]:
        self.require_context(game_id=game_id, import_job_id=import_job_id)
        self._session.scalar(
            select(JobModel)
            .where(JobModel.id == import_job_id, JobModel.game_id == game_id)
            .with_for_update()
        )
        rows = list(
            self._session.execute(
                _base_query(game_id, import_job_id, None)
                .order_by(
                    ImageImportJobFileModel.order_index,
                    RecognizedBoardModel.position_index,
                    ImageReviewItemModel.id,
                )
                .with_for_update()
            )
            .tuples()
            .all()
        )
        return self._items_from_rows(rows), self._counts(game_id, import_job_id)

    def lock_cumulative_verified_snapshot(
        self,
        *,
        game_id: UUID,
    ) -> Sequence[ImageReviewItem]:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise ImageReviewNotFoundError(
                "VERIFIED_TRAINING_COHORT_GAME_NOT_FOUND",
                "The selected training cohort game does not exist.",
            )
        rows = list(
            self._session.execute(
                _base_game_query(game_id)
                .order_by(
                    JobModel.id,
                    ImageImportJobFileModel.order_index,
                    RecognizedBoardModel.position_index,
                    ImageReviewItemModel.id,
                )
                .with_for_update()
            )
            .tuples()
            .all()
        )
        return self._items_from_rows(rows)

    def lock_model_prediction_target(
        self,
        *,
        review_item_id: UUID,
        expected_resolution_revision: int,
        expected_geometry_revision: int,
    ) -> None:
        row = self._session.execute(
            select(ImageReviewItemModel, RecognizedBoardModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(ImageReviewItemModel.id == review_item_id)
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise ImageReviewNotFoundError(
                "MODEL_PREDICTION_TARGET_NOT_FOUND",
                "The automatic prediction target does not exist.",
            )
        item, board = row
        require_pending_model_prediction_target(
            status=item.status,
            resolution_revision=item.resolution_revision,
            expected_resolution_revision=expected_resolution_revision,
            geometry_revision=board.geometry_revision,
            expected_geometry_revision=expected_geometry_revision,
        )

    def save_resolution(
        self,
        *,
        review_item_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        expected_revision: int,
        resolution: ValidatedImageReviewResolution,
        resolved_at: datetime,
    ) -> tuple[ImageReviewItem, ImageReviewResolutionEvent, bool]:
        locked = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            for_update=True,
        )
        if locked is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_ITEM_NOT_FOUND",
                "The operational review item does not exist in this game and job.",
            )
        prior = self._session.scalar(
            select(ImageReviewResolutionEventModel).where(
                ImageReviewResolutionEventModel.review_item_id == review_item_id,
                ImageReviewResolutionEventModel.idempotency_key == idempotency_key,
            )
        )
        if prior is not None:
            if prior.command_sha256 != resolution.command_sha256:
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already represents another command.",
                )
            return locked, _event_from_record(prior), False
        if locked.resolution_revision != expected_revision:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_REVISION_CONFLICT",
                "The operational review item changed after it was loaded.",
            )
        active_codes = self.active_symbol_codes(game_id)
        revalidated = validate_image_review_resolution(
            item=locked,
            action=resolution.action,
            sequence_number=resolution.sequence_number,
            geometry_revision=resolution.geometry_revision,
            cells=resolution.cells,
            rejection_reason=resolution.rejection_reason,
            resolved_by=resolution.resolved_by,
            active_symbol_codes=active_codes,
        )
        if revalidated.command_sha256 != resolution.command_sha256:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COMMAND_CHANGED",
                "The review command changed before persistence.",
            )
        item_record = self._session.get(
            ImageReviewItemModel,
            review_item_id,
            with_for_update=True,
        )
        board = self._session.get(
            RecognizedBoardModel,
            locked.recognized_board_id,
            with_for_update=True,
        )
        source = (
            self._session.get(SourceImageModel, board.source_image_id, with_for_update=True)
            if board is not None
            else None
        )
        if item_record is None or board is None or source is None:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_PROJECTION_MISSING",
                "The operational review projection is incomplete.",
            )
        revision = item_record.resolution_revision + 1
        event_record = ImageReviewResolutionEventModel(
            review_item_id=review_item_id,
            revision=revision,
            idempotency_key=idempotency_key,
            action=resolution.action.value,
            command_sha256=resolution.command_sha256,
            resolved_value=dict(resolution.resolved_value),
            resolved_by=resolution.resolved_by,
            created_at=resolved_at,
        )
        self._session.add(event_record)
        item_record.status = resolution.action.value
        item_record.resolved_value = dict(resolution.resolved_value)
        item_record.resolved_by = resolution.resolved_by
        item_record.resolved_at = resolved_at
        item_record.resolution_revision = revision
        board.status = resolution.action.value
        if resolution.action.value == "rejected":
            self._session.execute(
                delete(ImageLayoutStagingRowModel).where(
                    ImageLayoutStagingRowModel.import_job_id == import_job_id,
                    ImageLayoutStagingRowModel.recognized_board_id == board.id,
                )
            )
        else:
            symbols = tuple(cell.symbol_code for cell in resolution.cells)
            mobile_codes = self._mobile_codes(game_id, symbols)
            staging = self._session.get(
                ImageLayoutStagingRowModel,
                {
                    "import_job_id": import_job_id,
                    "recognized_board_id": board.id,
                },
                with_for_update=True,
            )
            if staging is None:
                self._session.add(
                    ImageLayoutStagingRowModel(
                        import_job_id=import_job_id,
                        recognized_board_id=board.id,
                        review_item_id=review_item_id,
                        sequence_number=cast(int, resolution.sequence_number),
                        cells=mobile_codes,
                        created_at=resolved_at,
                    )
                )
            elif staging.review_item_id != review_item_id:
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_STAGING_CONFLICT",
                    "The recognized board belongs to another staging decision.",
                )
            else:
                staging.sequence_number = cast(int, resolution.sequence_number)
                staging.cells = mobile_codes
        self._session.flush()
        pending_count = self._session.scalar(
            select(func.count())
            .select_from(ImageReviewItemModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(
                RecognizedBoardModel.source_image_id == source.id,
                ImageReviewItemModel.status == "pending",
            )
        )
        if int(pending_count or 0) > 0:
            source.status = "waiting_for_review"
        else:
            accepted_count = self._session.scalar(
                select(func.count())
                .select_from(ImageReviewItemModel)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .where(
                    RecognizedBoardModel.source_image_id == source.id,
                    ImageReviewItemModel.status.in_(("accepted", "corrected")),
                )
            )
            source.status = "accepted" if int(accepted_count or 0) else "rejected"
        source.processed_at = resolved_at
        self._session.flush()
        updated = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        if updated is None:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_PROJECTION_MISSING",
                "The resolved review projection cannot be reloaded.",
            )
        return updated, _event_from_record(event_record), True

    def list_resolution_events(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> Sequence[ImageReviewResolutionEvent]:
        if (
            self.get_item(
                review_item_id,
                game_id=game_id,
                import_job_id=import_job_id,
            )
            is None
        ):
            return ()
        return tuple(
            _event_from_record(record)
            for record in self._session.scalars(
                select(ImageReviewResolutionEventModel)
                .where(ImageReviewResolutionEventModel.review_item_id == review_item_id)
                .order_by(ImageReviewResolutionEventModel.revision)
            ).all()
        )

    def get_geometry_revision_by_idempotency(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
    ) -> ImageReviewGeometryRevision | None:
        if (
            self.get_item(
                review_item_id,
                game_id=game_id,
                import_job_id=import_job_id,
            )
            is None
        ):
            return None
        record = self._session.scalar(
            select(ImageBoardGeometryRevisionModel).where(
                ImageBoardGeometryRevisionModel.review_item_id == review_item_id,
                ImageBoardGeometryRevisionModel.idempotency_key == idempotency_key,
            )
        )
        return _geometry_revision_from_record(record) if record is not None else None

    def save_geometry_revision(
        self,
        *,
        review_item_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        command: ValidatedImageReviewGeometryCommand,
        artifacts: ImageReviewGeometryArtifacts,
        created_at: datetime,
    ) -> tuple[ImageReviewItem, ImageReviewGeometryRevision, bool]:
        locked = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            for_update=True,
        )
        if locked is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_ITEM_NOT_FOUND",
                "The operational review item does not exist in this game and job.",
            )
        prior = self._session.scalar(
            select(ImageBoardGeometryRevisionModel).where(
                ImageBoardGeometryRevisionModel.review_item_id == review_item_id,
                ImageBoardGeometryRevisionModel.idempotency_key == idempotency_key,
            )
        )
        if prior is not None:
            if prior.command_sha256 != command.command_sha256:
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT",
                    "The geometry idempotency key already represents another command.",
                )
            return locked, _geometry_revision_from_record(prior), False
        if (
            locked.geometry_revision != command.expected_geometry_revision
            or locked.resolution_revision != command.expected_resolution_revision
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT",
                "The review item changed before corrected geometry was persisted.",
            )
        if len(artifacts.cells) != 15 or [
            (cell.row_index, cell.column_index) for cell in artifacts.cells
        ] != [(row, column) for row in range(3) for column in range(5)]:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_GEOMETRY_CELLS_INVALID",
                "Corrected geometry must contain exactly 15 row-major crop artifacts.",
            )
        item_record = self._session.get(
            ImageReviewItemModel,
            review_item_id,
            with_for_update=True,
        )
        board = self._session.get(
            RecognizedBoardModel,
            locked.recognized_board_id,
            with_for_update=True,
        )
        if item_record is None or board is None:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_PROJECTION_MISSING",
                "The corrected geometry projection is incomplete.",
            )
        revision = board.geometry_revision + 1
        record = ImageBoardGeometryRevisionModel(
            review_item_id=review_item_id,
            recognized_board_id=board.id,
            revision=revision,
            idempotency_key=idempotency_key,
            command_sha256=command.command_sha256,
            corners=[{"x": point.x, "y": point.y} for point in command.corners],
            geometry=dict(artifacts.geometry),
            board_relative_path=artifacts.board_relative_path,
            board_checksum_sha256=artifacts.board_checksum_sha256,
            cropper_version=artifacts.cropper_version,
            crop_artifacts=[
                {
                    "columnIndex": cell.column_index,
                    "cropChecksumSha256": cell.crop_checksum_sha256,
                    "cropRelativePath": cell.crop_relative_path,
                    "rowIndex": cell.row_index,
                }
                for cell in artifacts.cells
            ],
            corrected_by=command.corrected_by,
            created_at=created_at,
        )
        self._session.add(record)
        previous_status = item_record.status
        item_record.status = "pending"
        item_record.resolved_value = cast(Any, null())
        item_record.resolved_by = None
        item_record.resolved_at = None
        item_record.resolution_revision += 1
        board.geometry_revision = revision
        board.board_geometry = dict(artifacts.geometry)
        board.board_relative_path = artifacts.board_relative_path
        board.board_checksum_sha256 = artifacts.board_checksum_sha256
        board.status = "pending_review"
        self._session.execute(
            delete(ImageLayoutStagingRowModel).where(
                ImageLayoutStagingRowModel.import_job_id == import_job_id,
                ImageLayoutStagingRowModel.recognized_board_id == board.id,
            )
        )
        self._session.add(
            ImageReviewResolutionEventModel(
                review_item_id=review_item_id,
                revision=item_record.resolution_revision,
                idempotency_key=uuid5(
                    NAMESPACE_URL,
                    f"image-review-geometry-reopen:{idempotency_key}",
                ),
                action="reopened",
                command_sha256=command.command_sha256,
                resolved_value={
                    "action": "reopened",
                    "geometryRevision": revision,
                    "previousStatus": previous_status,
                },
                resolved_by=command.corrected_by,
                created_at=created_at,
            )
        )
        source = self._session.get(
            SourceImageModel,
            board.source_image_id,
            with_for_update=True,
        )
        if source is not None:
            source.status = "waiting_for_review"
            source.processed_at = created_at
        self._session.flush()
        updated = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        if updated is None:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_PROJECTION_MISSING",
                "The corrected geometry projection cannot be reloaded.",
            )
        return updated, _geometry_revision_from_record(record), True

    def _mobile_codes(self, game_id: UUID, symbol_codes: Sequence[str]) -> list[int]:
        records = self._session.scalars(
            select(SymbolModel).where(
                SymbolModel.game_id == game_id,
                SymbolModel.code.in_(set(symbol_codes)),
                SymbolModel.status == SymbolStatus.ACTIVE,
            )
        ).all()
        by_code = {record.code: record.mobile_code for record in records}
        if set(by_code) != set(symbol_codes):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_SYMBOL_INVALID",
                "Every reviewed symbol must be active in the selected game.",
            )
        return [by_code[code] for code in symbol_codes]

    def _items_from_rows(self, rows: Sequence[ReviewRow]) -> tuple[ImageReviewItem, ...]:
        board_ids = [board.id for _item, board, _source, _association, _job in rows]
        observations_by_board: dict[UUID, list[CellObservationModel]] = defaultdict(list)
        if board_ids:
            observations = self._session.scalars(
                select(CellObservationModel)
                .where(CellObservationModel.recognized_board_id.in_(board_ids))
                .order_by(
                    CellObservationModel.recognized_board_id,
                    CellObservationModel.row_index,
                    CellObservationModel.column_index,
                )
            ).all()
            for observation in observations:
                observations_by_board[observation.recognized_board_id].append(observation)
        revisions_by_board: dict[UUID, ImageBoardGeometryRevisionModel] = {}
        if board_ids:
            for revision in self._session.scalars(
                select(ImageBoardGeometryRevisionModel)
                .where(ImageBoardGeometryRevisionModel.recognized_board_id.in_(board_ids))
                .order_by(
                    ImageBoardGeometryRevisionModel.recognized_board_id,
                    ImageBoardGeometryRevisionModel.revision,
                )
            ).all():
                revisions_by_board[revision.recognized_board_id] = revision
        return tuple(
            _item_from_records(
                item,
                board,
                source,
                association,
                job,
                observations_by_board[board.id],
                revisions_by_board.get(board.id),
            )
            for item, board, source, association, job in rows
        )

    def _counts(self, game_id: UUID, import_job_id: UUID) -> ImageReviewCounts:
        rows = self._session.execute(
            select(ImageReviewItemModel.status, func.count())
            .select_from(ImageReviewItemModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(
                SourceImageModel,
                SourceImageModel.id == RecognizedBoardModel.source_image_id,
            )
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.id == import_job_id,
                JobModel.game_id == game_id,
            )
            .group_by(ImageReviewItemModel.status)
        ).all()
        values = {status: int(count) for status, count in rows}
        return ImageReviewCounts(
            pending=values.get("pending", 0),
            accepted=values.get("accepted", 0),
            corrected=values.get("corrected", 0),
            rejected=values.get("rejected", 0),
        )

    def _cursor_exists(
        self,
        query: Any,
        order: tuple[ColumnElement[object], ...],
        key: OrderKey,
    ) -> bool:
        statement = query.where(_lexicographic_equal(order, key))
        return self._session.execute(statement.limit(1)).first() is not None

    def _exists_before(
        self,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        key: OrderKey,
    ) -> bool:
        order = _order_expressions(view)
        return (
            self._session.execute(
                _base_query(game_id, import_job_id, view)
                .where(_lexicographic_before(order, key))
                .limit(1)
            ).first()
            is not None
        )

    def _exists_after(
        self,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        key: OrderKey,
    ) -> bool:
        order = _order_expressions(view)
        return (
            self._session.execute(
                _base_query(game_id, import_job_id, view)
                .where(_lexicographic_after(order, key))
                .limit(1)
            ).first()
            is not None
        )


def _base_query(
    game_id: UUID,
    import_job_id: UUID,
    view: ImageReviewView | None,
) -> Any:
    query = (
        select(
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            ImageImportJobFileModel,
            JobModel,
        )
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .join(
            ImageImportJobFileModel,
            and_(
                ImageImportJobFileModel.job_id == SourceImageModel.import_job_id,
                ImageImportJobFileModel.file_execution_key == SourceImageModel.file_execution_key,
            ),
        )
        .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
        .where(JobModel.id == import_job_id, JobModel.game_id == game_id)
    )
    if view is ImageReviewView.PENDING:
        query = query.where(ImageReviewItemModel.status == "pending")
    elif view is ImageReviewView.COMPLETED:
        query = query.where(ImageReviewItemModel.status.in_(("accepted", "corrected")))
    return query


def _base_game_query(game_id: UUID) -> Any:
    return (
        select(
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            ImageImportJobFileModel,
            JobModel,
        )
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .join(
            ImageImportJobFileModel,
            and_(
                ImageImportJobFileModel.job_id == SourceImageModel.import_job_id,
                ImageImportJobFileModel.file_execution_key == SourceImageModel.file_execution_key,
            ),
        )
        .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
        .where(JobModel.game_id == game_id)
    )


def _sequence_expression(view: ImageReviewView) -> ColumnElement[int]:
    if view is ImageReviewView.PENDING:
        return cast(ColumnElement[int], RecognizedBoardModel.sequence_number)
    resolved_sequence = cast(
        ColumnElement[int],
        ImageReviewItemModel.resolved_value["sequenceNumber"].astext.cast(BigInteger),
    )
    if view is ImageReviewView.ALL:
        return cast(
            ColumnElement[int],
            func.coalesce(resolved_sequence, RecognizedBoardModel.sequence_number),
        )
    return resolved_sequence


def _order_expressions(view: ImageReviewView) -> tuple[ColumnElement[object], ...]:
    sequence: ColumnElement[object] = cast(
        ColumnElement[object],
        (
            literal(0)
            if view in {ImageReviewView.PENDING, ImageReviewView.ALL}
            else _sequence_expression(view)
        ),
    )
    return (
        sequence,
        cast(ColumnElement[object], ImageImportJobFileModel.order_index),
        cast(ColumnElement[object], RecognizedBoardModel.position_index),
        cast(ColumnElement[object], ImageReviewItemModel.id.cast(String)),
    )


def _lexicographic_after(
    expressions: Sequence[ColumnElement[object]],
    key: OrderKey,
) -> ColumnElement[bool]:
    return or_(
        expressions[0] > key[0],
        and_(expressions[0] == key[0], expressions[1] > key[1]),
        and_(
            expressions[0] == key[0],
            expressions[1] == key[1],
            expressions[2] > key[2],
        ),
        and_(
            expressions[0] == key[0],
            expressions[1] == key[1],
            expressions[2] == key[2],
            expressions[3] > key[3],
        ),
    )


def _lexicographic_before(
    expressions: Sequence[ColumnElement[object]],
    key: OrderKey,
) -> ColumnElement[bool]:
    return or_(
        expressions[0] < key[0],
        and_(expressions[0] == key[0], expressions[1] < key[1]),
        and_(
            expressions[0] == key[0],
            expressions[1] == key[1],
            expressions[2] < key[2],
        ),
        and_(
            expressions[0] == key[0],
            expressions[1] == key[1],
            expressions[2] == key[2],
            expressions[3] < key[3],
        ),
    )


def _lexicographic_equal(
    expressions: Sequence[ColumnElement[object]],
    key: OrderKey,
) -> ColumnElement[bool]:
    return and_(*(expression == value for expression, value in zip(expressions, key, strict=True)))


def _item_from_records(
    item: ImageReviewItemModel,
    board: RecognizedBoardModel,
    source: SourceImageModel,
    association: ImageImportJobFileModel,
    job: JobModel,
    observations: Sequence[CellObservationModel],
    geometry_revision: ImageBoardGeometryRevisionModel | None,
) -> ImageReviewItem:
    if len(observations) != 15:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_CELL_COUNT_INVALID",
            "The operational review item must contain exactly 15 cell observations.",
        )
    resolved = cast(Mapping[str, object] | None, item.resolved_value)
    raw_symbols = resolved.get("symbolCodes") if resolved is not None else None
    resolved_symbols = (
        tuple(cast(Sequence[str], raw_symbols))
        if isinstance(raw_symbols, list | tuple) and len(raw_symbols) == 15
        else None
    )
    cells: list[ImageReviewCell] = []
    revised_cells: dict[int, Mapping[str, object]] = {}
    if board.geometry_revision > 0:
        if (
            geometry_revision is None
            or geometry_revision.revision != board.geometry_revision
            or len(geometry_revision.crop_artifacts) != 15
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID",
                "The current manual geometry revision is incomplete.",
            )
        revised_cells = {
            cast(int, raw["rowIndex"]) * 5 + cast(int, raw["columnIndex"]): raw
            for raw in geometry_revision.crop_artifacts
        }
        if set(revised_cells) != set(range(15)):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID",
                "The current manual geometry cells are not complete row-major crops.",
            )
    for index, observation in enumerate(observations):
        expected_index = observation.row_index * 5 + observation.column_index
        if expected_index != index:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_CELL_ORDER_INVALID",
                "The operational review cells are not a complete row-major board.",
            )
        prediction = cast(Mapping[str, object], observation.prediction)
        symbol_code = prediction.get("symbolCode")
        confidence = prediction.get("confidence")
        raw_alternatives = prediction.get("alternatives")
        if (
            not isinstance(symbol_code, str)
            or not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not isinstance(raw_alternatives, list | tuple)
            or not 1 <= len(raw_alternatives) <= MAX_IMAGE_REVIEW_ALTERNATIVES
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_PREDICTION_INVALID",
                "A cell prediction does not match the operational review contract.",
            )
        alternatives: list[ImageReviewAlternative] = []
        for raw in raw_alternatives:
            if not isinstance(raw, Mapping):
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_PREDICTION_INVALID",
                    "A symbol alternative is invalid.",
                )
            alternative_code = raw.get("symbolCode")
            alternative_confidence = raw.get("confidence")
            if (
                not isinstance(alternative_code, str)
                or not isinstance(alternative_confidence, int | float)
                or isinstance(alternative_confidence, bool)
            ):
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_PREDICTION_INVALID",
                    "A symbol alternative is invalid.",
                )
            alternatives.append(
                ImageReviewAlternative(
                    symbol_code=alternative_code,
                    confidence=float(alternative_confidence),
                )
            )
        revised = revised_cells.get(index)
        crop_relative_path = (
            cast(str, revised["cropRelativePath"])
            if revised is not None
            else observation.crop_relative_path
        )
        crop_checksum_sha256 = (
            cast(str, revised["cropChecksumSha256"])
            if revised is not None
            else observation.crop_checksum_sha256
        )
        cropper_version = (
            geometry_revision.cropper_version
            if geometry_revision is not None and revised is not None
            else observation.cropper_version
        )
        sample_id = crop_sample_id(
            recognized_board_id=board.id,
            row_index=observation.row_index,
            column_index=observation.column_index,
            cropper_version=cropper_version,
            crop_relative_path=crop_relative_path,
            crop_checksum_sha256=crop_checksum_sha256,
        )
        cells.append(
            ImageReviewCell(
                observation_id=observation.id,
                cell_index=index,
                row_index=observation.row_index,
                column_index=observation.column_index,
                crop_sample_id=sample_id,
                crop_relative_path=crop_relative_path,
                crop_checksum_sha256=crop_checksum_sha256,
                predicted_symbol_code=symbol_code,
                confidence=float(confidence),
                alternatives=tuple(alternatives),
                current_symbol_code=(
                    resolved_symbols[index] if resolved_symbols is not None else symbol_code
                ),
            )
        )
    queue_sequence = (
        cast(int, resolved["sequenceNumber"])
        if resolved is not None and isinstance(resolved.get("sequenceNumber"), int)
        else None
    )
    return ImageReviewItem(
        id=item.id,
        game_id=cast(UUID, job.game_id),
        import_job_id=source.import_job_id,
        source_image_id=source.id,
        recognized_board_id=board.id,
        status=item.status,
        source_order_index=association.order_index,
        position_index=board.position_index,
        queue_sequence_number=queue_sequence,
        suggested_sequence_number=board.sequence_number,
        source_relative_path=source.relative_path,
        source_checksum_sha256=source.checksum_sha256,
        board_relative_path=board.board_relative_path,
        board_checksum_sha256=board.board_checksum_sha256,
        geometry_revision=board.geometry_revision,
        geometry=dict(board.board_geometry),
        pipeline_fingerprint=board.pipeline_fingerprint,
        cells=tuple(cells),
        resolved_value=dict(resolved) if resolved is not None else None,
        resolved_by=item.resolved_by,
        resolved_at=item.resolved_at,
        resolution_revision=item.resolution_revision,
        created_at=item.created_at,
    )


def _event_from_record(
    record: ImageReviewResolutionEventModel,
) -> ImageReviewResolutionEvent:
    return ImageReviewResolutionEvent(
        id=record.id,
        review_item_id=record.review_item_id,
        revision=record.revision,
        idempotency_key=record.idempotency_key,
        action=record.action,
        command_sha256=record.command_sha256,
        resolved_value=dict(record.resolved_value),
        resolved_by=record.resolved_by,
        created_at=record.created_at,
    )


def _geometry_revision_from_record(
    record: ImageBoardGeometryRevisionModel,
) -> ImageReviewGeometryRevision:
    try:
        corners = cast(
            tuple[
                ImageReviewGeometryPoint,
                ImageReviewGeometryPoint,
                ImageReviewGeometryPoint,
                ImageReviewGeometryPoint,
            ],
            tuple(ImageReviewGeometryPoint(x=point["x"], y=point["y"]) for point in record.corners),
        )
        cells = tuple(
            ImageReviewGeometryCellArtifact(
                row_index=cast(int, cell["rowIndex"]),
                column_index=cast(int, cell["columnIndex"]),
                crop_relative_path=cast(str, cell["cropRelativePath"]),
                crop_checksum_sha256=cast(str, cell["cropChecksumSha256"]),
            )
            for cell in record.crop_artifacts
        )
    except (KeyError, TypeError) as error:
        raise ImageReviewConflictError(
            "IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID",
            "A persisted geometry revision is invalid.",
        ) from error
    return ImageReviewGeometryRevision(
        id=record.id,
        review_item_id=record.review_item_id,
        recognized_board_id=record.recognized_board_id,
        revision=record.revision,
        idempotency_key=record.idempotency_key,
        command_sha256=record.command_sha256,
        corners=corners,
        board_relative_path=record.board_relative_path,
        board_checksum_sha256=record.board_checksum_sha256,
        cropper_version=record.cropper_version,
        cells=cells,
        corrected_by=record.corrected_by,
        created_at=record.created_at,
    )


__all__ = ["SqlAlchemyOperationalImageReviewRepository"]
