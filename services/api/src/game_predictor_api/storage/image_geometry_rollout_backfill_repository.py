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
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    SEQUENCE_ATTESTATION_SCHEMA_VERSION,
    SOURCE_COORDINATE_SPACE,
    ImageGeometryContractError,
    board_topology_fingerprint_sha256,
    sequence_attestation_checksum_sha256,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_import_engine_policy import (
    ImageImportEnginePolicy,
    ImageImportEnginePolicyPreview,
    ImageImportEnginePolicySnapshot,
    engine_policy_preview_token,
    policy_from_rollout_modes,
    policy_rollout_modes,
)
from game_predictor_api.domain.image_reviews import canonical_image_review_bytes
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    AdditiveVirtualGeometryContractError,
    derive_v2_render_identity_from_legacy_spec,
    verification_outcome_value,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.job_repository import job_from_record, job_record_from_domain
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImageGeometryRolloutStateModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionModel,
    SourceImageModel,
    VerifiedTrainingCohortCellModel,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_JOB_STATUSES = (JobStatus.CREATED, JobStatus.PROCESSING)
_WORKFLOW = "image_geometry_rollout_backfill"
_ACTOR = "system:image-geometry-rollout-backfill"
_POLICY_ACTOR = "local-admin:image-import-engine-policy"
_MAX_BATCH_SIZE = 100


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
    source_revision_backfill_count: int = 0
    observation_backfill_count: int = 0
    review_cell_backfill_count: int = 0
    training_cell_backfill_count: int = 0


class SqlAlchemyImageGeometryRolloutBackfillRepository:
    """Validate metadata only; legacy files and image bytes remain untouched."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def status(self, game_id: UUID) -> ImageGeometryRolloutStatus:
        self._require_game(game_id, lock=False)
        state = self._require_state(game_id, lock=False)
        return self._status(game_id, state=state)

    def engine_policy(self, game_id: UUID) -> ImageImportEnginePolicySnapshot:
        self._require_game(game_id, lock=False)
        return self._engine_policy_snapshot(self._require_state(game_id, lock=False))

    def preview_engine_policy(
        self,
        game_id: UUID,
        *,
        target: ImageImportEnginePolicy,
    ) -> ImageImportEnginePolicyPreview:
        self._require_game(game_id, lock=False)
        state = self._require_state(game_id, lock=False)
        current = self._engine_policy_snapshot(state)
        target_geometry, target_assets = policy_rollout_modes(target)
        return ImageImportEnginePolicyPreview(
            current=current,
            target=ImageImportEnginePolicySnapshot(
                game_id=game_id,
                policy=target,
                geometry_mode=target_geometry,
                cell_asset_mode=target_assets,
                revision=current.revision + int(target is not current.policy),
            ),
            preview_token=engine_policy_preview_token(
                game_id=game_id,
                current_revision=current.revision,
                current_geometry_mode=current.geometry_mode,
                current_cell_asset_mode=current.cell_asset_mode,
                target_policy=target,
            ),
        )

    def apply_engine_policy(
        self,
        game_id: UUID,
        *,
        target: ImageImportEnginePolicy,
        expected_revision: int,
        preview_token: str,
    ) -> ImageImportEnginePolicySnapshot:
        self._require_game(game_id, lock=True)
        state = self._require_state(game_id, lock=True)
        current = self._engine_policy_snapshot(state)
        if current.revision != expected_revision:
            raise ImageGridReviewError(
                "IMAGE_ENGINE_POLICY_STALE",
                "The image engine policy changed after the preview was created.",
            )
        expected_token = engine_policy_preview_token(
            game_id=game_id,
            current_revision=current.revision,
            current_geometry_mode=current.geometry_mode,
            current_cell_asset_mode=current.cell_asset_mode,
            target_policy=target,
        )
        if preview_token != expected_token:
            raise ImageGridReviewError(
                "IMAGE_ENGINE_POLICY_PREVIEW_INVALID",
                "The image engine policy preview token is invalid.",
            )
        if current.policy is target:
            return current
        if self._active_job(game_id) is not None:
            raise ImageGridReviewError(
                "IMAGE_ENGINE_POLICY_ROLLOUT_BUSY",
                "Finish the active virtual-geometry validation before changing the engine.",
            )
        if target is ImageImportEnginePolicy.STRUCTURED_SHADOW:
            source_count = int(
                self._session.scalar(
                    select(func.count(SourceImageModel.id))
                    .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                    .where(JobModel.game_id == game_id)
                )
                or 0
            )
            if source_count > 0 and state.backfill_status != "ready":
                raise ImageGridReviewError(
                    "IMAGE_ENGINE_POLICY_VALIDATION_REQUIRED",
                    "Validate existing image provenance before enabling structured shadow.",
                )
        state.geometry_mode, state.cell_asset_mode = policy_rollout_modes(target)
        state.revision += 1
        state.backfill_status = "not_started"
        state.last_source_image_id = None
        state.failure_code = None
        state.failure_message = None
        state.validation_rollout_revision = None
        state.validation_input_checksum_sha256 = None
        state.validation_job_id = None
        state.updated_by = _POLICY_ACTOR
        self._session.flush()
        return self._engine_policy_snapshot(state)

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
            and not self._has_v2_backfill_candidates(game_id)
        ):
            return ImageGeometryRolloutStart(
                rollout=self._status(game_id, state=state),
                job=None,
                created=False,
            )
        if self._has_v2_backfill_candidates(game_id) and not self._has_source_after_cursor(state):
            state.last_source_image_id = None
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
            "schema_version": 3,
            "workflow": _WORKFLOW,
            "contract_backfill_version": "additive-virtual-geometry-v2-backfill-v1",
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
        source_revision_backfill_count = 0
        observation_backfill_count = 0
        review_cell_backfill_count = 0
        training_cell_backfill_count = 0
        for source in batch:
            is_virtual, counts = self._validate_source(game_id=game_id, source=source)
            virtual_count += int(is_virtual)
            source_revision_backfill_count += counts[0]
            observation_backfill_count += counts[1]
            review_cell_backfill_count += counts[2]
            training_cell_backfill_count += counts[3]
        if batch:
            state.last_source_image_id = batch[-1].id
            state.updated_by = _ACTOR
            self._session.flush()
        return ImageGeometryRolloutBackfillStep(
            processed_source_count=len(batch),
            virtual_source_count=virtual_count,
            last_source_image_id=(state.last_source_image_id if batch else None),
            has_more=len(sources) > limit,
            source_revision_backfill_count=source_revision_backfill_count,
            observation_backfill_count=observation_backfill_count,
            review_cell_backfill_count=review_cell_backfill_count,
            training_cell_backfill_count=training_cell_backfill_count,
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
        if self._has_v2_backfill_candidates(game_id):
            raise ImageGeometryRolloutBackfillError(
                "IMAGE_GEOMETRY_ROLLOUT_V2_BACKFILL_INCOMPLETE",
                "Additive virtual-geometry contracts remain incomplete or ambiguous.",
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

    def _validate_source(
        self,
        *,
        game_id: UUID,
        source: SourceImageModel,
    ) -> tuple[bool, tuple[int, int, int, int]]:
        source_revision_backfill_count = self._backfill_source_revisions(
            game_id=game_id,
            source=source,
        )
        review_cell_backfill_count = self._backfill_review_outcomes_for_source(
            source=source,
        )
        training_cell_backfill_count = self._backfill_training_cells_for_source(source=source)
        boards = tuple(
            self._session.scalars(
                select(RecognizedBoardModel)
                .join(
                    ImageBoardSearchFastDocumentModel,
                    ImageBoardSearchFastDocumentModel.recognized_board_id
                    == RecognizedBoardModel.id,
                )
                .where(RecognizedBoardModel.source_image_id == source.id)
                .order_by(RecognizedBoardModel.position_index)
            )
        )
        virtual_boards = tuple(board for board in boards if board.asset_mode == "virtual_source")
        if not virtual_boards:
            return False, (
                source_revision_backfill_count,
                0,
                review_cell_backfill_count,
                training_cell_backfill_count,
            )
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
        observation_backfill_count = 0
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
                or not _is_sha256(geometry.topology_fingerprint_sha256)
                or geometry.sequence_attestation_schema_version
                != SEQUENCE_ATTESTATION_SCHEMA_VERSION
                or not _is_sha256(geometry.sequence_attestation_checksum_sha256)
            ):
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_SOURCE_GEOMETRY_INVALID",
                    "A virtual board is not bound to a complete source geometry revision.",
                )
            topology = self._topology_for_geometry(source=source, geometry=geometry)
            if (
                int(board.grid_rows or 3) != topology.rows
                or int(board.grid_columns or 5) != topology.columns
            ):
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_TOPOLOGY_MISMATCH",
                    "A virtual board does not match its source geometry topology.",
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
            for observation in observations:
                observation_backfill_count += self._backfill_render_identity(
                    source=source,
                    geometry=geometry,
                    topology=topology,
                    board=board,
                    cell=observation,
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
                    or not _is_sha256(observation.logical_cell_key_v2)
                    or not _is_sha256(observation.render_identity_v2_sha256)
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
            for cell in review_cells:
                review_cell_backfill_count += self._backfill_render_identity(
                    source=source,
                    geometry=geometry,
                    topology=topology,
                    board=board,
                    cell=cell,
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
                    or not _is_sha256(cell.logical_cell_key_v2)
                    or not _is_sha256(cell.render_identity_v2_sha256)
                    or cell.verification_outcome is None
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
        return True, (
            source_revision_backfill_count,
            observation_backfill_count,
            review_cell_backfill_count,
            training_cell_backfill_count,
        )

    def _backfill_source_revisions(
        self,
        *,
        game_id: UUID,
        source: SourceImageModel,
    ) -> int:
        revisions = tuple(
            self._session.scalars(
                select(ImageSourceGeometryRevisionModel).where(
                    ImageSourceGeometryRevisionModel.game_id == game_id,
                    ImageSourceGeometryRevisionModel.source_image_id == source.id,
                )
            )
        )
        updated = 0
        for geometry in revisions:
            topology = self._topology_for_geometry(source=source, geometry=geometry)
            try:
                topology_fingerprint = board_topology_fingerprint_sha256(
                    topology_rules_version_id=geometry.topology_rules_version_id,
                    topology=topology,
                )
                attestation_checksum = sequence_attestation_checksum_sha256(
                    sequence_range_start=int(geometry.sequence_range_start),
                    sequence_range_end=int(geometry.sequence_range_end),
                    active_board_slots=tuple(int(value) for value in geometry.active_board_slots),
                )
            except ImageGeometryContractError as error:
                self._invalid_source(source, error.code, str(error))
            current = (
                geometry.topology_fingerprint_sha256,
                geometry.sequence_attestation_schema_version,
                geometry.sequence_attestation_checksum_sha256,
            )
            expected = (
                topology_fingerprint,
                SEQUENCE_ATTESTATION_SCHEMA_VERSION,
                attestation_checksum,
            )
            if current == (None, None, None):
                (
                    geometry.topology_fingerprint_sha256,
                    geometry.sequence_attestation_schema_version,
                    geometry.sequence_attestation_checksum_sha256,
                ) = expected
                updated += 1
            elif current != expected:
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_SOURCE_CONTRACT_V2_MISMATCH",
                    "A source geometry revision differs from its derived v2 contracts.",
                )
        return updated

    def _topology_for_geometry(
        self,
        *,
        source: SourceImageModel,
        geometry: ImageSourceGeometryRevisionModel,
    ) -> BoardTopology:
        rules = self._session.scalar(
            select(RulesVersionModel).where(
                RulesVersionModel.id == geometry.topology_rules_version_id,
                RulesVersionModel.game_id == geometry.game_id,
            )
        )
        if rules is None:
            self._invalid_source(
                source,
                "IMAGE_GEOMETRY_ROLLOUT_TOPOLOGY_MISSING",
                "A source geometry revision lacks its pinned topology rules.",
            )
        return BoardTopology(rows=int(rules.rows), columns=int(rules.columns))

    def _backfill_review_outcomes_for_source(self, *, source: SourceImageModel) -> int:
        cells = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
                )
                .join(
                    ImageBoardSearchFastDocumentModel,
                    ImageBoardSearchFastDocumentModel.review_item_id
                    == ImageSymbolReviewCellModel.review_item_id,
                )
                .where(
                    RecognizedBoardModel.source_image_id == source.id,
                    ImageBoardSearchFastDocumentModel.recognized_board_id
                    == ImageSymbolReviewCellModel.recognized_board_id,
                )
            )
        )
        updated = 0
        for cell in cells:
            try:
                verification = verification_outcome_value(
                    review_state=cell.review_state,
                    quality_issue=cell.quality_issue,
                    assigned_symbol_id=cell.assigned_symbol_id,
                    prediction_present=cell.prediction_symbol_code not in {None, "?"},
                    assignment_source=cell.assignment_source,
                )
            except AdditiveVirtualGeometryContractError as error:
                self._invalid_source(source, error.code, str(error))
            current = (cell.verification_outcome, cell.verified_symbol_id_v2)
            expected = (verification.outcome, verification.verified_symbol_id)
            if current == (None, None):
                cell.verification_outcome, cell.verified_symbol_id_v2 = expected
                updated += 1
            elif current != expected:
                self._invalid_source(
                    source,
                    "SYMBOL_VERIFICATION_OUTCOME_V2_MISMATCH",
                    "A persisted verification outcome differs from its current review state.",
                )
        return updated

    def _backfill_training_cells_for_source(self, *, source: SourceImageModel) -> int:
        cells = tuple(
            self._session.scalars(
                select(VerifiedTrainingCohortCellModel).where(
                    VerifiedTrainingCohortCellModel.source_image_id == source.id,
                    VerifiedTrainingCohortCellModel.asset_mode == "virtual_source",
                )
            )
        )
        updated = 0
        for cell in cells:
            board = self._session.get(RecognizedBoardModel, cell.recognized_board_id)
            geometry = (
                None
                if board is None
                or board.source_image_id != source.id
                or board.asset_mode != "virtual_source"
                else self._session.get(
                    ImageSourceGeometryRevisionModel,
                    cell.source_geometry_revision_id,
                )
            )
            if (
                board is None
                or geometry is None
                or geometry.source_image_id != source.id
                or geometry.source_checksum_sha256 != source.checksum_sha256
                or int(board.position_index) not in geometry.active_board_slots
            ):
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_TRAINING_PROVENANCE_INVALID",
                    "A verified virtual training cell lacks its immutable geometry context.",
                )
            topology = self._topology_for_geometry(source=source, geometry=geometry)
            row_index, column_index = topology.coordinates(int(cell.cell_index))
            updated += self._backfill_render_identity(
                source=source,
                geometry=geometry,
                topology=topology,
                board=board,
                cell=cell,
                row_index=row_index,
                column_index=column_index,
            )
            if not _is_sha256(cell.logical_cell_key_v2) or not _is_sha256(
                cell.render_identity_v2_sha256
            ):
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_TRAINING_PROVENANCE_INVALID",
                    "A verified virtual training cell lacks v2 render provenance.",
                )
        return updated

    def _backfill_render_identity(
        self,
        *,
        source: SourceImageModel,
        geometry: ImageSourceGeometryRevisionModel,
        topology: BoardTopology,
        board: RecognizedBoardModel,
        cell: CellObservationModel | ImageSymbolReviewCellModel | VerifiedTrainingCohortCellModel,
        row_index: int | None = None,
        column_index: int | None = None,
    ) -> int:
        if isinstance(cell, VerifiedTrainingCohortCellModel):
            if row_index is None or column_index is None:
                self._invalid_source(
                    source,
                    "IMAGE_GEOMETRY_ROLLOUT_TRAINING_PROVENANCE_INVALID",
                    "A verified training cell requires explicit topology coordinates.",
                )
            resolved_row = row_index
            resolved_column = column_index
        else:
            resolved_row = int(cell.row_index) if row_index is None else row_index
            resolved_column = int(cell.column_index) if column_index is None else column_index
        cell_index = (
            resolved_row * topology.columns + resolved_column
            if isinstance(cell, CellObservationModel)
            else int(cell.cell_index)
        )
        try:
            identity = derive_v2_render_identity_from_legacy_spec(
                cell.render_spec,
                import_job_id=source.import_job_id,
                file_execution_key=source.file_execution_key,
                topology_rules_version_id=geometry.topology_rules_version_id,
                topology=topology,
                board_slot=int(board.position_index),
                cell_index=cell_index,
                row_index=resolved_row,
                column_index=resolved_column,
            )
        except AdditiveVirtualGeometryContractError as error:
            self._invalid_source(source, error.code, str(error))
        current = (cell.logical_cell_key_v2, cell.render_identity_v2_sha256)
        expected = (identity.logical_cell_key_v2, identity.render_identity_v2_sha256)
        if current == (None, None):
            cell.logical_cell_key_v2, cell.render_identity_v2_sha256 = expected
            return 1
        if current != expected:
            self._invalid_source(
                source,
                "IMAGE_V2_RENDER_IDENTITY_PERSISTENCE_MISMATCH",
                "A persisted v2 render identity differs from immutable render inputs.",
            )
        return 0

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

    @staticmethod
    def _engine_policy_snapshot(
        state: ImageGeometryRolloutStateModel,
    ) -> ImageImportEnginePolicySnapshot:
        try:
            policy = policy_from_rollout_modes(state.geometry_mode, state.cell_asset_mode)
        except ValueError as error:
            raise ImageGridReviewError(
                "IMAGE_ENGINE_POLICY_UNSUPPORTED_STATE",
                "The game uses a rollout mode that is not available in safe engine settings.",
            ) from error
        return ImageImportEnginePolicySnapshot(
            game_id=state.game_id,
            policy=policy,
            geometry_mode=state.geometry_mode,
            cell_asset_mode=state.cell_asset_mode,
            revision=state.revision,
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

    def _has_v2_backfill_candidates(self, game_id: UUID) -> bool:
        source_revision = self._session.scalar(
            select(ImageSourceGeometryRevisionModel.id)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game_id,
                or_(
                    ImageSourceGeometryRevisionModel.topology_fingerprint_sha256.is_(None),
                    ImageSourceGeometryRevisionModel.sequence_attestation_schema_version.is_(None),
                    ImageSourceGeometryRevisionModel.sequence_attestation_checksum_sha256.is_(None),
                ),
            )
            .limit(1)
        )
        if source_revision is not None:
            return True
        observation = self._session.scalar(
            select(CellObservationModel.id)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .join(
                ImageBoardSearchFastDocumentModel,
                ImageBoardSearchFastDocumentModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .where(
                JobModel.game_id == game_id,
                CellObservationModel.asset_mode == "virtual_source",
                or_(
                    CellObservationModel.logical_cell_key_v2.is_(None),
                    CellObservationModel.render_identity_v2_sha256.is_(None),
                ),
            )
            .limit(1)
        )
        if observation is not None:
            return True
        review_cell = self._session.scalar(
            select(ImageSymbolReviewCellModel.id)
            .join(
                ImageBoardSearchFastDocumentModel,
                ImageBoardSearchFastDocumentModel.review_item_id
                == ImageSymbolReviewCellModel.review_item_id,
            )
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageBoardSearchFastDocumentModel.recognized_board_id
                == ImageSymbolReviewCellModel.recognized_board_id,
                or_(
                    ImageSymbolReviewCellModel.verification_outcome.is_(None),
                    and_(
                        ImageSymbolReviewCellModel.asset_mode == "virtual_source",
                        or_(
                            ImageSymbolReviewCellModel.logical_cell_key_v2.is_(None),
                            ImageSymbolReviewCellModel.render_identity_v2_sha256.is_(None),
                        ),
                    ),
                ),
            )
            .limit(1)
        )
        if review_cell is not None:
            return True
        training_cell = self._session.scalar(
            select(VerifiedTrainingCohortCellModel.id)
            .join(
                SourceImageModel,
                SourceImageModel.id == VerifiedTrainingCohortCellModel.source_image_id,
            )
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                VerifiedTrainingCohortCellModel.asset_mode == "virtual_source",
                or_(
                    VerifiedTrainingCohortCellModel.logical_cell_key_v2.is_(None),
                    VerifiedTrainingCohortCellModel.render_identity_v2_sha256.is_(None),
                ),
            )
            .limit(1)
        )
        return training_cell is not None

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
