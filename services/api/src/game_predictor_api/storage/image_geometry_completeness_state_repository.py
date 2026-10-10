"""Persisted D-484 geometry completeness of source images: the pipeline gate.

TASK-0807. ``source_images.geometry_completeness_status`` is the state the
pipeline reads before it cuts a board into symbol-review cells or projects its
symbol evidence into board search:

* every write that creates or changes a board, its geometry, its geometry
  approval, its liveness or a deferred-geometry row calls
  ``recompute_source_image_geometry_completeness`` in its own transaction; the
  recompute classifies the image with the domain classifier
  (``domain.image_geometry_completeness``, the single definition) and never
  catches its own errors, so a failed recompute rolls the geometry write back;
* ``withheld_review_item_ids`` is the one gate predicate used by the symbol-cell
  write-through, the symbol-cell backfill and the search projection: a board is
  withheld while its image is ``geometry_incomplete`` (or, under an operator
  exception, while its own position is not ``ok``/approved partial) and it has
  no cells yet. Existing cells and decisions are never touched;
* an image that becomes admitted (``geometry_incomplete`` -> complete or
  exception) materializes every active board in the same transaction through
  the existing write-through;
* a new source geometry revision re-points the live boards of the image whose
  geometry is identical in the new revision (``plan_board_repoint`` /
  ``apply_board_repoint``): pointer columns only, never crops or decisions.

Every statement filters by ``game_id`` and runs after ``GameStorageRouter.bind``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_geometry_completeness import (
    ADMITTED_SOURCE_IMAGE_STATUSES,
    MAX_GEOMETRY_EXCEPTION_ACTOR_LENGTH,
    GeometryImageState,
    GeometryPositionFacts,
    SourceImageGeometryStatus,
    classify_position,
    geometry_gate_withholds_board,
    recomputed_status,
    require_geometry_exception_reason,
)
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourceLatticeNodes,
    SourcePoint,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewError,
    ImageReviewNotFoundError,
)
from game_predictor_api.domain.neural_crop_policy import full_neural_prediction_geometry
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.image_geometry_completeness_repository import (
    classify_source_images,
)
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    GameModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.sequence_ownership_lock import (
    acquire_sequence_ownership_lock,
)

GEOMETRY_COMPLETENESS_ACTOR: Final = "system:geometry-completeness"
_ACTIVE_REVIEW_STATUSES: Final = ("pending", "accepted", "corrected")

# Reasons a live board on an older source revision is not re-pointed.
REPOINT_POSITION_NOT_IN_REVISION: Final = "POSITION_NOT_IN_NEWEST_REVISION"
REPOINT_SOURCE_PROVENANCE_DIFFERS: Final = "SOURCE_REVISION_PROVENANCE_DIFFERS"
REPOINT_GEOMETRY_ENTRY_DIFFERS: Final = "GEOMETRY_ENTRY_DIFFERS"
REPOINT_BOARD_GEOMETRY_REVISION_PINNED: Final = "BOARD_GEOMETRY_REVISION_PINNED"
REPOINT_BOARD_CHECKSUM_DRIFT: Final = "BOARD_CHECKSUM_DRIFT"
REPOINT_RENDER_MANIFEST_DRIFT: Final = "RENDER_MANIFEST_DRIFT"
REPOINT_CELL_PROVENANCE_DRIFT: Final = "CELL_PROVENANCE_DRIFT"
REPOINT_VERIFIED_COHORT_PINNED: Final = "VERIFIED_COHORT_PINNED"


@dataclass(frozen=True, slots=True)
class SourceImageGeometryRecompute:
    source_image_id: UUID
    image_state: GeometryImageState
    previous_status: SourceImageGeometryStatus | None
    status: SourceImageGeometryStatus | None
    materialized_review_item_count: int = 0

    @property
    def became_admitted(self) -> bool:
        return (
            self.previous_status is SourceImageGeometryStatus.GEOMETRY_INCOMPLETE
            and self.status in ADMITTED_SOURCE_IMAGE_STATUSES
        )


@dataclass(frozen=True, slots=True)
class BoardRepointDecision:
    """One live board that points to an older source geometry revision."""

    recognized_board_id: UUID
    source_image_id: UUID
    review_item_id: UUID | None
    position_index: int
    from_revision_id: UUID
    from_revision: int
    to_revision_id: UUID
    to_revision: int
    to_revision_status: str
    to_geometry_checksum_sha256: str
    # ``None`` = the geometry is identical in the newer revision: re-pointable.
    reason_code: str | None

    @property
    def repointable(self) -> bool:
        return self.reason_code is None


@dataclass(frozen=True, slots=True)
class SourceImageGeometryException:
    source_image_id: UUID
    status: SourceImageGeometryStatus | None
    image_state: GeometryImageState
    reason: str | None
    exception_by: str | None
    exception_at: datetime | None
    materialized_review_item_count: int


def _status(value: str | None) -> SourceImageGeometryStatus | None:
    return None if value is None else SourceImageGeometryStatus(value)


def _execute(session: Session, sql: str, parameters: Mapping[str, object]) -> Any:
    # Connection-level execution keeps the read route of a read-only
    # transaction: the session's generic textual-SQL event treats unknown SQL
    # as a write (see ``PartialBoardReconciliationRepository``).
    return session.connection().execute(text(sql), dict(parameters))


def recompute_source_image_geometry_completeness(
    session: Session,
    game_id: UUID,
    source_image_id: UUID,
    *,
    actor: str = GEOMETRY_COMPLETENESS_ACTOR,
    now: datetime | None = None,
    materialize: bool = True,
) -> SourceImageGeometryRecompute:
    """Classify one image and persist its gate status in the caller's transaction.

    No exception is caught here: a failed recompute fails the caller's
    geometry write. With ``materialize`` an image that just became admitted
    gets every active board synchronized (search and symbol cells) right away;
    callers that synchronize the image's items themselves pass ``False`` and
    use ``active_review_item_ids``.
    """

    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
    session.flush()
    locked = _execute(
        session,
        "SELECT id FROM source_images WHERE game_id = :game_id AND id = :source_image_id "
        "FOR UPDATE",
        {"game_id": game_id, "source_image_id": source_image_id},
    ).first()
    source = (
        None
        if locked is None
        else session.get(SourceImageModel, source_image_id, populate_existing=True)
    )
    if source is None:
        raise ImageReviewNotFoundError(
            "IMAGE_GEOMETRY_SOURCE_IMAGE_NOT_FOUND",
            "The source image does not belong to this game.",
        )
    state = classify_source_images(session, game_id, (source_image_id,))[source_image_id]
    previous = _status(source.geometry_completeness_status)
    status = recomputed_status(current=previous, state=state)
    source.geometry_completeness_status = None if status is None else status.value
    source.geometry_completeness_evaluated_at = now or datetime.now(UTC)
    if status is not SourceImageGeometryStatus.GEOMETRY_EXCEPTION:
        source.geometry_exception_reason = None
        source.geometry_exception_by = None
        source.geometry_exception_at = None
    session.flush()
    result = SourceImageGeometryRecompute(
        source_image_id=source_image_id,
        image_state=state,
        previous_status=previous,
        status=status,
    )
    if materialize and result.became_admitted:
        count = materialize_admitted_source_image(session, game_id, source_image_id, actor=actor)
        result = SourceImageGeometryRecompute(
            source_image_id=source_image_id,
            image_state=state,
            previous_status=previous,
            status=status,
            materialized_review_item_count=count,
        )
    return result


_DEFERRED_MATERIALIZATIONS_KEY: Final = "game_predictor.deferred_gate_materializations"


def lock_source_images(session: Session, game_id: UUID, source_image_ids: Iterable[UUID]) -> None:
    """Lock several source rows in one statement, in ascending id order (TASK-0971)."""

    ids = sorted(set(source_image_ids), key=str)
    if not ids:
        return
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
    _execute(
        session,
        "SELECT id FROM source_images WHERE game_id = :game_id AND id = ANY (:ids) "
        "ORDER BY id FOR UPDATE",
        {"game_id": game_id, "ids": ids},
    ).all()


def start_deferred_gate_materializations(session: Session) -> None:
    """Begin collecting admitted images for ``finish_deferred_gate_materializations``."""

    session.info[_DEFERRED_MATERIALIZATIONS_KEY] = {}


def finish_deferred_gate_materializations(session: Session) -> int:
    """Stop collecting and cut the collected images (after the last source lock)."""

    bucket = session.info.pop(_DEFERRED_MATERIALIZATIONS_KEY, None) or {}
    return materialize_deferred_source_images(session, bucket)


@contextmanager
def deferred_gate_materializations(session: Session) -> Iterator[dict[tuple[UUID, UUID], str]]:
    """Collect the images admitted by multi-image recomputes; the caller cuts them.

    A writer that locks more source rows later in its transaction (the import
    writer, one board after another) cuts the admitted images only after its
    last source lock, so the counters state is never locked before a source
    row (global lock order, ``storage.sequence_ownership_lock``).
    """

    info = session.info
    previous = info.get(_DEFERRED_MATERIALIZATIONS_KEY)
    bucket: dict[tuple[UUID, UUID], str] = {}
    info[_DEFERRED_MATERIALIZATIONS_KEY] = bucket
    try:
        yield bucket
    finally:
        if previous is None:
            info.pop(_DEFERRED_MATERIALIZATIONS_KEY, None)
        else:
            info[_DEFERRED_MATERIALIZATIONS_KEY] = previous


def materialize_deferred_source_images(
    session: Session, bucket: Mapping[tuple[UUID, UUID], str]
) -> int:
    """Cut the deferred admitted images (ascending id) after the last source lock."""

    count = 0
    for game_id, source_image_id in sorted(bucket, key=lambda key: (str(key[0]), str(key[1]))):
        count += materialize_admitted_source_image(
            session, game_id, source_image_id, actor=bucket[(game_id, source_image_id)]
        )
    return count


def recompute_source_images(
    session: Session,
    game_id: UUID,
    source_image_ids: Iterable[UUID],
    *,
    actor: str = GEOMETRY_COMPLETENESS_ACTOR,
    now: datetime | None = None,
    exclude_source_image_id: UUID | None = None,
) -> tuple[SourceImageGeometryRecompute, ...]:
    """Recompute several images: all source rows first, then the cuts (TASK-0971).

    Every source row is locked in ascending id order before any image is
    recomputed, and the images that became admitted are cut only after all of
    them (the cut locks the counters state). Inside
    ``deferred_gate_materializations`` the cuts are left to the caller.
    """

    ids = sorted(set(source_image_ids) - {exclude_source_image_id}, key=str)
    if not ids:
        return ()
    lock_source_images(session, game_id, ids)
    results = tuple(
        recompute_source_image_geometry_completeness(
            session, game_id, image_id, actor=actor, now=now, materialize=False
        )
        for image_id in ids
    )
    admitted = [result.source_image_id for result in results if result.became_admitted]
    info = getattr(session, "info", None)
    bucket = info.get(_DEFERRED_MATERIALIZATIONS_KEY) if isinstance(info, dict) else None
    if bucket is not None:
        for image_id in admitted:
            bucket[(game_id, image_id)] = actor
    else:
        for image_id in admitted:
            materialize_admitted_source_image(session, game_id, image_id, actor=actor)
    return results


def recompute_source_images_of_boards(
    session: Session,
    game_id: UUID,
    recognized_board_ids: Iterable[UUID],
    *,
    actor: str = GEOMETRY_COMPLETENESS_ACTOR,
) -> tuple[SourceImageGeometryRecompute, ...]:
    """Recompute every image that owns one of the boards (sorted, deterministic)."""

    board_ids = sorted(set(recognized_board_ids), key=str)
    if not board_ids:
        return ()
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
    session.flush()
    image_ids = sorted(
        {
            row[0]
            for row in _execute(
                session,
                "SELECT DISTINCT source_image_id FROM recognized_boards "
                "WHERE game_id = :game_id AND id = ANY (:board_ids)",
                {"game_id": game_id, "board_ids": board_ids},
            )
        },
        key=str,
    )
    return recompute_source_images(session, game_id, image_ids, actor=actor)


def recompute_source_images_of_review_items(
    session: Session,
    game_id: UUID,
    review_item_ids: Iterable[UUID],
    *,
    exclude_source_image_id: UUID | None = None,
    actor: str = GEOMETRY_COMPLETENESS_ACTOR,
) -> tuple[SourceImageGeometryRecompute, ...]:
    """Recompute the images of the items' boards (e.g. a lost sequence ownership)."""

    item_ids = sorted(set(review_item_ids), key=str)
    if not item_ids:
        return ()
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
    session.flush()
    image_ids = sorted(
        {
            row[0]
            for row in _execute(
                session,
                """SELECT DISTINCT b.source_image_id
                FROM image_review_items ri
                JOIN recognized_boards b ON b.game_id = ri.game_id AND b.id = ri.recognized_board_id
                WHERE ri.game_id = :game_id AND ri.id = ANY (:item_ids)""",
                {"game_id": game_id, "item_ids": item_ids},
            )
        }
        - ({exclude_source_image_id} if exclude_source_image_id is not None else set()),
        key=str,
    )
    return recompute_source_images(session, game_id, image_ids, actor=actor)


def active_review_item_ids(
    session: Session, game_id: UUID, source_image_id: UUID
) -> tuple[UUID, ...]:
    """Active review items of the live boards of one image, by position."""

    return tuple(
        row[0]
        for row in _execute(
            session,
            """SELECT ri.id
            FROM recognized_boards b
            JOIN image_review_items ri ON ri.game_id = b.game_id AND ri.recognized_board_id = b.id
            WHERE b.game_id = :game_id AND b.source_image_id = :source_image_id
              AND b.status <> 'rejected' AND ri.status IN ('pending', 'accepted', 'corrected')
            ORDER BY b.position_index""",
            {"game_id": game_id, "source_image_id": source_image_id},
        )
    )


def materialize_admitted_source_image(
    session: Session,
    game_id: UUID,
    source_image_id: UUID,
    *,
    actor: str = GEOMETRY_COMPLETENESS_ACTOR,
) -> int:
    """Synchronize every active board of an admitted image (search, then cells).

    The existing write-through does the work, so it is idempotent: a cell key
    that exists is updated, never duplicated.
    """

    # Local imports: both modules use the gate predicate of this module.
    from game_predictor_api.storage.board_search_projection_repository import (
        SqlAlchemyBoardSearchProjectionRepository,
    )
    from game_predictor_api.storage.image_symbol_review_repository import (
        SymbolCellReviewWriteThroughCoordinator,
    )

    review_item_ids = active_review_item_ids(session, game_id, source_image_id)
    if not review_item_ids:
        return 0
    SqlAlchemyBoardSearchProjectionRepository(session).sync_review_items(review_item_ids)
    coordinator = SymbolCellReviewWriteThroughCoordinator(session)
    for review_item_id in review_item_ids:
        coordinator.synchronize_after_geometry_admission(
            game_id=game_id, review_item_id=review_item_id, actor=actor
        )
    return len(review_item_ids)


def withheld_review_item_ids(
    session: Session,
    game_id: UUID,
    rows: Iterable[tuple[UUID, RecognizedBoardModel, SourceImageModel]],
) -> frozenset[UUID]:
    """Review items whose board the D-484 gate withholds (one predicate for all).

    ``rows`` are ``(review_item_id, board, source)``. Only images with a
    non-``NULL`` status other than ``geometry_complete`` need a database read:
    which of their items already have cells, and (under an exception) the
    status of the source revision each board points to.
    """

    gated = [
        (review_item_id, board, source)
        for review_item_id, board, source in rows
        if source.geometry_completeness_status
        in {
            SourceImageGeometryStatus.GEOMETRY_INCOMPLETE.value,
            SourceImageGeometryStatus.GEOMETRY_EXCEPTION.value,
        }
    ]
    if not gated:
        return frozenset()
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
    item_ids = sorted({review_item_id for review_item_id, _board, _source in gated}, key=str)
    with_cells = {
        row[0]
        for row in _execute(
            session,
            "SELECT DISTINCT review_item_id FROM image_symbol_review_cells "
            "WHERE game_id = :game_id AND review_item_id = ANY (:item_ids)",
            {"game_id": game_id, "item_ids": item_ids},
        )
    }
    revision_ids = sorted(
        {
            board.source_geometry_revision_id
            for _item, board, source in gated
            if board.source_geometry_revision_id is not None
            and source.geometry_completeness_status
            == SourceImageGeometryStatus.GEOMETRY_EXCEPTION.value
        },
        key=str,
    )
    accepted_revisions = (
        {
            row[0]
            for row in _execute(
                session,
                "SELECT id FROM image_source_geometry_revisions "
                "WHERE game_id = :game_id AND id = ANY (:revision_ids) AND status = 'accepted'",
                {"game_id": game_id, "revision_ids": revision_ids},
            )
        }
        if revision_ids
        else set()
    )
    withheld: set[UUID] = set()
    for review_item_id, board, source in gated:
        if (
            board.asset_mode == "virtual_source"
            and board.geometry_engine_name == "neural_grid_v1"
            and board.completeness_status == "complete"
            and board.source_geometry_revision_id is not None
            and full_neural_prediction_geometry(
                board.board_geometry,
                position=board.position_index,
                sequence=board.sequence_number,
                width=source.width,
                height=source.height,
                game_id=str(game_id),
                source_checksum_sha256=source.checksum_sha256,
            )
        ):
            continue
        approved = (
            board.approved_geometry_revision is not None
            and board.approved_geometry_revision == board.geometry_revision
        )
        position_state = classify_position(
            GeometryPositionFacts(
                position_index=int(board.position_index),
                board_exists=board.status != "rejected",
                completeness_status=board.completeness_status,
                geometry_approved=approved,
                source_revision_accepted=board.source_geometry_revision_id in accepted_revisions,
            )
        ).state
        if geometry_gate_withholds_board(
            image_status=_status(source.geometry_completeness_status),
            position_state=position_state,
            qualified_partial_approved=board.geometry_qualification is not None and approved,
            has_cells=review_item_id in with_cells,
            manual_neural_lattice_approved=_manual_neural_lattice_approved(board),
        ):
            withheld.add(review_item_id)
    return frozenset(withheld)


def _manual_neural_lattice_approved(board: RecognizedBoardModel) -> bool:
    """D-522: a current human save, never an unapproved neural proposal."""
    geometry = board.board_geometry
    if (
        board.asset_mode != "virtual_source"
        or board.geometry_engine_name != "manual_v1"
        or board.geometry_revision <= 0
        or board.approved_geometry_revision != board.geometry_revision
        or not board.geometry_approved_by
        or board.geometry_approved_at is None
        or not isinstance(geometry, Mapping)
    ):
        return False
    checksum = geometry.get("neuralProposalChecksumSha256")
    nodes = geometry.get("latticeNodes")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or any(character not in "0123456789abcdef" for character in checksum)
        or not isinstance(nodes, list)
        or not all(isinstance(point, Mapping) for point in nodes)
    ):
        return False
    try:
        SourceLatticeNodes(
            tuple(SourcePoint(float(point["x"]), float(point["y"])) for point in nodes)
        )
    except (ImageGeometryContractError, KeyError, TypeError, ValueError):
        return False
    return True


# -- re-pointing of live boards to the newest source revision ---------------

_REPOINT_PLAN_SQL = """
WITH newest AS (
  SELECT DISTINCT ON (r.source_image_id)
    r.source_image_id, r.id, r.revision, r.status, r.board_geometries, r.active_board_slots,
    r.topology_rules_version_id, r.geometry_checksum_sha256, r.source_checksum_sha256,
    r.normalized_pixel_checksum_sha256
  FROM image_source_geometry_revisions r
  WHERE r.game_id = :game_id AND r.source_image_id = ANY (:image_ids)
    AND r.status <> 'reverted'
  ORDER BY r.source_image_id, r.revision DESC
)
SELECT b.id, b.source_image_id, b.position_index, b.geometry_revision, b.geometry_checksum_sha256,
  p.id, p.revision, p.geometry_checksum_sha256,
  n.id, n.revision, n.status, n.geometry_checksum_sha256,
  b.position_index = ANY (n.active_board_slots) AS in_newest_slots,
  (p.topology_rules_version_id = n.topology_rules_version_id
   AND p.source_checksum_sha256 = n.source_checksum_sha256
   AND p.normalized_pixel_checksum_sha256 = n.normalized_pixel_checksum_sha256) AS same_source,
  jsonb_path_query_first(p.board_geometries, '$[*] ? (@.positionIndex == $position)',
    jsonb_build_object('position', b.position_index)) AS old_entry,
  jsonb_path_query_first(n.board_geometries, '$[*] ? (@.positionIndex == $position)',
    jsonb_build_object('position', b.position_index)) AS new_entry,
  ri.id AS review_item_id,
  EXISTS (
    SELECT 1 FROM board_render_manifests m
    WHERE m.game_id = :game_id AND m.recognized_board_id = b.id
      AND m.geometry_revision = b.geometry_revision AND m.source_geometry_revision_id <> p.id
  ) AS manifest_drift,
  ri.id IS NOT NULL AND EXISTS (
    SELECT 1 FROM image_symbol_review_cells c
    WHERE c.game_id = :game_id AND c.review_item_id = ri.id AND c.recognized_board_id = b.id
      AND c.source_geometry_revision_id IS DISTINCT FROM p.id
  ) AS cell_drift,
  EXISTS (
    SELECT 1 FROM verified_training_cohort_cells vc
    WHERE vc.game_id = :game_id AND vc.recognized_board_id = b.id
  ) AS cohort_pinned
FROM recognized_boards b
JOIN newest n ON n.source_image_id = b.source_image_id
JOIN image_source_geometry_revisions p
  ON p.game_id = :game_id AND p.id = b.source_geometry_revision_id
LEFT JOIN image_review_items ri ON ri.game_id = :game_id AND ri.recognized_board_id = b.id
WHERE b.game_id = :game_id AND b.source_image_id = ANY (:image_ids)
  AND b.status <> 'rejected' AND p.revision < n.revision
ORDER BY b.source_image_id, b.position_index
"""


def plan_board_repoint(
    session: Session, game_id: UUID, source_image_ids: Sequence[UUID]
) -> tuple[BoardRepointDecision, ...]:
    """Read-only: every live board on an older revision, re-pointable or not.

    A board is re-pointable only when the newer revision's entry for its
    position is identical (quad and cell lattice the render manifest was built
    from) and every pointer that names the old revision is consistent, so that
    moving the pointers cannot change a crop, a checksum or a decision.
    """

    if not source_image_ids:
        return ()
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
    decisions: list[BoardRepointDecision] = []
    for row in _execute(
        session,
        _REPOINT_PLAN_SQL,
        {"game_id": game_id, "image_ids": list(dict.fromkeys(source_image_ids))},
    ):
        (
            board_id,
            source_image_id,
            position_index,
            geometry_revision,
            board_checksum,
            from_id,
            from_revision,
            from_checksum,
            to_id,
            to_revision,
            to_status,
            to_checksum,
            in_newest_slots,
            same_source,
            old_entry,
            new_entry,
            review_item_id,
            manifest_drift,
            cell_drift,
            cohort_pinned,
        ) = row
        reason: str | None = None
        if not in_newest_slots:
            reason = REPOINT_POSITION_NOT_IN_REVISION
        elif not same_source:
            reason = REPOINT_SOURCE_PROVENANCE_DIFFERS
        elif old_entry is None or new_entry is None or old_entry != new_entry:
            reason = REPOINT_GEOMETRY_ENTRY_DIFFERS
        elif int(geometry_revision) != 0:
            # A board geometry revision record pins its own source revision.
            reason = REPOINT_BOARD_GEOMETRY_REVISION_PINNED
        elif board_checksum != from_checksum:
            reason = REPOINT_BOARD_CHECKSUM_DRIFT
        elif manifest_drift:
            reason = REPOINT_RENDER_MANIFEST_DRIFT
        elif cell_drift:
            reason = REPOINT_CELL_PROVENANCE_DRIFT
        elif cohort_pinned:
            reason = REPOINT_VERIFIED_COHORT_PINNED
        decisions.append(
            BoardRepointDecision(
                recognized_board_id=board_id,
                source_image_id=source_image_id,
                review_item_id=review_item_id,
                position_index=int(position_index),
                from_revision_id=from_id,
                from_revision=int(from_revision),
                to_revision_id=to_id,
                to_revision=int(to_revision),
                to_revision_status=str(to_status),
                to_geometry_checksum_sha256=str(to_checksum),
                reason_code=reason,
            )
        )
    return tuple(decisions)


def apply_board_repoint(
    session: Session,
    game_id: UUID,
    decisions: Iterable[BoardRepointDecision],
) -> tuple[BoardRepointDecision, ...]:
    """Move the re-pointable boards to the newer revision; return the moved ones.

    Together with the board move the pointers that must agree with it: the
    board's source geometry checksum (the manual-correction context and the
    search document identity), the render manifest of its current geometry
    revision, and the cells' current and approval source revision. Pixels,
    render specs, crop identities, decisions and events stay as they are.
    Every update is guarded by the old value and must hit its row, otherwise
    the transaction fails (a concurrent change is never overwritten).
    """

    moved = tuple(decision for decision in decisions if decision.repointable)
    if not moved:
        return ()
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
    session.flush()
    for decision in moved:
        parameters = {
            "game_id": game_id,
            "board_id": decision.recognized_board_id,
            "from_id": decision.from_revision_id,
            "to_id": decision.to_revision_id,
            "to_checksum": decision.to_geometry_checksum_sha256,
        }
        updated = _execute(
            session,
            """UPDATE recognized_boards
            SET source_geometry_revision_id = :to_id, geometry_checksum_sha256 = :to_checksum
            WHERE game_id = :game_id AND id = :board_id AND source_geometry_revision_id = :from_id
              AND geometry_revision = 0 AND status <> 'rejected'""",
            parameters,
        )
        if updated.rowcount != 1:
            raise ImageReviewConflictError(
                "IMAGE_GEOMETRY_REPOINT_CONFLICT",
                "A board changed while it was re-pointed to the newer source revision.",
                details={"recognizedBoardId": str(decision.recognized_board_id)},
            )
        _execute(
            session,
            """UPDATE board_render_manifests SET source_geometry_revision_id = :to_id
            WHERE game_id = :game_id AND recognized_board_id = :board_id
              AND geometry_revision = 0 AND source_geometry_revision_id = :from_id""",
            parameters,
        )
        _execute(
            session,
            """UPDATE image_symbol_review_cells SET source_geometry_revision_id = :to_id
            WHERE game_id = :game_id AND recognized_board_id = :board_id
              AND source_geometry_revision_id = :from_id""",
            parameters,
        )
        _execute(
            session,
            """UPDATE image_symbol_review_cells SET approved_source_geometry_revision_id = :to_id
            WHERE game_id = :game_id AND recognized_board_id = :board_id
              AND approved_source_geometry_revision_id = :from_id""",
            parameters,
        )
    _expire_repointed(session, {decision.recognized_board_id for decision in moved})
    return moved


def _expire_repointed(session: Session, board_ids: set[UUID]) -> None:
    """Drop identity-map copies the textual updates made stale."""

    for instance in list(session.identity_map.values()):
        if (
            (isinstance(instance, RecognizedBoardModel) and instance.id in board_ids)
            or (
                isinstance(instance, ImageSymbolReviewCellModel)
                and instance.recognized_board_id in board_ids
            )
            or (
                isinstance(instance, BoardRenderManifestModel)
                and instance.recognized_board_id in board_ids
            )
        ):
            session.expire(instance)


def repoint_live_boards_to_newest_source_revision(
    session: Session,
    game_id: UUID,
    source_image_id: UUID,
) -> tuple[BoardRepointDecision, ...]:
    """Rule of a new source revision (TASK-0807): re-point the identical boards.

    Returns every decision (moved and left with a reason); the moved boards'
    search documents are refreshed because their identity checksum changed.
    """

    decisions = plan_board_repoint(session, game_id, (source_image_id,))
    moved = apply_board_repoint(session, game_id, decisions)
    review_item_ids = tuple(
        decision.review_item_id for decision in moved if decision.review_item_id is not None
    )
    if review_item_ids:
        from game_predictor_api.storage.board_search_projection_repository import (
            SqlAlchemyBoardSearchProjectionRepository,
        )

        SqlAlchemyBoardSearchProjectionRepository(session).sync_review_items(review_item_ids)
    return decisions


# -- operator exception ------------------------------------------------------


class SqlAlchemyImageGeometryCompletenessStateRepository:
    """Operator exception of one source image (Admin API, high impact)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def set_exception(
        self,
        game_id: UUID,
        source_image_id: UUID,
        *,
        reason: str,
        actor: str,
        now: datetime | None = None,
    ) -> SourceImageGeometryException | None:
        """Admit an incomplete image: its ``ok``/approved partial boards are cut."""

        value = require_geometry_exception_reason(reason)
        author = _require_actor(actor)
        if not self._bind(game_id):
            return None
        # TASK-0971: the cut locks the counters state before cell rows (the
        # write-through order); symbol-cell decisions, the only shared holders,
        # lock cells before the state. Exclusive keeps the two orders apart.
        acquire_sequence_ownership_lock(self._session, game_id=game_id)
        decided_at = now or datetime.now(UTC)
        current = recompute_source_image_geometry_completeness(
            self._session, game_id, source_image_id, actor=author, now=decided_at
        )
        source = self._source(source_image_id)
        if current.status is SourceImageGeometryStatus.GEOMETRY_EXCEPTION:
            if source.geometry_exception_reason == value:
                return self._view(source, current.image_state, 0)
            raise ImageReviewConflictError(
                "IMAGE_GEOMETRY_EXCEPTION_ALREADY_SET",
                "The source image already has a geometry exception with another reason.",
            )
        if current.status is not SourceImageGeometryStatus.GEOMETRY_INCOMPLETE:
            raise ImageReviewConflictError(
                "IMAGE_GEOMETRY_EXCEPTION_NOT_INCOMPLETE",
                "A geometry exception is allowed only for an incomplete source image.",
                details={
                    "status": None if current.status is None else current.status.value,
                    "imageState": current.image_state.value,
                },
            )
        source.geometry_completeness_status = SourceImageGeometryStatus.GEOMETRY_EXCEPTION.value
        source.geometry_completeness_evaluated_at = decided_at
        source.geometry_exception_reason = value
        source.geometry_exception_by = author
        source.geometry_exception_at = decided_at
        self._session.flush()
        materialized = materialize_admitted_source_image(
            self._session, game_id, source_image_id, actor=author
        )
        return self._view(source, current.image_state, materialized)

    def withdraw_exception(
        self,
        game_id: UUID,
        source_image_id: UUID,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> SourceImageGeometryException | None:
        """Withdraw an exception before any human cell decision; never deletes data."""

        _require_actor(actor)
        if not self._bind(game_id):
            return None
        source = self._locked_source(game_id, source_image_id)
        if source.geometry_completeness_status != (
            SourceImageGeometryStatus.GEOMETRY_EXCEPTION.value
        ):
            raise ImageReviewConflictError(
                "IMAGE_GEOMETRY_EXCEPTION_NOT_SET",
                "The source image has no geometry exception to withdraw.",
            )
        decisions = int(
            _execute(
                self._session,
                """SELECT count(*)
                FROM image_symbol_review_cells c
                JOIN recognized_boards b ON b.game_id = c.game_id AND b.id = c.recognized_board_id
                WHERE c.game_id = :game_id AND b.source_image_id = :source_image_id
                  AND (c.review_state = 'approved' OR c.quality_issue = 'grid_issue'
                       OR c.assignment_source IN ('human', 'board_decision'))""",
                {"game_id": game_id, "source_image_id": source_image_id},
            ).scalar_one()
        )
        if decisions:
            raise ImageReviewConflictError(
                "IMAGE_GEOMETRY_EXCEPTION_HUMAN_DECISIONS_PRESENT",
                "The exception cannot be withdrawn after human symbol decisions on its cells.",
                details={"humanDecisionCellCount": decisions},
            )
        # The recompute keeps an exception, so drop it first; the status then
        # follows the classifier (usually back to geometry_incomplete). Cells
        # created under the exception stay: the gate only blocks new ones.
        source.geometry_completeness_status = None
        source.geometry_exception_reason = None
        source.geometry_exception_by = None
        source.geometry_exception_at = None
        self._session.flush()
        result = recompute_source_image_geometry_completeness(
            self._session, game_id, source_image_id, actor=actor, now=now, materialize=False
        )
        return self._view(self._source(source_image_id), result.image_state, 0)

    def _bind(self, game_id: UUID) -> bool:
        if self._session.scalar(select(GameModel.id).where(GameModel.id == game_id)) is None:
            return False
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.WRITE)
        return True

    def _locked_source(self, game_id: UUID, source_image_id: UUID) -> SourceImageModel:
        locked = _execute(
            self._session,
            "SELECT id FROM source_images WHERE game_id = :game_id AND id = :source_image_id "
            "FOR UPDATE",
            {"game_id": game_id, "source_image_id": source_image_id},
        ).first()
        if locked is None:
            raise ImageReviewNotFoundError(
                "IMAGE_GEOMETRY_SOURCE_IMAGE_NOT_FOUND",
                "The source image does not belong to this game.",
            )
        return self._source(source_image_id)

    def _source(self, source_image_id: UUID) -> SourceImageModel:
        source = self._session.get(SourceImageModel, source_image_id)
        if source is None:
            raise ImageReviewNotFoundError(
                "IMAGE_GEOMETRY_SOURCE_IMAGE_NOT_FOUND",
                "The source image does not belong to this game.",
            )
        return source

    @staticmethod
    def _view(
        source: SourceImageModel, image_state: GeometryImageState, materialized: int
    ) -> SourceImageGeometryException:
        return SourceImageGeometryException(
            source_image_id=source.id,
            status=_status(source.geometry_completeness_status),
            image_state=image_state,
            reason=source.geometry_exception_reason,
            exception_by=source.geometry_exception_by,
            exception_at=source.geometry_exception_at,
            materialized_review_item_count=materialized,
        )


def _require_actor(actor: str) -> str:
    value = actor.strip()
    if not value or len(value) > MAX_GEOMETRY_EXCEPTION_ACTOR_LENGTH:
        raise ImageReviewError(
            "IMAGE_GEOMETRY_EXCEPTION_ACTOR_INVALID",
            "A geometry exception requires a named actor.",
        )
    return value


# -- resumable backfill ------------------------------------------------------

_UNEVALUATED_IMAGES_SQL = """
SELECT s.id FROM source_images s
WHERE s.game_id = :game_id AND s.geometry_completeness_evaluated_at IS NULL{after}
ORDER BY s.id
LIMIT :row_limit
"""

_IMAGES_WITH_CELLS_SQL = """
SELECT DISTINCT b.source_image_id
FROM recognized_boards b
JOIN image_review_items ri ON ri.game_id = b.game_id AND ri.recognized_board_id = b.id
WHERE b.game_id = :game_id AND b.source_image_id = ANY (:image_ids)
  AND EXISTS (
    SELECT 1 FROM image_symbol_review_cells c
    WHERE c.game_id = :game_id AND c.review_item_id = ri.id
  )
"""

_STATUS_SUMMARY_SQL = """
SELECT s.geometry_completeness_status, s.geometry_completeness_evaluated_at IS NOT NULL,
  count(*)
FROM source_images s
WHERE s.game_id = :game_id
GROUP BY 1, 2
"""

_INCOMPLETE_WITH_CELLS_SQL = """
SELECT count(DISTINCT b.source_image_id)
FROM source_images s
JOIN recognized_boards b ON b.game_id = s.game_id AND b.source_image_id = s.id
JOIN image_review_items ri ON ri.game_id = b.game_id AND ri.recognized_board_id = b.id
WHERE s.game_id = :game_id AND s.geometry_completeness_status = 'geometry_incomplete'
  AND EXISTS (
    SELECT 1 FROM image_symbol_review_cells c
    WHERE c.game_id = :game_id AND c.review_item_id = ri.id
  )
"""

MAX_BACKFILL_BATCH_SIZE: Final = 500


def status_key(status: SourceImageGeometryStatus | None) -> str:
    return "null" if status is None else status.value


@dataclass(frozen=True, slots=True)
class GeometryCompletenessBackfillBatch:
    """One batch (one transaction) of the state backfill."""

    processed_image_count: int
    last_source_image_id: UUID | None
    has_more: bool
    status_counts: Mapping[str, int]
    image_state_counts: Mapping[str, int]
    incomplete_with_cells_count: int
    repointed_board_count: int
    not_repointable: tuple[BoardRepointDecision, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class GeometryCompletenessGameSummary:
    """Persisted state of one game, read after (or without) a backfill run."""

    status_counts: Mapping[str, int]
    not_evaluated_count: int
    incomplete_with_cells_count: int


class SourceImageGeometryCompletenessBackfill:
    """Give every not yet evaluated image its gate status, resumably.

    ``apply=False`` is the preview: read-only (the caller runs it in a
    ``READ ONLY`` transaction), it plans the re-pointing and classifies as if
    it had happened. ``apply=True`` re-points the identical boards, then sets
    the status of images whose ``geometry_completeness_evaluated_at`` is still
    ``NULL`` -- an image the live pipeline evaluated in the meantime is never
    overwritten, and a restarted run skips everything already evaluated, so
    nothing is counted twice. Nothing is materialized and nothing is deleted:
    an image that was admitted before (``NULL``) keeps its cells and documents.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def next_batch(
        self,
        game_id: UUID,
        *,
        after_source_image_id: UUID | None,
        limit: int = MAX_BACKFILL_BATCH_SIZE,
        apply: bool,
        now: datetime | None = None,
    ) -> GeometryCompletenessBackfillBatch:
        if not 1 <= limit <= MAX_BACKFILL_BATCH_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_BACKFILL_BATCH_SIZE}")
        intent = GameStorageIntent.WRITE if apply else GameStorageIntent.READ
        GameStorageRouter().bind(self._session, game_id, intent=intent)
        parameters: dict[str, object] = {"game_id": game_id, "row_limit": limit + 1}
        after = ""
        if after_source_image_id is not None:
            after = " AND s.id > :after_id"
            parameters["after_id"] = after_source_image_id
        rows = _execute(
            self._session, _UNEVALUATED_IMAGES_SQL.format(after=after), parameters
        ).all()
        image_ids = [row[0] for row in rows[:limit]]
        if not image_ids:
            return GeometryCompletenessBackfillBatch(
                processed_image_count=0,
                last_source_image_id=after_source_image_id,
                has_more=False,
                status_counts={},
                image_state_counts={},
                incomplete_with_cells_count=0,
                repointed_board_count=0,
            )
        if apply:
            # Lock the batch in id order before boards and cells are touched.
            _execute(
                self._session,
                "SELECT id FROM source_images WHERE game_id = :game_id AND id = ANY (:ids) "
                "ORDER BY id FOR UPDATE",
                {"game_id": game_id, "ids": image_ids},
            ).all()
        decisions = plan_board_repoint(self._session, game_id, image_ids)
        repointable = tuple(decision for decision in decisions if decision.repointable)
        overrides: dict[UUID, bool] = {}
        if apply:
            moved = apply_board_repoint(self._session, game_id, repointable)
            moved_items = tuple(
                decision.review_item_id for decision in moved if decision.review_item_id is not None
            )
            if moved_items:
                from game_predictor_api.storage.board_search_projection_repository import (
                    SqlAlchemyBoardSearchProjectionRepository,
                )

                SqlAlchemyBoardSearchProjectionRepository(self._session).sync_review_items(
                    moved_items
                )
            repointed = len(moved)
        else:
            overrides = {
                decision.recognized_board_id: decision.to_revision_status == "accepted"
                for decision in repointable
            }
            repointed = len(repointable)
        states = classify_source_images(
            self._session, game_id, image_ids, accepted_board_overrides=overrides
        )
        statuses = {
            image_id: recomputed_status(current=None, state=state)
            for image_id, state in states.items()
        }
        incomplete = [
            image_id
            for image_id, status in statuses.items()
            if status is SourceImageGeometryStatus.GEOMETRY_INCOMPLETE
        ]
        with_cells = (
            {
                row[0]
                for row in _execute(
                    self._session,
                    _IMAGES_WITH_CELLS_SQL,
                    {"game_id": game_id, "image_ids": incomplete},
                )
            }
            if incomplete
            else set()
        )
        if apply:
            evaluated_at = now or datetime.now(UTC)
            by_status: dict[SourceImageGeometryStatus | None, list[UUID]] = {}
            for image_id, status in statuses.items():
                by_status.setdefault(status, []).append(image_id)
            for status, ids in by_status.items():
                _execute(
                    self._session,
                    """UPDATE source_images
                    SET geometry_completeness_status = :status,
                        geometry_completeness_evaluated_at = :evaluated_at
                    WHERE game_id = :game_id AND id = ANY (:ids)
                      AND geometry_completeness_evaluated_at IS NULL
                      AND geometry_completeness_status IS NULL""",
                    {
                        "game_id": game_id,
                        "ids": ids,
                        "status": None if status is None else status.value,
                        "evaluated_at": evaluated_at,
                    },
                )
            self._expire_sources(set(image_ids))
        status_counts: dict[str, int] = {}
        for status in statuses.values():
            status_counts[status_key(status)] = status_counts.get(status_key(status), 0) + 1
        state_counts: dict[str, int] = {}
        for state in states.values():
            state_counts[state.value] = state_counts.get(state.value, 0) + 1
        return GeometryCompletenessBackfillBatch(
            processed_image_count=len(image_ids),
            last_source_image_id=image_ids[-1],
            has_more=len(rows) > limit,
            status_counts=status_counts,
            image_state_counts=state_counts,
            incomplete_with_cells_count=len(with_cells),
            repointed_board_count=repointed,
            not_repointable=tuple(decision for decision in decisions if not decision.repointable),
        )

    def summary(self, game_id: UUID) -> GeometryCompletenessGameSummary:
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        counts: dict[str, int] = {}
        not_evaluated = 0
        for status, evaluated, count in _execute(
            self._session, _STATUS_SUMMARY_SQL, {"game_id": game_id}
        ):
            if not evaluated:
                not_evaluated += int(count)
                continue
            key = "null" if status is None else str(status)
            counts[key] = counts.get(key, 0) + int(count)
        incomplete_with_cells = int(
            _execute(self._session, _INCOMPLETE_WITH_CELLS_SQL, {"game_id": game_id}).scalar_one()
        )
        return GeometryCompletenessGameSummary(
            status_counts=counts,
            not_evaluated_count=not_evaluated,
            incomplete_with_cells_count=incomplete_with_cells,
        )

    def _expire_sources(self, image_ids: set[UUID]) -> None:
        for instance in list(self._session.identity_map.values()):
            if isinstance(instance, SourceImageModel) and instance.id in image_ids:
                self._session.expire(instance)


__all__ = [
    "GEOMETRY_COMPLETENESS_ACTOR",
    "MAX_BACKFILL_BATCH_SIZE",
    "REPOINT_BOARD_CHECKSUM_DRIFT",
    "REPOINT_BOARD_GEOMETRY_REVISION_PINNED",
    "REPOINT_CELL_PROVENANCE_DRIFT",
    "REPOINT_GEOMETRY_ENTRY_DIFFERS",
    "REPOINT_POSITION_NOT_IN_REVISION",
    "REPOINT_RENDER_MANIFEST_DRIFT",
    "REPOINT_SOURCE_PROVENANCE_DIFFERS",
    "REPOINT_VERIFIED_COHORT_PINNED",
    "BoardRepointDecision",
    "GeometryCompletenessBackfillBatch",
    "GeometryCompletenessGameSummary",
    "SourceImageGeometryCompletenessBackfill",
    "SourceImageGeometryException",
    "SourceImageGeometryRecompute",
    "SqlAlchemyImageGeometryCompletenessStateRepository",
    "active_review_item_ids",
    "apply_board_repoint",
    "deferred_gate_materializations",
    "finish_deferred_gate_materializations",
    "start_deferred_gate_materializations",
    "lock_source_images",
    "materialize_admitted_source_image",
    "materialize_deferred_source_images",
    "recompute_source_images",
    "plan_board_repoint",
    "recompute_source_image_geometry_completeness",
    "recompute_source_images_of_boards",
    "recompute_source_images_of_review_items",
    "repoint_live_boards_to_newest_source_revision",
    "status_key",
    "withheld_review_item_ids",
]
