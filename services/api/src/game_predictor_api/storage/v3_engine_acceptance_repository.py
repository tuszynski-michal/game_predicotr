"""Finalize only new pinned neural revisions in the recognition transaction."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.neural_crop_policy import NEURAL_AUTO_CROP_POLICY
from game_predictor_api.domain.v3_engine_acceptance import (
    V3_ENGINE_ACCEPTANCE_ACTOR,
    V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY,
    V3_ENGINE_ACCEPTANCE_POLICY,
    V3EnginePosition,
    qualify_v3_engine_acceptance,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)


def finalize_v3_engine_acceptance(
    session: Session,
    *,
    job: JobModel,
    source: SourceImageModel,
    revision: ImageSourceGeometryRevisionModel | None,
    structured: object,
) -> tuple[str, ...]:
    """Require locked source/sequences and flushed owners before qualification.

    This writer is limited to a fresh import's original board revision (zero)
    and owners of that same job. Re-inference/proposals have separate writers;
    this function does not approve a replacement of human or historical work.

    Status is the only mutated field. Its existing actor, auto provenance and
    engine version distinguish engine acceptance. No payload/checksum, human
    approval, crop, decision or owner is updated. Caller recomputes the gate
    and synchronizes projections in this same transaction; failures roll back.
    """
    if job.input_payload.get(V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY) != V3_ENGINE_ACCEPTANCE_POLICY:
        return ("V3_ACCEPTANCE_LEGACY_JOB",)
    if job.game_id is None:
        return ("V3_ACCEPTANCE_SOURCE_OR_MODEL_DRIFT",)
    GameStorageRouter().bind(session, job.game_id, intent=GameStorageIntent.WRITE)
    if (
        revision is None
        or revision.created_by != V3_ENGINE_ACCEPTANCE_ACTOR
        or revision.geometry_source != "auto"
        or revision.engine_kind != "neural_grid_v1"
        or revision.engine_version != NEURAL_AUTO_CROP_POLICY
        or revision.status not in ("needs_review", "accepted")
    ):
        return ("V3_ACCEPTANCE_REVISION_PROVENANCE_INVALID",)
    session.flush()
    latest_id = session.scalar(
        select(ImageSourceGeometryRevisionModel.id)
        .where(
            ImageSourceGeometryRevisionModel.game_id == job.game_id,
            ImageSourceGeometryRevisionModel.source_image_id == source.id,
            ImageSourceGeometryRevisionModel.status != "reverted",
        )
        .order_by(ImageSourceGeometryRevisionModel.revision.desc())
        .limit(1)
    )
    if latest_id != revision.id:
        # An old job never rewrites the status of a historical revision.
        return ("V3_ACCEPTANCE_REVISION_CONFLICT",)
    initialization = revision.global_initialization
    evidence = (
        initialization.get("v3EngineAcceptance") if isinstance(initialization, Mapping) else None
    )
    blockers: tuple[str, ...]
    if not isinstance(evidence, Mapping) or not isinstance(structured, Mapping):
        blockers = ("V3_ACCEPTANCE_EVIDENCE_MISSING",)
    else:
        boards = session.scalars(
            select(RecognizedBoardModel)
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == job.game_id,
                RecognizedBoardModel.source_image_id == source.id,
                RecognizedBoardModel.status != "rejected",
            )
        ).all()
        reviews = session.scalars(
            select(ImageReviewItemModel).where(
                ImageReviewItemModel.game_id == job.game_id,
                ImageReviewItemModel.recognized_board_id.in_([board.id for board in boards]),
            )
        ).all()
        owners = {item.recognized_board_id: item for item in reviews}
        external_owners = set(
            session.scalars(
                select(ImageReviewItemModel.sequence_number).where(
                    ImageReviewItemModel.game_id == job.game_id,
                    ImageReviewItemModel.sequence_number.between(
                        revision.sequence_range_start, revision.sequence_range_end
                    ),
                    ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
                    ImageReviewItemModel.recognized_board_id.not_in([board.id for board in boards]),
                )
            ).all()
        )
        canonical_owners = {
            item.sequence_number: item.review_item_id
            for item in session.scalars(
                select(ImageSequenceCanonicalModel).where(
                    ImageSequenceCanonicalModel.game_id == job.game_id,
                    ImageSequenceCanonicalModel.sequence_number.between(
                        revision.sequence_range_start, revision.sequence_range_end
                    ),
                )
            ).all()
        }
        issues = set(
            session.scalars(
                select(ImageSymbolReviewCellModel.recognized_board_id)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
                )
                .where(
                    ImageSymbolReviewCellModel.game_id == job.game_id,
                    ImageSymbolReviewCellModel.recognized_board_id.in_(
                        [board.id for board in boards]
                    ),
                    ImageSymbolReviewCellModel.quality_issue == "grid_issue",
                    ImageSymbolReviewCellModel.review_state == "pending",
                    ImageSymbolReviewCellModel.geometry_revision
                    == RecognizedBoardModel.geometry_revision,
                    ImageSymbolReviewCellModel.source_geometry_revision_id
                    == RecognizedBoardModel.source_geometry_revision_id,
                    ImageSymbolReviewCellModel.asset_mode == "virtual_source",
                )
            ).all()
        )
        deferred = session.scalar(
            select(ImageBoardGeometryPendingModel.id)
            .where(
                ImageBoardGeometryPendingModel.game_id == job.game_id,
                ImageBoardGeometryPendingModel.source_image_id == source.id,
                ImageBoardGeometryPendingModel.status == "pending",
            )
            .limit(1)
        )
        stored_slots = {item.get("positionIndex"): item for item in revision.board_geometries}
        positions = []
        for board in boards:
            owner = owners.get(board.id)
            slot = stored_slots.get(board.position_index)
            same_geometry = (
                isinstance(slot, Mapping)
                and isinstance(board.board_geometry, Mapping)
                and slot.get("latticeNodes") == board.board_geometry.get("latticeNodes")
                and slot.get("finalQuad") == board.board_geometry.get("quad")
                and slot.get("sequenceNumber") == board.sequence_number
                and all(
                    slot.get(field) == board.board_geometry.get(field)
                    for field in (
                        "neuralExecutionPolicy",
                        "neuralProposalChecksumSha256",
                        "neuralProposalBinding",
                        "detectionId",
                    )
                )
            )
            positions.append(
                V3EnginePosition(
                    position=board.position_index,
                    sequence=board.sequence_number,
                    geometry=board.board_geometry,
                    complete=board.completeness_status == "complete"
                    and not board.unavailable_cell_indices,
                    current_revision=board.source_geometry_revision_id == revision.id
                    and board.geometry_checksum_sha256 == revision.geometry_checksum_sha256
                    and board.geometry_engine_name == revision.engine_kind
                    and board.geometry_engine_version == revision.engine_version
                    and board.asset_mode == "virtual_source"
                    and board.grid_rows == 3
                    and board.grid_columns == 5
                    and board.geometry_revision == 0
                    and board.approved_geometry_revision is None
                    and same_geometry,
                    current_owner=owner is not None
                    and owner.import_job_id == job.id
                    and owner.sequence_number == board.sequence_number
                    and owner.status in ("pending", "accepted", "corrected")
                    and board.sequence_number is not None
                    and board.sequence_number not in external_owners
                    and canonical_owners.get(board.sequence_number, owner.id) == owner.id,
                    grid_issue=board.id in issues,
                )
            )
        blockers = qualify_v3_engine_acceptance(
            policy=evidence.get("policyVersion"),
            proposal=evidence.get("proposal"),
            binding=evidence.get("binding"),
            model_snapshot=job.input_payload.get("neural_grid_proposal"),
            game_id=str(job.game_id),
            source_checksum_sha256=source.checksum_sha256,
            width=cast(int, source.oriented_width),
            height=cast(int, source.oriented_height),
            active_slots=revision.active_board_slots,
            sequence_start=revision.sequence_range_start,
            sequence_end=revision.sequence_range_end,
            positions=positions,
            deferred=deferred is not None,
            source_current=latest_id == revision.id
            and revision.game_id == job.game_id
            and revision.source_image_id == source.id
            and source.import_job_id == job.id
            and source.checksum_sha256 == revision.source_checksum_sha256
            and source.normalized_pixel_checksum_sha256 == revision.normalized_pixel_checksum_sha256
            and source.oriented_width == revision.oriented_width
            and source.oriented_height == revision.oriented_height
            and source.normalization_adapter_version == revision.normalization_adapter_version
            and structured.get("globalInitialization") == revision.global_initialization
            and structured.get("boards") == revision.board_geometries
            and structured.get("resultChecksumSha256") == revision.geometry_checksum_sha256
            and sha256(
                canonical_json_bytes(
                    {
                        key: value
                        for key, value in structured.items()
                        if key != "resultChecksumSha256"
                    }
                )
            ).hexdigest()
            == revision.geometry_checksum_sha256,
        )
    revision.status = "needs_review" if blockers else "accepted"
    session.flush()
    return blockers
