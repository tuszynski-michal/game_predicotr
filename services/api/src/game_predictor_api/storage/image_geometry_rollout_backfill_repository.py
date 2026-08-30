"""Durable, bounded validation of v0.10 virtual-geometry provenance."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import NoReturn, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from game_predictor_api.application.image_geometry_rollout import (
    ImageGeometryBackfillStatus,
    ImageGeometryRolloutStart,
    ImageGeometryRolloutStatus,
)
from game_predictor_api.domain.image_geometry_v2 import SOURCE_COORDINATE_SPACE
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_reviews import canonical_image_review_bytes
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.job_repository import job_from_record, job_record_from_domain
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryRevisionModel,
    ImageGeometryRolloutStateModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_JOB_STATUSES = (JobStatus.CREATED, JobStatus.PROCESSING)
_WORKFLOW = "image_geometry_rollout_backfill"
_ACTOR = "system:image-geometry-rollout-backfill"
_MAX_BATCH_SIZE = 200


class ImageGeometryRolloutBackfillError(ImageGridReviewError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        source_image_id: UUID | None = None,
    ) -> None:
        super().__init__(code, message)
        self.source_image_id = source_image_id


@dataclass(frozen=True, slots=True)
class ImageGeometryRolloutBackfillStep:
    processed_source_count: int
    virtual_source_count: int
    last_source_image_id: UUID | None
    has_more: bool


class SqlAlchemyImageGeometryRolloutBackfillRepository:
    """Validate metadata only; legacy files and image bytes remain untouched."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def status(self, game_id: UUID) -> ImageGeometryRolloutStatus:
        self._require_game(game_id, lock=False)
        state = self._require_state(game_id, lock=False)
        return self._status(game_id, state=state)

    def start(self, game_id: UUID) -> ImageGeometryRolloutStart:
        self._require_game(game_id, lock=True)
        state = self._require_state(game_id, lock=True)
        active = self._active_job(game_id)
        if active is not None:
            self._bind_validation_job(state=state, job=active)
            return ImageGeometryRolloutStart(
                rollout=self._status(game_id, state=state),
                job=job_from_record(active),
                created=False,
            )
        if (
            state.backfill_status == "ready"
            and not self._has_source_after_cursor(state)
            and self._validation_binding_is_current(state)
        ):
            return ImageGeometryRolloutStart(
                rollout=self._status(game_id, state=state),
                job=None,
                created=False,
            )
        generation = (
            int(
                self._session.scalar(
                    select(func.count(JobModel.id)).where(
                        JobModel.game_id == game_id,
                        JobModel.job_type == JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
                    )
                )
                or 0
            )
            + 1
        )
        state.backfill_status = "processing"
        state.failure_code = None
        state.failure_message = None
        state.validation_rollout_revision = None
        state.validation_input_checksum_sha256 = None
        state.validation_job_id = None
        state.updated_by = _ACTOR
        input_payload: dict[str, object] = {
            "schema_version": 2,
            "workflow": _WORKFLOW,
            "generation": generation,
            "rollout_revision": state.revision,
            "geometry_mode": state.geometry_mode,
            "cell_asset_mode": state.cell_asset_mode,
        }
        job = create_job(
            JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
            game_id=game_id,
            input_payload=input_payload,
        )
        record = job_record_from_domain(job)
        self._session.add(record)
        self._session.flush()
        self._bind_validation_job(state=state, job=record)
        return ImageGeometryRolloutStart(
            rollout=self._status(game_id, state=state),
            job=job_from_record(record),
            created=True,
        )

    def validate_next_batch(
        self,
        game_id: UUID,
        *,
        limit: int = 100,
    ) -> ImageGeometryRolloutBackfillStep:
        if limit < 1 or limit > _MAX_BATCH_SIZE:
            raise ValueError(f"limit must be between 1 and {_MAX_BATCH_SIZE}")
        state = self._require_state(game_id, lock=True)
        if state.backfill_status != "processing":
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_NOT_PROCESSING",
                "Start the virtual-geometry rollout validation before processing a batch.",
            )
        statement = (
            select(SourceImageModel)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(JobModel.game_id == game_id)
            .order_by(SourceImageModel.created_at, SourceImageModel.id)
            .limit(limit + 1)
        )
        cursor = self._cursor(state)
        if cursor is not None:
            statement = statement.where(
                or_(
                    SourceImageModel.created_at > cursor.created_at,
                    and_(
                        SourceImageModel.created_at == cursor.created_at,
                        SourceImageModel.id > cursor.id,
                    ),
                )
            )
        sources = tuple(self._session.scalars(statement))
        batch = sources[:limit]
        virtual_count = 0
        for source in batch:
            virtual_count += int(self._validate_source(game_id=game_id, source=source))
        if batch:
            state.last_source_image_id = batch[-1].id
            state.updated_by = _ACTOR
            self._session.flush()
        return ImageGeometryRolloutBackfillStep(
            processed_source_count=len(batch),
            virtual_source_count=virtual_count,
            last_source_image_id=(state.last_source_image_id if batch else None),
            has_more=len(sources) > limit,
        )

    def finalize(self, game_id: UUID) -> ImageGeometryRolloutStatus:
        state = self._require_state(game_id, lock=True)
        if state.backfill_status != "processing":
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_NOT_PROCESSING",
                "The virtual-geometry rollout validation is not processing.",
            )
        if self._has_source_after_cursor(state):
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_NOT_STABLE",
                "New source images appeared before rollout validation finalized.",
            )
        self._require_current_validation_binding(state)
        state.backfill_status = "ready"
        state.failure_code = None
        state.failure_message = None
        state.updated_by = _ACTOR
        self._session.flush()
        return self._status(game_id, state=state)

    def fail(
        self,
        game_id: UUID,
        *,
        error: ImageGeometryRolloutBackfillError,
    ) -> None:
        state = self._require_state(game_id, lock=True)
        state.backfill_status = "failed"
        state.failure_code = error.code
        suffix = "" if error.source_image_id is None else f" [source={error.source_image_id}]"
        state.failure_message = f"{error.message}{suffix}"[:1000]
        state.updated_by = _ACTOR

    def _validate_source(self, *, game_id: UUID, source: SourceImageModel) -> bool:
        boards = tuple(
            self._session.scalars(
                select(RecognizedBoardModel)
                .where(RecognizedBoardModel.source_image_id == source.id)
                .order_by(RecognizedBoardModel.position_index)
            )
        )
        virtual_boards = tuple(board for board in boards if board.asset_mode == "virtual_source")
        if not virtual_boards:
            return False
        if (
            source.coordinate_space != SOURCE_COORDINATE_SPACE
            or source.raw_width is None
            or source.raw_height is None
            or source.oriented_width is None
            or source.oriented_height is None
            or not source.normalization_adapter_version
            or not _is_sha256(source.normalized_pixel_checksum_sha256)
        ):
            self._invalid_source(
                source,
                "IMAGE_GEOMETRY_ROLLOUT_SOURCE_PROVENANCE_INVALID",
                "A virtual source has incomplete canonical coordinate metadata.",
            )
        for board in virtual_boards:
            geometry = self._session.get(
                ImageSourceGeometryRevisionModel,
                board.source_geometry_revision_id,
            )
            if (
                geometry is None
                or geometry.game_id != game_id
                or geometry.source_image_id != source.id
                or geometry.source_checksum_sha256 != source.checksum_sha256
                or geometry.normalized_pixel_checksum_sha256
                != source.normalized_pixel_checksum_sha256
                or board.position_index not in geometry.active_board_slots
                or board.geometry_checksum_sha256 != geometry.geometry_checksum_sha256
            ):
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_SOURCE_GEOMETRY_INVALID",
                    "A virtual board is not bound to a complete source geometry revision.",
                )
            topology_count = int(board.grid_rows or 3) * int(board.grid_columns or 5)
            observations = tuple(
                self._session.scalars(
                    select(CellObservationModel)
                    .where(CellObservationModel.recognized_board_id == board.id)
                    .order_by(CellObservationModel.row_index, CellObservationModel.column_index)
                )
            )
            expected_coordinates = tuple(
                (row_index, column_index)
                for row_index in range(int(board.grid_rows or 3))
                for column_index in range(int(board.grid_columns or 5))
            )
            if (
                len(observations) != topology_count
                or tuple(
                    (int(observation.row_index), int(observation.column_index))
                    for observation in observations
                )
                != expected_coordinates
                or any(
                    observation.asset_mode != "virtual_source"
                    or observation.source_geometry_revision_id != geometry.id
                    or observation.crop_relative_path is not None
                    or not _is_sha256(observation.logical_cell_key)
                    or not isinstance(observation.render_spec, dict)
                    or not _is_sha256(observation.render_spec_checksum_sha256)
                    or not _is_sha256(observation.rendered_pixel_checksum_sha256)
                    or observation.crop_checksum_sha256
                    != observation.rendered_pixel_checksum_sha256
                    for observation in observations
                )
            ):
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_CELL_PROVENANCE_INVALID",
                    "A virtual board does not contain every checksum-bound virtual cell.",
                )
            if board.geometry_revision > 0:
                revision = self._session.scalar(
                    select(ImageBoardGeometryRevisionModel).where(
                        ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                        ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
                    )
                )
                if (
                    revision is None
                    or revision.asset_mode != "virtual_source"
                    or revision.source_geometry_revision_id != geometry.id
                    or revision.geometry_checksum_sha256 != geometry.geometry_checksum_sha256
                    or revision.board_relative_path is not None
                    or revision.board_checksum_sha256 is not None
                    or revision.crop_artifacts is not None
                    or not isinstance(revision.virtual_render_spec, dict)
                    or not _is_sha256(revision.virtual_render_spec_checksum_sha256)
                ):
                    self._invalid_source(
                        source,
                        "IMAGE_GEOMETRY_ROLLOUT_MANUAL_REVISION_INVALID",
                        "A current virtual manual geometry revision is incomplete.",
                    )
            review_cells = tuple(
                self._session.scalars(
                    select(ImageSymbolReviewCellModel)
                    .where(ImageSymbolReviewCellModel.recognized_board_id == board.id)
                    .order_by(ImageSymbolReviewCellModel.cell_index)
                )
            )
            if review_cells and (
                len(review_cells) != topology_count
                or tuple(int(cell.cell_index) for cell in review_cells)
                != tuple(range(topology_count))
                or any(
                    cell.asset_mode != "virtual_source"
                    or cell.source_geometry_revision_id != geometry.id
                    or cell.crop_relative_path is not None
                    or not _is_sha256(cell.logical_cell_key)
                    or not isinstance(cell.render_spec, dict)
                    or not _is_sha256(cell.render_spec_checksum_sha256)
                    or not _is_sha256(cell.rendered_pixel_checksum_sha256)
                    or cell.crop_checksum_sha256 != cell.rendered_pixel_checksum_sha256
                    for cell in review_cells
                )
            ):
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_REVIEW_PROVENANCE_INVALID",
                    "The current symbol review projection does not match virtual source cells.",
                )
            review_item_id = self._session.scalar(
                select(ImageReviewItemModel.id).where(
                    ImageReviewItemModel.recognized_board_id == board.id
                )
            )
            if review_item_id is None:
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_REVIEW_ITEM_MISSING",
                    "A virtual board does not have an operational review item.",
                )
            SqlAlchemyBoardSearchProjectionRepository(self._session).sync_review_item(
                review_item_id
            )
        return True

    def _status(
        self,
        game_id: UUID,
        *,
        state: ImageGeometryRolloutStateModel,
    ) -> ImageGeometryRolloutStatus:
        source_count = int(
            self._session.scalar(
                select(func.count(SourceImageModel.id))
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .where(JobModel.game_id == game_id)
            )
            or 0
        )
        virtual_source_count = int(
            self._session.scalar(
                select(func.count(func.distinct(RecognizedBoardModel.source_image_id)))
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .where(
                    JobModel.game_id == game_id,
                    RecognizedBoardModel.asset_mode == "virtual_source",
                )
            )
            or 0
        )
        cursor = self._cursor(state)
        processed = 0
        if cursor is not None:
            processed = int(
                self._session.scalar(
                    select(func.count(SourceImageModel.id))
                    .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                    .where(
                        JobModel.game_id == game_id,
                        or_(
                            SourceImageModel.created_at < cursor.created_at,
                            and_(
                                SourceImageModel.created_at == cursor.created_at,
                                SourceImageModel.id <= cursor.id,
                            ),
                        ),
                    )
                )
                or 0
            )
        active = self._active_job(game_id)
        return ImageGeometryRolloutStatus(
            game_id=game_id,
            geometry_mode=state.geometry_mode,
            cell_asset_mode=state.cell_asset_mode,
            rollout_revision=state.revision,
            backfill_status=cast(ImageGeometryBackfillStatus, state.backfill_status),
            source_count=source_count,
            processed_source_count=processed,
            virtual_source_count=virtual_source_count,
            active_job_id=None if active is None else active.id,
            last_source_image_id=state.last_source_image_id,
            failure_code=state.failure_code,
            failure_message=state.failure_message,
        )

    def _has_source_after_cursor(self, state: ImageGeometryRolloutStateModel) -> bool:
        cursor = self._cursor(state)
        statement = (
            select(SourceImageModel.id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(JobModel.game_id == state.game_id)
            .limit(1)
        )
        if cursor is not None:
            statement = statement.where(
                or_(
                    SourceImageModel.created_at > cursor.created_at,
                    and_(
                        SourceImageModel.created_at == cursor.created_at,
                        SourceImageModel.id > cursor.id,
                    ),
                )
            )
        return self._session.scalar(statement) is not None

    def _cursor(
        self,
        state: ImageGeometryRolloutStateModel,
    ) -> SourceImageModel | None:
        if state.last_source_image_id is None:
            return None
        cursor = self._session.get(SourceImageModel, state.last_source_image_id)
        if (
            cursor is None
            or self._session.scalar(
                select(JobModel.id).where(
                    JobModel.id == cursor.import_job_id,
                    JobModel.game_id == state.game_id,
                )
            )
            is None
        ):
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_CURSOR_INVALID",
                "The persisted virtual-geometry rollout cursor no longer exists in this game.",
            )
        return cursor

    def _active_job(self, game_id: UUID) -> JobModel | None:
        return self._session.scalar(
            select(JobModel)
            .where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
                JobModel.status.in_(_ACTIVE_JOB_STATUSES),
            )
            .order_by(JobModel.created_at.desc(), JobModel.id.desc())
            .limit(1)
        )

    def _bind_validation_job(
        self,
        *,
        state: ImageGeometryRolloutStateModel,
        job: JobModel,
    ) -> None:
        checksum = _validation_input_checksum(job.input_payload)
        if state.validation_job_id is not None and (
            state.validation_job_id != job.id
            or state.validation_rollout_revision != state.revision
            or state.validation_input_checksum_sha256 != checksum
        ):
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_VALIDATION_BINDING_CONFLICT",
                "The rollout state is already bound to a different validation snapshot.",
            )
        state.validation_rollout_revision = state.revision
        state.validation_input_checksum_sha256 = checksum
        state.validation_job_id = job.id
        state.updated_by = _ACTOR

    def _require_current_validation_binding(
        self,
        state: ImageGeometryRolloutStateModel,
    ) -> None:
        if state.validation_job_id is None or not _is_sha256(
            state.validation_input_checksum_sha256
        ):
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_VALIDATION_BINDING_MISSING",
                "The rollout cannot become ready without an exact validation snapshot.",
            )
        if not self._validation_binding_is_current(state):
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_VALIDATION_BINDING_STALE",
                "The rollout validation job no longer matches the current policy revision.",
            )

    def _validation_binding_is_current(
        self,
        state: ImageGeometryRolloutStateModel,
    ) -> bool:
        if (
            state.validation_job_id is None
            or state.validation_rollout_revision != state.revision
            or not _is_sha256(state.validation_input_checksum_sha256)
        ):
            return False
        job = self._session.get(JobModel, state.validation_job_id)
        return bool(
            job is not None
            and job.game_id == state.game_id
            and job.job_type == JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL
            and _validation_input_checksum(job.input_payload)
            == state.validation_input_checksum_sha256
            and job.input_payload.get("rollout_revision") == state.revision
        )

    def _require_game(self, game_id: UUID, *, lock: bool) -> None:
        statement = select(GameModel.id).where(GameModel.id == game_id)
        if lock:
            statement = statement.with_for_update()
        if self._session.scalar(statement) is None:
            raise ImageGridReviewError("GAME_NOT_FOUND", "The selected game does not exist.")

    def _require_state(
        self,
        game_id: UUID,
        *,
        lock: bool,
    ) -> ImageGeometryRolloutStateModel:
        statement = select(ImageGeometryRolloutStateModel).where(
            ImageGeometryRolloutStateModel.game_id == game_id
        )
        if lock:
            statement = statement.with_for_update()
        state = self._session.scalar(statement)
        if state is None:
            raise ImageGridReviewError(
                "IMAGE_GEOMETRY_ROLLOUT_STATE_MISSING",
                "Run the bounded rollout-state backfill before validating this game.",
            )
        return state

    @staticmethod
    def _invalid_source(
        source: SourceImageModel,
        code: str,
        message: str,
    ) -> NoReturn:
        raise ImageGeometryRolloutBackfillError(
            code,
            message,
            source_image_id=source.id,
        )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _validation_input_checksum(input_payload: object) -> str:
    if not isinstance(input_payload, dict):
        raise ImageGeometryRolloutBackfillError(
            "IMAGE_GEOMETRY_ROLLOUT_VALIDATION_INPUT_INVALID",
            "The rollout validation job input is not an immutable object.",
        )
    return hashlib.sha256(canonical_image_review_bytes(input_payload)).hexdigest()


__all__ = [
    "ImageGeometryRolloutBackfillError",
    "ImageGeometryRolloutBackfillStep",
    "SqlAlchemyImageGeometryRolloutBackfillRepository",
]
