"""Status-only historical acceptance, with a frozen target and receipt per source."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.grid_engine_acceptance import (
    HISTORICAL_ACCEPTANCE_ACTOR,
    HISTORICAL_ACCEPTANCE_POLICY,
    HistoricalAcceptanceItem,
    HistoricalAcceptanceReport,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.domain.neural_crop_policy import NEURAL_AUTO_CROP_POLICY
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridProposalError,
    NeuralGridSnapshot,
)
from game_predictor_api.domain.v3_engine_acceptance import (
    V3_ENGINE_ACCEPTANCE_POLICY,
    V3EnginePosition,
    qualify_v3_engine_acceptance,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_engine_acceptance_models import (
    HistoricalGridAcceptanceOperationModel as Operation,
)
from game_predictor_api.storage.grid_engine_acceptance_models import (
    HistoricalGridAcceptanceReceiptModel as Receipt,
)
from game_predictor_api.storage.grid_engine_acceptance_models import (
    HistoricalGridAcceptanceTargetModel as Target,
)
from game_predictor_api.storage.historical_grid_evidence import (
    HistoricalEvidenceUnavailable,
    original_neural_evidence,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    recompute_source_image_geometry_completeness,
)
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    GameModel,
    ImageBoardGeometryPendingModel,
    ImageBoardSearchCandidateModel,
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default).encode()
    ).hexdigest()


def _record(value: object, exclude: tuple[str, ...] = ()) -> dict[str, object]:
    return {
        column.key: getattr(value, column.key)
        for column in cast(Any, value).__table__.columns
        if column.key not in exclude
    }


def _count_reasons(current: Mapping[str, int], reasons: Iterable[str]) -> dict[str, int]:
    result = dict(current)
    for reason in reasons:
        result[reason] = result.get(reason, 0) + 1
    return result


def _conflict(code: str) -> ImageReviewConflictError:
    return ImageReviewConflictError(
        code, "The historical acceptance command conflicts with its frozen operation."
    )


@dataclass(frozen=True)
class _Qualification:
    revision: ImageSourceGeometryRevisionModel | None
    reasons: tuple[str, ...]
    fingerprint: str
    protected_fingerprint: str
    review_ids: tuple[UUID, ...]


class SqlAlchemyHistoricalAcceptanceRepository:
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self.session = session
        self.artifact_root = artifact_root

    def _bind(self, game_id: UUID) -> None:
        GameStorageRouter().bind(self.session, game_id, intent=GameStorageIntent.WRITE)
        self.session.connection().execute(text("SET LOCAL lock_timeout = '3s'"))
        self.session.connection().execute(text("SET LOCAL statement_timeout = '20s'"))
        game = self.session.get(GameModel, game_id)
        if game is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_GAME_NOT_FOUND", "The selected game does not exist."
            )
        if game.code == "7":
            raise _conflict("HISTORICAL_ACCEPTANCE_LEGACY_GAME_EXCLUDED")

    def _lock(self, game_id: UUID, identity: object) -> None:
        key = int.from_bytes(
            hashlib.sha256(f"historical-acceptance:{game_id}:{identity}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        self.session.execute(select(func.pg_advisory_xact_lock(key)))
        acquire_sequence_ownership_lock(self.session, game_id=game_id)
        self.session.scalar(select(GameModel).where(GameModel.id == game_id).with_for_update())

    def _operation(self, game_id: UUID, operation_id: UUID, *, lock: bool = False) -> Operation:
        statement = select(Operation).where(
            Operation.game_id == game_id, Operation.id == operation_id
        )
        if lock:
            statement = statement.with_for_update()
        value = self.session.scalar(statement.execution_options(populate_existing=True))
        if value is None:
            raise ImageReviewNotFoundError(
                "HISTORICAL_ACCEPTANCE_OPERATION_NOT_FOUND",
                "The operation does not belong to this game.",
            )
        return value

    def create(self, game_id: UUID, key: UUID) -> HistoricalAcceptanceReport:
        self._bind(game_id)
        self._lock(game_id, key)
        command_hash = _hash(
            {"policy": HISTORICAL_ACCEPTANCE_POLICY, "gameId": game_id, "action": "preview"}
        )
        existing = self.session.scalar(
            select(Operation).where(Operation.game_id == game_id, Operation.idempotency_key == key)
        )
        if existing is None:
            existing = Operation(
                game_id=game_id,
                idempotency_key=key,
                command_sha256=command_hash,
                phase="previewing",
            )
            self.session.add(existing)
            self.session.flush()
        elif existing.command_sha256 != command_hash:
            raise _conflict("HISTORICAL_ACCEPTANCE_IDEMPOTENCY_CONFLICT")
        return self.report(game_id, existing.id)

    def _next_source(self, game_id: UUID, operation: Operation) -> SourceImageModel | None:
        statement = (
            select(SourceImageModel)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(JobModel.game_id == game_id, SourceImageModel.created_at < operation.started_at)
        )
        if operation.preview_after_source_id is not None:
            statement = statement.where(SourceImageModel.id > operation.preview_after_source_id)
        return self.session.scalar(statement.order_by(SourceImageModel.id).limit(1))

    def preview_next(
        self, game_id: UUID, operation_id: UUID, cursor: int
    ) -> HistoricalAcceptanceReport:
        self._bind(game_id)
        operation = self._operation(game_id, operation_id)
        preparation_state = None
        # Prepare the reproducible index before any ownership/game/source row lock.
        # Run never builds it inside a source transaction.
        if operation.phase == "previewing" and cursor == operation.preview_cursor:
            source = self._next_source(game_id, operation)
            if source is not None:
                job = self.session.get(JobModel, source.import_job_id)
                if job is not None and job.input_payload.get("page_geometry_manifest"):
                    try:
                        original_neural_evidence(
                            self.artifact_root,
                            job.input_payload,
                            game_id=str(game_id),
                            source_sha256=source.checksum_sha256,
                        )
                    except HistoricalEvidenceUnavailable as error:
                        preparation_state = str(error)
        self._lock(game_id, operation_id)
        operation = self._operation(game_id, operation_id, lock=True)
        if cursor < operation.preview_cursor or operation.phase != "previewing":
            return self.report(game_id, operation_id)
        if cursor != operation.preview_cursor:
            raise _conflict("HISTORICAL_ACCEPTANCE_CURSOR_CONFLICT")
        operation.preparation_state = preparation_state
        if preparation_state in (
            "HISTORICAL_EVIDENCE_PREPARING",
            "HISTORICAL_EVIDENCE_VERIFICATION_TIME_LIMIT",
        ):
            self.session.flush()
            return self.report(game_id, operation_id)
        source = self._next_source(game_id, operation)
        if source is None:
            operation.phase = "previewed"
        else:
            self._lock_source(game_id, source.id)
            result = self._qualify(game_id, source.id)
            revision = result.revision
            operation.revision_count += int(revision is not None)
            operation.eligible_count += int(not result.reasons)
            operation.preview_reasons = _count_reasons(operation.preview_reasons, result.reasons)
            operation.preview_cursor += 1
            operation.preview_after_source_id = source.id
            self.session.add(
                Target(
                    game_id=game_id,
                    operation_id=operation_id,
                    ordinal=operation.preview_cursor,
                    source_image_id=source.id,
                    revision_id=None if revision is None else revision.id,
                    revision_number=None if revision is None else revision.revision,
                    previous_status=None if revision is None else revision.status,
                    fingerprint_sha256=result.fingerprint,
                    reasons=list(result.reasons),
                )
            )
        self.session.flush()
        return self.report(game_id, operation_id)

    def confirm(self, game_id: UUID, operation_id: UUID, key: UUID) -> HistoricalAcceptanceReport:
        self._bind(game_id)
        self._lock(game_id, operation_id)
        operation = self._operation(game_id, operation_id, lock=True)
        command_hash = _hash(
            {
                "policy": HISTORICAL_ACCEPTANCE_POLICY,
                "operationId": operation_id,
                "gameId": game_id,
                "action": "confirm",
                "sourceCount": operation.preview_cursor,
            }
        )
        if operation.confirm_key is not None:
            if operation.confirm_key != key or operation.confirm_sha256 != command_hash:
                raise _conflict("HISTORICAL_ACCEPTANCE_IDEMPOTENCY_CONFLICT")
        else:
            if operation.phase != "previewed":
                raise _conflict("HISTORICAL_ACCEPTANCE_PREVIEW_NOT_COMPLETE")
            operation.confirm_key, operation.confirm_sha256 = key, command_hash
            operation.phase = "running" if operation.preview_cursor else "done"
        self.session.flush()
        return self.report(game_id, operation_id)

    def _lock_source(self, game_id: UUID, source_id: UUID) -> None:
        revision = self.session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game_id,
                ImageSourceGeometryRevisionModel.source_image_id == source_id,
                ImageSourceGeometryRevisionModel.status != "reverted",
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        if revision is not None:
            acquire_image_sequence_locks(
                self.session,
                game_id=game_id,
                sequence_numbers=set(
                    range(revision.sequence_range_start, revision.sequence_range_end + 1)
                ),
            )
        self.session.scalar(
            select(SourceImageModel).where(SourceImageModel.id == source_id).with_for_update()
        )

    def run_next(
        self, game_id: UUID, operation_id: UUID, cursor: int, key: UUID
    ) -> HistoricalAcceptanceReport:
        self._bind(game_id)
        self._lock(game_id, operation_id)
        operation = self._operation(game_id, operation_id, lock=True)
        command_hash = _hash(
            {
                "policy": HISTORICAL_ACCEPTANCE_POLICY,
                "gameId": game_id,
                "operationId": operation_id,
                "cursor": cursor,
                "action": "run-next",
            }
        )
        prior = self.session.scalar(
            select(Receipt).where(Receipt.game_id == game_id, Receipt.idempotency_key == key)
        )
        if prior is not None:
            if prior.command_sha256 != command_hash:
                raise _conflict("HISTORICAL_ACCEPTANCE_IDEMPOTENCY_CONFLICT")
            return self.report(game_id, operation_id)
        if operation.confirm_key is None:
            raise _conflict("HISTORICAL_ACCEPTANCE_CONFIRMATION_REQUIRED")
        if cursor < operation.run_cursor:
            # Only the durable receipt key replays a consumed command. A new
            # transport key cannot silently claim another command's result.
            raise _conflict("HISTORICAL_ACCEPTANCE_CURSOR_CONFLICT")
        if cursor != operation.run_cursor:
            raise _conflict("HISTORICAL_ACCEPTANCE_CURSOR_CONFLICT")
        if operation.phase == "done":
            return self.report(game_id, operation_id)
        target = self.session.get(Target, (game_id, operation_id, cursor + 1))
        if target is None:
            raise _conflict("HISTORICAL_ACCEPTANCE_FROZEN_TARGET_MISSING")
        self._lock_source(game_id, target.source_image_id)
        qualified = self._qualify(game_id, target.source_image_id)
        reasons = list(target.reasons)
        if not reasons and qualified.fingerprint != target.fingerprint_sha256:
            reasons = ["HISTORICAL_FROZEN_REVISION_CONFLICT"]
        if not reasons:
            reasons = list(qualified.reasons)
        accepted = not reasons and qualified.revision is not None
        if accepted:
            qualified.revision.status = "accepted"  # type: ignore[union-attr]
            self.session.flush()
            recompute_source_image_geometry_completeness(
                self.session,
                game_id,
                target.source_image_id,
                actor=HISTORICAL_ACCEPTANCE_ACTOR,
                materialize=False,
            )
            projection = SqlAlchemyBoardSearchProjectionRepository(self.session)
            projection.sync_review_items(
                tuple(projection.stale_review_item_ids(qualified.review_ids))
            )
            self.session.flush()
            after = self._qualify(game_id, target.source_image_id)
            if after.protected_fingerprint != qualified.protected_fingerprint:
                raise _conflict("HISTORICAL_ACCEPTANCE_PROTECTED_DATA_CHANGED")
        self.session.add(
            Receipt(
                game_id=game_id,
                operation_id=operation_id,
                ordinal=target.ordinal,
                idempotency_key=key,
                command_sha256=command_hash,
                source_image_id=target.source_image_id,
                revision_id=target.revision_id,
                outcome="accepted" if accepted else "skipped",
                reasons=reasons,
                actor=HISTORICAL_ACCEPTANCE_ACTOR,
            )
        )
        operation.accepted_count += int(accepted)
        operation.skipped_count += int(not accepted)
        operation.run_reasons = _count_reasons(operation.run_reasons, reasons)
        operation.run_cursor = target.ordinal
        if operation.run_cursor == operation.preview_cursor:
            operation.phase = "done"
        self.session.flush()
        return self.report(game_id, operation_id)

    def _qualify(self, game_id: UUID, source_id: UUID) -> _Qualification:
        source = self.session.get(SourceImageModel, source_id, populate_existing=True)
        revision = self.session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game_id,
                ImageSourceGeometryRevisionModel.source_image_id == source_id,
                ImageSourceGeometryRevisionModel.status != "reverted",
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if source is None or revision is None:
            return _Qualification(
                revision,
                ("HISTORICAL_SOURCE_GEOMETRY_MISSING",),
                _hash([source_id, None]),
                _hash(None),
                (),
            )
        job = self.session.get(JobModel, source.import_job_id, populate_existing=True)
        boards = self.session.scalars(
            select(RecognizedBoardModel)
            .where(
                RecognizedBoardModel.source_image_id == source_id,
                RecognizedBoardModel.status != "rejected",
            )
            .order_by(RecognizedBoardModel.id)
            .execution_options(populate_existing=True)
        ).all()
        board_ids = [board.id for board in boards]
        reviews = self.session.scalars(
            select(ImageReviewItemModel)
            .where(
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.recognized_board_id.in_(board_ids),
            )
            .order_by(ImageReviewItemModel.id)
            .execution_options(populate_existing=True)
        ).all()
        cells = self.session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.recognized_board_id.in_(board_ids),
            )
            .order_by(ImageSymbolReviewCellModel.id)
        ).all()
        renders = self.session.scalars(
            select(BoardRenderManifestModel)
            .where(BoardRenderManifestModel.recognized_board_id.in_(board_ids))
            .order_by(BoardRenderManifestModel.recognized_board_id)
        ).all()
        canonical = self.session.scalars(
            select(ImageSequenceCanonicalModel)
            .where(
                ImageSequenceCanonicalModel.game_id == game_id,
                ImageSequenceCanonicalModel.sequence_number.between(
                    revision.sequence_range_start, revision.sequence_range_end
                ),
            )
            .order_by(ImageSequenceCanonicalModel.sequence_number)
        ).all()
        owners = {item.recognized_board_id: item for item in reviews}
        own_ids = [item.id for item in reviews]
        external = self.session.scalars(
            select(ImageReviewItemModel.id).where(
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.sequence_number.between(
                    revision.sequence_range_start, revision.sequence_range_end
                ),
                ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
                ImageReviewItemModel.id.not_in(own_ids),
            )
        ).all()
        documents = self.session.scalars(
            select(ImageBoardSearchFastDocumentModel)
            .where(
                ImageBoardSearchFastDocumentModel.game_id == game_id,
                ImageBoardSearchFastDocumentModel.sequence_number.between(
                    revision.sequence_range_start, revision.sequence_range_end
                ),
            )
            .order_by(ImageBoardSearchFastDocumentModel.sequence_number)
        ).all()
        candidates = self.session.scalars(
            select(ImageBoardSearchCandidateModel).where(
                ImageBoardSearchCandidateModel.game_id == game_id,
                ImageBoardSearchCandidateModel.review_item_id.in_(own_ids),
            )
        ).all()
        document_owners = {item.sequence_number: item.review_item_id for item in documents}
        protected = [
            _record(source, ("geometry_completeness_status", "geometry_completeness_evaluated_at")),
            _record(revision, ("status",)),
            [_record(board) for board in boards],
            [_record(item) for item in reviews],
            [_record(cell) for cell in cells],
            [_record(render) for render in renders],
            [_record(item) for item in canonical],
            document_owners,
        ]
        protected_fingerprint = _hash(protected)
        fingerprint = _hash(
            [protected_fingerprint, revision.status, None if job is None else job.input_payload]
        )
        reasons: list[str] = []
        if source.geometry_exception_reason is not None:
            reasons.append("HISTORICAL_OPERATOR_EXCEPTION_PRESENT")
        current_geometry = {board.id: board.geometry_revision for board in boards}
        if any(
            cell.source_geometry_revision_id != revision.id
            or cell.geometry_revision != current_geometry.get(cell.recognized_board_id)
            or cell.approved_source_geometry_revision_id not in (None, revision.id)
            for cell in cells
        ) or any(
            render.source_geometry_revision_id != revision.id
            or render.geometry_revision != current_geometry.get(render.recognized_board_id)
            for render in renders
        ):
            reasons.append("HISTORICAL_MIXED_CELL_OR_RENDER_REVISION")
        if revision.status == "accepted":
            reasons.append("HISTORICAL_ALREADY_ACCEPTED")
        elif revision.status not in ("needs_review", "pending"):
            reasons.append("HISTORICAL_REVISION_NOT_ELIGIBLE")
        if (
            revision.geometry_source != "auto"
            or revision.engine_kind != "neural_grid_v1"
            or revision.engine_version != NEURAL_AUTO_CROP_POLICY
        ):
            reasons.append("HISTORICAL_MODEL_PROVENANCE_UNSUPPORTED")
        proposal: object = None
        binding: object = None
        initialization = revision.global_initialization or {}
        evidence = initialization.get("v3EngineAcceptance")
        if isinstance(evidence, Mapping):
            proposal, binding = evidence.get("proposal"), evidence.get("binding")
        elif job is not None:
            try:
                proposal, binding = original_neural_evidence(
                    self.artifact_root,
                    job.input_payload,
                    game_id=str(game_id),
                    source_sha256=source.checksum_sha256,
                    build=False,
                )
            except HistoricalEvidenceUnavailable as error:
                reasons.append(str(error))
        try:
            snapshot = NeuralGridSnapshot.from_payload(
                None if job is None else job.input_payload.get("neural_grid_proposal")
            )
            # Read the pinned version; never the game's currently active version.
            snapshot_payload: object = snapshot.to_payload()
        except NeuralGridProposalError:
            snapshot_payload = None
            reasons.append("HISTORICAL_MODEL_SNAPSHOT_INVALID")
        slots = {item.get("positionIndex"): item for item in revision.board_geometries}
        canonical_owners = {item.sequence_number: item.review_item_id for item in canonical}
        positions = []
        for board in boards:
            owner, slot = owners.get(board.id), slots.get(board.position_index)
            geometry = board.board_geometry
            same_geometry = (
                isinstance(slot, Mapping)
                and isinstance(geometry, Mapping)
                and slot.get("finalQuad") == geometry.get("quad")
                and all(
                    slot.get(field) == geometry.get(field)
                    for field in (
                        "latticeNodes",
                        "neuralExecutionPolicy",
                        "neuralProposalChecksumSha256",
                        "neuralProposalBinding",
                        "detectionId",
                    )
                )
                and slot.get("sequenceNumber") == board.sequence_number
            )
            positions.append(
                V3EnginePosition(
                    position=board.position_index,
                    sequence=board.sequence_number,
                    geometry=geometry,
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
                    and same_geometry,
                    current_owner=owner is not None
                    and owner.import_job_id == source.import_job_id
                    and owner.sequence_number == board.sequence_number
                    and owner.status in ("pending", "accepted", "corrected")
                    and not external
                    and board.sequence_number is not None
                    and canonical_owners.get(board.sequence_number, owner.id) == owner.id
                    and document_owners.get(board.sequence_number) == owner.id,
                    grid_issue=any(
                        cell.recognized_board_id == board.id
                        and cell.quality_issue == "grid_issue"
                        and cell.review_state == "pending"
                        and cell.geometry_revision == board.geometry_revision
                        and cell.source_geometry_revision_id == board.source_geometry_revision_id
                        for cell in cells
                    ),
                )
            )
        if {item.review_item_id for item in candidates} != set(own_ids) or len(documents) != len(
            boards
        ):
            reasons.append("HISTORICAL_EXISTING_PROJECTION_MISSING")
        pending = self.session.scalar(
            select(ImageBoardGeometryPendingModel.id)
            .where(
                ImageBoardGeometryPendingModel.game_id == game_id,
                ImageBoardGeometryPendingModel.source_image_id == source_id,
                ImageBoardGeometryPendingModel.status == "pending",
            )
            .limit(1)
        )
        reasons.extend(
            qualify_v3_engine_acceptance(
                policy=V3_ENGINE_ACCEPTANCE_POLICY,
                proposal=proposal,
                binding=binding,
                model_snapshot=snapshot_payload,
                game_id=str(game_id),
                source_checksum_sha256=source.checksum_sha256,
                width=revision.oriented_width,
                height=revision.oriented_height,
                active_slots=revision.active_board_slots,
                sequence_start=revision.sequence_range_start,
                sequence_end=revision.sequence_range_end,
                positions=positions,
                deferred=pending is not None,
                source_current=job is not None
                and job.game_id == game_id
                and revision.source_checksum_sha256 == source.checksum_sha256
                and revision.normalized_pixel_checksum_sha256
                == source.normalized_pixel_checksum_sha256
                and revision.oriented_width == source.oriented_width
                and revision.oriented_height == source.oriented_height
                and revision.normalization_adapter_version == source.normalization_adapter_version,
            )
        )
        return _Qualification(
            revision,
            tuple(dict.fromkeys(reasons)),
            fingerprint,
            protected_fingerprint,
            tuple(own_ids),
        )

    def report(
        self, game_id: UUID, operation_id: UUID, after: int = 0
    ) -> HistoricalAcceptanceReport:
        self._bind(game_id)
        operation = self._operation(game_id, operation_id)
        rows = self.session.execute(
            select(Target, Receipt)
            .outerjoin(
                Receipt,
                (Receipt.game_id == Target.game_id)
                & (Receipt.operation_id == Target.operation_id)
                & (Receipt.ordinal == Target.ordinal),
            )
            .where(
                Target.game_id == game_id,
                Target.operation_id == operation_id,
                Target.ordinal > after,
            )
            .order_by(Target.ordinal)
            .limit(26)
        ).all()
        return HistoricalAcceptanceReport(
            game_id=game_id,
            operation_id=operation_id,
            phase=operation.phase,
            preparation_state=operation.preparation_state,
            started_at=operation.started_at,
            preview_cursor=operation.preview_cursor,
            run_cursor=operation.run_cursor,
            source_count=operation.preview_cursor,
            revision_count=operation.revision_count,
            eligible_count=operation.eligible_count,
            accepted_count=operation.accepted_count,
            skipped_count=operation.skipped_count,
            preview_reasons=dict(operation.preview_reasons),
            run_reasons=dict(operation.run_reasons),
            items=tuple(
                HistoricalAcceptanceItem(
                    ordinal=target.ordinal,
                    source_image_id=target.source_image_id,
                    revision_id=target.revision_id,
                    previous_status=target.previous_status,
                    reasons=tuple(target.reasons if receipt is None else receipt.reasons),
                    outcome=None if receipt is None else receipt.outcome,
                )
                for target, receipt in rows[:25]
            ),
            next_item_cursor=rows[24][0].ordinal if len(rows) > 25 else None,
        )
