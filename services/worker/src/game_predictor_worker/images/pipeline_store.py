"""PostgreSQL projections for versioned image stage results and review staging."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.jobs import require_active_job_lease
from game_predictor_api.storage.job_repository import job_from_record
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageLayoutStagingRowModel,
    ImagePipelineStageResultModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
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
        if not (detection.keys() == crops.keys() == sequences.keys() == symbols.keys()):
            raise ImagePipelineStoreError(
                "IMAGE_RECOGNITION_POSITION_CONFLICT",
                "Board positions differ between persisted image stages.",
            )
        model_version = cast(str, stage_results["symbol_inference"].payload["modelVersion"])
        with self._session_factory() as session, session.begin():
            _require_candidate_lease(
                session,
                candidate,
                job_id=job_id,
                lease_token=lease_token,
                checked_at=executed_at,
            )
            source = _locked_source(session, job_id, candidate.execution.file_execution_key)
            for position in sorted(detection):
                detected = detection[position]
                cropped = crops[position]
                sequence = sequences[position]
                symbol = symbols[position]
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
                board_geometry = dict(cast(Mapping[str, object], detected["geometry"]))
                sequence_label_quad = sequence.get("sequenceLabelQuad")
                if sequence_label_quad is not None:
                    board_geometry["sequenceLabelQuad"] = sequence_label_quad
                if board is None:
                    board = RecognizedBoardModel(
                        source_image_id=source.id,
                        position_index=position,
                        sequence_number_raw=cast(str, sequence["rawText"]),
                        sequence_number=cast(int | None, sequence["normalizedNumber"]),
                        sequence_confidence=float(cast(float, sequence["confidence"])),
                        board_geometry=board_geometry,
                        board_relative_path=cast(str, cropped["boardRelativePath"]),
                        board_checksum_sha256=cast(
                            str,
                            cropped["boardChecksumSha256"],
                        ),
                        cells_prediction=prediction,
                        board_confidence=float(cast(float, detected["confidence"])),
                        pipeline_fingerprint=candidate.execution.pipeline_fingerprint,
                        status="pending_review",
                        created_at=executed_at,
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
                        cropper_version=cropper_version,
                        created_at=executed_at,
                    )
                _upsert_review_item(
                    session,
                    board,
                    source,
                    sequence,
                    detected,
                    cropped,
                    prediction,
                    created_at=executed_at,
                )
            source.status = "waiting_for_review"
            source.processed_at = executed_at
            session.flush()

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
            return int(value or 0)

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
                if item.status == "rejected":
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
                session.execute(
                    delete(ImageLayoutStagingRowModel).where(
                        ImageLayoutStagingRowModel.import_job_id == job_id,
                        ImageLayoutStagingRowModel.recognized_board_id == board.id,
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
    expected_geometry = dict(cast(Mapping[str, object], detected["geometry"]))
    if sequence.get("sequenceLabelQuad") is not None:
        expected_geometry["sequenceLabelQuad"] = sequence["sequenceLabelQuad"]
    if (
        board.sequence_number_raw != sequence["rawText"]
        or board.sequence_number != sequence["normalizedNumber"]
        or board.sequence_confidence != float(cast(float, sequence["confidence"]))
        or canonical_json_bytes(board.board_geometry) != canonical_json_bytes(expected_geometry)
        or board.board_relative_path != cropped["boardRelativePath"]
        or board.board_checksum_sha256 != cropped["boardChecksumSha256"]
        or canonical_json_bytes(board.cells_prediction) != canonical_json_bytes(prediction)
        or board.board_confidence != float(cast(float, detected["confidence"]))
        or board.pipeline_fingerprint != candidate.execution.pipeline_fingerprint
    ):
        raise ImagePipelineStoreError(
            "IMAGE_RECOGNIZED_BOARD_CONFLICT",
            "The recognized board projection already has different content.",
        )


def _upsert_cell(
    session: Session,
    board: RecognizedBoardModel,
    crop: Mapping[str, object],
    prediction: Mapping[str, object],
    *,
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
    if record is None:
        session.add(
            CellObservationModel(
                recognized_board_id=board.id,
                row_index=row,
                column_index=column,
                crop_relative_path=cast(str, crop["cropRelativePath"]),
                crop_checksum_sha256=cast(str, crop["cropChecksumSha256"]),
                cropper_version=cropper_version,
                prediction=dict(prediction),
                created_at=created_at,
            )
        )
        return
    if (
        record.crop_relative_path != crop["cropRelativePath"]
        or record.crop_checksum_sha256 != crop["cropChecksumSha256"]
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
    sequence: Mapping[str, object],
    detected: Mapping[str, object],
    cropped: Mapping[str, object],
    prediction: Mapping[str, object],
    *,
    created_at: datetime,
) -> None:
    snapshot = {
        "boardChecksumSha256": cropped["boardChecksumSha256"],
        "boardRelativePath": cropped["boardRelativePath"],
        "cells": prediction["cells"],
        "geometry": dict(board.board_geometry),
        "pipelineFingerprint": board.pipeline_fingerprint,
        "positionIndex": board.position_index,
        "sequence": dict(sequence),
        "sourceChecksumSha256": source.checksum_sha256,
        "sourceRelativePath": source.relative_path,
    }
    item = session.scalar(
        select(ImageReviewItemModel)
        .where(ImageReviewItemModel.recognized_board_id == board.id)
        .with_for_update()
    )
    if item is None:
        session.add(
            ImageReviewItemModel(
                recognized_board_id=board.id,
                status="pending",
                snapshot=snapshot,
                resolution_revision=0,
                created_at=created_at,
            )
        )
        return
    if canonical_json_bytes(item.snapshot) != canonical_json_bytes(snapshot):
        raise ImagePipelineStoreError(
            "IMAGE_REVIEW_SNAPSHOT_CONFLICT",
            "The immutable image review snapshot already has different content.",
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


__all__ = [
    "ImagePipelineStoreError",
    "SqlAlchemyImagePipelineStore",
]
