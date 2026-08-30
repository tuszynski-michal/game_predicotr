"""PostgreSQL projections for versioned image stage results and review staging."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.image_geometry_v2 import SOURCE_COORDINATE_SPACE
from game_predictor_api.domain.jobs import require_active_job_lease
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    v2_render_identity_from_spec,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_geometry_v2_repository import (
    ImageGeometryPersistenceError,
    SourceGeometryRevisionInput,
    SqlAlchemyImageSourceGeometryRepository,
)
from game_predictor_api.storage.image_review_repository import (
    acquire_image_review_sequence_locks,
    acquire_image_sequence_locks,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.job_repository import job_from_record
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageLayoutStagingRowModel,
    ImagePipelineStageResultModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    ImageSequenceAlternativeModel,
    ImageSequenceCanonicalModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolPredictionRevisionModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)
from game_predictor_api.storage.pending_sequence_ownership import (
    create_owned_pending_review_item,
)
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobHandlerError

from .orchestration import ImageBatchCandidate
from .pipeline_contract import (
    PIPELINE_STAGES,
    canonical_json_bytes,
    validate_file_checkpoint,
)
from .pipeline_execution import (
    ContinuityIssue,
    StoredImageStageResult,
    continuity_issues,
)


class ImagePipelineStoreError(JobHandlerError):
    """Stable persistence or resolution error."""


class SqlAlchemyImagePipelineStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def stage_results(
        self,
        file_execution_key: str,
    ) -> Mapping[str, StoredImageStageResult]:
        with self._session_factory() as session:
            records = session.scalars(
                select(ImagePipelineStageResultModel)
                .where(ImagePipelineStageResultModel.file_execution_key == file_execution_key)
                .order_by(ImagePipelineStageResultModel.created_at)
            ).all()
            return {
                record.stage: StoredImageStageResult(
                    adapter_version=record.adapter_version,
                    payload=dict(record.result_payload),
                )
                for record in records
            }

    def save_stage_result(
        self,
        candidate: ImageBatchCandidate,
        *,
        stage: str,
        adapter_version: str,
        payload: Mapping[str, object],
    ) -> StoredImageStageResult:
        job_id, lease_token, executed_at = _execution_context(candidate)
        with self._session_factory() as session, session.begin():
            _require_candidate_lease(
                session,
                candidate,
                job_id=job_id,
                lease_token=lease_token,
                checked_at=executed_at,
            )
            key = {
                "file_execution_key": candidate.execution.file_execution_key,
                "stage": stage,
            }
            record = session.get(
                ImagePipelineStageResultModel,
                key,
                with_for_update=True,
            )
            if record is None:
                record = ImagePipelineStageResultModel(
                    file_execution_key=candidate.execution.file_execution_key,
                    stage=stage,
                    adapter_version=adapter_version,
                    result_payload=dict(payload),
                    created_at=executed_at,
                )
                session.add(record)
                session.flush()
            elif record.adapter_version != adapter_version or canonical_json_bytes(
                record.result_payload
            ) != canonical_json_bytes(payload):
                raise ImagePipelineStoreError(
                    "IMAGE_STAGE_RESULT_CONFLICT",
                    "An immutable image stage result already has different content.",
                )
            return StoredImageStageResult(
                adapter_version=record.adapter_version,
                payload=dict(record.result_payload),
            )

    def project_source(
        self,
        candidate: ImageBatchCandidate,
        *,
        discovery: Mapping[str, object],
    ) -> None:
        job_id, lease_token, executed_at = _execution_context(candidate)
        width = cast(int, discovery["width"])
        height = cast(int, discovery["height"])
        with self._session_factory() as session, session.begin():
            _require_candidate_lease(
                session,
                candidate,
                job_id=job_id,
                lease_token=lease_token,
                checked_at=executed_at,
            )
            source = session.scalar(
                select(SourceImageModel)
                .where(
                    SourceImageModel.import_job_id == job_id,
                    SourceImageModel.file_execution_key == candidate.execution.file_execution_key,
                )
                .with_for_update()
            )
            if source is None:
                session.add(
                    SourceImageModel(
                        import_job_id=job_id,
                        file_execution_key=candidate.execution.file_execution_key,
                        relative_path=candidate.source_relative_path,
                        checksum_sha256=candidate.execution.source_checksum_sha256,
                        width=width,
                        height=height,
                        status="processing",
                        created_at=executed_at,
                    )
                )
                session.flush()
                return
            if (
                source.relative_path != candidate.source_relative_path
                or source.checksum_sha256 != candidate.execution.source_checksum_sha256
                or source.width != width
                or source.height != height
            ):
                raise ImagePipelineStoreError(
                    "IMAGE_SOURCE_PROJECTION_CONFLICT",
                    "The source image projection differs from its discovery result.",
                )

    def project_source_metadata(
        self,
        candidate: ImageBatchCandidate,
        *,
        normalization: StoredImageStageResult,
    ) -> None:
        payload = normalization.payload
        if "normalizedPixelChecksumSha256" not in payload:
            return
        job_id, lease_token, executed_at = _execution_context(candidate)
        with self._session_factory() as session, session.begin():
            _require_candidate_lease(
                session,
                candidate,
                job_id=job_id,
                lease_token=lease_token,
                checked_at=executed_at,
            )
            source = _locked_source(session, job_id, candidate.execution.file_execution_key)
            expected = {
                "raw_width": cast(int, payload["sourceWidth"]),
                "raw_height": cast(int, payload["sourceHeight"]),
                "oriented_width": cast(int, payload["width"]),
                "oriented_height": cast(int, payload["height"]),
                "exif_orientation": cast(int | None, payload.get("exifOrientation")),
                "coordinate_space": SOURCE_COORDINATE_SPACE,
                "normalization_adapter_version": normalization.adapter_version,
                "normalized_pixel_checksum_sha256": cast(
                    str, payload["normalizedPixelChecksumSha256"]
                ),
            }
            current = {key: getattr(source, key) for key in expected}
            if all(value is None for value in current.values()):
                for key, value in expected.items():
                    setattr(source, key, value)
            elif current != expected:
                raise ImagePipelineStoreError(
                    "IMAGE_SOURCE_COORDINATE_METADATA_CONFLICT",
                    "The immutable source coordinate metadata already differs.",
                )

    def project_source_geometry(
        self,
        candidate: ImageBatchCandidate,
        *,
        stage_results: Mapping[str, StoredImageStageResult],
    ) -> None:
        geometry_stage = stage_results.get("board_cell_geometry")
        normalization = stage_results.get("normalization")
        if geometry_stage is None or normalization is None:
            return
        structured_value = geometry_stage.payload.get("structuredGeometry")
        if not isinstance(structured_value, Mapping):
            return
        structured = cast(Mapping[str, object], structured_value)
        job_id, lease_token, executed_at = _execution_context(candidate)
        with self._session_factory() as session, session.begin():
            _require_candidate_lease(
                session,
                candidate,
                job_id=job_id,
                lease_token=lease_token,
                checked_at=executed_at,
            )
            source = _locked_source(session, job_id, candidate.execution.file_execution_key)
            job = session.get(JobModel, job_id)
            topology = cast(Mapping[str, object], structured["topology"])
            boards = tuple(
                dict(cast(Mapping[str, object], value))
                for value in cast(Sequence[object], structured["boards"])
            )
            if job is None or job.game_id is None:
                raise ImagePipelineStoreError(
                    "IMAGE_PIPELINE_GAME_MISSING",
                    "Structured geometry requires a game-scoped import.",
                )
            sequence_numbers = tuple(cast(int, board["sequenceNumber"]) for board in boards)
            try:
                SqlAlchemyImageSourceGeometryRepository(session).append(
                    SourceGeometryRevisionInput(
                        game_id=job.game_id,
                        source_image_id=source.id,
                        topology_rules_version_id=UUID(cast(str, topology["rulesVersionId"])),
                        sequence_range_start=min(sequence_numbers),
                        sequence_range_end=max(sequence_numbers),
                        active_board_slots=tuple(
                            cast(int, value)
                            for value in cast(Sequence[object], structured["activeBoardSlots"])
                        ),
                        source_checksum_sha256=cast(str, structured["sourceChecksumSha256"]),
                        normalized_pixel_checksum_sha256=cast(
                            str, structured["normalizedPixelChecksumSha256"]
                        ),
                        oriented_width=cast(int, structured["canonicalWidth"]),
                        oriented_height=cast(int, structured["canonicalHeight"]),
                        normalization_adapter_version=normalization.adapter_version,
                        global_initialization=dict(
                            cast(Mapping[str, object], structured["globalInitialization"])
                        ),
                        board_geometries=boards,
                        engine_kind="structured_opencv_v1",
                        engine_version=cast(str, structured["engineVersion"]),
                        geometry_source="auto",
                        status=(
                            "accepted"
                            if structured["status"] == "ready"
                            and structured.get("rolloutMode") == "structured_default"
                            else "needs_review"
                        ),
                        geometry_checksum_sha256=cast(str, structured["resultChecksumSha256"]),
                        processing_time_ms=None,
                        warnings=tuple(
                            {"reasonCode": value}
                            for value in cast(Sequence[object], structured["reasonCodes"])
                        ),
                        created_by="system:image-pipeline-v0.10",
                    )
                )
            except ImageGeometryPersistenceError as error:
                raise ImagePipelineStoreError(error.code, str(error)) from error

    def project_recognition(
        self,
        candidate: ImageBatchCandidate,
        *,
        stage_results: Mapping[str, StoredImageStageResult],
    ) -> None:
        job_id, lease_token, executed_at = _execution_context(candidate)
        required = {
            "board_detection",
            "board_crops",
            "sequence_ocr",
            "symbol_inference",
        }
        if not required.issubset(stage_results):
            raise ImagePipelineStoreError(
                "IMAGE_RECOGNITION_STAGE_MISSING",
                "Recognition projection requires geometry, crops, OCR and symbols.",
            )
        detection = _boards_by_position(stage_results["board_detection"].payload)
        crops = _boards_by_position(stage_results["board_crops"].payload)
        sequences = _boards_by_position(stage_results["sequence_ocr"].payload)
        symbols = _boards_by_position(stage_results["symbol_inference"].payload)
        if "board_cell_geometry" in stage_results:
            # v20 persists failed boards in the dedicated deferred projection.
            # Only positions with verified 15-cell crops may reach recognition.
            detection = {position: detection[position] for position in crops}
        if not (detection.keys() == crops.keys() == sequences.keys() == symbols.keys()):
            raise ImagePipelineStoreError(
                "IMAGE_RECOGNITION_POSITION_CONFLICT",
                "Board positions differ between persisted image stages.",
            )
        model_version = cast(str, stage_results["symbol_inference"].payload["modelVersion"])
        crop_payload = stage_results["board_crops"].payload
        symbol_payload = stage_results["symbol_inference"].payload
        virtual_shadow_crops = (
            _boards_by_position(cast(Mapping[str, object], crop_payload["virtualShadow"]))
            if isinstance(crop_payload.get("virtualShadow"), Mapping)
            else {}
        )
        virtual_shadow_symbols = (
            _boards_by_position(cast(Mapping[str, object], symbol_payload["virtualShadow"]))
            if isinstance(symbol_payload.get("virtualShadow"), Mapping)
            else {}
        )
        with self._session_factory() as session, session.begin():
            _require_candidate_lease(
                session,
                candidate,
                job_id=job_id,
                lease_token=lease_token,
                checked_at=executed_at,
            )
            source = _locked_source(session, job_id, candidate.execution.file_execution_key)
            job = session.get(JobModel, job_id)
            if job is None or job.game_id is None:
                raise ImagePipelineStoreError(
                    "IMAGE_PIPELINE_GAME_MISSING",
                    "The image import job has no game projection.",
                )
            geometry_checksum = _virtual_geometry_checksum(crop_payload)
            source_geometry = (
                session.scalar(
                    select(ImageSourceGeometryRevisionModel).where(
                        ImageSourceGeometryRevisionModel.source_image_id == source.id,
                        ImageSourceGeometryRevisionModel.geometry_checksum_sha256
                        == geometry_checksum,
                    )
                )
                if geometry_checksum is not None
                else None
            )
            if geometry_checksum is not None and source_geometry is None:
                raise ImagePipelineStoreError(
                    "IMAGE_SOURCE_GEOMETRY_PROJECTION_MISSING",
                    "Virtual recognition requires its persisted source geometry revision.",
                )
            projected_positions = 0
            changed_review_item_ids: set[UUID] = set()
            for position in sorted(detection):
                detected = detection[position]
                cropped = crops[position]
                sequence = sequences[position]
                symbol = symbols[position]
                sequence_number = sequence.get("normalizedNumber")
                canonical = None
                if isinstance(sequence_number, int) and not isinstance(sequence_number, bool):
                    normalized_sequence_number = sequence_number
                    canonical = session.scalar(
                        select(ImageSequenceCanonicalModel).where(
                            ImageSequenceCanonicalModel.game_id == job.game_id,
                            ImageSequenceCanonicalModel.sequence_number == sequence_number,
                        )
                    )
                if canonical is not None:
                    pending_duplicate_row = session.execute(
                        select(ImageReviewItemModel, RecognizedBoardModel)
                        .join(
                            RecognizedBoardModel,
                            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                        )
                        .where(
                            RecognizedBoardModel.source_image_id == source.id,
                            RecognizedBoardModel.position_index == position,
                            ImageReviewItemModel.status == "pending",
                        )
                        .with_for_update()
                    ).one_or_none()
                    if pending_duplicate_row is not None:
                        pending_duplicate, pending_board = pending_duplicate_row
                        resolved_value: dict[str, object] = {
                            "action": "superseded",
                            "canonicalImportJobId": str(canonical.import_job_id),
                            "canonicalReviewItemId": str(canonical.review_item_id),
                            "reason": "canonical_sequence_already_resolved",
                            "sequenceNumber": normalized_sequence_number,
                        }
                        actor = "system:canonical-import"
                        revision = pending_duplicate.resolution_revision + 1
                        idempotency_key = uuid5(
                            NAMESPACE_URL,
                            "image-review-superseded:"
                            f"{job.game_id}:{normalized_sequence_number}:"
                            f"{canonical.review_item_id}:{pending_duplicate.id}",
                        )
                        session.add(
                            ImageReviewResolutionEventModel(
                                review_item_id=pending_duplicate.id,
                                revision=revision,
                                idempotency_key=idempotency_key,
                                action="superseded",
                                command_sha256=_review_command_sha256(
                                    action="superseded",
                                    resolved_value=resolved_value,
                                    resolved_by=actor,
                                ),
                                resolved_value=resolved_value,
                                resolved_by=actor,
                                created_at=executed_at,
                            )
                        )
                        pending_duplicate.status = "superseded"
                        pending_duplicate.resolved_value = resolved_value
                        pending_duplicate.resolved_by = actor
                        pending_duplicate.resolved_at = executed_at
                        pending_duplicate.resolution_revision = revision
                        pending_board.status = "rejected"
                        session.execute(
                            delete(ImageLayoutStagingRowModel).where(
                                ImageLayoutStagingRowModel.review_item_id == pending_duplicate.id
                            )
                        )
                        changed_review_item_ids.add(pending_duplicate.id)
                    if (
                        canonical.source_checksum_sha256 != source.checksum_sha256
                        or canonical.import_job_id != job_id
                    ):
                        alternative_exists = session.scalar(
                            select(ImageSequenceAlternativeModel.id).where(
                                ImageSequenceAlternativeModel.game_id == job.game_id,
                                ImageSequenceAlternativeModel.sequence_number
                                == normalized_sequence_number,
                                ImageSequenceAlternativeModel.import_job_id == job_id,
                                ImageSequenceAlternativeModel.source_checksum_sha256
                                == source.checksum_sha256,
                            )
                        )
                        if alternative_exists is None:
                            session.add(
                                ImageSequenceAlternativeModel(
                                    game_id=job.game_id,
                                    sequence_number=normalized_sequence_number,
                                    import_job_id=job_id,
                                    source_checksum_sha256=source.checksum_sha256,
                                    source_relative_path=source.relative_path,
                                    reason="superseded_first_save_wins",
                                )
                            )
                    continue
                board = session.scalar(
                    select(RecognizedBoardModel)
                    .where(
                        RecognizedBoardModel.source_image_id == source.id,
                        RecognizedBoardModel.position_index == position,
                    )
                    .with_for_update()
                )
                prediction = {
                    "cells": list(cast(Sequence[object], symbol["cells"])),
                    "modelVersion": model_version,
                }
                board_geometry = _recognized_board_geometry(
                    detected=detected,
                    cropped=cropped,
                    sequence=sequence,
                )
                if board is None:
                    virtual = cropped.get("assetMode") == "virtual_source"
                    board = RecognizedBoardModel(
                        source_image_id=source.id,
                        position_index=position,
                        sequence_number_raw=cast(str, sequence["rawText"]),
                        sequence_number=cast(int | None, sequence["normalizedNumber"]),
                        sequence_confidence=float(cast(float, sequence["confidence"])),
                        board_geometry=board_geometry,
                        asset_mode="virtual_source" if virtual else "legacy_file",
                        source_geometry_revision_id=(
                            source_geometry.id if virtual and source_geometry is not None else None
                        ),
                        geometry_engine_name=(
                            cast(str, cropped["geometryEngineName"]) if virtual else None
                        ),
                        geometry_engine_version=(
                            cast(str, cropped["geometryEngineVersion"]) if virtual else None
                        ),
                        geometry_checksum_sha256=(
                            cast(str, cropped["geometryChecksumSha256"]) if virtual else None
                        ),
                        board_relative_path=(
                            None if virtual else cast(str, cropped["boardRelativePath"])
                        ),
                        board_checksum_sha256=(
                            None if virtual else cast(str, cropped["boardChecksumSha256"])
                        ),
                        cells_prediction=prediction,
                        board_confidence=float(cast(float, detected["confidence"])),
                        pipeline_fingerprint=candidate.execution.pipeline_fingerprint,
                        status="pending_review",
                        created_at=executed_at,
                        grid_rows=_optional_positive_integer(cropped.get("gridRows")),
                        grid_columns=_optional_positive_integer(cropped.get("gridColumns")),
                    )
                    session.add(board)
                    session.flush()
                else:
                    _require_same_board(
                        board,
                        candidate,
                        detected=detected,
                        cropped=cropped,
                        sequence=sequence,
                        prediction=prediction,
                    )
                cropper_version = cast(str, cropped["cropperVersion"])
                crop_cells = cast(Sequence[object], cropped["cells"])
                symbol_cells = cast(Sequence[object], symbol["cells"])
                for crop_value, prediction_value in zip(
                    crop_cells,
                    symbol_cells,
                    strict=True,
                ):
                    crop = cast(Mapping[str, object], crop_value)
                    cell_prediction = cast(Mapping[str, object], prediction_value)
                    _upsert_cell(
                        session,
                        board,
                        crop,
                        cell_prediction,
                        source_geometry_revision_id=(
                            source_geometry.id if source_geometry is not None else None
                        ),
                        cropper_version=cropper_version,
                        created_at=executed_at,
                    )
                review_item, ownership_changes = _upsert_review_item(
                    session,
                    board,
                    source,
                    job,
                    sequence,
                    detected,
                    cropped,
                    prediction,
                    created_at=executed_at,
                )
                changed_review_item_ids.update(ownership_changes)
                if review_item.status == "pending":
                    _append_prediction_revision(
                        session,
                        game_id=job.game_id,
                        job_id=job_id,
                        review_item=review_item,
                        board=board,
                        crop_board=cropped,
                        symbol_board=symbol,
                        symbol_payload=symbol_payload,
                        created_at=executed_at,
                    )
                    shadow_crop = virtual_shadow_crops.get(position)
                    shadow_symbol = virtual_shadow_symbols.get(position)
                    if shadow_crop is not None and shadow_symbol is not None:
                        _append_prediction_revision(
                            session,
                            game_id=job.game_id,
                            job_id=job_id,
                            review_item=review_item,
                            board=board,
                            crop_board=shadow_crop,
                            symbol_board=shadow_symbol,
                            symbol_payload=cast(
                                Mapping[str, object], symbol_payload["virtualShadow"]
                            ),
                            created_at=executed_at,
                        )
                    projected_positions += 1
            deferred_positions = _pending_board_geometry_count(
                session,
                job_id=job_id,
                source_image_id=source.id,
            )
            source.status = (
                "waiting_for_review" if projected_positions or deferred_positions else "completed"
            )
            source.processed_at = executed_at
            session.flush()
            SqlAlchemyBoardSearchProjectionRepository(session).sync_review_items(
                tuple(changed_review_item_ids)
            )
            coordinator = SymbolCellReviewWriteThroughCoordinator(session)
            for review_item_id in sorted(changed_review_item_ids, key=str):
                coordinator.synchronize_after_prediction_refresh(
                    game_id=job.game_id,
                    review_item_id=review_item_id,
                    actor="system:image-pipeline",
                )

    def pending_review_count(self, candidate: ImageBatchCandidate) -> int:
        job_id = _job_id(candidate)
        with self._session_factory() as session:
            source = _source(session, job_id, candidate.execution.file_execution_key)
            if source is None:
                return 0
            value = session.scalar(
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
            deferred = _pending_board_geometry_count(
                session,
                job_id=job_id,
                source_image_id=source.id,
            )
            return int(value or 0) + deferred

    def resolve_board(
        self,
        review_item_id: UUID,
        *,
        expected_revision: int,
        action: str,
        sequence_number: int | None,
        symbol_codes: Sequence[str],
        resolved_by: str,
        resolved_at: datetime,
        idempotency_key: UUID,
        reason: str | None = None,
    ) -> None:
        if action not in {"accepted", "corrected", "rejected"}:
            raise ImagePipelineStoreError(
                "IMAGE_REVIEW_ACTION_INVALID",
                "Image review action must accept, correct or reject a board.",
            )
        actor = resolved_by.strip()
        if not actor:
            raise ImagePipelineStoreError(
                "IMAGE_REVIEW_ACTOR_INVALID",
                "Image review requires a non-empty local administrator identity.",
            )
        if action == "rejected":
            if not reason or not reason.strip() or sequence_number is not None or symbol_codes:
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_REJECTION_INVALID",
                    "Rejected image review requires only a non-empty reason.",
                )
            resolved_value: dict[str, object] = {
                "action": action,
                "reason": reason.strip(),
            }
        else:
            if (
                not isinstance(sequence_number, int)
                or isinstance(sequence_number, bool)
                or sequence_number < 1
                or len(symbol_codes) != 15
                or any(not code.strip() for code in symbol_codes)
            ):
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_BOARD_INVALID",
                    "Accepted image review requires a positive number and 15 symbols.",
                )
            resolved_value = {
                "action": action,
                "sequenceNumber": sequence_number,
                "symbolCodes": list(symbol_codes),
            }
        with self._session_factory() as session, session.begin():
            game_id = session.scalar(
                select(JobModel.game_id)
                .join(SourceImageModel, SourceImageModel.import_job_id == JobModel.id)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.source_image_id == SourceImageModel.id,
                )
                .join(
                    ImageReviewItemModel,
                    ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
                )
                .where(ImageReviewItemModel.id == review_item_id)
            )
            if game_id is None:
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_GAME_MISSING",
                    "The image review item has no game context.",
                )
            acquire_image_review_sequence_locks(
                session,
                game_id=game_id,
                review_item_id=review_item_id,
                requested_sequence_number=sequence_number,
            )
            item = session.get(ImageReviewItemModel, review_item_id, with_for_update=True)
            if item is None:
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_ITEM_NOT_FOUND",
                    "The image review item does not exist.",
                )
            command_sha256 = _review_command_sha256(
                action=action,
                resolved_value=resolved_value,
                resolved_by=actor,
            )
            prior_event = session.scalar(
                select(ImageReviewResolutionEventModel).where(
                    ImageReviewResolutionEventModel.review_item_id == review_item_id,
                    ImageReviewResolutionEventModel.idempotency_key == idempotency_key,
                )
            )
            if prior_event is not None:
                if prior_event.command_sha256 == command_sha256:
                    return
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_IDEMPOTENCY_CONFLICT",
                    "The image review idempotency key already represents another command.",
                )
            if item.status != "pending":
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_ALREADY_RESOLVED",
                    "The image review item already has another decision.",
                )
            if item.resolution_revision != expected_revision:
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_REVISION_CONFLICT",
                    "The image review item was changed by another operation.",
                )
            board = session.get(
                RecognizedBoardModel,
                item.recognized_board_id,
                with_for_update=True,
            )
            if board is None:
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_BOARD_NOT_FOUND",
                    "The recognized board no longer exists.",
                )
            if action != "rejected":
                _require_active_symbol_codes(
                    session,
                    board,
                    symbol_codes,
                )
                predicted_codes = [
                    cast(str, cast(Mapping[str, object], value)["symbolCode"])
                    for value in cast(Sequence[object], board.cells_prediction["cells"])
                ]
                if action == "accepted" and (
                    list(symbol_codes) != predicted_codes
                    or sequence_number != board.sequence_number
                ):
                    raise ImagePipelineStoreError(
                        "IMAGE_REVIEW_ACCEPTED_VALUE_CHANGED",
                        "Accepted review must preserve the OCR number and predictions.",
                    )
                if (
                    action == "corrected"
                    and list(symbol_codes) == predicted_codes
                    and sequence_number == board.sequence_number
                ):
                    raise ImagePipelineStoreError(
                        "IMAGE_REVIEW_CORRECTION_EMPTY",
                        "Corrected review must change the number or at least one symbol.",
                    )
            revision = item.resolution_revision + 1
            session.add(
                ImageReviewResolutionEventModel(
                    review_item_id=item.id,
                    revision=revision,
                    idempotency_key=idempotency_key,
                    action=action,
                    command_sha256=command_sha256,
                    resolved_value=resolved_value,
                    resolved_by=actor,
                    created_at=resolved_at,
                )
            )
            item.status = action
            item.resolved_value = resolved_value
            item.resolved_by = actor
            item.resolved_at = resolved_at
            item.resolution_revision = revision
            board.status = action
            session.flush()
            projection = SqlAlchemyBoardSearchProjectionRepository(session)
            projection.sync_review_item(review_item_id)
            if isinstance(sequence_number, int) and not isinstance(sequence_number, bool):
                projection.sync_sequence_candidates(game_id, sequence_number)
            coordinator = SymbolCellReviewWriteThroughCoordinator(session)
            coordinator.synchronize_after_board_resolution(
                game_id=game_id,
                review_item_id=review_item_id,
                actor=actor,
            )
            coordinator.synchronize_after_projection_change(game_id=game_id)

    def materialize_resolved_staging(self, candidate: ImageBatchCandidate) -> int:
        job_id, lease_token, executed_at = _execution_context(candidate)
        with self._session_factory() as session, session.begin():
            _require_candidate_lease(
                session,
                candidate,
                job_id=job_id,
                lease_token=lease_token,
                checked_at=executed_at,
            )
            source = _locked_source(session, job_id, candidate.execution.file_execution_key)
            rows = session.execute(
                select(ImageReviewItemModel, RecognizedBoardModel)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .where(RecognizedBoardModel.source_image_id == source.id)
                .order_by(RecognizedBoardModel.position_index)
                .with_for_update()
            ).all()
            if any(item.status == "pending" for item, _board in rows):
                raise ImagePipelineStoreError(
                    "IMAGE_REVIEW_PENDING",
                    "A source cannot enter staging while a board is pending review.",
                )
            materialized = 0
            accepted = 0
            for item, board in rows:
                if item.status in {"rejected", "superseded"}:
                    continue
                accepted += 1
                resolution = cast(Mapping[str, object], item.resolved_value)
                symbol_codes = cast(Sequence[str], resolution["symbolCodes"])
                mobile_codes = _mobile_codes(session, source.import_job_id, symbol_codes)
                existing = session.get(
                    ImageLayoutStagingRowModel,
                    {
                        "import_job_id": job_id,
                        "recognized_board_id": board.id,
                    },
                    with_for_update=True,
                )
                sequence_number = cast(int, resolution["sequenceNumber"])
                if existing is None:
                    session.add(
                        ImageLayoutStagingRowModel(
                            import_job_id=job_id,
                            recognized_board_id=board.id,
                            review_item_id=item.id,
                            sequence_number=sequence_number,
                            cells=mobile_codes,
                            created_at=executed_at,
                        )
                    )
                    materialized += 1
                elif (
                    existing.review_item_id != item.id
                    or existing.sequence_number != sequence_number
                    or existing.cells != mobile_codes
                ):
                    raise ImagePipelineStoreError(
                        "IMAGE_STAGING_ROW_CONFLICT",
                        "An image staging row already has different accepted values.",
                    )
            source.status = "accepted" if accepted else "rejected"
            if not rows:
                source.status = "completed"
            source.processed_at = executed_at
            session.flush()
            return materialized

    def reopen_continuity_conflicts(
        self,
        candidate: ImageBatchCandidate,
    ) -> tuple[ContinuityIssue, ...]:
        job_id, lease_token, executed_at = _execution_context(candidate)
        with self._session_factory() as session, session.begin():
            _require_candidate_lease(
                session,
                candidate,
                job_id=job_id,
                lease_token=lease_token,
                checked_at=executed_at,
            )
            job = session.get(JobModel, job_id)
            if job is None or job.game_id is None:
                raise ImagePipelineStoreError(
                    "IMAGE_PIPELINE_GAME_MISSING",
                    "The image import job has no game projection.",
                )
            sequence_numbers = session.scalars(
                select(ImageLayoutStagingRowModel.sequence_number).where(
                    ImageLayoutStagingRowModel.import_job_id == job_id
                )
            ).all()
            acquire_image_sequence_locks(
                session,
                game_id=job.game_id,
                sequence_numbers=sequence_numbers,
            )
            rows = session.execute(
                select(
                    ImageLayoutStagingRowModel,
                    ImageReviewItemModel,
                    RecognizedBoardModel,
                    SourceImageModel,
                )
                .join(
                    ImageReviewItemModel,
                    ImageReviewItemModel.id == ImageLayoutStagingRowModel.review_item_id,
                )
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageLayoutStagingRowModel.recognized_board_id,
                )
                .join(
                    SourceImageModel,
                    SourceImageModel.id == RecognizedBoardModel.source_image_id,
                )
                .where(ImageLayoutStagingRowModel.import_job_id == job_id)
                .order_by(
                    ImageLayoutStagingRowModel.sequence_number,
                    RecognizedBoardModel.position_index,
                )
                .with_for_update()
            ).all()
            if not rows:
                return ()
            issues = continuity_issues(
                tuple(staging.sequence_number for staging, _item, _board, _source in rows)
            )
            if not issues:
                return ()
            affected_numbers = _affected_sequence_numbers(
                tuple(staging.sequence_number for staging, _item, _board, _source in rows),
                issues,
            )
            reason_codes = sorted({issue.code for issue in issues})
            affected_executions: set[str] = set()
            reopened_review_item_ids: set[UUID] = set()
            reopened_sequence_numbers: set[int] = set()
            for staging, item, board, source in rows:
                if staging.sequence_number not in affected_numbers:
                    continue
                revision = item.resolution_revision + 1
                resolved_value: dict[str, object] = {
                    "action": "reopened",
                    "reasonCodes": reason_codes,
                    "sequenceNumber": staging.sequence_number,
                }
                idempotency_key = uuid5(
                    NAMESPACE_URL,
                    f"image-continuity:{job_id}:{item.id}:{revision}:{','.join(reason_codes)}",
                )
                session.add(
                    ImageReviewResolutionEventModel(
                        review_item_id=item.id,
                        revision=revision,
                        idempotency_key=idempotency_key,
                        action="reopened",
                        command_sha256=_review_command_sha256(
                            action="reopened",
                            resolved_value=resolved_value,
                            resolved_by="system:continuity-validation",
                        ),
                        resolved_value=resolved_value,
                        resolved_by="system:continuity-validation",
                        created_at=executed_at,
                    )
                )
                item.status = "pending"
                item.resolved_value = None
                item.resolved_by = None
                item.resolved_at = None
                item.resolution_revision = revision
                board.status = "pending_review"
                source.status = "waiting_for_review"
                source.processed_at = executed_at
                affected_executions.add(source.file_execution_key)
                reopened_review_item_ids.add(item.id)
                reopened_sequence_numbers.add(staging.sequence_number)
                session.execute(
                    delete(ImageLayoutStagingRowModel).where(
                        ImageLayoutStagingRowModel.import_job_id == job_id,
                        ImageLayoutStagingRowModel.recognized_board_id == board.id,
                    )
                )
                session.execute(
                    delete(ImageSequenceCanonicalModel).where(
                        ImageSequenceCanonicalModel.game_id == job.game_id,
                        ImageSequenceCanonicalModel.sequence_number == staging.sequence_number,
                        ImageSequenceCanonicalModel.review_item_id == item.id,
                    )
                )
            for execution_key in affected_executions:
                association = session.get(
                    ImageImportJobFileModel,
                    {
                        "job_id": job_id,
                        "file_execution_key": execution_key,
                    },
                    with_for_update=True,
                )
                if association is None:
                    raise ImagePipelineStoreError(
                        "IMAGE_BATCH_FILE_NOT_LINKED",
                        "A conflicting review source is not linked to this import job.",
                    )
                checkpoint = validate_file_checkpoint(association.workflow_checkpoint_payload)
                automated_count = PIPELINE_STAGES.index("manual_review")
                association.workflow_checkpoint_payload = {
                    **checkpoint,
                    "completedStages": list(PIPELINE_STAGES[:automated_count]),
                    "nextStage": "manual_review",
                    "status": "waiting_for_review",
                }
                association.workflow_status = "waiting_for_review"
                association.review_required = True
                association.failed_stage = None
                association.error_code = None
                association.error_message = None
                association.last_failed_at = None
                association.updated_at = executed_at
            session.flush()
            projection = SqlAlchemyBoardSearchProjectionRepository(session)
            projection.sync_review_items(tuple(sorted(reopened_review_item_ids, key=str)))
            for sequence_number in sorted(reopened_sequence_numbers):
                projection.sync_sequence_candidates(
                    game_id=job.game_id, sequence_number=sequence_number
                )
            coordinator = SymbolCellReviewWriteThroughCoordinator(session)
            for review_item_id in sorted(reopened_review_item_ids, key=str):
                coordinator.synchronize_after_board_reopened(
                    game_id=job.game_id,
                    review_item_id=review_item_id,
                    actor="system:continuity-validation",
                )
            coordinator.synchronize_after_projection_change(game_id=job.game_id)
            return issues


def _review_command_sha256(
    *,
    action: str,
    resolved_value: Mapping[str, object],
    resolved_by: str,
) -> str:
    return sha256(
        canonical_json_bytes(
            {
                "action": action,
                "resolvedBy": resolved_by,
                "resolvedValue": dict(resolved_value),
            }
        )
    ).hexdigest()


def _affected_sequence_numbers(
    sequence_numbers: Sequence[int],
    issues: Sequence[ContinuityIssue],
) -> set[int]:
    available = sorted(set(sequence_numbers))
    affected = {
        issue.sequence_number
        for issue in issues
        if issue.code == "IMAGE_SEQUENCE_DUPLICATE" and issue.sequence_number is not None
    }
    for issue in issues:
        if issue.code != "IMAGE_SEQUENCE_GAP" or issue.sequence_number is None:
            continue
        lower = [value for value in available if value < issue.sequence_number]
        upper = [value for value in available if value > issue.sequence_number]
        if lower:
            affected.add(lower[-1])
        if upper:
            affected.add(upper[0])
    return affected


def _execution_context(candidate: ImageBatchCandidate) -> tuple[UUID, UUID, datetime]:
    if candidate.job_id is None or candidate.lease_token is None or candidate.executed_at is None:
        raise ImagePipelineStoreError(
            "IMAGE_PIPELINE_EXECUTION_CONTEXT_MISSING",
            "Image persistence requires job, lease and timestamp context.",
        )
    return candidate.job_id, candidate.lease_token, candidate.executed_at


def _job_id(candidate: ImageBatchCandidate) -> UUID:
    if candidate.job_id is None:
        raise ImagePipelineStoreError(
            "IMAGE_PIPELINE_JOB_MISSING",
            "Image pipeline projection requires a job identity.",
        )
    return candidate.job_id


def _pending_board_geometry_count(
    session: Session,
    *,
    job_id: UUID,
    source_image_id: UUID,
) -> int:
    value = session.scalar(
        select(func.count()).where(
            ImageBoardGeometryPendingModel.import_job_id == job_id,
            ImageBoardGeometryPendingModel.source_image_id == source_image_id,
            ImageBoardGeometryPendingModel.status == "pending",
        )
    )
    return int(value or 0)


def _require_candidate_lease(
    session: Session,
    candidate: ImageBatchCandidate,
    *,
    job_id: UUID,
    lease_token: UUID,
    checked_at: datetime,
) -> None:
    job = session.get(JobModel, job_id, with_for_update=True)
    if job is None:
        raise ImagePipelineStoreError(
            "IMAGE_PIPELINE_JOB_NOT_FOUND",
            "The image import job no longer exists.",
        )
    require_active_job_lease(
        job_from_record(job),
        lease_token=lease_token,
        checked_at=checked_at,
    )
    association = session.get(
        ImageImportJobFileModel,
        {
            "job_id": job_id,
            "file_execution_key": candidate.execution.file_execution_key,
        },
    )
    execution = session.get(
        ImageFileExecutionModel,
        candidate.execution.file_execution_key,
    )
    if (
        association is None
        or execution is None
        or execution.source_checksum_sha256 != candidate.execution.source_checksum_sha256
        or execution.pipeline_fingerprint != candidate.execution.pipeline_fingerprint
    ):
        raise ImagePipelineStoreError(
            "IMAGE_PIPELINE_PROVENANCE_INVALID",
            "The source is not linked to this job and pipeline execution.",
        )


def _source(
    session: Session,
    job_id: UUID,
    file_execution_key: str,
) -> SourceImageModel | None:
    return cast(
        SourceImageModel | None,
        session.scalar(
            select(SourceImageModel).where(
                SourceImageModel.import_job_id == job_id,
                SourceImageModel.file_execution_key == file_execution_key,
            )
        ),
    )


def _locked_source(
    session: Session,
    job_id: UUID,
    file_execution_key: str,
) -> SourceImageModel:
    source = session.scalar(
        select(SourceImageModel)
        .where(
            SourceImageModel.import_job_id == job_id,
            SourceImageModel.file_execution_key == file_execution_key,
        )
        .with_for_update()
    )
    if source is None:
        raise ImagePipelineStoreError(
            "IMAGE_SOURCE_PROJECTION_MISSING",
            "Discovery must project the source before recognition.",
        )
    return source


def _boards_by_position(
    payload: Mapping[str, object],
) -> dict[int, Mapping[str, object]]:
    return {
        cast(int, board["positionIndex"]): board
        for board in (
            cast(Mapping[str, object], value) for value in cast(Sequence[object], payload["boards"])
        )
    }


def _require_same_board(
    board: RecognizedBoardModel,
    candidate: ImageBatchCandidate,
    *,
    detected: Mapping[str, object],
    cropped: Mapping[str, object],
    sequence: Mapping[str, object],
    prediction: Mapping[str, object],
) -> None:
    expected_geometry = _recognized_board_geometry(
        detected=detected,
        cropped=cropped,
        sequence=sequence,
    )
    expected_grid_rows = _optional_positive_integer(cropped.get("gridRows"))
    expected_grid_columns = _optional_positive_integer(cropped.get("gridColumns"))
    expected_asset_mode = (
        "virtual_source" if cropped.get("assetMode") == "virtual_source" else "legacy_file"
    )
    if (
        board.sequence_number_raw != sequence["rawText"]
        or board.sequence_number != sequence["normalizedNumber"]
        or board.sequence_confidence != float(cast(float, sequence["confidence"]))
        or canonical_json_bytes(board.board_geometry) != canonical_json_bytes(expected_geometry)
        or board.grid_rows != expected_grid_rows
        or board.grid_columns != expected_grid_columns
        or board.asset_mode != expected_asset_mode
        or board.board_relative_path != cropped.get("boardRelativePath")
        or board.board_checksum_sha256 != cropped.get("boardChecksumSha256")
        or board.geometry_engine_name != cropped.get("geometryEngineName")
        or board.geometry_engine_version != cropped.get("geometryEngineVersion")
        or board.geometry_checksum_sha256 != cropped.get("geometryChecksumSha256")
        or canonical_json_bytes(board.cells_prediction) != canonical_json_bytes(prediction)
        or board.board_confidence != float(cast(float, detected["confidence"]))
        or board.pipeline_fingerprint != candidate.execution.pipeline_fingerprint
    ):
        raise ImagePipelineStoreError(
            "IMAGE_RECOGNIZED_BOARD_CONFLICT",
            "The recognized board projection already has different content.",
        )


def _recognized_board_geometry(
    *,
    detected: Mapping[str, object],
    cropped: Mapping[str, object],
    sequence: Mapping[str, object],
) -> dict[str, object]:
    geometry = dict(cast(Mapping[str, object], detected["geometry"]))
    sequence_label_quad = sequence.get("sequenceLabelQuad")
    if sequence_label_quad is not None:
        geometry["sequenceLabelQuad"] = sequence_label_quad
    for key in ("attestedRangeStart", "attestedRangeEnd", "sequenceSource"):
        value = sequence.get(key)
        if value is not None:
            geometry[key] = value
    source_context_bounds = cropped.get("sourceContextBounds")
    if source_context_bounds is not None:
        geometry["sourceContextBounds"] = source_context_bounds
    display_asset_kind = cropped.get("displayAssetKind")
    if display_asset_kind is not None:
        geometry["displayAssetKind"] = display_asset_kind
    cell_output_size = cropped.get("cellOutputSize")
    if cell_output_size is not None:
        geometry["cellOutputSize"] = cell_output_size
    return geometry


def _upsert_cell(
    session: Session,
    board: RecognizedBoardModel,
    crop: Mapping[str, object],
    prediction: Mapping[str, object],
    *,
    source_geometry_revision_id: UUID | None,
    cropper_version: str,
    created_at: datetime,
) -> None:
    row = cast(int, crop["rowIndex"])
    column = cast(int, crop["columnIndex"])
    record = session.scalar(
        select(CellObservationModel)
        .where(
            CellObservationModel.recognized_board_id == board.id,
            CellObservationModel.row_index == row,
            CellObservationModel.column_index == column,
        )
        .with_for_update()
    )
    virtual = crop.get("assetMode") == "virtual_source"
    v2_identity = v2_render_identity_from_spec(crop.get("renderSpec")) if virtual else None
    if v2_identity is not None and (
        crop.get("logicalCellKeyV2Sha256") != v2_identity.logical_cell_key_v2
        or crop.get("renderIdentityV2Sha256") != v2_identity.render_identity_v2_sha256
    ):
        raise ImagePipelineStoreError(
            "IMAGE_V2_RENDER_IDENTITY_CONFLICT",
            "The virtual cell payload differs from its checksummed v2 render specification.",
        )
    if record is None:
        session.add(
            CellObservationModel(
                recognized_board_id=board.id,
                row_index=row,
                column_index=column,
                asset_mode="virtual_source" if virtual else "legacy_file",
                source_geometry_revision_id=(source_geometry_revision_id if virtual else None),
                logical_cell_key=(cast(str, crop["logicalCellKeySha256"]) if virtual else None),
                logical_cell_key_v2=(
                    None if v2_identity is None else v2_identity.logical_cell_key_v2
                ),
                render_identity_v2_sha256=(
                    None if v2_identity is None else v2_identity.render_identity_v2_sha256
                ),
                render_spec=(
                    dict(cast(Mapping[str, object], crop["renderSpec"])) if virtual else None
                ),
                render_spec_checksum_sha256=(
                    cast(str, crop["renderSpecChecksumSha256"]) if virtual else None
                ),
                rendered_pixel_checksum_sha256=(
                    cast(str, crop["renderedPixelChecksumSha256"]) if virtual else None
                ),
                extractor_version=(cast(str, crop["extractorVersion"]) if virtual else None),
                crop_relative_path=(None if virtual else cast(str, crop["cropRelativePath"])),
                crop_checksum_sha256=cast(str, crop["cropChecksumSha256"]),
                cropper_version=cropper_version,
                prediction=dict(prediction),
                created_at=created_at,
            )
        )
        return
    if (
        record.asset_mode
        != ("virtual_source" if crop.get("assetMode") == "virtual_source" else "legacy_file")
        or record.crop_relative_path != crop.get("cropRelativePath")
        or record.crop_checksum_sha256 != crop["cropChecksumSha256"]
        or record.source_geometry_revision_id
        != (source_geometry_revision_id if crop.get("assetMode") == "virtual_source" else None)
        or record.logical_cell_key != crop.get("logicalCellKeySha256")
        or record.logical_cell_key_v2
        != (None if v2_identity is None else v2_identity.logical_cell_key_v2)
        or record.render_identity_v2_sha256
        != (None if v2_identity is None else v2_identity.render_identity_v2_sha256)
        or canonical_json_bytes(record.render_spec) != canonical_json_bytes(crop.get("renderSpec"))
        or record.render_spec_checksum_sha256 != crop.get("renderSpecChecksumSha256")
        or record.rendered_pixel_checksum_sha256 != crop.get("renderedPixelChecksumSha256")
        or record.extractor_version != crop.get("extractorVersion")
        or record.cropper_version != cropper_version
        or canonical_json_bytes(record.prediction) != canonical_json_bytes(prediction)
    ):
        raise ImagePipelineStoreError(
            "IMAGE_CELL_OBSERVATION_CONFLICT",
            "A cell observation already has different crop or prediction data.",
        )


def _upsert_review_item(
    session: Session,
    board: RecognizedBoardModel,
    source: SourceImageModel,
    job: JobModel,
    sequence: Mapping[str, object],
    detected: Mapping[str, object],
    cropped: Mapping[str, object],
    prediction: Mapping[str, object],
    *,
    created_at: datetime,
) -> tuple[ImageReviewItemModel, tuple[UUID, ...]]:
    snapshot: dict[str, object] = {
        "boardChecksumSha256": cropped.get("boardChecksumSha256"),
        "boardRelativePath": cropped.get("boardRelativePath"),
        "cells": prediction["cells"],
        "geometry": dict(board.board_geometry),
        "pipelineFingerprint": board.pipeline_fingerprint,
        "positionIndex": board.position_index,
        "sequence": dict(sequence),
        "sourceChecksumSha256": source.checksum_sha256,
        "sourceRelativePath": source.relative_path,
    }
    if cropped.get("assetMode") == "virtual_source":
        snapshot.update(
            {
                "assetMode": "virtual_source",
                "geometryChecksumSha256": cropped.get("geometryChecksumSha256"),
                "geometryEngineName": cropped.get("geometryEngineName"),
                "geometryEngineVersion": cropped.get("geometryEngineVersion"),
            }
        )
    item = session.scalar(
        select(ImageReviewItemModel)
        .where(ImageReviewItemModel.recognized_board_id == board.id)
        .with_for_update()
    )
    if item is None:
        if job.game_id is None:
            raise ImagePipelineStoreError(
                "IMAGE_PIPELINE_GAME_MISSING",
                "Image review requires a game-scoped import job.",
            )
        return create_owned_pending_review_item(
            session,
            board=board,
            game_id=job.game_id,
            import_job=job,
            snapshot=snapshot,
            created_at=created_at,
        )
    if canonical_json_bytes(item.snapshot) != canonical_json_bytes(snapshot):
        raise ImagePipelineStoreError(
            "IMAGE_REVIEW_SNAPSHOT_CONFLICT",
            "The immutable image review snapshot already has different content.",
        )
    return item, (item.id,)


def _virtual_geometry_checksum(payload: Mapping[str, object]) -> str | None:
    if payload.get("assetMode") == "virtual_source":
        value = payload.get("geometryChecksumSha256")
        return value if isinstance(value, str) else None
    shadow = payload.get("virtualShadow")
    if isinstance(shadow, Mapping):
        value = shadow.get("geometryChecksumSha256")
        return value if isinstance(value, str) else None
    return None


def _append_prediction_revision(
    session: Session,
    *,
    game_id: UUID,
    job_id: UUID,
    review_item: ImageReviewItemModel,
    board: RecognizedBoardModel,
    crop_board: Mapping[str, object],
    symbol_board: Mapping[str, object],
    symbol_payload: Mapping[str, object],
    created_at: datetime,
) -> None:
    if crop_board.get("assetMode") != "virtual_source":
        return
    crop_manifest_checksum = sha256(
        canonical_json_bytes(
            {
                "assetMode": "virtual_source",
                "cells": crop_board["cells"],
                "geometryChecksumSha256": crop_board["geometryChecksumSha256"],
                "positionIndex": crop_board["positionIndex"],
            }
        )
    ).hexdigest()
    model_checksum = cast(str, symbol_payload["modelChecksumSha256"])
    existing = session.scalar(
        select(ImageSymbolPredictionRevisionModel.id).where(
            ImageSymbolPredictionRevisionModel.review_item_id == review_item.id,
            ImageSymbolPredictionRevisionModel.model_checksum_sha256 == model_checksum,
            ImageSymbolPredictionRevisionModel.crop_manifest_checksum_sha256
            == crop_manifest_checksum,
        )
    )
    if existing is not None:
        return
    raw_iteration = symbol_payload.get("modelIterationId")
    crop_cells = cast(Sequence[object], crop_board["cells"])
    symbol_cells = cast(Sequence[object], symbol_board["cells"])
    session.add(
        ImageSymbolPredictionRevisionModel(
            game_id=game_id,
            review_item_id=review_item.id,
            recognized_board_id=board.id,
            source_job_id=job_id,
            model_iteration_id=(UUID(raw_iteration) if isinstance(raw_iteration, str) else None),
            model_version=cast(str, symbol_payload["modelVersion"]),
            model_checksum_sha256=model_checksum,
            crop_manifest_checksum_sha256=crop_manifest_checksum,
            predictions=[
                {
                    **dict(cast(Mapping[str, object], symbol_value)),
                    "virtualCell": {
                        "cropChecksumSha256": cast(Mapping[str, object], crop_value)[
                            "cropChecksumSha256"
                        ],
                        "extractorVersion": cast(Mapping[str, object], crop_value)[
                            "extractorVersion"
                        ],
                        "logicalCellKeySha256": cast(Mapping[str, object], crop_value)[
                            "logicalCellKeySha256"
                        ],
                        **(
                            {
                                "logicalCellKeyV2Sha256": cast(Mapping[str, object], crop_value)[
                                    "logicalCellKeyV2Sha256"
                                ]
                            }
                            if isinstance(
                                cast(Mapping[str, object], crop_value).get(
                                    "logicalCellKeyV2Sha256"
                                ),
                                str,
                            )
                            else {}
                        ),
                        **(
                            {
                                "renderIdentityV2Sha256": cast(Mapping[str, object], crop_value)[
                                    "renderIdentityV2Sha256"
                                ]
                            }
                            if isinstance(
                                cast(Mapping[str, object], crop_value).get(
                                    "renderIdentityV2Sha256"
                                ),
                                str,
                            )
                            else {}
                        ),
                        "renderSpec": cast(Mapping[str, object], crop_value)["renderSpec"],
                        "renderSpecChecksumSha256": cast(Mapping[str, object], crop_value)[
                            "renderSpecChecksumSha256"
                        ],
                        "renderedPixelChecksumSha256": cast(Mapping[str, object], crop_value)[
                            "renderedPixelChecksumSha256"
                        ],
                    },
                }
                for crop_value, symbol_value in zip(crop_cells, symbol_cells, strict=True)
            ],
            created_at=created_at,
        )
    )


def _require_active_symbol_codes(
    session: Session,
    board: RecognizedBoardModel,
    symbol_codes: Sequence[str],
) -> None:
    source = session.get(SourceImageModel, board.source_image_id)
    if source is None:
        raise ImagePipelineStoreError(
            "IMAGE_SOURCE_PROJECTION_MISSING",
            "The board source no longer exists.",
        )
    job = session.get(JobModel, source.import_job_id)
    if job is None or job.game_id is None:
        raise ImagePipelineStoreError(
            "IMAGE_PIPELINE_GAME_MISSING",
            "Image review requires a game-scoped import job.",
        )
    records = session.scalars(
        select(SymbolModel).where(
            SymbolModel.game_id == job.game_id,
            SymbolModel.code.in_(set(symbol_codes)),
            SymbolModel.status == SymbolStatus.ACTIVE,
        )
    ).all()
    if {record.code for record in records} != set(symbol_codes):
        raise ImagePipelineStoreError(
            "IMAGE_REVIEW_SYMBOL_INVALID",
            "Every reviewed symbol must be active in the image import game.",
        )


def _mobile_codes(
    session: Session,
    job_id: UUID,
    symbol_codes: Sequence[str],
) -> list[int]:
    job = session.get(JobModel, job_id)
    if job is None or job.game_id is None:
        raise ImagePipelineStoreError(
            "IMAGE_PIPELINE_GAME_MISSING",
            "Image staging requires a game-scoped import job.",
        )
    records = session.scalars(
        select(SymbolModel).where(
            SymbolModel.game_id == job.game_id,
            SymbolModel.code.in_(set(symbol_codes)),
            SymbolModel.status == SymbolStatus.ACTIVE,
        )
    ).all()
    by_code = {record.code: record.mobile_code for record in records}
    if set(by_code) != set(symbol_codes):
        raise ImagePipelineStoreError(
            "IMAGE_REVIEW_SYMBOL_INVALID",
            "Every reviewed symbol must be active in the image import game.",
        )
    return [by_code[code] for code in symbol_codes]


def _optional_positive_integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ImagePipelineStoreError(
            "IMAGE_PIPELINE_TOPOLOGY_INVALID",
            "The pinned board topology dimensions are invalid.",
        )
    return value


__all__ = [
    "ImagePipelineStoreError",
    "SqlAlchemyImagePipelineStore",
]
