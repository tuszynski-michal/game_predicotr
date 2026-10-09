"""Use cases: list, preview and revert the last manual grid-geometry correction.

TASK-0945 (plan D-538). The repository evaluates every rule from facts read
from storage (under lock for a revert) with
``domain.geometry_correction_reverts.evaluate_revert_eligibility`` and performs
the revert in the caller's single transaction; this service validates the
request and delegates. HTTP adapters come with TASK-0947.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.geometry_correction_reverts import (
    DEFAULT_GEOMETRY_CORRECTION_LIST_LIMIT,
    GEOMETRY_REVERT_REQUEST_INVALID,
    MAX_GEOMETRY_CORRECTION_LIST_LIMIT,
    MAX_GEOMETRY_REVERT_ACTOR_LENGTH,
    GeometryCorrectionKind,
    RevertBlockingReason,
    blocking_reason_message,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_reviews import ImageReviewError


@dataclass(frozen=True, slots=True)
class GeometryCorrectionEntry:
    """One manual geometry save of the import, newest first in a list."""

    board_geometry_revision_id: UUID
    kind: GeometryCorrectionKind
    recognized_board_id: UUID
    review_item_id: UUID
    pending_geometry_id: UUID | None
    source_image_id: UUID
    sequence_number: int
    position_index: int
    created_at: datetime
    actor: str
    geometry_revision: int
    resolution_revision: int
    blocking_reason: RevertBlockingReason | None

    @property
    def revertable(self) -> bool:
        return self.blocking_reason is None

    @property
    def blocking_reason_message(self) -> str | None:
        return (
            None if self.blocking_reason is None else blocking_reason_message(self.blocking_reason)
        )


@dataclass(frozen=True, slots=True)
class GeometryCorrectionRevertPreview:
    """Effects of a revert, computed without any write."""

    correction: GeometryCorrectionEntry
    removes_board: bool
    removed_cell_count: int
    repointed_board_count: int
    restored_cell_decision_count: int
    reverted_source_geometry_revision_id: UUID
    restored_source_geometry_revision_id: UUID | None
    restored_source_engine_kind: str | None
    restored_source_status: str | None


@dataclass(frozen=True, slots=True)
class GeometryCorrectionRevertResult:
    revert_id: UUID
    created: bool
    kind: GeometryCorrectionKind
    board_geometry_revision_id: UUID
    pending_geometry_id: UUID | None
    recognized_board_id: UUID
    review_item_id: UUID
    reverted_source_geometry_revision_id: UUID
    restored_source_geometry_revision_id: UUID
    repointed_board_ids: tuple[UUID, ...]
    removed_cell_count: int
    source_image_geometry_status: SourceImageGeometryStatus | None
    snapshot_checksum_sha256: str
    created_at: datetime


class GeometryCorrectionRevertRepository(Protocol):
    def list_recent(
        self, *, game_id: UUID, import_job_id: UUID, limit: int
    ) -> tuple[GeometryCorrectionEntry, ...]: ...

    def preview(
        self, *, game_id: UUID, import_job_id: UUID, board_geometry_revision_id: UUID
    ) -> GeometryCorrectionRevertPreview: ...

    def revert(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        board_geometry_revision_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        actor: str,
        reverted_at: datetime,
    ) -> GeometryCorrectionRevertResult: ...


def _require_revision_token(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ImageReviewError(
            GEOMETRY_REVERT_REQUEST_INVALID, f"{name} must be a non-negative integer."
        )
    return value


def _require_actor(actor: str) -> str:
    value = actor.strip() if isinstance(actor, str) else ""
    if not value or len(value) > MAX_GEOMETRY_REVERT_ACTOR_LENGTH:
        raise ImageReviewError(
            GEOMETRY_REVERT_REQUEST_INVALID,
            f"The actor must have 1-{MAX_GEOMETRY_REVERT_ACTOR_LENGTH} characters.",
        )
    return value


class GeometryCorrectionRevertService:
    def __init__(self, repository: GeometryCorrectionRevertRepository) -> None:
        self._repository = repository

    def list_recent(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        limit: int = DEFAULT_GEOMETRY_CORRECTION_LIST_LIMIT,
    ) -> tuple[GeometryCorrectionEntry, ...]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_GEOMETRY_CORRECTION_LIST_LIMIT
        ):
            raise ImageReviewError(
                GEOMETRY_REVERT_REQUEST_INVALID,
                f"The limit must be between 1 and {MAX_GEOMETRY_CORRECTION_LIST_LIMIT}.",
            )
        return self._repository.list_recent(
            game_id=game_id, import_job_id=import_job_id, limit=limit
        )

    def preview(
        self, *, game_id: UUID, import_job_id: UUID, board_geometry_revision_id: UUID
    ) -> GeometryCorrectionRevertPreview:
        return self._repository.preview(
            game_id=game_id,
            import_job_id=import_job_id,
            board_geometry_revision_id=board_geometry_revision_id,
        )

    def revert(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        board_geometry_revision_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        actor: str,
        reverted_at: datetime,
    ) -> GeometryCorrectionRevertResult:
        """Revert one correction in the caller's transaction, all or nothing.

        A retry with the same idempotency key returns the stored result
        (``created=False``); the same key for another correction conflicts.
        """

        return self._repository.revert(
            game_id=game_id,
            import_job_id=import_job_id,
            board_geometry_revision_id=board_geometry_revision_id,
            idempotency_key=idempotency_key,
            expected_geometry_revision=_require_revision_token(
                expected_geometry_revision, "expectedGeometryRevision"
            ),
            expected_resolution_revision=_require_revision_token(
                expected_resolution_revision, "expectedResolutionRevision"
            ),
            actor=_require_actor(actor),
            reverted_at=reverted_at,
        )


__all__ = [
    "GeometryCorrectionEntry",
    "GeometryCorrectionRevertPreview",
    "GeometryCorrectionRevertRepository",
    "GeometryCorrectionRevertResult",
    "GeometryCorrectionRevertService",
]
