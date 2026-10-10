"""Game-scoped sequence-ownership lock protocol (TASK-0971, audit P0-4/P0-5).

A sequence takeover (D-543) and a resolution that supersedes another photo's
item recompute the geometry gate of *other* source images, i.e. they lock a
second ``source_images`` row after their own. Two such writes with crossed
images deadlock unless they are serialized. Every write that can lock another
image therefore holds this transaction-scoped advisory lock of the game in
``EXCLUSIVE`` mode.

Symbol-cell decisions can reopen or resolve their board while they hold the
sequence lock. They take the same lock in ``SHARED`` mode at their very start,
so an exclusive writer never waits for a sequence lock held by a cell decision
that then waits for the ownership lock; shared holders never block each other.

Global lock order (TASK-0971, audit rounds 2-4), for every participant:

1. the idempotency-key advisory lock of the request, or the worker's job lease
   row (``jobs FOR NO KEY UPDATE``, so the foreign-key checks of inserts that
   reference the job, ``FOR KEY SHARE``, never wait for it) - the only job row
   lock; a writer that holds the ownership lock never locks a job row
   afterwards (``FOR UPDATE OF`` lists the modified tables only);
2. the ownership lock (``SHARED`` or ``EXCLUSIVE``);
3. the game row of the projection guard (``games FOR UPDATE``), if needed;
4. the sequence advisory locks (ascending, one statement per set);
5. source rows - several of them in ascending id order in one statement
   (``lock_source_images``) before any of them is recomputed or cut;
6. board, review item, pending slot, canonical and queue rows;
7. ``image_symbol_review_states`` (the counters), then symbol-review cell rows
   - the write-through order of every exclusive writer. A symbol-cell decision
   (the only ``SHARED`` holder) locks its board's cell rows before the
   counters state (TASK-0885); the two orders never run concurrently because
   shared and exclusive holders exclude each other, and shared holders all use
   the same cells -> state order.

Every transaction that locks a source row and, later, the counters state or a
second source row is a participant (``EXCLUSIVE``; only symbol-cell decisions
take ``SHARED``); an exclusive holder is therefore alone among them. The import
writer defers the cuts of images admitted by takeovers to the end of its
transaction (``deferred_gate_materializations``), after its last source lock.

The lock is re-entrant within one database transaction (``session.info``
remembers the mode per root transaction). A nested request for the same or a
weaker mode is a no-op; a request for ``EXCLUSIVE`` while only ``SHARED`` is
held never upgrades (an upgrade under held sequence locks is exactly the
reversed order) and raises ``SEQUENCE_OWNERSHIP_LOCK_UPGRADE``.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, aliased

from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage.models import ImageReviewItemModel, RecognizedBoardModel

SEQUENCE_OWNERSHIP_LOCK_SCOPE: Final = "sequence-ownership"
SEQUENCE_OWNERSHIP_LOCK_UPGRADE: Final = "SEQUENCE_OWNERSHIP_LOCK_UPGRADE"
_INFO_KEY: Final = "game_predictor.sequence_ownership_locks"


class SequenceOwnershipLockMode(StrEnum):
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


def sequence_ownership_lock_key(game_id: UUID) -> int:
    digest = hashlib.sha256(f"{game_id}:{SEQUENCE_OWNERSHIP_LOCK_SCOPE}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _registry(session: Session) -> dict[UUID, SequenceOwnershipLockMode] | None:
    """Locks held in the current root transaction (``None`` for test doubles)."""

    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return None
    transaction = session.get_transaction()
    state: Any = info.get(_INFO_KEY)
    if not isinstance(state, tuple) or state[0] is not transaction:
        state = (transaction, {})
        info[_INFO_KEY] = state
    registry: dict[UUID, SequenceOwnershipLockMode] = state[1]
    return registry


def held_sequence_ownership_lock(
    session: Session, *, game_id: UUID
) -> SequenceOwnershipLockMode | None:
    registry = _registry(session)
    return None if registry is None else registry.get(game_id)


def acquire_sequence_ownership_lock(
    session: Session,
    *,
    game_id: UUID,
    mode: SequenceOwnershipLockMode = SequenceOwnershipLockMode.EXCLUSIVE,
) -> SequenceOwnershipLockMode:
    """Take the game's ownership lock in ``mode`` (re-entrant, never upgrades)."""

    # Begin the transaction first so the registry is bound to it.
    session.connection()
    registry = _registry(session)
    held = None if registry is None else registry.get(game_id)
    if held is SequenceOwnershipLockMode.EXCLUSIVE or held is mode:
        return held
    if held is SequenceOwnershipLockMode.SHARED:
        raise ImageReviewConflictError(
            SEQUENCE_OWNERSHIP_LOCK_UPGRADE,
            "This operation would touch another image while holding only the shared "
            "sequence-ownership lock; retry it.",
        )
    lock = (
        func.pg_advisory_xact_lock
        if mode is SequenceOwnershipLockMode.EXCLUSIVE
        else func.pg_advisory_xact_lock_shared
    )
    session.execute(select(lock(sequence_ownership_lock_key(game_id))))
    if registry is not None:
        registry[game_id] = mode
    return mode


def ensure_sequence_ownership_lock(session: Session, *, game_id: UUID) -> None:
    """Nested participant: keep any held mode, else take ``EXCLUSIVE`` as entry point."""

    if held_sequence_ownership_lock(session, game_id=game_id) is None:
        acquire_sequence_ownership_lock(session, game_id=game_id)


def require_exclusive_sequence_ownership(session: Session, *, game_id: UUID) -> None:
    """Guard of a write that is about to lock another image's source row."""

    acquire_sequence_ownership_lock(
        session, game_id=game_id, mode=SequenceOwnershipLockMode.EXCLUSIVE
    )


def cell_decision_lock_mode(
    session: Session, *, game_id: UUID, review_item_id: UUID
) -> SequenceOwnershipLockMode:
    """Mode a symbol-cell decision on this board needs (read before any lock).

    A decision that resolves its board can supersede other pending items of
    the board's sequence (first save wins) and recompute their images' gates;
    only then it needs ``EXCLUSIVE``. Under D-543 a sequence has at most one
    pending item, so such an occurrence exists only after a sequence
    correction. Everything else (reopen, resolve without other occurrences) is
    confined to the board's own image and runs ``SHARED``. A race that adds an
    occurrence after this read is caught by ``require_exclusive_sequence_ownership``.
    """

    own_item = aliased(ImageReviewItemModel)
    own_board = aliased(RecognizedBoardModel)
    other_board = aliased(RecognizedBoardModel)
    own = session.execute(
        select(own_board.sequence_number, own_item.sequence_number)
        .join(own_item, own_item.recognized_board_id == own_board.id)
        .where(own_item.game_id == game_id, own_item.id == review_item_id)
    ).first()
    sequences = (
        {value for value in own if isinstance(value, int)} if isinstance(own, Row) else set()
    )
    if not sequences:
        return SequenceOwnershipLockMode.SHARED
    exists = session.scalar(
        select(ImageReviewItemModel.id)
        .join(other_board, other_board.id == ImageReviewItemModel.recognized_board_id)
        .where(
            ImageReviewItemModel.game_id == game_id,
            ImageReviewItemModel.status == "pending",
            ImageReviewItemModel.id != review_item_id,
            other_board.sequence_number.in_(sorted(sequences)),
        )
        .limit(1)
    )
    return (
        SequenceOwnershipLockMode.SHARED if exists is None else SequenceOwnershipLockMode.EXCLUSIVE
    )


__all__ = [
    "SEQUENCE_OWNERSHIP_LOCK_SCOPE",
    "SEQUENCE_OWNERSHIP_LOCK_UPGRADE",
    "SequenceOwnershipLockMode",
    "acquire_sequence_ownership_lock",
    "cell_decision_lock_mode",
    "ensure_sequence_ownership_lock",
    "held_sequence_ownership_lock",
    "require_exclusive_sequence_ownership",
    "sequence_ownership_lock_key",
]
