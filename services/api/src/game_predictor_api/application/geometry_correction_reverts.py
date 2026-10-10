"""Use cases: list, preview and revert the last manual grid-geometry correction.

TASK-0966/TASK-0967 (plan D-542). The repository evaluates every rule from
facts read from storage (under lock for a revert) with
``domain.geometry_correction_reverts.evaluate_revert_eligibility`` and performs
the revert in the caller's single transaction; this service validates the
request and delegates. Both kinds are reverted without rendering: a deferred
slot loses the rows its save created, an existing board gets revision
``N + 1`` that reuses the stored render of its previous revision. HTTP
adapters come with TASK-0968.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from game_predictor_api.application.image_review_assets import (
    resolve_grid_review_source_asset,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_correction_reverts import (
    DEFAULT_GEOMETRY_CORRECTION_LIST_LIMIT,
    GEOMETRY_REVERT_RENDER_FAILED,
    GEOMETRY_REVERT_REQUEST_INVALID,
    MAX_GEOMETRY_CORRECTION_LIST_LIMIT,
    MAX_GEOMETRY_REVERT_ACTOR_LENGTH,
    GeometryCorrectionKind,
    RejectionTarget,
    RevertBlockingReason,
    blocking_reason_message,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewSourceAsset
from game_predictor_api.domain.image_reviews import ImageReviewConflictError, ImageReviewError
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError


@dataclass(frozen=True, slots=True)
class GeometryCorrectionEntry:
    """One manual geometry save of the import, newest first in a list."""

    board_geometry_revision_id: UUID
    kind: GeometryCorrectionKind
    # ``None`` for the rejection of a deferred slot, which has no board yet.
    recognized_board_id: UUID | None
    review_item_id: UUID | None
    pending_geometry_id: UUID | None
    source_image_id: UUID
    sequence_number: int
    position_index: int
    created_at: datetime
    actor: str
    geometry_revision: int
    resolution_revision: int
    blocking_reason: RevertBlockingReason | None
    # ``rejection`` entries only: ``board_geometry_revision_id`` is then the id
    # of the rejected slot (``pending_slot``) or of the rejection event of the
    # review item (``review_item``).
    rejection_target: RejectionTarget | None = None
    rejection_reason: str | None = None
    rejection_note: str | None = None

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
    reverted_source_geometry_revision_id: UUID | None
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
    recognized_board_id: UUID | None
    review_item_id: UUID | None
    # ``None`` for the revert of a rejection (no geometry revision moves).
    reverted_source_geometry_revision_id: UUID | None
    restored_source_geometry_revision_id: UUID | None
    repointed_board_ids: tuple[UUID, ...]
    removed_cell_count: int
    source_image_geometry_status: SourceImageGeometryStatus | None
    snapshot_checksum_sha256: str
    created_at: datetime
    # Case A (TASK-0967): the revision ``N + 1`` the revert wrote and the
    # number of cells whose decisions it restored.
    restored_geometry_revision: int | None = None
    restored_cell_decision_count: int = 0


@dataclass(frozen=True, slots=True)
class RestoredRenderRequest:
    """The stored cell renders a case-A revert restores (TASK-0967).

    ``render_specs`` maps each cell index to the ``renderSpec`` of the
    restored revision's manifest entry.
    """

    review_item_id: UUID
    source_image_id: UUID
    source_relative_path: str
    source_checksum_sha256: str
    source_width: int
    source_height: int
    geometry_revision: int
    resolution_revision: int
    topology: BoardTopology
    render_specs: Mapping[int, Mapping[str, object]]


class RestoredRenderVerifier(Protocol):
    def rendered_pixel_checksums(self, request: RestoredRenderRequest) -> Mapping[int, str]:
        """The checksum of the pixels each spec renders now, by cell index."""
        ...


class VirtualRestoredRenderVerifier:
    """Render the restored cells as every preview does (D-462 on real pixels).

    The revert reuses the stored render specification of the restored
    revision; the pixels it produces today decide whether an approval comes
    back. The render is the preview's source-direct warp of the attested
    managed original, so a cell approved here is shown with exactly the
    checksum it carries.
    """

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()

    def rendered_pixel_checksums(self, request: RestoredRenderRequest) -> Mapping[int, str]:
        from game_predictor_worker.images.normalization import (
            CanonicalSourceLoader,
            CanonicalSourceLoadError,
            rgb_pixel_checksum_sha256,
        )
        from game_predictor_worker.images.virtual_cell_extraction import (
            VirtualCellExtractionError,
        )

        if not request.render_specs:
            return {}
        path = resolve_grid_review_source_asset(
            ImageGridReviewSourceAsset(
                review_item_id=request.review_item_id,
                source_image_id=request.source_image_id,
                source_relative_path=request.source_relative_path,
                source_checksum_sha256=request.source_checksum_sha256,
                source_width=request.source_width,
                source_height=request.source_height,
                geometry_revision=request.geometry_revision,
                resolution_revision=request.resolution_revision,
                topology=request.topology,
            ),
            self._artifact_root,
        ).path
        loader = CanonicalSourceLoader()
        try:
            frame = loader.load(
                path, expected_source_checksum_sha256=request.source_checksum_sha256
            )
            return {
                index: rgb_pixel_checksum_sha256(self._render(spec, frame))
                for index, spec in sorted(request.render_specs.items())
            }
        except (
            CanonicalSourceLoadError,
            VirtualCellExtractionError,
            SymbolCellReviewError,
        ) as error:
            raise ImageReviewConflictError(
                GEOMETRY_REVERT_RENDER_FAILED,
                "Nie udało się odtworzyć renderu przywracanych komórek: "
                f"{getattr(error, 'code', type(error).__name__)}.",
            ) from error
        finally:
            loader.clear()

    def _render(self, spec: Mapping[str, object], frame: Any) -> Any:
        from game_predictor_api.application.virtual_cell_previews import render_spec_cell_rgb

        return render_spec_cell_rgb(render_spec=spec, frame=frame)


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
        render_verifier: RestoredRenderVerifier | None = None,
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
    def __init__(
        self,
        repository: GeometryCorrectionRevertRepository,
        *,
        render_verifier: RestoredRenderVerifier | None = None,
    ) -> None:
        """``render_verifier`` renders the cells a board-revision revert restores.

        Without it a board-revision revert is refused
        (``GEOMETRY_REVERT_RENDERER_UNAVAILABLE``); deferred-slot reverts never
        render.
        """

        self._repository = repository
        self._render_verifier = render_verifier

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
            render_verifier=self._render_verifier,
        )


__all__ = [
    "GeometryCorrectionEntry",
    "GeometryCorrectionRevertPreview",
    "GeometryCorrectionRevertRepository",
    "GeometryCorrectionRevertResult",
    "GeometryCorrectionRevertService",
    "RestoredRenderRequest",
    "RestoredRenderVerifier",
    "VirtualRestoredRenderVerifier",
]
