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
    PendingGridReinferencePreview,
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
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageReviewQueueItemModel,
    ImageReviewQueueStateModel,
    ImageReviewResolutionEventModel,
    ImageSequenceAlternativeModel,
    ImageSequenceCanonicalModel,
    ImageSequenceSourceOverrideEventModel,
    ImageSymbolPredictionRevisionModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)

ReviewRow = tuple[
    ImageReviewItemModel,
    RecognizedBoardModel,
    SourceImageModel,
    ImageReviewQueueItemModel,
    JobModel,
]
OrderKey = tuple[int, int, str]


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
            select(ImageSequenceCanonicalModel.sequence_number.label("sequence_number")).where(
                ImageSequenceCanonicalModel.game_id == game_id
            )
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
        canonical = self._session.scalar(
            select(ImageSequenceCanonicalModel).where(
                ImageSequenceCanonicalModel.game_id == game_id,
                ImageSequenceCanonicalModel.sequence_number == sequence_number,
            )
        )
        manual_id = None if override is None else override.selected_review_item_id
        selected_id = (
            canonical.review_item_id if canonical is not None else manual_id or rows[0][0].id
        )
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
        expected_queue_version: int | None,
        sequence_number: int | None,
        resume_at_first_pending: bool,
        limit: int,
    ) -> ImageReviewPage:
        self.require_context(game_id=game_id, import_job_id=import_job_id)
        queue_version, _counts = self._queue_snapshot(import_job_id)
        if expected_queue_version is not None and expected_queue_version != queue_version:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_CURSOR_STALE",
                "The operational review queue topology changed; reload the queue.",
            )
        order = _queue_order_expressions()
        query = _base_query(game_id, import_job_id, view)
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
                pending_item, _pending_board, _source, pending_queue_item, _job = pending_row
                pending_key: OrderKey = (
                    pending_queue_item.source_order_index,
                    pending_queue_item.position_index,
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
                    items[0].queue_order_key,
                )
            )
            has_next = (
                self._exists_after(
                    game_id,
                    import_job_id,
                    view,
                    items[-1].queue_order_key,
                )
                if descending
                else extra
            )
        else:
            has_previous = False
            has_next = False
        final_queue_version, final_counts = self._queue_snapshot(import_job_id)
        if final_queue_version != queue_version:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_CURSOR_STALE",
                "The operational review queue topology changed while it was read.",
            )
        return ImageReviewPage(
            items=items,
            counts=final_counts,
            has_previous=has_previous,
            has_next=has_next,
            queue_version=final_queue_version,
        )

    def list_canonical_pending_items(
        self,
        *,
        game_id: UUID,
        after_sequence: int | None,
        limit: int,
    ) -> ImageReviewPage:
        """Return one game-wide queue ordered by attested sequence number.

        A pending duplicate of an already canonical sequence is hidden here;
        it remains available through its job-local endpoint for audit purposes.
        ``None`` sequence values are retained at the end for manual range
        assignment.
        """

        query = _base_game_query(game_id).where(ImageReviewItemModel.status == "pending")
        canonical_exists = (
            select(ImageSequenceCanonicalModel.sequence_number)
            .where(
                ImageSequenceCanonicalModel.game_id == game_id,
                ImageSequenceCanonicalModel.sequence_number == RecognizedBoardModel.sequence_number,
            )
            .exists()
        )
        query = query.where(or_(RecognizedBoardModel.sequence_number.is_(None), ~canonical_exists))
        order = _sequence_order_expressions(ImageReviewView.PENDING)
        if after_sequence is not None:
            query = query.where(
                or_(
                    RecognizedBoardModel.sequence_number > after_sequence,
                    RecognizedBoardModel.sequence_number.is_(None),
                )
            )
        rows = list(
            self._session.execute(
                query.order_by(*[expression.asc() for expression in order]).limit(limit + 1)
            )
            .tuples()
            .all()
        )
        has_next = len(rows) > limit
        return ImageReviewPage(
            items=self._items_from_rows(rows[:limit]),
            counts=self._counts_for_game(game_id),
            has_previous=after_sequence is not None,
            has_next=has_next,
        )

    def canonical_pending_count(self, game_id: UUID) -> int:
        canonical_exists = (
            select(ImageSequenceCanonicalModel.sequence_number)
            .where(
                ImageSequenceCanonicalModel.game_id == game_id,
                ImageSequenceCanonicalModel.sequence_number == RecognizedBoardModel.sequence_number,
            )
            .exists()
        )
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(ImageReviewItemModel)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .where(
                    JobModel.game_id == game_id,
                    ImageReviewItemModel.status == "pending",
                    or_(RecognizedBoardModel.sequence_number.is_(None), ~canonical_exists),
                )
            )
            or 0
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
                        JobModel.job_type == JobType.SYMBOL_TRAINING,
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
                    ImageReviewQueueItemModel.source_order_index,
                    ImageReviewQueueItemModel.position_index,
                    ImageReviewQueueItemModel.review_item_id,
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
                    ImageReviewQueueItemModel.source_order_index,
                    ImageReviewQueueItemModel.position_index,
                    ImageReviewQueueItemModel.review_item_id,
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
            resolved_sequence = cast(int, resolution.sequence_number)
            canonical = self._session.scalar(
                select(ImageSequenceCanonicalModel)
                .where(
                    ImageSequenceCanonicalModel.game_id == game_id,
                    ImageSequenceCanonicalModel.sequence_number == resolved_sequence,
                )
                .with_for_update()
            )
            staging = self._session.get(
                ImageLayoutStagingRowModel,
                {
                    "import_job_id": import_job_id,
                    "recognized_board_id": board.id,
                },
                with_for_update=True,
            )
            if canonical is None or canonical.review_item_id == review_item_id:
                if staging is None:
                    self._session.add(
                        ImageLayoutStagingRowModel(
                            import_job_id=import_job_id,
                            recognized_board_id=board.id,
                            review_item_id=review_item_id,
                            sequence_number=resolved_sequence,
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
                    staging.sequence_number = resolved_sequence
                    staging.cells = mobile_codes
                if canonical is None:
                    self._session.add(
                        ImageSequenceCanonicalModel(
                            game_id=game_id,
                            sequence_number=resolved_sequence,
                            review_item_id=review_item_id,
                            recognized_board_id=board.id,
                            import_job_id=import_job_id,
                            source_image_id=source.id,
                            source_checksum_sha256=source.checksum_sha256,
                            board_checksum_sha256=board.board_checksum_sha256,
                            status=resolution.action.value,
                            resolution_revision=revision,
                            geometry_revision=board.geometry_revision,
                            created_at=resolved_at,
                            updated_at=resolved_at,
                        )
                    )
                else:
                    canonical.status = resolution.action.value
                    canonical.resolution_revision = revision
                    canonical.geometry_revision = board.geometry_revision
                    canonical.board_checksum_sha256 = board.board_checksum_sha256
                    canonical.updated_at = resolved_at
            else:
                alternative_exists = self._session.scalar(
                    select(ImageSequenceAlternativeModel.id).where(
                        ImageSequenceAlternativeModel.game_id == game_id,
                        ImageSequenceAlternativeModel.sequence_number == resolved_sequence,
                        ImageSequenceAlternativeModel.import_job_id == import_job_id,
                        ImageSequenceAlternativeModel.source_checksum_sha256
                        == source.checksum_sha256,
                    )
                )
                if alternative_exists is None:
                    self._session.add(
                        ImageSequenceAlternativeModel(
                            game_id=game_id,
                            sequence_number=resolved_sequence,
                            import_job_id=import_job_id,
                            source_checksum_sha256=source.checksum_sha256,
                            source_relative_path=source.relative_path,
                            reason="reused_accepted",
                        )
                    )
                if staging is not None:
                    self._session.delete(staging)
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
        revised_geometry = dict(artifacts.geometry)
        for retained_key in (
            "sequenceLabelQuad",
            "sourceContextBounds",
            "attestedRangeStart",
            "attestedRangeEnd",
            "sequenceSource",
        ):
            retained_value = board.board_geometry.get(retained_key)
            if retained_value is not None and retained_key not in revised_geometry:
                revised_geometry[retained_key] = retained_value
        record = ImageBoardGeometryRevisionModel(
            review_item_id=review_item_id,
            recognized_board_id=board.id,
            revision=revision,
            idempotency_key=idempotency_key,
            command_sha256=command.command_sha256,
            corners=[{"x": point.x, "y": point.y} for point in command.corners],
            geometry=revised_geometry,
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
        previous_resolved = cast(Mapping[str, object] | None, item_record.resolved_value)
        previous_sequence = (
            previous_resolved.get("sequenceNumber") if previous_resolved is not None else None
        )
        if (
            previous_status in {"accepted", "corrected"}
            and isinstance(previous_sequence, int)
            and not isinstance(previous_sequence, bool)
        ):
            self._session.execute(
                delete(ImageSequenceCanonicalModel).where(
                    ImageSequenceCanonicalModel.game_id == game_id,
                    ImageSequenceCanonicalModel.sequence_number == previous_sequence,
                    ImageSequenceCanonicalModel.review_item_id == review_item_id,
                )
            )
        item_record.status = "pending"
        item_record.resolved_value = cast(Any, null())
        item_record.resolved_by = None
        item_record.resolved_at = None
        item_record.resolution_revision += 1
        board.geometry_revision = revision
        board.board_geometry = revised_geometry
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
        board_ids = [board.id for _item, board, _source, _queue_item, _job in rows]
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
        predictions_by_item: dict[UUID, list[dict[str, object]]] = {}
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
            item_ids = [item.id for item, _board, _source, _queue_item, _job in rows]
            if item_ids:
                for symbol_revision in self._session.scalars(
                    select(ImageSymbolPredictionRevisionModel)
                    .where(ImageSymbolPredictionRevisionModel.review_item_id.in_(item_ids))
                    .order_by(
                        ImageSymbolPredictionRevisionModel.review_item_id,
                        ImageSymbolPredictionRevisionModel.created_at,
                    )
                ).all():
                    predictions_by_item[symbol_revision.review_item_id] = list(
                        symbol_revision.predictions
                    )
        return tuple(
            _item_from_records(
                item,
                board,
                source,
                queue_item,
                job,
                observations_by_board[board.id],
                revisions_by_board.get(board.id),
                predictions_by_item.get(item.id),
            )
            for item, board, source, queue_item, job in rows
        )

    def _counts(self, game_id: UUID, import_job_id: UUID) -> ImageReviewCounts:
        del game_id
        return self._queue_snapshot(import_job_id)[1]

    def _counts_for_game(self, game_id: UUID) -> ImageReviewCounts:
        totals = self._session.execute(
            select(
                func.coalesce(func.sum(ImageReviewQueueStateModel.pending_count), 0),
                func.coalesce(func.sum(ImageReviewQueueStateModel.accepted_count), 0),
                func.coalesce(func.sum(ImageReviewQueueStateModel.corrected_count), 0),
                func.coalesce(func.sum(ImageReviewQueueStateModel.rejected_count), 0),
            )
            .select_from(ImageReviewQueueStateModel)
            .join(JobModel, JobModel.id == ImageReviewQueueStateModel.import_job_id)
            .where(JobModel.game_id == game_id)
        ).one()
        return ImageReviewCounts(
            pending=int(totals[0]),
            accepted=int(totals[1]),
            corrected=int(totals[2]),
            rejected=int(totals[3]),
        )

    def _queue_snapshot(self, import_job_id: UUID) -> tuple[int, ImageReviewCounts]:
        state = self._session.scalar(
            select(ImageReviewQueueStateModel)
            .where(ImageReviewQueueStateModel.import_job_id == import_job_id)
            .execution_options(populate_existing=True)
        )
        if state is None:
            projected_count = int(
                self._session.scalar(
                    select(func.count())
                    .select_from(ImageReviewQueueItemModel)
                    .where(ImageReviewQueueItemModel.import_job_id == import_job_id)
                )
                or 0
            )
            if projected_count:
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_QUEUE_PROJECTION_INVALID",
                    "The operational review queue state is missing.",
                )
            return 0, ImageReviewCounts(pending=0, accepted=0, corrected=0, rejected=0)
        return state.queue_version, ImageReviewCounts(
            pending=state.pending_count,
            accepted=state.accepted_count,
            corrected=state.corrected_count,
            rejected=state.rejected_count,
        )

    def game_counts(self, game_id: UUID) -> ImageReviewCounts:
        """Return status counts across every import belonging to a game."""

        return self._counts_for_game(game_id)

    def pending_grid_reinference_preview(
        self,
        game_id: UUID,
        *,
        geometry_version: str,
        cropper_version: str,
        audit_report_checksum_sha256: str,
    ) -> PendingGridReinferencePreview:
        rows = self._session.execute(
            select(
                SourceImageModel.id,
                ImageReviewItemModel.status,
                RecognizedBoardModel.board_geometry,
            )
            .select_from(ImageReviewItemModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(JobModel.game_id == game_id)
        ).all()
        source_statuses: dict[UUID, set[str]] = defaultdict(set)
        pending_board_count = 0
        recalculable_board_count = 0
        current_v19_board_count = 0
        protected_board_count = 0
        for source_id, status, board_geometry in rows:
            source_statuses[source_id].add(str(status))
            if status == "pending":
                pending_board_count += 1
                if (
                    board_geometry.get("geometryVersion") == geometry_version
                    and board_geometry.get("cropperVersion") == cropper_version
                ):
                    current_v19_board_count += 1
                else:
                    recalculable_board_count += 1
            else:
                protected_board_count += 1
        pending_sources = sum("pending" in statuses for statuses in source_statuses.values())
        partial_sources = sum(
            "pending" in statuses and len(statuses) > 1 for statuses in source_statuses.values()
        )
        fully_resolved_sources = sum(
            "pending" not in statuses for statuses in source_statuses.values()
        )
        return PendingGridReinferencePreview(
            game_id=game_id,
            pending_board_count=pending_board_count,
            recalculable_board_count=recalculable_board_count,
            current_v19_board_count=current_v19_board_count,
            protected_board_count=protected_board_count,
            pending_source_count=pending_sources,
            partially_resolved_source_count=partial_sources,
            fully_resolved_source_count=fully_resolved_sources,
            geometry_version=geometry_version,
            cropper_version=cropper_version,
            audit_report_checksum_sha256=audit_report_checksum_sha256,
        )

    def _exists_before(
        self,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        key: OrderKey,
    ) -> bool:
        order = _queue_order_expressions()
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
        order = _queue_order_expressions()
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
            ImageReviewQueueItemModel,
            JobModel,
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
        .where(JobModel.id == import_job_id, JobModel.game_id == game_id)
    )
    if view is ImageReviewView.PENDING:
        query = query.where(ImageReviewQueueItemModel.status == "pending")
    elif view is ImageReviewView.COMPLETED:
        query = query.where(ImageReviewQueueItemModel.status.in_(("accepted", "corrected")))
    return query


def _base_game_query(game_id: UUID) -> Any:
    return (
        select(
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            ImageReviewQueueItemModel,
            JobModel,
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


def _sequence_order_expressions(
    view: ImageReviewView,
) -> tuple[ColumnElement[object], ...]:
    raw_sequence = _sequence_expression(view)
    sequence: ColumnElement[object] = cast(
        ColumnElement[object],
        func.coalesce(raw_sequence, literal(9223372036854775807)),
    )
    return (
        sequence,
        cast(ColumnElement[object], ImageReviewQueueItemModel.source_order_index),
        cast(ColumnElement[object], RecognizedBoardModel.position_index),
        cast(ColumnElement[object], ImageReviewItemModel.id.cast(String)),
    )


def _queue_order_expressions() -> tuple[ColumnElement[object], ...]:
    return (
        cast(ColumnElement[object], ImageReviewQueueItemModel.source_order_index),
        cast(ColumnElement[object], ImageReviewQueueItemModel.position_index),
        cast(ColumnElement[object], ImageReviewQueueItemModel.review_item_id.cast(String)),
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
    queue_item: ImageReviewQueueItemModel,
    job: JobModel,
    observations: Sequence[CellObservationModel],
    geometry_revision: ImageBoardGeometryRevisionModel | None,
    prediction_override: Sequence[Mapping[str, object]] | None = None,
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
        prediction = (
            prediction_override[index]
            if prediction_override is not None and len(prediction_override) == 15
            else cast(Mapping[str, object], observation.prediction)
        )
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
        source_order_index=queue_item.source_order_index,
        position_index=queue_item.position_index,
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
        decision_checksum_sha256=(
            cast(str, record.geometry["decisionChecksumSha256"])
            if isinstance(record.geometry.get("decisionChecksumSha256"), str)
            else None
        ),
        corners=corners,
        board_relative_path=record.board_relative_path,
        board_checksum_sha256=record.board_checksum_sha256,
        cropper_version=record.cropper_version,
        cells=cells,
        corrected_by=record.corrected_by,
        created_at=record.created_at,
    )


__all__ = ["SqlAlchemyOperationalImageReviewRepository"]
