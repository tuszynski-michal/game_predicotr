"""Who owns a known sequence number when a new board arrives (D-543, TASK-0971).

D-543 changes D-238 ("the newest import replaces an unresolved board"). For one
game and one known ``sequence_number`` there is at most one active ``pending``
review item. A new board of an import or of a manual slot resolution:

* never replaces a canonical (resolved) owner - first save wins, unchanged;
* takes the sequence over when it has no live owner, which includes an owner
  the operator rejected (a ``rejected`` review item or a ``rejected`` deferred
  slot is not live);
* is superseded when a live ``pending`` item of *another photo* owns the
  sequence (reason ``superseded_existing_owner_kept``, with an
  ``image_sequence_alternatives`` row): the operator rejects the old board
  first when the new photo should win;
* keeps the D-238 order among the imports of the *same photo* (same source
  checksum, i.e. a reprocessing): the newest import by ``(job.created_at,
  job.id)`` owns the sequence and the older pending item becomes
  ``superseded``.

The rule is pure: the storage layer reads the facts under the sequence lock and
applies the returned outcome. The API slot resolution and the worker import
share that one storage function, so the rule has no second copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

CANONICAL_OWNER_KEPT_REASON: Final = "canonical_sequence_already_resolved"
NEWER_SAME_SOURCE_OWNER_KEPT_REASON: Final = "pending_sequence_owned_by_newer_import"
OLDER_SAME_SOURCE_OWNER_REPLACED_REASON: Final = "pending_sequence_replaced_by_newer_import"
EXISTING_OWNER_KEPT_REASON: Final = "superseded_existing_owner_kept"
"""Reason of the superseded new item and of its sequence alternative (D-543)."""
CANONICAL_ALTERNATIVE_REASON: Final = "superseded_first_save_wins"
"""Reason of the sequence alternative of a source skipped for a canonical owner."""
SKIPPED_OWNER_REASONS: Final = (EXISTING_OWNER_KEPT_REASON, CANONICAL_ALTERNATIVE_REASON)
"""Alternative reasons reported as "skipped, the sequence has an owner"."""


class SequenceClaimOutcome(StrEnum):
    """What happens to the incoming board's review item and to the incumbent."""

    # No live owner (none, or only rejected ones): the incoming item is pending.
    TAKE_OVER = "take_over"
    # Same photo, newer import (D-238 kept for reprocessing): the incumbent
    # pending item is superseded and the incoming item is pending.
    REPLACE_SAME_SOURCE = "replace_same_source"
    # A canonical owner exists: the incoming item is superseded.
    KEEP_CANONICAL = "keep_canonical"
    # Same photo, the incumbent comes from a newer import: incoming superseded.
    KEEP_NEWER_SAME_SOURCE = "keep_newer_same_source"
    # A live pending item of another photo owns the sequence: incoming superseded.
    KEEP_EXISTING_OWNER = "keep_existing_owner"


@dataclass(frozen=True, slots=True)
class ImportOrder:
    """Deterministic order of an import: ``(job.created_at, str(job.id))``."""

    created_at: datetime
    job_id: str

    def key(self) -> tuple[datetime, str]:
        return (self.created_at, self.job_id)


@dataclass(frozen=True, slots=True)
class PendingOwnerFacts:
    """The live ``pending`` owner of the sequence, read under the sequence lock."""

    source_checksum_sha256: str
    import_order: ImportOrder


@dataclass(frozen=True, slots=True)
class SequenceClaim:
    outcome: SequenceClaimOutcome
    # Reason written into the incoming item's ``superseded`` resolution, if any.
    incoming_reason: str | None = None
    # Reason written into the incumbent's ``superseded`` resolution, if any.
    incumbent_reason: str | None = None
    # Reason of the ``image_sequence_alternatives`` row of the incoming source.
    alternative_reason: str | None = None

    @property
    def incoming_owns(self) -> bool:
        """The incoming item becomes the pending owner of the sequence."""

        return self.outcome in {
            SequenceClaimOutcome.TAKE_OVER,
            SequenceClaimOutcome.REPLACE_SAME_SOURCE,
        }


def decide_sequence_claim(
    *,
    canonical_exists: bool,
    incumbent: PendingOwnerFacts | None,
    incoming_source_checksum_sha256: str | None,
    incoming_order: ImportOrder,
) -> SequenceClaim:
    """Decide the owner of one sequence for an incoming board (D-543).

    ``incumbent`` is the live ``pending`` item of the sequence (at most one by
    the partial unique index); rejected items and rejected slots are not
    passed: they are no owner. ``incoming_source_checksum_sha256`` is needed
    only when an incumbent exists; ``None`` never matches a checksum.
    """

    if canonical_exists:
        return SequenceClaim(
            SequenceClaimOutcome.KEEP_CANONICAL, incoming_reason=CANONICAL_OWNER_KEPT_REASON
        )
    if incumbent is None:
        return SequenceClaim(SequenceClaimOutcome.TAKE_OVER)
    same_source = (
        incoming_source_checksum_sha256 is not None
        and incoming_source_checksum_sha256 == incumbent.source_checksum_sha256
    )
    if not same_source:
        return SequenceClaim(
            SequenceClaimOutcome.KEEP_EXISTING_OWNER,
            incoming_reason=EXISTING_OWNER_KEPT_REASON,
            alternative_reason=EXISTING_OWNER_KEPT_REASON,
        )
    if incoming_order.key() <= incumbent.import_order.key():
        return SequenceClaim(
            SequenceClaimOutcome.KEEP_NEWER_SAME_SOURCE,
            incoming_reason=NEWER_SAME_SOURCE_OWNER_KEPT_REASON,
        )
    return SequenceClaim(
        SequenceClaimOutcome.REPLACE_SAME_SOURCE,
        incumbent_reason=OLDER_SAME_SOURCE_OWNER_REPLACED_REASON,
    )


__all__ = [
    "CANONICAL_ALTERNATIVE_REASON",
    "CANONICAL_OWNER_KEPT_REASON",
    "EXISTING_OWNER_KEPT_REASON",
    "NEWER_SAME_SOURCE_OWNER_KEPT_REASON",
    "OLDER_SAME_SOURCE_OWNER_REPLACED_REASON",
    "SKIPPED_OWNER_REASONS",
    "ImportOrder",
    "PendingOwnerFacts",
    "SequenceClaim",
    "SequenceClaimOutcome",
    "decide_sequence_claim",
]
