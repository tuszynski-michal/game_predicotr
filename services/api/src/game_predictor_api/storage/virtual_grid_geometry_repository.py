"""Transactional metadata-only persistence for manual virtual board geometry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from game_predictor_api.application.virtual_grid_geometry import (
    PreparedVirtualGridGeometry,
    PreparedVirtualGridGeometrySource,
    VirtualGridGeometryCell,
    VirtualGridGeometryContext,
    VirtualGridGeometryRevision,
    VirtualGridGeometrySaveResult,
    VirtualGridGeometrySourceSaveResult,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import DirectCellRenderConfiguration
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.image_symbol_reviews import SymbolCellAssignmentSource
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    AdditiveVirtualGeometryContractError,
    optional_verification_outcome_value,
    verification_outcome_value,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_geometry_v2_repository import (
    ImageGeometryPersistenceError,
    SourceGeometryRevisionInput,
    SqlAlchemyImageSourceGeometryRepository,
    StoredSourceGeometryRevision,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
    acquire_image_review_sequence_locks,
    acquire_image_sequence_locks,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
    _apply_count_deltas,
    _CountedCellState,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryReviewEventModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImageGeometryRolloutStateModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    ImageSymbolReviewStateModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)
from game_predictor_api.storage.pending_sequence_ownership import (
    create_owned_pending_review_item,
)


class SqlAlchemyVirtualGridGeometryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def virtual_geometry_replay(
        self, *, context: VirtualGridGeometryContext, idempotency_key: UUID
    ) -> VirtualGridGeometryRevision | None:
        if context.review_item_id is None:
            return None
        prior = self._session.scalar(
            select(ImageBoardGeometryRevisionModel).where(
                ImageBoardGeometryRevisionModel.review_item_id == context.review_item_id,
                ImageBoardGeometryRevisionModel.recognized_board_id == context.recognized_board_id,
                ImageBoardGeometryRevisionModel.idempotency_key == idempotency_key,
            )
        )
        return None if prior is None else _revision_from_model(prior)

    def virtual_geometry_context(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID | None,
        pending_geometry_id: UUID | None,
    ) -> VirtualGridGeometryContext:
        if (review_item_id is None) == (pending_geometry_id is None):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SLOT_IDENTITY_INVALID",
                "A manual source slot requires exactly one current or deferred identity.",
            )
        if pending_geometry_id is not None:
            return self._pending_context(
                game_id=game_id,
                import_job_id=import_job_id,
                pending_geometry_id=pending_geometry_id,
                lock=False,
            )
        assert review_item_id is not None
        row = self._current_row(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
            lock=False,
        )
        return self._context_from_row(row)

    def save_virtual_geometry_revision(
        self,
        *,
        prepared: PreparedVirtualGridGeometry,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> VirtualGridGeometrySaveResult:
        context = prepared.context
        if prepared.command.geometry_qualification is not None:
            self._ensure_projection_state(context.game_id)
        if context.review_item_id is None or context.pending_geometry_id is not None:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_DEFERRED_SOURCE_REQUIRED",
                "A deferred board slot must be saved with every slot of its source image.",
            )
        acquire_image_review_sequence_locks(
            self._session,
            game_id=context.game_id,
            review_item_id=context.review_item_id,
            requested_sequence_number=None,
        )
        row = self._current_row(
            game_id=context.game_id,
            import_job_id=context.import_job_id,
            review_item_id=context.review_item_id,
            lock=True,
        )
        current = self._context_from_row(row)
        prior = self._session.scalar(
            select(ImageBoardGeometryRevisionModel).where(
                ImageBoardGeometryRevisionModel.review_item_id == context.review_item_id,
                ImageBoardGeometryRevisionModel.idempotency_key == idempotency_key,
            )
        )
        if prior is not None:
            if prior.command_sha256 != prepared.command.command_sha256:
                raise ImageGridReviewError(
                    "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT",
                    "The geometry idempotency key already represents another command.",
                )
            return VirtualGridGeometrySaveResult(
                revision=_revision_from_model(prior),
                created=False,
            )
        _require_same_context(current, context)
        availability_snapshot = self._availability_snapshot((prepared,))
        item, board, source, source_geometry, _rollout, _document = row
        if item.status == "superseded":
            raise ImageGridReviewError(
                "IMAGE_REVIEW_SUPERSEDED",
                "A superseded source cannot receive a manual virtual geometry revision.",
            )
        self._reopen_qualified_revision(prepared, idempotency_key, created_at)
        try:
            stored_source_geometry = SqlAlchemyImageSourceGeometryRepository(self._session).append(
                SourceGeometryRevisionInput(
                    game_id=context.game_id,
                    source_image_id=context.source_image_id,
                    topology_rules_version_id=context.topology_rules_version_id,
                    sequence_range_start=context.sequence_range_start,
                    sequence_range_end=context.sequence_range_end,
                    active_board_slots=context.active_board_slots,
                    source_checksum_sha256=context.source_checksum_sha256,
                    normalized_pixel_checksum_sha256=(context.normalized_pixel_checksum_sha256),
                    oriented_width=context.oriented_width,
                    oriented_height=context.oriented_height,
                    normalization_adapter_version=context.normalization_adapter_version,
                    global_initialization=(
                        None
                        if context.global_initialization is None
                        else dict(context.global_initialization)
                    ),
                    board_geometries=tuple(dict(value) for value in prepared.board_geometries),
                    engine_kind="manual_v1",
                    engine_version="manual-source-geometry-v1",
                    geometry_source="manual",
                    status="accepted",
                    geometry_checksum_sha256=prepared.source_geometry_checksum_sha256,
                    processing_time_ms=None,
                    warnings=(),
                    created_by=prepared.command.corrected_by,
                )
            )
        except ImageGeometryPersistenceError as error:
            raise ImageGridReviewError(error.code, str(error)) from error

        revision_number = board.geometry_revision + 1
        record = ImageBoardGeometryRevisionModel(
            review_item_id=item.id,
            recognized_board_id=board.id,
            revision=revision_number,
            idempotency_key=idempotency_key,
            command_sha256=prepared.command.command_sha256,
            corners=[{"x": point.x, "y": point.y} for point in prepared.command.corners],
            geometry=dict(prepared.board_geometry),
            asset_mode="virtual_source",
            source_geometry_revision_id=stored_source_geometry.id,
            geometry_checksum_sha256=prepared.source_geometry_checksum_sha256,
            virtual_render_spec=dict(prepared.virtual_render_spec),
            virtual_render_spec_checksum_sha256=(prepared.virtual_render_spec_checksum_sha256),
            board_relative_path=None,
            board_checksum_sha256=None,
            cropper_version=prepared.cropper_version,
            crop_artifacts=None,
            corrected_by=prepared.command.corrected_by,
            created_at=created_at,
        )
        self._session.add(record)
        previous_approved_geometry_revision = board.approved_geometry_revision
        board.geometry_revision = revision_number
        board.approved_geometry_revision = revision_number
        board.geometry_approved_at = created_at
        board.geometry_approved_by = prepared.command.corrected_by
        board.board_geometry = dict(prepared.board_geometry)
        _project_geometry_qualification(board, prepared.board_geometries[context.position_index])
        board.source_geometry_revision_id = stored_source_geometry.id
        board.geometry_checksum_sha256 = prepared.source_geometry_checksum_sha256
        board.geometry_engine_name = "manual_v1"
        board.geometry_engine_version = "manual-source-geometry-v1"
        self._session.add(
            ImageBoardGeometryReviewEventModel(
                review_item_id=item.id,
                recognized_board_id=board.id,
                geometry_revision=revision_number,
                grid_rows=context.topology.rows,
                grid_columns=context.topology.columns,
                board_checksum_sha256=prepared.source_geometry_checksum_sha256,
                action="geometry_saved",
                previous_approved_geometry_revision=previous_approved_geometry_revision,
                approved_geometry_revision=revision_number,
                actor=prepared.command.corrected_by,
                created_at=created_at,
            )
        )
        self._replace_current_cells(
            context=context,
            revision_number=revision_number,
            source_geometry_revision_id=stored_source_geometry.id,
            prepared=prepared,
            actor=prepared.command.corrected_by,
            changed_at=created_at,
        )
        source.processed_at = created_at
        self._session.flush()
        SymbolCellReviewWriteThroughCoordinator(self._session).synchronize_after_cell_mutation(
            game_id=context.game_id
        )
        self._reconcile_availability(availability_snapshot)
        return VirtualGridGeometrySaveResult(
            revision=_revision_from_model(record),
            created=True,
        )

    def save_virtual_source_geometry_revision(
        self,
        *,
        prepared: PreparedVirtualGridGeometrySource,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> VirtualGridGeometrySourceSaveResult:
        """Persist one complete source geometry revision and every board projection.

        The whole write stays inside the request transaction.  A concurrent
        reviewer may therefore either win before the exact snapshot is locked,
        producing a conflict, or observe all newly corrected slots together.
        """

        entries = tuple(
            sorted(
                prepared.entries,
                key=lambda entry: (entry.context.sequence_number, entry.context.position_index),
            )
        )
        if not entries:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_TARGETS_EMPTY",
                "Manual source geometry requires at least one board target.",
            )
        base_context = entries[0].context
        if any(entry.command.geometry_qualification is not None for entry in entries):
            self._ensure_projection_state(base_context.game_id)
        acquire_image_sequence_locks(
            self._session,
            game_id=base_context.game_id,
            sequence_numbers=[entry.context.sequence_number for entry in entries],
        )
        locked_rows: dict[UUID, tuple[Any, ...]] = {}
        locked_pending: dict[UUID, ImageBoardGeometryPendingModel] = {}
        current_contexts: list[VirtualGridGeometryContext] = []
        for entry in entries:
            context = entry.context
            if context.pending_geometry_id is not None:
                current = self._pending_context(
                    game_id=context.game_id,
                    import_job_id=context.import_job_id,
                    pending_geometry_id=context.pending_geometry_id,
                    lock=True,
                )
                pending = self._session.get(
                    ImageBoardGeometryPendingModel,
                    context.pending_geometry_id,
                )
                assert pending is not None
                locked_pending[context.target_id] = pending
                if current.review_item_id is not None:
                    locked_rows[context.target_id] = self._current_row(
                        game_id=context.game_id,
                        import_job_id=context.import_job_id,
                        review_item_id=current.review_item_id,
                        lock=True,
                    )
            else:
                assert context.review_item_id is not None
                row = self._current_row(
                    game_id=context.game_id,
                    import_job_id=context.import_job_id,
                    review_item_id=context.review_item_id,
                    lock=True,
                )
                locked_rows[context.target_id] = row
                current = self._context_from_row(row)
            current_contexts.append(current)
        review_item_ids = tuple(
            context.review_item_id
            for context in current_contexts
            if context.review_item_id is not None
        )
        prior_records = tuple(
            self._session.scalars(
                select(ImageBoardGeometryRevisionModel)
                .where(
                    ImageBoardGeometryRevisionModel.review_item_id.in_(review_item_ids),
                    ImageBoardGeometryRevisionModel.idempotency_key == idempotency_key,
                )
                .order_by(ImageBoardGeometryRevisionModel.review_item_id)
            )
        )
        if prior_records:
            prior_by_item = {record.review_item_id: record for record in prior_records}
            current_by_target = {
                expected.context.target_id: current
                for expected, current in zip(entries, current_contexts, strict=True)
            }
            if (
                len(review_item_ids) != len(entries)
                or set(prior_by_item) != set(review_item_ids)
                or any(
                    prior_by_item[
                        _require_review_item_id(current_by_target[entry.context.target_id])
                    ].command_sha256
                    != entry.command.command_sha256
                    for entry in entries
                )
            ):
                raise ImageGridReviewError(
                    "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT",
                    "The geometry idempotency key already represents another source command.",
                )
            return VirtualGridGeometrySourceSaveResult(
                revisions=tuple(
                    _revision_from_model(
                        prior_by_item[
                            _require_review_item_id(current_by_target[entry.context.target_id])
                        ]
                    )
                    for entry in entries
                ),
                created=False,
            )

        _require_current_source_batch(
            expected_entries=entries,
            current_contexts=tuple(current_contexts),
        )
        availability_snapshot = self._availability_snapshot(entries)
        for row in locked_rows.values():
            item = row[0]
            if item.status == "superseded":
                raise ImageGridReviewError(
                    "IMAGE_REVIEW_SUPERSEDED",
                    "A superseded source cannot receive a manual virtual geometry revision.",
                )

        for entry in entries:
            if entry.context.review_item_id is not None:
                self._reopen_qualified_revision(entry, idempotency_key, created_at)

        try:
            stored_source_geometry = SqlAlchemyImageSourceGeometryRepository(self._session).append(
                SourceGeometryRevisionInput(
                    game_id=base_context.game_id,
                    source_image_id=base_context.source_image_id,
                    topology_rules_version_id=base_context.topology_rules_version_id,
                    sequence_range_start=base_context.sequence_range_start,
                    sequence_range_end=base_context.sequence_range_end,
                    active_board_slots=base_context.active_board_slots,
                    source_checksum_sha256=base_context.source_checksum_sha256,
                    normalized_pixel_checksum_sha256=(
                        base_context.normalized_pixel_checksum_sha256
                    ),
                    oriented_width=base_context.oriented_width,
                    oriented_height=base_context.oriented_height,
                    normalization_adapter_version=base_context.normalization_adapter_version,
                    global_initialization=(
                        None
                        if base_context.global_initialization is None
                        else dict(base_context.global_initialization)
                    ),
                    board_geometries=tuple(dict(value) for value in prepared.board_geometries),
                    engine_kind="manual_v1",
                    engine_version="manual-source-geometry-v1",
                    geometry_source="manual",
                    status="accepted",
                    geometry_checksum_sha256=prepared.source_geometry_checksum_sha256,
                    processing_time_ms=None,
                    warnings=(),
                    created_by=entries[0].command.corrected_by,
                )
            )
        except ImageGeometryPersistenceError as error:
            raise ImageGridReviewError(error.code, str(error)) from error

        records: list[ImageBoardGeometryRevisionModel] = []
        changed_review_item_ids: set[UUID] = set()
        qualified_review_item_ids: set[UUID] = set()
        for entry in entries:
            pending = locked_pending.get(entry.context.target_id)
            if pending is not None and pending.status == "pending":
                record, review_item_ids = self._materialize_pending_source_slot(
                    pending=pending,
                    entry=entry,
                    stored_source_geometry=stored_source_geometry,
                    idempotency_key=idempotency_key,
                    created_at=created_at,
                )
                changed_review_item_ids.update(review_item_ids)
                if entry.command.geometry_qualification is not None:
                    qualified_review_item_ids.add(record.review_item_id)
                records.append(record)
                continue
            row = locked_rows[entry.context.target_id]
            item, board, _source, _source_geometry, _rollout, _document = row
            revision_number = board.geometry_revision + 1
            record = self._geometry_revision_record(
                entry=entry,
                review_item_id=item.id,
                recognized_board_id=board.id,
                revision_number=revision_number,
                source_geometry_revision_id=stored_source_geometry.id,
                idempotency_key=idempotency_key,
                created_at=created_at,
            )
            self._session.add(record)
            previous_approved_geometry_revision = board.approved_geometry_revision
            board.geometry_revision = revision_number
            board.approved_geometry_revision = revision_number
            board.geometry_approved_at = created_at
            board.geometry_approved_by = entry.command.corrected_by
            board.board_geometry = dict(entry.board_geometry)
            _project_geometry_qualification(
                board, prepared.board_geometries[entry.context.position_index]
            )
            board.source_geometry_revision_id = stored_source_geometry.id
            board.geometry_checksum_sha256 = prepared.source_geometry_checksum_sha256
            board.geometry_engine_name = "manual_v1"
            board.geometry_engine_version = "manual-source-geometry-v1"
            self._append_geometry_event(
                entry=entry,
                review_item_id=item.id,
                recognized_board_id=board.id,
                revision_number=revision_number,
                source_geometry_checksum_sha256=prepared.source_geometry_checksum_sha256,
                previous_approved_geometry_revision=previous_approved_geometry_revision,
                created_at=created_at,
            )
            self._replace_current_cells(
                context=entry.context,
                revision_number=revision_number,
                source_geometry_revision_id=stored_source_geometry.id,
                prepared=entry,
                actor=entry.command.corrected_by,
                changed_at=created_at,
            )
            records.append(record)

        source = self._session.get(SourceImageModel, base_context.source_image_id)
        assert source is not None
        source.processed_at = created_at
        self._session.flush()
        self._synchronize_changed_source_items(
            game_id=base_context.game_id,
            changed_review_item_ids=changed_review_item_ids,
            qualified_review_item_ids=qualified_review_item_ids,
            actor=entries[0].command.corrected_by,
        )
        self._reconcile_availability(availability_snapshot)
        return VirtualGridGeometrySourceSaveResult(
            revisions=tuple(_revision_from_model(record) for record in records),
            created=True,
        )

    def _synchronize_changed_source_items(
        self,
        *,
        game_id: UUID,
        changed_review_item_ids: set[UUID],
        qualified_review_item_ids: set[UUID],
        actor: str,
    ) -> None:
        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        for review_item_id in changed_review_item_ids:
            changed = coordinator.synchronize_after_geometry_change(
                game_id=game_id,
                review_item_id=review_item_id,
                actor=actor,
            )
            if review_item_id in qualified_review_item_ids:
                self._require_qualified_projection(game_id=game_id, changed=changed)
        coordinator.synchronize_after_cell_mutation(game_id=game_id)

    def _require_qualified_projection(self, *, game_id: UUID, changed: bool) -> None:
        state = self._session.get(ImageSymbolReviewStateModel, game_id)
        if state is None or (not changed and state.failure_message):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE",
                "Qualified geometry could not reconcile its current symbol projection.",
            )

    def _reopen_qualified_revision(
        self,
        prepared: PreparedVirtualGridGeometry,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> None:
        # Reopen while the old selector/render is still coherent. Keeping a
        # resolved layout would publish symbols whose pixels have just changed.
        if prepared.command.geometry_qualification is None:
            return
        context = prepared.context
        SqlAlchemyOperationalImageReviewRepository(self._session).reopen_for_symbol_cell_issue(
            review_item_id=_require_review_item_id(context),
            game_id=context.game_id,
            import_job_id=context.import_job_id,
            idempotency_key=idempotency_key,
            command_sha256=prepared.command.command_sha256,
            reopened_by=prepared.command.corrected_by,
            reopened_at=created_at,
            reason="manual_geometry_revision",
        )

    def _ensure_projection_state(self, game_id: UUID) -> None:
        # Same lock order as explicit backfill, before sequence/board locks.
        # Never reset an existing state or claim that a game-wide backfill ran.
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_GAME_NOT_FOUND", "The selected game does not exist."
            )
        if self._session.get(ImageSymbolReviewStateModel, game_id) is None:
            self._session.add(
                ImageSymbolReviewStateModel(
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
            )
            self._session.flush()

    def _availability_snapshot(
        self,
        entries: tuple[PreparedVirtualGridGeometry, ...],
    ) -> tuple[ImageSymbolReviewStateModel, tuple[int, ...], int] | None:
        if not any(entry.command.geometry_qualification is not None for entry in entries):
            return None
        state = self._session.get(
            ImageSymbolReviewStateModel,
            entries[0].context.game_id,
            with_for_update=True,
        )
        if state is None:
            return None
        sequences = tuple(entry.context.sequence_number for entry in entries)
        return state, sequences, self._selected_available_count(state.game_id, sequences)

    def _selected_available_count(self, game_id: UUID, sequences: tuple[int, ...]) -> int:
        # At most nine sequence owners, not a game-wide multi-million-row count.
        cell = ImageSymbolReviewCellModel
        owner = ImageBoardSearchFastDocumentModel
        return int(
            self._session.scalar(
                select(func.count(cell.id))
                .join(
                    owner,
                    and_(
                        owner.game_id == cell.game_id,
                        owner.sequence_number == cell.sequence_number,
                        owner.review_item_id == cell.review_item_id,
                    ),
                )
                .where(
                    owner.game_id == game_id,
                    owner.sequence_number.in_(sequences),
                    cell.source_available.is_(True),
                )
            )
            or 0
        )

    def _reconcile_availability(
        self,
        snapshot: tuple[ImageSymbolReviewStateModel, tuple[int, ...], int] | None,
    ) -> None:
        if snapshot is None:
            return
        self._session.flush()
        state, sequences, before = snapshot
        state.cell_count += self._selected_available_count(state.game_id, sequences) - before

    def _geometry_revision_record(
        self,
        *,
        entry: PreparedVirtualGridGeometry,
        review_item_id: UUID,
        recognized_board_id: UUID,
        revision_number: int,
        source_geometry_revision_id: UUID,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> ImageBoardGeometryRevisionModel:
        return ImageBoardGeometryRevisionModel(
            review_item_id=review_item_id,
            recognized_board_id=recognized_board_id,
            revision=revision_number,
            idempotency_key=idempotency_key,
            command_sha256=entry.command.command_sha256,
            corners=[{"x": point.x, "y": point.y} for point in entry.command.corners],
            geometry=dict(entry.board_geometry),
            asset_mode="virtual_source",
            source_geometry_revision_id=source_geometry_revision_id,
            geometry_checksum_sha256=entry.source_geometry_checksum_sha256,
            virtual_render_spec=dict(entry.virtual_render_spec),
            virtual_render_spec_checksum_sha256=entry.virtual_render_spec_checksum_sha256,
            board_relative_path=None,
            board_checksum_sha256=None,
            cropper_version=entry.cropper_version,
            crop_artifacts=None,
            corrected_by=entry.command.corrected_by,
            created_at=created_at,
        )

    def _append_geometry_event(
        self,
        *,
        entry: PreparedVirtualGridGeometry,
        review_item_id: UUID,
        recognized_board_id: UUID,
        revision_number: int,
        source_geometry_checksum_sha256: str,
        previous_approved_geometry_revision: int | None,
        created_at: datetime,
    ) -> None:
        self._session.add(
            ImageBoardGeometryReviewEventModel(
                review_item_id=review_item_id,
                recognized_board_id=recognized_board_id,
                geometry_revision=revision_number,
                grid_rows=entry.context.topology.rows,
                grid_columns=entry.context.topology.columns,
                board_checksum_sha256=source_geometry_checksum_sha256,
                action="geometry_saved",
                previous_approved_geometry_revision=previous_approved_geometry_revision,
                approved_geometry_revision=revision_number,
                actor=entry.command.corrected_by,
                created_at=created_at,
            )
        )

    def _materialize_pending_source_slot(
        self,
        *,
        pending: ImageBoardGeometryPendingModel,
        entry: PreparedVirtualGridGeometry,
        stored_source_geometry: StoredSourceGeometryRevision,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> tuple[ImageBoardGeometryRevisionModel, tuple[UUID, ...]]:
        context = entry.context
        source = self._session.get(SourceImageModel, context.source_image_id)
        job = self._session.get(JobModel, context.import_job_id)
        if source is None or job is None or pending.id != context.pending_geometry_id:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
                "The deferred source slot changed before manual geometry was saved.",
            )
        predictions = [
            {
                "alternatives": [{"confidence": 1.0, "symbolCode": "?"}],
                "columnIndex": cell.column_index,
                "confidence": 0.0,
                "rowIndex": cell.row_index,
                "symbolCode": "?",
            }
            for cell in entry.cells
        ]
        revision_number = context.geometry_revision + 1
        board = RecognizedBoardModel(
            id=context.recognized_board_id,
            source_image_id=context.source_image_id,
            position_index=context.position_index,
            sequence_number_raw=str(context.sequence_number),
            sequence_number=context.sequence_number,
            sequence_confidence=1.0,
            board_geometry=dict(entry.board_geometry),
            asset_mode="virtual_source",
            source_geometry_revision_id=stored_source_geometry.id,
            geometry_engine_name="manual_v1",
            geometry_engine_version="manual-source-geometry-v1",
            geometry_checksum_sha256=entry.source_geometry_checksum_sha256,
            board_relative_path=None,
            board_checksum_sha256=None,
            cells_prediction={"cells": predictions, "modelVersion": "manual-unclassified-v1"},
            completeness_status="complete",
            unavailable_cell_indices=[],
            board_confidence=0.0,
            pipeline_fingerprint=context.pipeline_fingerprint,
            geometry_revision=revision_number,
            grid_rows=context.topology.rows,
            grid_columns=context.topology.columns,
            approved_geometry_revision=revision_number,
            geometry_approved_at=created_at,
            geometry_approved_by=entry.command.corrected_by,
            status="pending_review",
            created_at=created_at,
        )
        _project_geometry_qualification(board, entry.board_geometries[context.position_index])
        self._session.add(board)
        self._session.flush()
        for cell, prediction in zip(entry.cells, predictions, strict=True):
            self._session.add(
                CellObservationModel(
                    recognized_board_id=board.id,
                    row_index=cell.row_index,
                    column_index=cell.column_index,
                    asset_mode="virtual_source",
                    source_geometry_revision_id=stored_source_geometry.id,
                    logical_cell_key=cell.logical_cell_key,
                    logical_cell_key_v2=cell.logical_cell_key_v2,
                    render_identity_v2_sha256=cell.render_identity_v2_sha256,
                    render_spec=dict(cell.render_spec),
                    render_spec_checksum_sha256=cell.render_spec_checksum_sha256,
                    rendered_pixel_checksum_sha256=cell.rendered_pixel_checksum_sha256,
                    extractor_version=cell.extractor_version,
                    crop_relative_path=None,
                    crop_checksum_sha256=cell.crop_checksum_sha256,
                    cropper_version=entry.cropper_version,
                    prediction=prediction,
                    created_at=created_at,
                )
            )
        snapshot = {
            "assetMode": "virtual_source",
            "boardChecksumSha256": None,
            "boardRelativePath": None,
            "cells": predictions,
            "geometry": dict(entry.board_geometry),
            "geometryChecksumSha256": entry.source_geometry_checksum_sha256,
            "geometryEngineName": "manual_v1",
            "geometryEngineVersion": "manual-source-geometry-v1",
            "pipelineFingerprint": context.pipeline_fingerprint,
            "positionIndex": context.position_index,
            "sequence": {
                "confidence": 1.0,
                "normalizedNumber": context.sequence_number,
                "positionIndex": context.position_index,
                "rawText": str(context.sequence_number),
                "reviewReasons": [],
                "sequenceSource": "filename",
            },
            "sourceChecksumSha256": source.checksum_sha256,
            "sourceRelativePath": source.relative_path,
        }
        review, ownership_changes = create_owned_pending_review_item(
            self._session,
            board=board,
            game_id=context.game_id,
            import_job=job,
            snapshot=snapshot,
            created_at=created_at,
            resolution_revision=context.resolution_revision,
        )
        record = self._geometry_revision_record(
            entry=entry,
            review_item_id=review.id,
            recognized_board_id=board.id,
            revision_number=revision_number,
            source_geometry_revision_id=stored_source_geometry.id,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )
        self._session.add(record)
        self._append_geometry_event(
            entry=entry,
            review_item_id=review.id,
            recognized_board_id=board.id,
            revision_number=revision_number,
            source_geometry_checksum_sha256=entry.source_geometry_checksum_sha256,
            previous_approved_geometry_revision=None,
            created_at=created_at,
        )
        pending.recognized_board_id = board.id
        pending.review_item_id = review.id
        pending.status = "resolved"
        pending.resolved_geometry_revision = revision_number
        pending.resolved_at = created_at
        pending.updated_at = created_at
        source.status = "waiting_for_review" if review.status == "pending" else "completed"
        self._session.flush()
        SqlAlchemyBoardSearchProjectionRepository(self._session).sync_review_items(
            ownership_changes
        )
        return record, tuple({review.id, *ownership_changes})

    def _replace_current_cells(
        self,
        *,
        context: VirtualGridGeometryContext,
        revision_number: int,
        source_geometry_revision_id: UUID,
        prepared: PreparedVirtualGridGeometry,
        actor: str,
        changed_at: datetime,
    ) -> None:
        if prepared.command.geometry_qualification is not None:
            # One current-render reconciliation owns both cell transitions and
            # events; do not mutate rows here and repeat invalidation later.
            self._session.flush()
            changed = SymbolCellReviewWriteThroughCoordinator(
                self._session
            ).synchronize_after_geometry_change(
                game_id=context.game_id,
                review_item_id=_require_review_item_id(context),
                actor=actor,
            )
            self._require_qualified_projection(game_id=context.game_id, changed=changed)
            return
        cells = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.review_item_id == context.review_item_id,
                    ImageSymbolReviewCellModel.recognized_board_id == context.recognized_board_id,
                )
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .with_for_update()
            )
        )
        if len(cells) != context.topology.cell_count or tuple(
            int(cell.cell_index) for cell in cells
        ) != tuple(range(context.topology.cell_count)):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_CELLS_INCOMPLETE",
                "Manual virtual geometry requires every current symbol-cell projection.",
            )
        count_state = self._session.get(
            ImageSymbolReviewStateModel,
            context.game_id,
            with_for_update=True,
        )
        count_before = tuple(_CountedCellState.from_model(cell) for cell in cells)
        if len(prepared.cells) != context.topology.cell_count:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_VIRTUAL_CELLS_INCOMPLETE",
                "Manual virtual geometry did not render every configured cell.",
            )
        active_symbol_ids_by_code = {
            code: symbol_id
            for symbol_id, code in self._session.execute(
                select(SymbolModel.id, SymbolModel.code).where(
                    SymbolModel.game_id == context.game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
            )
        }
        for cell, rendered in zip(cells, prepared.cells, strict=True):
            previous = _event_previous(cell)
            cell.asset_mode = "virtual_source"
            cell.source_geometry_revision_id = source_geometry_revision_id
            cell.logical_cell_key = rendered.logical_cell_key
            cell.logical_cell_key_v2 = rendered.logical_cell_key_v2
            cell.render_identity_v2_sha256 = rendered.render_identity_v2_sha256
            cell.render_spec = dict(rendered.render_spec)
            cell.render_spec_checksum_sha256 = rendered.render_spec_checksum_sha256
            cell.rendered_pixel_checksum_sha256 = rendered.rendered_pixel_checksum_sha256
            cell.extractor_version = rendered.extractor_version
            cell.crop_sample_id = rendered.crop_sample_id
            cell.crop_relative_path = None
            cell.crop_checksum_sha256 = rendered.crop_checksum_sha256
            cell.geometry_revision = revision_number
            cell.cropper_version = prepared.cropper_version
            _reset_grid_issue_after_virtual_recrop(
                cell,
                active_symbol_ids_by_code=active_symbol_ids_by_code,
            )
            try:
                verification = verification_outcome_value(
                    review_state=cell.review_state,
                    quality_issue=cell.quality_issue,
                    assigned_symbol_id=cell.assigned_symbol_id,
                    prediction_present=cell.prediction_symbol_code not in {None, "?"},
                    assignment_source=cell.assignment_source,
                )
            except AdditiveVirtualGeometryContractError as error:
                raise ImageGridReviewError(error.code, str(error)) from error
            cell.verification_outcome = verification.outcome
            cell.verified_symbol_id_v2 = verification.verified_symbol_id
            cell.revision += 1
            cell.last_reviewed_by = actor
            cell.last_reviewed_at = changed_at
            self._session.add(
                ImageSymbolReviewEventModel(
                    cell_review_id=cell.id,
                    review_item_id=cell.review_item_id,
                    logical_cell_key=cell.logical_cell_key,
                    previous_logical_cell_key_v2=previous["logical_cell_key_v2"],
                    logical_cell_key_v2=cell.logical_cell_key_v2,
                    previous_render_identity_v2_sha256=previous["render_identity_v2_sha256"],
                    render_identity_v2_sha256=cell.render_identity_v2_sha256,
                    previous_asset_mode=previous["asset_mode"],
                    asset_mode=cell.asset_mode,
                    previous_source_geometry_revision_id=previous["source_geometry_revision_id"],
                    source_geometry_revision_id=cell.source_geometry_revision_id,
                    previous_render_spec_checksum_sha256=previous["render_spec_checksum_sha256"],
                    render_spec_checksum_sha256=cell.render_spec_checksum_sha256,
                    previous_rendered_pixel_checksum_sha256=previous[
                        "rendered_pixel_checksum_sha256"
                    ],
                    rendered_pixel_checksum_sha256=cell.rendered_pixel_checksum_sha256,
                    extractor_version=cell.extractor_version,
                    crop_sample_id=cell.crop_sample_id,
                    crop_checksum_sha256=cell.crop_checksum_sha256,
                    geometry_revision=cell.geometry_revision,
                    cell_revision=cell.revision,
                    action="geometry_invalidated",
                    previous_assigned_symbol_id=previous["assigned_symbol_id"],
                    assigned_symbol_id=cell.assigned_symbol_id,
                    previous_review_state=previous["review_state"],
                    review_state=cell.review_state,
                    previous_quality_issue=previous["quality_issue"],
                    quality_issue=cell.quality_issue,
                    previous_verification_outcome=previous["verification_outcome"],
                    verification_outcome=cell.verification_outcome,
                    previous_verified_symbol_id_v2=previous["verified_symbol_id_v2"],
                    verified_symbol_id_v2=cell.verified_symbol_id_v2,
                    previous_approved_crop_sample_id=previous["approved_crop_sample_id"],
                    approved_crop_sample_id=cell.approved_crop_sample_id,
                    previous_approved_crop_checksum_sha256=previous[
                        "approved_crop_checksum_sha256"
                    ],
                    approved_crop_checksum_sha256=cell.approved_crop_checksum_sha256,
                    previous_approved_geometry_revision=previous["approved_geometry_revision"],
                    approved_geometry_revision=cell.approved_geometry_revision,
                    operation_id=None,
                    actor=actor,
                )
            )
        if count_state is not None:
            _apply_count_deltas(
                count_state,
                before=count_before,
                after=tuple(_CountedCellState.from_model(cell) for cell in cells),
            )

    def _pending_context(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        pending_geometry_id: UUID,
        lock: bool,
    ) -> VirtualGridGeometryContext:
        statement = select(ImageBoardGeometryPendingModel).where(
            ImageBoardGeometryPendingModel.id == pending_geometry_id,
            ImageBoardGeometryPendingModel.game_id == game_id,
            ImageBoardGeometryPendingModel.import_job_id == import_job_id,
        )
        if lock:
            statement = statement.with_for_update()
        pending = self._session.scalar(statement)
        if pending is None:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_ITEM_NOT_FOUND",
                "The deferred source slot no longer exists in this scope.",
            )
        if pending.status == "resolved" and pending.review_item_id is not None:
            current = self._context_from_row(
                self._current_row(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    review_item_id=pending.review_item_id,
                    lock=lock,
                )
            )
            return replace(current, pending_geometry_id=pending.id)
        if pending.status != "pending":
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
                "The deferred source slot changed after the page was loaded.",
            )
        source = self._session.get(SourceImageModel, pending.source_image_id)
        job = self._session.get(JobModel, import_job_id)
        geometry = self._session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game_id,
                ImageSourceGeometryRevisionModel.source_image_id == pending.source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        if (
            source is None
            or job is None
            or job.game_id != game_id
            or source.import_job_id != import_job_id
            or geometry is None
            or source.checksum_sha256 != pending.source_checksum_sha256
            or source.raw_width is None
            or source.raw_height is None
            or source.oriented_width is None
            or source.oriented_height is None
            or source.normalized_pixel_checksum_sha256 is None
            or source.normalization_adapter_version is None
            or geometry.source_checksum_sha256 != source.checksum_sha256
            or geometry.active_board_slots != list(range(len(geometry.board_geometries)))
            or pending.position_index not in geometry.active_board_slots
            or geometry.sequence_range_start + pending.position_index != pending.sequence_number
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_VIRTUAL_PROVENANCE_INVALID",
                "The deferred board slot has incomplete virtual source provenance.",
            )
        configuration = self._pending_render_configuration(
            source_image_id=source.id,
            import_job_id=import_job_id,
            job=job,
        )
        return VirtualGridGeometryContext(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=None,
            recognized_board_id=pending.id,
            pending_geometry_id=pending.id,
            source_image_id=source.id,
            file_execution_key=source.file_execution_key,
            position_index=int(pending.position_index),
            sequence_number=int(pending.sequence_number),
            source_relative_path=source.relative_path,
            source_checksum_sha256=source.checksum_sha256,
            raw_width=int(source.raw_width),
            raw_height=int(source.raw_height),
            oriented_width=int(source.oriented_width),
            oriented_height=int(source.oriented_height),
            exif_orientation=source.exif_orientation,
            normalized_pixel_checksum_sha256=source.normalized_pixel_checksum_sha256,
            normalization_adapter_version=source.normalization_adapter_version,
            pipeline_fingerprint=pending.pipeline_fingerprint_sha256,
            resolution_revision=int(pending.expected_review_resolution_revision),
            geometry_revision=int(pending.expected_geometry_revision),
            topology=BoardTopology(rows=3, columns=5),
            topology_rules_version_id=geometry.topology_rules_version_id,
            source_geometry_revision_id=geometry.id,
            source_geometry_revision=int(geometry.revision),
            sequence_range_start=int(geometry.sequence_range_start),
            sequence_range_end=int(geometry.sequence_range_end),
            active_board_slots=tuple(int(value) for value in geometry.active_board_slots),
            global_initialization=(
                None
                if geometry.global_initialization is None
                else dict(geometry.global_initialization)
            ),
            board_geometries=tuple(dict(value) for value in geometry.board_geometries),
            render_configuration=configuration,
        )

    def _pending_render_configuration(
        self,
        *,
        source_image_id: UUID,
        import_job_id: UUID,
        job: JobModel,
    ) -> DirectCellRenderConfiguration:
        render_spec = self._session.scalar(
            select(ImageSymbolReviewCellModel.render_spec)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .where(
                ImageSymbolReviewCellModel.asset_mode == "virtual_source",
                RecognizedBoardModel.source_image_id == source_image_id,
            )
            .order_by(ImageSymbolReviewCellModel.cell_index)
            .limit(1)
        )
        if render_spec is None:
            render_spec = self._session.scalar(
                select(ImageSymbolReviewCellModel.render_spec)
                .where(
                    ImageSymbolReviewCellModel.asset_mode == "virtual_source",
                    ImageSymbolReviewCellModel.import_job_id == import_job_id,
                )
                .limit(1)
            )
        if render_spec is not None:
            return _configuration(render_spec)
        from game_predictor_worker.images.pipeline_contract import GeometryPipelineRolloutSnapshot
        from game_predictor_worker.images.virtual_cell_extraction import (
            VIRTUAL_CELL_INTERPOLATION_VERSION,
        )

        from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot

        try:
            model = SymbolModelJobSnapshot.from_payload(job.input_payload.get("symbol_model"))
            rollout = GeometryPipelineRolloutSnapshot.from_payload(
                job.input_payload.get("image_geometry_rollout")
            )
        except (ValueError, TypeError) as error:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_RENDER_CONFIGURATION_INVALID",
                "The deferred slot has no pinned virtual render configuration.",
            ) from error
        return DirectCellRenderConfiguration(
            extractor_version=rollout.virtual_renderer_version,
            preprocessing_version=rollout.preprocessing_version,
            interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
            output_width=model.input_size,
            output_height=model.input_size,
            padding_fraction=0.08,
        )

    def _current_row(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        lock: bool,
    ) -> tuple[
        ImageReviewItemModel,
        RecognizedBoardModel,
        SourceImageModel,
        ImageSourceGeometryRevisionModel,
        ImageGeometryRolloutStateModel,
        ImageBoardSearchFastDocumentModel,
    ]:
        statement = (
            select(
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImageSourceGeometryRevisionModel,
                ImageGeometryRolloutStateModel,
                ImageBoardSearchFastDocumentModel,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .join(
                ImageSourceGeometryRevisionModel,
                ImageSourceGeometryRevisionModel.id
                == RecognizedBoardModel.source_geometry_revision_id,
            )
            .join(
                ImageGeometryRolloutStateModel,
                ImageGeometryRolloutStateModel.game_id == game_id,
            )
            .join(
                ImageBoardSearchFastDocumentModel,
                and_(
                    ImageBoardSearchFastDocumentModel.game_id == game_id,
                    ImageBoardSearchFastDocumentModel.review_item_id == ImageReviewItemModel.id,
                    ImageBoardSearchFastDocumentModel.recognized_board_id
                    == RecognizedBoardModel.id,
                ),
            )
            .where(
                JobModel.game_id == game_id,
                JobModel.id == import_job_id,
                ImageReviewItemModel.id == review_item_id,
            )
        )
        if lock:
            statement = statement.with_for_update(
                of=(
                    ImageReviewItemModel,
                    RecognizedBoardModel,
                    SourceImageModel,
                    ImageGeometryRolloutStateModel,
                )
            )
        row = self._session.execute(statement).one_or_none()
        if row is None:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_ITEM_NOT_FOUND",
                "The current virtual grid review item does not exist in this scope.",
            )
        return cast(
            tuple[
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImageSourceGeometryRevisionModel,
                ImageGeometryRolloutStateModel,
                ImageBoardSearchFastDocumentModel,
            ],
            tuple(row),
        )

    def _context_from_row(
        self,
        row: tuple[
            ImageReviewItemModel,
            RecognizedBoardModel,
            SourceImageModel,
            ImageSourceGeometryRevisionModel,
            ImageGeometryRolloutStateModel,
            ImageBoardSearchFastDocumentModel,
        ],
    ) -> VirtualGridGeometryContext:
        item, board, source, geometry, rollout, document = row
        # The rollout backfill is a game-wide migration aid. It can be
        # incomplete because of another source, so it is not evidence about
        # this current board. Manual correction must instead fail closed on
        # the complete, source-scoped provenance checks below.
        if (
            board.asset_mode != "virtual_source"
            or board.source_geometry_revision_id != geometry.id
            or board.geometry_checksum_sha256 != geometry.geometry_checksum_sha256
            or source.raw_width is None
            or source.raw_height is None
            or source.oriented_width is None
            or source.oriented_height is None
            or source.normalized_pixel_checksum_sha256 is None
            or source.normalization_adapter_version is None
            or document.sequence_number < 1
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_VIRTUAL_PROVENANCE_INVALID",
                "The current board has incomplete virtual source provenance.",
            )
        topology = BoardTopology(rows=board.grid_rows or 3, columns=board.grid_columns or 5)
        review_cells = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == item.id)
                .where(ImageSymbolReviewCellModel.source_available.is_(True))
                .order_by(ImageSymbolReviewCellModel.cell_index)
            )
        )
        expected_indices = set(range(topology.cell_count))
        if board.geometry_qualification is not None:
            expected_indices -= set(board.unavailable_cell_indices)
        # Before the first backfill a valid board can have no review cells.
        # Read only its immutable provenance; GET/preview never initializes state.
        initial_configurations: tuple[DirectCellRenderConfiguration, ...] | None = None
        if not review_cells and expected_indices:
            if board.geometry_revision == 0:
                observations = tuple(
                    self._session.scalars(
                        select(CellObservationModel)
                        .where(CellObservationModel.recognized_board_id == board.id)
                        .order_by(CellObservationModel.row_index, CellObservationModel.column_index)
                    )
                )
                if (
                    len(observations) == len(expected_indices)
                    and {
                        cell.row_index * topology.columns + cell.column_index
                        for cell in observations
                    }
                    == expected_indices
                    and all(cell.asset_mode == "virtual_source" for cell in observations)
                ):
                    initial_configurations = tuple(
                        _configuration(cell.render_spec) for cell in observations
                    )
            else:
                revision = self._session.scalar(
                    select(ImageBoardGeometryRevisionModel).where(
                        ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                        ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
                    )
                )
                manifest = None if revision is None else revision.virtual_render_spec
                cells = manifest.get("cells") if isinstance(manifest, dict) else None
                if (
                    isinstance(cells, list)
                    and len(cells) == len(expected_indices)
                    and all(isinstance(cell, dict) for cell in cells)
                    and {cell.get("cellIndex") for cell in cells} == expected_indices
                ):
                    initial_configurations = tuple(
                        _configuration(cell.get("renderSpec")) for cell in cells
                    )
        if initial_configurations is None and (
            len(review_cells) != len(expected_indices)
            or {cell.cell_index for cell in review_cells} != expected_indices
            or any(cell.geometry_revision != board.geometry_revision for cell in review_cells)
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_CELLS_INCOMPLETE",
                "The current virtual board does not contain every review cell.",
            )
        configurations = initial_configurations or tuple(
            _configuration(cell.render_spec) for cell in review_cells
        )
        if not configurations and board.geometry_qualification is not None:
            revision = self._session.scalar(
                select(ImageBoardGeometryRevisionModel).where(
                    ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                    ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
                )
            )
            if revision is not None:
                configurations = (_configuration(revision.virtual_render_spec),)
            else:
                job = self._session.get(JobModel, source.import_job_id)
                if job is None:
                    raise ImageGridReviewError(
                        "IMAGE_GRID_REVIEW_RENDER_CONFIGURATION_INVALID",
                        "The unavailable board has no pinned import configuration.",
                    )
                configurations = (
                    self._pending_render_configuration(
                        source_image_id=source.id,
                        import_job_id=source.import_job_id,
                        job=job,
                    ),
                )
        if len(set(configurations)) != 1:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_RENDER_CONFIGURATION_DRIFT",
                "The current virtual cells do not share one pinned render configuration.",
            )
        return VirtualGridGeometryContext(
            game_id=rollout.game_id,
            import_job_id=source.import_job_id,
            review_item_id=item.id,
            recognized_board_id=board.id,
            pending_geometry_id=None,
            source_image_id=source.id,
            file_execution_key=source.file_execution_key,
            position_index=int(board.position_index),
            sequence_number=int(document.sequence_number),
            source_relative_path=source.relative_path,
            source_checksum_sha256=source.checksum_sha256,
            raw_width=int(source.raw_width),
            raw_height=int(source.raw_height),
            oriented_width=int(source.oriented_width),
            oriented_height=int(source.oriented_height),
            exif_orientation=source.exif_orientation,
            normalized_pixel_checksum_sha256=source.normalized_pixel_checksum_sha256,
            normalization_adapter_version=source.normalization_adapter_version,
            pipeline_fingerprint=board.pipeline_fingerprint,
            resolution_revision=int(item.resolution_revision),
            geometry_revision=int(board.geometry_revision),
            topology=topology,
            topology_rules_version_id=geometry.topology_rules_version_id,
            source_geometry_revision_id=geometry.id,
            source_geometry_revision=int(geometry.revision),
            sequence_range_start=int(geometry.sequence_range_start),
            sequence_range_end=int(geometry.sequence_range_end),
            active_board_slots=tuple(int(value) for value in geometry.active_board_slots),
            global_initialization=(
                None
                if geometry.global_initialization is None
                else dict(geometry.global_initialization)
            ),
            board_geometries=tuple(dict(value) for value in geometry.board_geometries),
            render_configuration=configurations[0],
        )


def _configuration(value: object) -> DirectCellRenderConfiguration:
    if not isinstance(value, dict) or not isinstance(value.get("configuration"), dict):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_RENDER_CONFIGURATION_INVALID",
            "A virtual review cell has no pinned render configuration.",
        )
    raw = cast(dict[str, object], value["configuration"])
    try:
        return DirectCellRenderConfiguration(
            extractor_version=cast(str, raw["extractorVersion"]),
            preprocessing_version=cast(str, raw["preprocessingVersion"]),
            interpolation=cast(str, raw["interpolation"]),
            output_width=cast(int, raw["outputWidth"]),
            output_height=cast(int, raw["outputHeight"]),
            padding_fraction=cast(float, raw["paddingFraction"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_RENDER_CONFIGURATION_INVALID",
            "A virtual review cell has an invalid render configuration.",
        ) from error


def _require_review_item_id(context: VirtualGridGeometryContext) -> UUID:
    if context.review_item_id is None:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SLOT_IDENTITY_INVALID",
            "A materialized grid-review slot is missing its review identity.",
        )
    return context.review_item_id


def _require_same_context(
    current: VirtualGridGeometryContext,
    expected: VirtualGridGeometryContext,
) -> None:
    if current != expected:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
            "The virtual grid review changed while its correction was rendered.",
        )


def _require_current_source_batch(
    *,
    expected_entries: tuple[PreparedVirtualGridGeometry, ...],
    current_contexts: tuple[VirtualGridGeometryContext, ...],
) -> None:
    if len(expected_entries) != len(current_contexts):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
            "The active source board slots changed before manual geometry could be saved.",
        )
    expected_base = expected_entries[0].context
    for expected, current in zip(expected_entries, current_contexts, strict=True):
        _require_same_context(current, expected.context)
        if (
            current.source_image_id != expected_base.source_image_id
            or current.source_geometry_revision_id != expected_base.source_geometry_revision_id
            or current.active_board_slots != expected_base.active_board_slots
            or current.board_geometries != expected_base.board_geometries
        ):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                "The source geometry changed before all manual board slots were saved.",
            )


def _event_previous(cell: ImageSymbolReviewCellModel) -> dict[str, Any]:
    previous_v2 = optional_verification_outcome_value(
        review_state=cell.review_state,
        quality_issue=cell.quality_issue,
        assigned_symbol_id=cell.assigned_symbol_id,
        prediction_present=cell.prediction_symbol_code not in {None, "?"},
        assignment_source=cell.assignment_source,
    )
    return {
        "asset_mode": cell.asset_mode,
        "source_geometry_revision_id": cell.source_geometry_revision_id,
        "logical_cell_key_v2": cell.logical_cell_key_v2,
        "render_identity_v2_sha256": cell.render_identity_v2_sha256,
        "verification_outcome": (
            cell.verification_outcome
            if cell.verification_outcome is not None
            else None
            if previous_v2 is None
            else previous_v2.outcome
        ),
        "verified_symbol_id_v2": (
            cell.verified_symbol_id_v2
            if cell.verification_outcome is not None
            else None
            if previous_v2 is None
            else previous_v2.verified_symbol_id
        ),
        "render_spec_checksum_sha256": cell.render_spec_checksum_sha256,
        "rendered_pixel_checksum_sha256": cell.rendered_pixel_checksum_sha256,
        "assigned_symbol_id": cell.assigned_symbol_id,
        "review_state": cell.review_state,
        "quality_issue": cell.quality_issue,
        "approved_crop_sample_id": cell.approved_crop_sample_id,
        "approved_crop_checksum_sha256": cell.approved_crop_checksum_sha256,
        "approved_geometry_revision": cell.approved_geometry_revision,
    }


def _project_geometry_qualification(
    board: RecognizedBoardModel, source_slot: Mapping[str, object]
) -> None:
    """The immutable source slot, not a UI projection, owns the decision."""
    raw = source_slot.get("geometryQualification")
    if raw is None:
        if board.geometry_qualification is not None:
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_QUALIFICATION_CONFLICT",
                "A legacy revision cannot silently discard explicit geometry qualification.",
            )
        return
    qualification = GeometryQualification.from_dict(raw)
    if board.board_geometry.get("geometryQualification") != qualification.to_dict():
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_QUALIFICATION_CONFLICT",
            "Board projection differs from its source geometry qualification.",
        )
    board.geometry_qualification = qualification.to_dict()
    board.completeness_status = qualification.completeness_status
    board.unavailable_cell_indices = list(qualification.unavailable_cell_indices)


def _reset_grid_issue_after_virtual_recrop(
    cell: ImageSymbolReviewCellModel,
    *,
    active_symbol_ids_by_code: dict[str, UUID],
) -> None:
    if cell.quality_issue != "grid_issue":
        return
    cell.quality_issue = None
    cell.assignment_source = SymbolCellAssignmentSource.MODEL.value
    cell.assigned_symbol_id = active_symbol_ids_by_code.get(cell.prediction_symbol_code or "")


def _revision_from_model(
    record: ImageBoardGeometryRevisionModel,
) -> VirtualGridGeometryRevision:
    if (
        record.asset_mode != "virtual_source"
        or record.source_geometry_revision_id is None
        or record.geometry_checksum_sha256 is None
        or record.virtual_render_spec_checksum_sha256 is None
        or not isinstance(record.virtual_render_spec, dict)
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_VIRTUAL_REVISION_INVALID",
            "The persisted virtual geometry revision is incomplete.",
        )
    raw_cells = record.virtual_render_spec.get("cells")
    if not isinstance(raw_cells, list):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_VIRTUAL_REVISION_INVALID",
            "The persisted virtual geometry cells are incomplete.",
        )
    cells: list[VirtualGridGeometryCell] = []
    for raw_value in raw_cells:
        if not isinstance(raw_value, dict) or not isinstance(raw_value.get("renderSpec"), dict):
            raise ImageGridReviewError(
                "IMAGE_GRID_REVIEW_VIRTUAL_REVISION_INVALID",
                "A persisted virtual geometry cell is invalid.",
            )
        render_spec = cast(dict[str, object], raw_value["renderSpec"])
        cells.append(
            VirtualGridGeometryCell(
                cell_index=cast(int, raw_value["cellIndex"]),
                row_index=cast(int, render_spec["rowIndex"]),
                column_index=cast(int, render_spec["columnIndex"]),
                crop_sample_id=cast(str, raw_value["cropSampleId"]),
                crop_checksum_sha256=cast(str, raw_value["renderedPixelChecksumSha256"]),
                logical_cell_key=cast(str, raw_value["logicalCellKeySha256"]),
                logical_cell_key_v2=cast(str | None, raw_value.get("logicalCellKeyV2Sha256")),
                render_identity_v2_sha256=cast(str | None, raw_value.get("renderIdentityV2Sha256")),
                render_spec=render_spec,
                render_spec_checksum_sha256=cast(str, raw_value["renderSpecChecksumSha256"]),
                rendered_pixel_checksum_sha256=cast(str, raw_value["renderedPixelChecksumSha256"]),
                extractor_version=record.cropper_version,
            )
        )
    if len(record.corners) != 4 or any(
        not isinstance(point, dict)
        or not isinstance(point.get("x"), int)
        or not isinstance(point.get("y"), int)
        for point in record.corners
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_VIRTUAL_REVISION_INVALID",
            "The persisted virtual geometry corners are invalid.",
        )
    corners = tuple(
        ImageReviewGeometryPoint(x=point["x"], y=point["y"]) for point in record.corners
    )
    return VirtualGridGeometryRevision(
        id=record.id,
        review_item_id=record.review_item_id,
        recognized_board_id=record.recognized_board_id,
        revision=int(record.revision),
        idempotency_key=record.idempotency_key,
        command_sha256=record.command_sha256,
        corners=corners,
        source_geometry_revision_id=record.source_geometry_revision_id,
        geometry_checksum_sha256=record.geometry_checksum_sha256,
        virtual_render_spec_checksum_sha256=(record.virtual_render_spec_checksum_sha256),
        cropper_version=record.cropper_version,
        cells=tuple(cells),
        corrected_by=record.corrected_by,
        created_at=record.created_at,
        geometry_qualification=(
            GeometryQualification.from_dict(record.geometry["geometryQualification"])
            if isinstance(record.geometry.get("geometryQualification"), dict)
            else None
        ),
    )


__all__ = ["SqlAlchemyVirtualGridGeometryRepository"]
