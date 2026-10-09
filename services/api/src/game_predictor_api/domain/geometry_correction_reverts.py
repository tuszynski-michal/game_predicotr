"""Revert of the last manual grid-geometry correction (TASK-0945, plan D-538).

Pure rules: the kinds of a correction, the fail-closed eligibility of a revert
evaluated from facts read under lock, the predicted gate status of the image
after a deferred-slot revert and the canonical snapshot checksum. No I/O.

A *correction* is one manual geometry save of one board, identified by its
``image_board_geometry_revisions`` row and its ``geometry_saved`` event:

* ``pending_slot`` (case B): the save resolved a deferred slot and created the
  board, its review item and cells; the revert deletes them and reopens the
  slot;
* ``board_revision`` (case A): the save added revision ``N`` of an existing
  board; its revert (a new revision ``N + 1``) belongs to TASK-0946.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from game_predictor_api.domain.image_geometry_completeness import (
    ADMITTED_SOURCE_IMAGE_STATUSES,
    GeometryImageState,
    SourceImageGeometryStatus,
    recomputed_status,
)

REVERTED_SOURCE_GEOMETRY_STATUS: Final = "reverted"
"""Status of a source geometry revision whose correction was reverted.

A reverted revision is never the current revision of its image, never
deduplicates a new write and is never re-pointed to; its row stays.
"""

GEOMETRY_REVERTED_ACTION: Final = "geometry_reverted"
DEFAULT_GEOMETRY_CORRECTION_LIST_LIMIT: Final = 20
MAX_GEOMETRY_CORRECTION_LIST_LIMIT: Final = 50
MAX_GEOMETRY_REVERT_ACTOR_LENGTH: Final = 200
SNAPSHOT_SCHEMA_VERSION: Final = "geometry-correction-revert-snapshot-v1"

GEOMETRY_CORRECTION_NOT_FOUND: Final = "GEOMETRY_CORRECTION_NOT_FOUND"
GEOMETRY_CORRECTION_REVERTED: Final = "GEOMETRY_CORRECTION_REVERTED"
GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT: Final = "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT"
GEOMETRY_REVERT_REQUEST_INVALID: Final = "GEOMETRY_REVERT_REQUEST_INVALID"


class GeometryCorrectionKind(StrEnum):
    PENDING_SLOT = "pending_slot"
    BOARD_REVISION = "board_revision"


class RevertBlockingReason(StrEnum):
    """Why a correction cannot be reverted; the first failing rule wins."""

    NOT_LATEST = "GEOMETRY_REVERT_NOT_LATEST"
    STALE = "GEOMETRY_REVERT_STALE"
    SOURCE_ADVANCED = "GEOMETRY_REVERT_SOURCE_ADVANCED"
    SHARED_SOURCE_REVISION = "GEOMETRY_REVERT_SHARED_SOURCE_REVISION"
    CELLS_CHANGED = "GEOMETRY_REVERT_CELLS_CHANGED"
    RESOLVED = "GEOMETRY_REVERT_RESOLVED"
    SEQUENCE_OWNERSHIP = "GEOMETRY_REVERT_SEQUENCE_OWNERSHIP"
    IMAGE_ADMITTED = "GEOMETRY_REVERT_IMAGE_ADMITTED"
    PINNED = "GEOMETRY_REVERT_PINNED"
    REOPENED_RESOLUTION = "GEOMETRY_REVERT_REOPENED_RESOLUTION"
    NOT_SUPPORTED = "GEOMETRY_REVERT_NOT_SUPPORTED"


BLOCKING_REASON_MESSAGES: Final[Mapping[RevertBlockingReason, str]] = {
    RevertBlockingReason.NOT_LATEST: (
        "To nie jest ostatnia zmiana geometrii tej planszy albo korekta została już cofnięta."
    ),
    RevertBlockingReason.STALE: (
        "Plansza zmieniła się od wczytania listy korekt. Odśwież listę i spróbuj ponownie."
    ),
    RevertBlockingReason.SOURCE_ADVANCED: (
        "Po tej korekcie poprawiono inny slot tego zdjęcia. Najpierw cofnij nowszą korektę."
    ),
    RevertBlockingReason.SHARED_SOURCE_REVISION: (
        "Geometrię zdjęcia zapisaną tą korektą wykorzystuje inna plansza."
    ),
    RevertBlockingReason.CELLS_CHANGED: (
        "Komórki planszy zmieniono po korekcie (np. weryfikacja symboli)."
    ),
    RevertBlockingReason.RESOLVED: "Pozycja przeglądu tej planszy jest już rozstrzygnięta.",
    RevertBlockingReason.SEQUENCE_OWNERSHIP: (
        "Korekta zastąpiła inną pozycję tej sekwencji albo przejęła jej komórki."
    ),
    RevertBlockingReason.IMAGE_ADMITTED: (
        "Korekta dopuściła zdjęcie do cięcia; cofnięcie odcięłoby pozostałe plansze."
    ),
    RevertBlockingReason.PINNED: (
        "Plansza lub jej komórki są użyte w kohorcie treningowej, bibliotece wzorców, "
        "operacji zbiorczej albo rewizji predykcji."
    ),
    RevertBlockingReason.REOPENED_RESOLUTION: (
        "Korekta ponownie otworzyła rozstrzygniętą pozycję; cofnięcie nie przywróci "
        "rozstrzygnięcia."
    ),
    RevertBlockingReason.NOT_SUPPORTED: (
        "Cofnięcie korekty istniejącej planszy nie jest jeszcze dostępne."
    ),
}


def blocking_reason_message(reason: RevertBlockingReason) -> str:
    return BLOCKING_REASON_MESSAGES[reason]


@dataclass(frozen=True, slots=True)
class RevertEligibilityFacts:
    """Facts about one correction, read from storage (under lock for a revert).

    ``cas_matches`` is ``None`` when no CAS tokens were supplied (list and
    preview); a revert always supplies them. ``image_status_before`` is the
    persisted gate status of the image now; ``image_status_after`` the status
    the image would have after the revert.
    """

    kind: GeometryCorrectionKind
    latest_board_revision: bool
    cas_matches: bool | None
    source_revision_newest_live: bool
    source_revision_shared: bool
    cells_changed_after_correction: bool
    review_resolved: bool
    sequence_ownership_changed: bool
    image_status_before: SourceImageGeometryStatus | None
    image_status_after: SourceImageGeometryStatus | None
    pinned: bool
    reopened_resolution: bool
    revert_supported: bool


def image_admission_blocks_revert(
    before: SourceImageGeometryStatus | None,
    after: SourceImageGeometryStatus | None,
) -> bool:
    """An admitted image must keep its status, or the revert cuts its neighbours off."""

    return before in ADMITTED_SOURCE_IMAGE_STATUSES and after is not before


def predicted_status_after_slot_revert(
    current: SourceImageGeometryStatus | None,
) -> SourceImageGeometryStatus | None:
    """Gate status of the image once the deferred slot is open again.

    The reopened slot is a ``deferred`` position, so the image is
    ``incomplete_missing``; an operator exception is kept (D-484). The revert
    itself recomputes the real status and refuses when it differs from an
    admitted one, so this prediction only drives the list and the preview.
    """

    if current is None:
        return None
    return recomputed_status(current=current, state=GeometryImageState.INCOMPLETE_MISSING)


def evaluate_revert_eligibility(facts: RevertEligibilityFacts) -> RevertBlockingReason | None:
    """First failing rule of the plan's table (fail-closed); ``None`` = revertable."""

    if not facts.latest_board_revision:
        return RevertBlockingReason.NOT_LATEST
    if facts.cas_matches is False:
        return RevertBlockingReason.STALE
    if not facts.source_revision_newest_live:
        return RevertBlockingReason.SOURCE_ADVANCED
    if facts.source_revision_shared:
        return RevertBlockingReason.SHARED_SOURCE_REVISION
    if facts.cells_changed_after_correction:
        return RevertBlockingReason.CELLS_CHANGED
    if facts.review_resolved:
        return RevertBlockingReason.RESOLVED
    if facts.sequence_ownership_changed:
        return RevertBlockingReason.SEQUENCE_OWNERSHIP
    if image_admission_blocks_revert(facts.image_status_before, facts.image_status_after):
        return RevertBlockingReason.IMAGE_ADMITTED
    if facts.pinned:
        return RevertBlockingReason.PINNED
    if facts.reopened_resolution:
        return RevertBlockingReason.REOPENED_RESOLUTION
    if not facts.revert_supported:
        return RevertBlockingReason.NOT_SUPPORTED
    return None


def canonical_snapshot_bytes(snapshot: Mapping[str, object]) -> bytes:
    """Canonical JSON (sorted keys, no whitespace, UTF-8) of a revert snapshot."""

    return json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def snapshot_checksum_sha256(snapshot: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_snapshot_bytes(snapshot)).hexdigest()


__all__ = [
    "BLOCKING_REASON_MESSAGES",
    "DEFAULT_GEOMETRY_CORRECTION_LIST_LIMIT",
    "GEOMETRY_CORRECTION_NOT_FOUND",
    "GEOMETRY_CORRECTION_REVERTED",
    "GEOMETRY_REVERTED_ACTION",
    "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT",
    "GEOMETRY_REVERT_REQUEST_INVALID",
    "MAX_GEOMETRY_CORRECTION_LIST_LIMIT",
    "MAX_GEOMETRY_REVERT_ACTOR_LENGTH",
    "REVERTED_SOURCE_GEOMETRY_STATUS",
    "SNAPSHOT_SCHEMA_VERSION",
    "GeometryCorrectionKind",
    "RevertBlockingReason",
    "RevertEligibilityFacts",
    "blocking_reason_message",
    "canonical_snapshot_bytes",
    "evaluate_revert_eligibility",
    "image_admission_blocks_revert",
    "predicted_status_after_slot_revert",
    "snapshot_checksum_sha256",
]
