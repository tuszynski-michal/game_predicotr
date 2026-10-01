"""Transactional metadata-only persistence for manual virtual board geometry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from game_predictor_api.application.legacy_board_conversion import (
    LegacyConversionBoardPlan,
    LegacyConversionBoardResult,
    LegacyConversionSourcePlan,
    LegacyConversionSourceResult,
)
from game_predictor_api.application.virtual_grid_geometry import (
    LegacyConversionTarget,
    PreparedVirtualGridGeometry,
    PreparedVirtualGridGeometrySource,
    VirtualGridGeometryCell,
    VirtualGridGeometryContext,
    VirtualGridGeometryRevision,
    VirtualGridGeometrySaveResult,
    VirtualGridGeometrySourceSaveResult,
)
from game_predictor_api.domain.board_render_manifests import (
    BoardRenderManifestError,
    revision_render_manifest,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.geometry_qualification import (
    GeometryQualification,
    GeometryQualificationError,
    available_cell_indices,
)
from game_predictor_api.domain.image_geometry_v2 import (
    DirectCellRenderConfiguration,
    ImageGeometryContractError,
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
    resolve_manual_geometry_qualification,
    unavailable_source_cell_indices,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellQualityIssue,
    SymbolCellReviewState,
    symbol_cell_approval_pixels_changed,
)
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    AdditiveVirtualGeometryContractError,
    optional_verification_outcome_value,
)
from game_predictor_api.storage.board_render_manifest_reader import load_current_render_manifest
from game_predictor_api.storage.board_render_manifest_repository import add_board_render_manifest
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
    _bind_game_store,
    _CountedCellState,
    _verification_v2,
)
from game_predictor_api.storage.models import (
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
        self._reopen_resolved_revision(prepared, idempotency_key, created_at)
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
        self._add_render_manifest(record, game_id=context.game_id)
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
        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        coordinator.synchronize_after_cell_mutation(game_id=context.game_id)
        # D-462 R2: the reopened board closes again when every verification
        # survived the new geometry.
        coordinator.synchronize_board_from_cells(
            game_id=context.game_id,
            review_item_id=_require_review_item_id(context),
            actor=prepared.command.corrected_by,
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
        # Two corrections of different slots of one source take different
        # sequence locks.  Serialize them on the source row (same order as the
        # import writer: sequences, then source) before the contexts are read
        # again, so the loser sees the winner's source revision and conflicts
        # instead of appending a sibling revision from a stale base.
        self._session.execute(
            select(SourceImageModel.id)
            .where(SourceImageModel.id == base_context.source_image_id)
            .with_for_update()
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
        occupied = self._occupied_pending_slots(entries, locked_pending)
        if occupied:
            if len(entries) != 1:
                raise ImageGridReviewError(
                    "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                    "A deferred slot of this source already has a recognized board.",
                )
            # The same rule as the deferred writer: a board created at the
            # position after the deferral (human or newer import) wins, and the
            # stale deferred item is superseded instead of creating a duplicate.
            pending = occupied[0]
            pending.status = "superseded"
            pending.superseded_at = created_at
            pending.updated_at = created_at
            self._session.flush()
            return VirtualGridGeometrySourceSaveResult(revisions=(), created=False)
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
                self._reopen_resolved_revision(entry, idempotency_key, created_at)

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
            self._add_render_manifest(record, game_id=entry.context.game_id)
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
        # D-462 R2: reopened boards close again from their surviving cells.
        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        for entry in entries:
            if entry.context.review_item_id is not None:
                coordinator.synchronize_board_from_cells(
                    game_id=base_context.game_id,
                    review_item_id=entry.context.review_item_id,
                    actor=entry.command.corrected_by,
                )
        self._reconcile_availability(availability_snapshot)
        return VirtualGridGeometrySourceSaveResult(
            revisions=tuple(_revision_from_model(record) for record in records),
            created=True,
        )

    # -- D-467 S6 (TASK-0791): legacy_file -> virtual_source conversion -------

    def legacy_conversion_source_ids(self, *, game_id: UUID) -> tuple[UUID, ...]:
        """Sources of the game that still own a ``legacy_file`` board, ordered."""

        _bind_game_store(self._session, game_id)
        return tuple(
            self._session.scalars(
                select(RecognizedBoardModel.source_image_id)
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .where(
                    JobModel.game_id == game_id,
                    RecognizedBoardModel.asset_mode == _LEGACY_ASSET_MODE,
                )
                .group_by(RecognizedBoardModel.source_image_id)
                .order_by(RecognizedBoardModel.source_image_id)
            )
        )

    def legacy_conversion_plan(
        self, *, game_id: UUID, source_image_id: UUID, lock: bool
    ) -> LegacyConversionSourcePlan:
        """Describe every ``legacy_file`` board of one source as a virtual target.

        Under ``lock`` the lock order of the virtual writers is kept: sequence
        advisory locks, then the source row, then boards, review items and
        cells.  The board list is read again after the locks, so a concurrent
        conversion of the same source finds nothing left (idempotent).
        """

        _bind_game_store(self._session, game_id)
        if lock:
            sequences = self._legacy_board_sequences(
                game_id=game_id, source_image_id=source_image_id
            )
            acquire_image_sequence_locks(self._session, game_id=game_id, sequence_numbers=sequences)
            self._session.execute(
                select(SourceImageModel.id)
                .where(SourceImageModel.id == source_image_id)
                .with_for_update()
            )
        statement = (
            select(RecognizedBoardModel)
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                RecognizedBoardModel.source_image_id == source_image_id,
                RecognizedBoardModel.asset_mode == _LEGACY_ASSET_MODE,
            )
            .order_by(RecognizedBoardModel.position_index)
        )
        if lock:
            statement = statement.with_for_update(of=RecognizedBoardModel)
        boards = tuple(self._session.scalars(statement))
        if not boards:
            return LegacyConversionSourcePlan(
                game_id=game_id, source_image_id=source_image_id, boards=()
            )
        source = self._session.get(SourceImageModel, source_image_id)
        assert source is not None
        job = self._session.get(JobModel, source.import_job_id)
        geometry = self._session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game_id,
                ImageSourceGeometryRevisionModel.source_image_id == source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        source_problems = _legacy_source_problems(source, job, geometry, game_id=game_id)
        configuration: DirectCellRenderConfiguration | None = None
        if not source_problems and job is not None:
            from game_predictor_worker.images.pipeline_contract import (
                VIRTUAL_CELL_RENDERER_VERSION,
            )

            try:
                # Output size, padding, preprocessing and interpolation follow
                # the source's current virtual cells; the extractor pin is the
                # renderer of this code, because the renderer refuses any
                # other pin and the converted revision is a new render anyway
                # (TASK-0663 bumped the contract version without changing
                # pixels; previews verify the stored checksums).
                configuration = replace(
                    self._pending_render_configuration(
                        source_image_id=source.id, import_job_id=source.import_job_id, job=job
                    ),
                    extractor_version=VIRTUAL_CELL_RENDERER_VERSION,
                )
            except ImageGridReviewError:
                source_problems = ("LEGACY_CONVERSION_RENDER_CONFIGURATION_INVALID",)
        return LegacyConversionSourcePlan(
            game_id=game_id,
            source_image_id=source_image_id,
            boards=tuple(
                self._legacy_board_plan(
                    board,
                    game_id=game_id,
                    source=source,
                    geometry=None if source_problems else geometry,
                    configuration=configuration,
                    source_problems=source_problems,
                    lock=lock,
                )
                for board in boards
            ),
        )

    def convert_legacy_source(
        self,
        *,
        plan: LegacyConversionSourcePlan,
        prepared: PreparedVirtualGridGeometrySource,
        actor: str,
        created_at: datetime,
    ) -> LegacyConversionSourceResult:
        """Persist the conversion of one locked source (TASK-0791).

        The same records as a manual virtual geometry save are written: one
        appended source geometry revision, per board a ``virtual_source``
        revision with ``virtual_render_spec``, its render manifest and the
        board's virtual provenance.  Unlike a manual save the review item is
        not reopened, the geometry approval is not changed and current cell
        decisions are carried over unchanged (see ``_convert_current_cells``).
        """

        entries_by_board = {entry.context.recognized_board_id: entry for entry in prepared.entries}
        boards = {board.recognized_board_id: board for board in plan.boards}
        if set(entries_by_board) != set(boards) or not prepared.entries:
            raise ImageGridReviewError(
                "LEGACY_CONVERSION_TARGETS_CHANGED",
                "The rendered legacy boards differ from the locked conversion plan.",
            )
        base_context = prepared.entries[0].context
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
                    created_by=actor,
                )
            )
        except ImageGeometryPersistenceError as error:
            raise ImageGridReviewError(error.code, str(error)) from error

        results: list[LegacyConversionBoardResult] = []
        changed_cells = False
        for entry in sorted(prepared.entries, key=lambda value: value.context.position_index):
            context = entry.context
            board_plan = boards[context.recognized_board_id]
            board = self._session.get(RecognizedBoardModel, context.recognized_board_id)
            if (
                board is None
                or board.asset_mode != _LEGACY_ASSET_MODE
                or board.geometry_revision != board_plan.geometry_revision
                or context.review_item_id is None
            ):
                raise ImageGridReviewError(
                    "LEGACY_CONVERSION_TARGETS_CHANGED",
                    "A legacy board changed before its conversion was persisted.",
                )
            previous_revision = int(board.geometry_revision)
            revision_number = context.next_geometry_revision
            record = self._geometry_revision_record(
                entry=entry,
                review_item_id=context.review_item_id,
                recognized_board_id=board.id,
                revision_number=revision_number,
                source_geometry_revision_id=stored_source_geometry.id,
                idempotency_key=uuid5(NAMESPACE_URL, f"{_LEGACY_CONVERSION_KEY_PREFIX}:{board.id}"),
                created_at=created_at,
            )
            geometry = _retain_legacy_board_context(entry.board_geometry, board.board_geometry)
            record.geometry = geometry
            self._session.add(record)
            self._add_render_manifest(record, game_id=context.game_id)
            board.asset_mode = "virtual_source"
            board.board_relative_path = None
            board.board_checksum_sha256 = None
            board.board_geometry = geometry
            _project_geometry_qualification(
                board, prepared.board_geometries[context.position_index]
            )
            board.source_geometry_revision_id = stored_source_geometry.id
            board.geometry_checksum_sha256 = prepared.source_geometry_checksum_sha256
            board.geometry_engine_name = "manual_v1"
            board.geometry_engine_version = "manual-source-geometry-v1"
            board.geometry_revision = revision_number
            # The approval state of the geometry is carried over: a board whose
            # geometry was approved keeps that approval on the same corners.
            if board.approved_geometry_revision == previous_revision:
                board.approved_geometry_revision = revision_number
            self._session.flush()
            converted, preserved = self._convert_current_cells(
                context=context,
                entry=entry,
                previous_revision=previous_revision,
                revision_number=revision_number,
                source_geometry_revision_id=stored_source_geometry.id,
                actor=actor,
            )
            changed_cells = changed_cells or converted > 0
            results.append(
                LegacyConversionBoardResult(
                    recognized_board_id=board.id,
                    review_item_id=context.review_item_id,
                    previous_geometry_revision=previous_revision,
                    geometry_revision=revision_number,
                    converted_cell_count=converted,
                    preserved_decision_cell_count=preserved,
                    render_manifest_written=bool(entry.cells),
                )
            )
        self._session.flush()
        projection = SqlAlchemyBoardSearchProjectionRepository(self._session)
        for result in results:
            # D-462 R8: the search document's board identity changes from the
            # file checksum to the source geometry checksum.
            projection.sync_review_item(result.review_item_id)
        if changed_cells:
            SymbolCellReviewWriteThroughCoordinator(self._session).synchronize_after_cell_mutation(
                game_id=plan.game_id
            )
        self._session.flush()
        return LegacyConversionSourceResult(
            source_image_id=plan.source_image_id,
            source_geometry_revision_id=stored_source_geometry.id,
            boards=tuple(results),
        )

    def _legacy_board_sequences(self, *, game_id: UUID, source_image_id: UUID) -> set[int]:
        sequences: set[int] = set()
        for board_sequence, item_sequence, resolved in self._session.execute(
            select(
                RecognizedBoardModel.sequence_number,
                ImageReviewItemModel.sequence_number,
                ImageReviewItemModel.resolved_value,
            )
            .outerjoin(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                RecognizedBoardModel.source_image_id == source_image_id,
                RecognizedBoardModel.asset_mode == _LEGACY_ASSET_MODE,
            )
        ):
            for value in (
                board_sequence,
                item_sequence,
                resolved.get("sequenceNumber") if isinstance(resolved, Mapping) else None,
            ):
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    sequences.add(value)
        return sequences

    def _legacy_board_plan(
        self,
        board: RecognizedBoardModel,
        *,
        game_id: UUID,
        source: SourceImageModel,
        geometry: ImageSourceGeometryRevisionModel | None,
        configuration: DirectCellRenderConfiguration | None,
        source_problems: tuple[str, ...],
        lock: bool,
    ) -> LegacyConversionBoardPlan:
        problems: list[str] = list(source_problems)
        item_statement = select(ImageReviewItemModel).where(
            ImageReviewItemModel.recognized_board_id == board.id
        )
        if lock:
            item_statement = item_statement.with_for_update()
        item = self._session.scalar(item_statement)
        sequence_number: int | None = None
        if item is None:
            problems.append("LEGACY_CONVERSION_REVIEW_ITEM_MISSING")
        else:
            sequence_number = item.sequence_number or board.sequence_number
        if sequence_number is None:
            problems.append("LEGACY_CONVERSION_SEQUENCE_MISSING")
        record = self._session.scalar(
            select(ImageBoardGeometryRevisionModel).where(
                ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
                ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
            )
        )
        corners = _legacy_corners(record)
        if corners is None:
            problems.append("LEGACY_CONVERSION_REVISION_MISSING")
        cells = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.recognized_board_id == board.id,
                )
                .order_by(ImageSymbolReviewCellModel.cell_index)
            )
        )
        if cells and (
            item is None
            or [int(cell.cell_index) for cell in cells] != list(range(15))
            or any(
                cell.review_item_id != item.id
                or cell.geometry_revision != board.geometry_revision
                or cell.asset_mode != _LEGACY_ASSET_MODE
                for cell in cells
            )
        ):
            problems.append("LEGACY_CONVERSION_CELLS_INCOMPLETE")
        qualification: GeometryQualification | None = None
        if board.geometry_qualification is not None:
            try:
                qualification = GeometryQualification.from_dict(board.geometry_qualification)
            except GeometryQualificationError:
                problems.append("LEGACY_CONVERSION_QUALIFICATION_INVALID")
        sequence_geometry_revision = (
            None
            if sequence_number is None
            else self._sequence_cell_revision(
                game_id=game_id, sequence_number=sequence_number, lock=lock
            )
        )
        if (
            geometry is not None
            and sequence_number is not None
            and (
                board.position_index not in geometry.active_board_slots
                or geometry.sequence_range_start + board.position_index != sequence_number
            )
        ):
            problems.append("LEGACY_CONVERSION_SOURCE_GEOMETRY_INVALID")
        target: LegacyConversionTarget | None = None
        if (
            not problems
            and item is not None
            and geometry is not None
            and configuration is not None
            and corners is not None
            and sequence_number is not None
        ):
            context = VirtualGridGeometryContext(
                game_id=game_id,
                import_job_id=source.import_job_id,
                review_item_id=item.id,
                recognized_board_id=board.id,
                pending_geometry_id=None,
                source_image_id=source.id,
                file_execution_key=source.file_execution_key,
                position_index=int(board.position_index),
                sequence_number=int(sequence_number),
                source_relative_path=source.relative_path,
                source_checksum_sha256=source.checksum_sha256,
                raw_width=int(cast(int, source.raw_width)),
                raw_height=int(cast(int, source.raw_height)),
                oriented_width=int(cast(int, source.oriented_width)),
                oriented_height=int(cast(int, source.oriented_height)),
                exif_orientation=source.exif_orientation,
                normalized_pixel_checksum_sha256=cast(str, source.normalized_pixel_checksum_sha256),
                normalization_adapter_version=cast(str, source.normalization_adapter_version),
                pipeline_fingerprint=board.pipeline_fingerprint,
                resolution_revision=int(item.resolution_revision),
                geometry_revision=int(board.geometry_revision),
                topology=BoardTopology(rows=board.grid_rows or 3, columns=board.grid_columns or 5),
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
                sequence_geometry_revision=sequence_geometry_revision,
            )
            problems.extend(
                _legacy_render_problems(context, corners, qualification, owns_cells=bool(cells))
            )
            if not problems:
                target = LegacyConversionTarget(
                    context=context, corners=corners, geometry_qualification=qualification
                )
        human_sources = {
            SymbolCellAssignmentSource.HUMAN.value,
            SymbolCellAssignmentSource.BOARD_DECISION.value,
        }
        return LegacyConversionBoardPlan(
            recognized_board_id=board.id,
            review_item_id=None if item is None else item.id,
            source_image_id=source.id,
            item_status=None if item is None else item.status,
            sequence_number=sequence_number,
            geometry_revision=int(board.geometry_revision),
            sequence_geometry_revision=sequence_geometry_revision,
            owned_cell_count=len(cells),
            assigned_cell_count=sum(cell.assigned_symbol_id is not None for cell in cells),
            human_decision_cell_count=sum(
                cell.review_state == SymbolCellReviewState.APPROVED.value
                or cell.assignment_source in human_sources
                for cell in cells
            ),
            approved_cell_count=sum(
                cell.review_state == SymbolCellReviewState.APPROVED.value for cell in cells
            ),
            target=target,
            problems=tuple(dict.fromkeys(problems)),
        )

    def _convert_current_cells(
        self,
        *,
        context: VirtualGridGeometryContext,
        entry: PreparedVirtualGridGeometry,
        previous_revision: int,
        revision_number: int,
        source_geometry_revision_id: UUID,
        actor: str,
    ) -> tuple[int, int]:
        """Move a converted board's current cells to their virtual render.

        Decision rule (TASK-0791, documented in D-467): the conversion keeps
        the corners, so it is not a geometry change.  Unlike
        ``_recheck_after_virtual_recrop`` (D-462 R5/R6, which returns an
        approval of other pixels to verification) every human decision stays:
        ``assigned_symbol_id``, ``assignment_source``, ``review_state``,
        ``quality_issue``, ``verification_outcome``/``verified_symbol_id_v2``
        and ``last_reviewed_by``/``last_reviewed_at``.  An approval is rebound
        to the new render of the same corners (``approved_*``), a pending
        cell's historical approval columns stay as history.  Every cell gets
        a ``geometry_invalidated`` event with both provenances.
        """

        cells = tuple(
            self._session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == context.game_id,
                    ImageSymbolReviewCellModel.review_item_id == context.review_item_id,
                    ImageSymbolReviewCellModel.recognized_board_id == context.recognized_board_id,
                )
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .with_for_update()
            )
        )
        if not cells:
            return 0, 0
        rendered_by_index = {cell.cell_index: cell for cell in entry.cells}
        if (
            [int(cell.cell_index) for cell in cells] != list(range(context.topology.cell_count))
            or set(rendered_by_index) != {int(cell.cell_index) for cell in cells}
            or any(
                cell.asset_mode != _LEGACY_ASSET_MODE or cell.geometry_revision != previous_revision
                for cell in cells
            )
        ):
            raise ImageGridReviewError(
                "LEGACY_CONVERSION_CELLS_INCOMPLETE",
                "A converted legacy board must own every current cell of its revision.",
            )
        count_state = self._session.get(
            ImageSymbolReviewStateModel, context.game_id, with_for_update=True
        )
        count_before = tuple(_CountedCellState.from_model(cell) for cell in cells)
        decisions_before = tuple(_cell_decision(cell) for cell in cells)
        human_sources = {
            SymbolCellAssignmentSource.HUMAN.value,
            SymbolCellAssignmentSource.BOARD_DECISION.value,
        }
        preserved = 0
        for cell in cells:
            rendered = rendered_by_index[int(cell.cell_index)]
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
            cell.cropper_version = entry.cropper_version
            if cell.review_state == SymbolCellReviewState.APPROVED.value:
                cell.approved_crop_sample_id = cell.crop_sample_id
                cell.approved_crop_checksum_sha256 = cell.crop_checksum_sha256
                cell.approved_geometry_revision = cell.geometry_revision
                cell.approved_asset_mode = cell.asset_mode
                cell.approved_source_geometry_revision_id = cell.source_geometry_revision_id
                cell.approved_render_spec_checksum_sha256 = cell.render_spec_checksum_sha256
                cell.approved_rendered_pixel_checksum_sha256 = cell.rendered_pixel_checksum_sha256
            if (
                cell.review_state == SymbolCellReviewState.APPROVED.value
                or cell.assignment_source in human_sources
            ):
                preserved += 1
            cell.revision += 1
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
        if tuple(_cell_decision(cell) for cell in cells) != decisions_before:
            raise ImageGridReviewError(
                "LEGACY_CONVERSION_DECISION_DRIFT",
                "The legacy conversion must not change a human cell decision.",
            )
        if count_state is not None:
            _apply_count_deltas(
                count_state,
                before=count_before,
                after=tuple(_CountedCellState.from_model(cell) for cell in cells),
            )
        return len(cells), preserved

    def _occupied_pending_slots(
        self,
        entries: tuple[PreparedVirtualGridGeometry, ...],
        locked_pending: Mapping[UUID, ImageBoardGeometryPendingModel],
    ) -> tuple[ImageBoardGeometryPendingModel, ...]:
        occupied: list[ImageBoardGeometryPendingModel] = []
        for entry in entries:
            pending = locked_pending.get(entry.context.target_id)
            if pending is None or pending.status != "pending":
                continue
            board_id = self._session.scalar(
                select(RecognizedBoardModel.id)
                .where(
                    RecognizedBoardModel.source_image_id == pending.source_image_id,
                    RecognizedBoardModel.position_index == pending.position_index,
                )
                .with_for_update()
            )
            if board_id is not None:
                occupied.append(pending)
        return tuple(occupied)

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

    def _reopen_resolved_revision(
        self,
        prepared: PreparedVirtualGridGeometry,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> None:
        # Reopen while the old selector/render is still coherent. Keeping a
        # resolved layout would publish symbols whose pixels have just changed.
        # D-462: this applies to every manual geometry, qualified or not; the
        # board closes again from its cells if every verification survives.
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

    def _add_render_manifest(
        self, record: ImageBoardGeometryRevisionModel, *, game_id: UUID
    ) -> None:
        """Persist the revision's render manifest in the same transaction (D-467).

        A revision without renderable cells (every cell outside the source)
        gets no manifest row: no manifest row <=> no cells.
        """

        if isinstance(record.virtual_render_spec, dict) and record.virtual_render_spec.get(
            "cells"
        ) in ([], ()):
            return
        if (
            record.virtual_render_spec is None
            or record.virtual_render_spec_checksum_sha256 is None
            or record.source_geometry_revision_id is None
        ):
            raise ImageGridReviewError(
                "BOARD_RENDER_MANIFEST_PROVENANCE_INVALID",
                "A virtual geometry revision needs a render spec and source geometry.",
            )
        try:
            manifest = revision_render_manifest(
                recognized_board_id=record.recognized_board_id,
                geometry_revision=record.revision,
                virtual_render_spec=record.virtual_render_spec,
                virtual_render_spec_checksum_sha256=record.virtual_render_spec_checksum_sha256,
            )
        except BoardRenderManifestError as error:
            raise ImageGridReviewError(error.code, error.message) from error
        add_board_render_manifest(
            self._session,
            game_id=game_id,
            manifest=manifest,
            source_geometry_revision_id=record.source_geometry_revision_id,
            extractor_version=record.cropper_version,
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
        cells_prediction = _pending_slot_cells_prediction(entry)
        predictions = cast(list[dict[str, object]], cells_prediction["cells"])
        # TASK-0702 handoff rule: continue the sequence's current revision.
        revision_number = context.next_geometry_revision
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
            cells_prediction=cells_prediction,
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
        # D-467 (TASK-0790): the render manifest of the new revision (added
        # below) is the only per-cell record; no cell observation is written.
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
        self._add_render_manifest(record, game_id=context.game_id)
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
            pixels_changed = (
                cell.rendered_pixel_checksum_sha256 != rendered.rendered_pixel_checksum_sha256
                if cell.rendered_pixel_checksum_sha256 is not None
                else cell.crop_checksum_sha256 != rendered.crop_checksum_sha256
            )
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
            _recheck_after_virtual_recrop(
                cell,
                pixels_changed=pixels_changed,
                active_symbol_ids_by_code=active_symbol_ids_by_code,
            )
            try:
                # The same mapping as the write-through: a pending human
                # suggestion after a recrop is `requires_review` (D-462 R6).
                verification = _verification_v2(
                    review_state=cell.review_state,
                    quality_issue=cell.quality_issue,
                    assigned_symbol_id=cell.assigned_symbol_id,
                    prediction_symbol_code=cell.prediction_symbol_code,
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
        # D-462 R8: search evidence is read from these cell rows; refresh it
        # after they changed, in the same transaction.
        self._session.flush()
        SqlAlchemyBoardSearchProjectionRepository(self._session).sync_review_item(
            _require_review_item_id(context)
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
        symbol_model = None if job is None else job.input_payload.get("symbol_model")
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
        sequence_geometry_revision = self._sequence_cell_revision(
            game_id=game_id,
            sequence_number=int(pending.sequence_number),
            lock=lock,
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
            pending_symbol_model=(
                dict(cast(Mapping[str, object], symbol_model))
                if isinstance(symbol_model, Mapping)
                else None
            ),
            sequence_geometry_revision=sequence_geometry_revision,
        )

    def _sequence_cell_revision(
        self,
        *,
        game_id: UUID,
        sequence_number: int,
        lock: bool,
    ) -> int | None:
        """Common revision of the sequence's 15 current cells, if any (TASK-0702).

        A deferred slot can become the newest owner of a sequence whose current
        projection belongs to another import.  The logical board then continues
        from that projection's revision.  An incomplete or inconsistent
        projection returns ``None`` and keeps the coordinator's fail-closed
        validation; under ``lock`` the rows are locked so the saved revision
        cannot drift after the sequence lock was taken.
        """

        _bind_game_store(self._session, game_id)
        statement = select(ImageSymbolReviewCellModel.geometry_revision).where(
            ImageSymbolReviewCellModel.game_id == game_id,
            ImageSymbolReviewCellModel.sequence_number == sequence_number,
        )
        if lock:
            statement = statement.with_for_update()
        revisions = tuple(int(value) for value in self._session.scalars(statement))
        if len(revisions) != 15 or len(set(revisions)) != 1:
            return None
        return revisions[0]

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
            expected_indices = set(
                available_cell_indices(
                    unavailable_cell_indices=board.unavailable_cell_indices,
                    geometry_qualification=board.geometry_qualification,
                    asset_mode=board.asset_mode,
                    cell_count=topology.cell_count,
                )
            )
        # Before the first backfill a valid board can have no review cells.
        # Read only its immutable provenance; GET/preview never initializes state.
        initial_configurations: tuple[DirectCellRenderConfiguration, ...] | None = None
        if not review_cells and expected_indices:
            if board.geometry_revision == 0:
                # D-467: the revision-0 render specs live in the board's
                # render manifest (cells sorted by ``cellIndex``).
                base_manifest = load_current_render_manifest(
                    self._session, game_id=document.game_id, board=board
                )
                if (
                    base_manifest is not None
                    and set(base_manifest.cell_indices) == expected_indices
                ):
                    initial_configurations = tuple(
                        _configuration(cell.get("renderSpec")) for cell in base_manifest.cells
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


_UNCLASSIFIED_MANUAL_MODEL_VERSION = "manual-unclassified-v1"

# The historical file-crop mode converted by TASK-0791 (D-467 S6).  After
# migration 0135 no board or review cell can carry it; the conversion is the
# only reader of the value outside historical migrations.
_LEGACY_ASSET_MODE = "legacy_file"
_LEGACY_CONVERSION_KEY_PREFIX = "legacy-board-conversion-v1"
# Board context the Reviewer reads from ``board_geometry`` (sequence label,
# source context, filename sequence) that the source slot does not carry.
_RETAINED_LEGACY_BOARD_KEYS = (
    "attestedRangeEnd",
    "attestedRangeStart",
    "displayAssetKind",
    "sequenceLabelQuad",
    "sequenceSource",
    "sourceContextBounds",
)


def _legacy_source_problems(
    source: SourceImageModel,
    job: JobModel | None,
    geometry: ImageSourceGeometryRevisionModel | None,
    *,
    game_id: UUID,
) -> tuple[str, ...]:
    if geometry is None:
        return ("LEGACY_CONVERSION_SOURCE_GEOMETRY_MISSING",)
    if (
        job is None
        or job.game_id != game_id
        or source.raw_width is None
        or source.raw_height is None
        or source.oriented_width is None
        or source.oriented_height is None
        or source.normalized_pixel_checksum_sha256 is None
        or source.normalization_adapter_version is None
    ):
        return ("LEGACY_CONVERSION_SOURCE_METADATA_INCOMPLETE",)
    if geometry.source_checksum_sha256 != source.checksum_sha256 or list(
        geometry.active_board_slots
    ) != list(range(len(geometry.board_geometries))):
        return ("LEGACY_CONVERSION_SOURCE_GEOMETRY_INVALID",)
    return ()


def _legacy_corners(
    record: ImageBoardGeometryRevisionModel | None,
) -> tuple[ImageReviewGeometryPoint, ...] | None:
    if record is None or record.asset_mode != _LEGACY_ASSET_MODE:
        return None
    raw = record.corners
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    points: list[ImageReviewGeometryPoint] = []
    for point in raw:
        if (
            not isinstance(point, dict)
            or type(point.get("x")) is not int
            or type(point.get("y")) is not int
        ):
            return None
        points.append(ImageReviewGeometryPoint(x=int(point["x"]), y=int(point["y"])))
    return tuple(points)


def _legacy_render_problems(
    context: VirtualGridGeometryContext,
    corners: tuple[ImageReviewGeometryPoint, ...],
    qualification: GeometryQualification | None,
    *,
    owns_cells: bool,
) -> tuple[str, ...]:
    """Pure geometry checks that the in-memory render would otherwise fail late."""

    quad = SourceQuad(
        corners=cast(
            tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
            tuple(SourcePoint(x=point.x, y=point.y) for point in corners),
        )
    )
    bounds = SourceImageBounds(context.oriented_width, context.oriented_height)
    try:
        if qualification is None:
            if unavailable_source_cell_indices(quad, source=bounds, topology=context.topology):
                return ("LEGACY_CONVERSION_PARTIAL_UNDECLARED",)
            return ()
        resolved = resolve_manual_geometry_qualification(
            quad=quad, source=bounds, topology=context.topology, qualification=qualification
        )
    except ImageGeometryContractError:
        return ("LEGACY_CONVERSION_QUALIFICATION_INVALID",)
    if owns_cells and resolved.fully_unavailable_cell_indices:
        # The cell would lose its render; that is a decision for an operator,
        # not for an asset-mode conversion.
        return ("LEGACY_CONVERSION_CELL_OUTSIDE_SOURCE",)
    return ()


def _retain_legacy_board_context(
    geometry: Mapping[str, object], previous: Mapping[str, object]
) -> dict[str, object]:
    value = dict(geometry)
    for key in _RETAINED_LEGACY_BOARD_KEYS:
        if key not in value and previous.get(key) is not None:
            value[key] = previous[key]
    return value


def _cell_decision(cell: ImageSymbolReviewCellModel) -> tuple[object, ...]:
    return (
        cell.assigned_symbol_id,
        cell.assignment_source,
        cell.review_state,
        cell.quality_issue,
        cell.verification_outcome,
        cell.verified_symbol_id_v2,
        cell.last_reviewed_by,
        cell.last_reviewed_at,
        cell.source_available,
        cell.source_visibility,
    )


def _pending_slot_cells_prediction(entry: PreparedVirtualGridGeometry) -> dict[str, object]:
    """Predictions aligned with the rendered cells of a resolved deferred slot.

    With a configured symbol predictor every rendered cell carries the pinned
    import model's prediction; otherwise the cells stay unclassified (``?``).
    """

    prediction = entry.slot_prediction
    if prediction is None:
        return {
            "cells": [
                {
                    "alternatives": [{"confidence": 1.0, "symbolCode": "?"}],
                    "columnIndex": cell.column_index,
                    "confidence": 0.0,
                    "rowIndex": cell.row_index,
                    "symbolCode": "?",
                }
                for cell in entry.cells
            ],
            "modelVersion": _UNCLASSIFIED_MANUAL_MODEL_VERSION,
        }
    by_position = {
        (cell.get("rowIndex"), cell.get("columnIndex")): cell for cell in prediction.cells
    }
    if len(by_position) != len(prediction.cells) or set(by_position) != {
        (cell.row_index, cell.column_index) for cell in entry.cells
    }:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_PREDICTION_CELLS_INVALID",
            "The deferred slot predictions do not match its rendered cells.",
        )
    payload = prediction.to_cells_prediction()
    payload["cells"] = [
        dict(by_position[(cell.row_index, cell.column_index)]) for cell in entry.cells
    ]
    return payload


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


def _recheck_after_virtual_recrop(
    cell: ImageSymbolReviewCellModel,
    *,
    pixels_changed: bool,
    active_symbol_ids_by_code: dict[str, UUID],
) -> None:
    """Apply D-462 R5/R6 to a cell that already carries its new render.

    A saved geometry resolves a grid report. A verification survives only for
    the same pixels, and its approval is then rebound to the current render;
    otherwise the human label stays as a pending suggestion, the old approval
    remains as history and pixel-bound flags do not carry over.
    """

    human_sources = {
        SymbolCellAssignmentSource.HUMAN.value,
        SymbolCellAssignmentSource.BOARD_DECISION.value,
    }
    if cell.quality_issue == SymbolCellQualityIssue.GRID_ISSUE.value:
        cell.quality_issue = None
        if pixels_changed or cell.assignment_source not in human_sources:
            cell.assignment_source = SymbolCellAssignmentSource.MODEL.value
            cell.assigned_symbol_id = active_symbol_ids_by_code.get(
                cell.prediction_symbol_code or ""
            )
        return
    if cell.review_state == SymbolCellReviewState.APPROVED.value:
        if symbol_cell_approval_pixels_changed(
            asset_mode=cell.asset_mode,
            crop_checksum_sha256=cell.crop_checksum_sha256,
            approved_crop_checksum_sha256=cell.approved_crop_checksum_sha256,
            rendered_pixel_checksum_sha256=cell.rendered_pixel_checksum_sha256,
            approved_rendered_pixel_checksum_sha256=cell.approved_rendered_pixel_checksum_sha256,
        ):
            cell.review_state = SymbolCellReviewState.PENDING.value
            cell.quality_issue = None
            return
        cell.approved_crop_sample_id = cell.crop_sample_id
        cell.approved_crop_checksum_sha256 = cell.crop_checksum_sha256
        cell.approved_geometry_revision = cell.geometry_revision
        cell.approved_asset_mode = cell.asset_mode
        cell.approved_source_geometry_revision_id = cell.source_geometry_revision_id
        cell.approved_render_spec_checksum_sha256 = cell.render_spec_checksum_sha256
        cell.approved_rendered_pixel_checksum_sha256 = cell.rendered_pixel_checksum_sha256
        return
    if pixels_changed and cell.assignment_source in human_sources:
        cell.quality_issue = None


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
