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
  board; its revert appends revision ``N + 1`` with the geometry and render of
  the board's previous revision and restores the cells' decisions from the
  earliest event of the correction transaction (TASK-0946).

TASK-0949 adds the ``rejection`` kind to the same list: an operator's rejection
of a deferred slot or of a cropped board. Its revert restores the slot (or the
review item) to ``pending`` unless a replacement owns the sequence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from game_predictor_api.domain.image_geometry_completeness import (
    ADMITTED_SOURCE_IMAGE_STATUSES,
    GeometryImageState,
    SourceImageGeometryStatus,
    recomputed_status,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellQualityIssue,
    SymbolCellReviewState,
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
# Case A renders the restored cells (TASK-0946 audit P0-3).
GEOMETRY_REVERT_RENDER_FAILED: Final = "GEOMETRY_REVERT_RENDER_FAILED"
GEOMETRY_REVERT_RENDERER_UNAVAILABLE: Final = "GEOMETRY_REVERT_RENDERER_UNAVAILABLE"


class GeometryCorrectionKind(StrEnum):
    PENDING_SLOT = "pending_slot"
    BOARD_REVISION = "board_revision"
    REJECTION = "rejection"


class RejectionTarget(StrEnum):
    """What a ``rejection`` entry rejected."""

    PENDING_SLOT = "pending_slot"
    REVIEW_ITEM = "review_item"


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
    HISTORY_INCOMPLETE = "GEOMETRY_REVERT_HISTORY_INCOMPLETE"
    NOT_SUPPORTED = "GEOMETRY_REVERT_NOT_SUPPORTED"
    # TASK-0949: another live board owns the rejected sequence (a replacement).
    REPLACED = "GEOMETRY_REVERT_REPLACED"


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
    RevertBlockingReason.HISTORY_INCOMPLETE: (
        "Historia planszy nie pozwala dokładnie odtworzyć stanu sprzed korekty "
        "(brak pochodzenia wcześniejszego zatwierdzenia komórki albo geometrii)."
    ),
    RevertBlockingReason.NOT_SUPPORTED: (
        "Tej korekty nie można cofnąć automatycznie: zapis historyczny bez geometrii "
        "zdjęcia, plansza z kwalifikacją geometrii albo niepełna historia komórek."
    ),
    RevertBlockingReason.REPLACED: (
        "Tę sekwencję przejęła już inna plansza (zdjęcie zastępcze); odrzucenia nie można cofnąć."
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
    # Case A: the provenance of every restored approval is recorded (TASK-0946).
    history_complete: bool = True


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
    if not facts.history_complete:
        return RevertBlockingReason.HISTORY_INCOMPLETE
    if not facts.revert_supported:
        return RevertBlockingReason.NOT_SUPPORTED
    return None


# -- rejections (TASK-0949) ---------------------------------------------------

BOARD_REJECT_CANONICAL: Final = "BOARD_REJECT_CANONICAL"
_OTHER_REASON_PREFIX: Final = "other:"


@dataclass(frozen=True, slots=True)
class RejectionRevertFacts:
    """Facts about one rejection, read from storage (under lock for a revert).

    ``still_rejected`` is true while the slot (or the review item, at the
    revision of the rejection event) is still rejected; ``position_free`` is
    false when a newer open slot or a board already sits at a rejected slot's
    position (restoring would duplicate it); ``replaced`` means a live review
    item of another image owns the sequence number (TASK-0950 replaces the
    rejected owner this way). ``cas_matches`` is ``None`` when no tokens were
    supplied (list and preview).
    """

    still_rejected: bool
    cas_matches: bool | None
    position_free: bool
    replaced: bool


def evaluate_rejection_revert_eligibility(
    facts: RejectionRevertFacts,
) -> RevertBlockingReason | None:
    """First failing rule for a rejection (fail-closed); ``None`` = revertable."""

    if not facts.still_rejected or not facts.position_free:
        return RevertBlockingReason.NOT_LATEST
    if facts.cas_matches is False:
        return RevertBlockingReason.STALE
    if facts.replaced:
        return RevertBlockingReason.REPLACED
    return None


def encode_board_rejection_reason(reason: str, note: str | None) -> str:
    """The ``rejection_reason`` text of the board resolution command.

    The resolution route keeps one free text (1-500 characters): ``cropped``,
    ``blurred`` or ``other: <note>``. The list decodes it back.
    """

    if reason == "other":
        return f"{_OTHER_REASON_PREFIX} {(note or '').strip()}"
    return reason


def decode_board_rejection_reason(text: str | None) -> tuple[str | None, str | None]:
    """``(reason, note)`` of a stored board rejection; ``(None, text)`` if free text."""

    if text is None:
        return None, None
    value = text.strip()
    if value in {"cropped", "blurred"}:
        return value, None
    if value.startswith(_OTHER_REASON_PREFIX):
        return "other", value[len(_OTHER_REASON_PREFIX) :].strip() or None
    return None, value or None


# -- case A: restoring the cells and the board approval (TASK-0946) ----------

# Cell events a correction transaction writes itself: the geometry write
# (``geometry_invalidated``) and the operator's D-488 symbols.
CORRECTION_TRANSACTION_CELL_ACTIONS: Final = frozenset(
    {"geometry_invalidated", "reassign", "mark_unreadable"}
)


@dataclass(frozen=True, slots=True)
class PreviousCellDecision:
    """A cell's decision before the correction.

    The values are the ``previous_*`` columns of the earliest cell event of
    the correction transaction; ``assignment_source`` is ``None`` for events
    written before migration ``0153``.
    """

    assigned_symbol_id: UUID | None
    review_state: str
    quality_issue: str | None
    assignment_source: str | None
    verification_outcome: str | None
    verified_symbol_id_v2: UUID | None


@dataclass(frozen=True, slots=True)
class RestoredCellDecision:
    """The decision a reverted cell gets back.

    ``approval_restored`` rebinds the approval to the restored render.
    ``verification_outcome`` is ``None`` when the verification must be
    derived again from the restored state (an approval that came back as a
    pending suggestion).
    """

    assigned_symbol_id: UUID | None
    review_state: str
    quality_issue: str | None
    assignment_source: str
    approval_restored: bool
    verification_outcome: str | None
    verified_symbol_id_v2: UUID | None


def restored_assignment_source(
    *,
    previous_assignment_source: str | None,
    previous_review_state: str,
    previous_quality_issue: str | None,
) -> str:
    """The recorded source, else the plan's rule for events before ``0153``.

    A previous approval was a human decision; a partially visible cell was
    labelled by the partial-geometry rule; anything else came from the model.
    """

    if previous_assignment_source is not None:
        return SymbolCellAssignmentSource(previous_assignment_source).value
    if previous_review_state == SymbolCellReviewState.APPROVED.value:
        return SymbolCellAssignmentSource.HUMAN.value
    if previous_quality_issue == SymbolCellQualityIssue.PARTIAL_VISIBILITY.value:
        return SymbolCellAssignmentSource.GEOMETRY_PARTIAL.value
    return SymbolCellAssignmentSource.MODEL.value


def restore_cell_decision(
    previous: PreviousCellDecision, *, approval_pixels_identical: bool
) -> RestoredCellDecision:
    """Restore a cell's decision on the restored render (D-462).

    An approval comes back only on identical pixels. Otherwise the human
    label stays as a pending suggestion and the pixel-bound quality flag of
    the approval does not carry over (as ``_recheck_after_virtual_recrop``).
    A pending decision comes back unchanged, including ``grid_issue``.
    """

    state = SymbolCellReviewState(previous.review_state)
    source = restored_assignment_source(
        previous_assignment_source=previous.assignment_source,
        previous_review_state=state.value,
        previous_quality_issue=previous.quality_issue,
    )
    if state is SymbolCellReviewState.APPROVED and not approval_pixels_identical:
        return RestoredCellDecision(
            assigned_symbol_id=previous.assigned_symbol_id,
            review_state=SymbolCellReviewState.PENDING.value,
            quality_issue=None,
            assignment_source=source,
            approval_restored=False,
            verification_outcome=None,
            verified_symbol_id_v2=None,
        )
    return RestoredCellDecision(
        assigned_symbol_id=previous.assigned_symbol_id,
        review_state=state.value,
        quality_issue=previous.quality_issue,
        assignment_source=source,
        approval_restored=state is SymbolCellReviewState.APPROVED,
        verification_outcome=previous.verification_outcome,
        verified_symbol_id_v2=(
            previous.verified_symbol_id_v2 if previous.verification_outcome is not None else None
        ),
    )


def restored_approved_geometry_revision(
    previous_approved_geometry_revision: int | None,
    *,
    restored_from_revision: int,
    written_revision: int,
) -> int | None:
    """Board ``approved_geometry_revision`` after a case-A revert.

    The value recorded by the correction comes back. An approval of exactly
    the revision whose geometry is restored follows that geometry to the new
    revision ``N + 1`` (same corners, same render), as the legacy conversion
    carries an approval over to its new revision; otherwise the board would
    look unapproved although its geometry is the approved one.
    """

    if previous_approved_geometry_revision is None:
        return None
    if previous_approved_geometry_revision == restored_from_revision:
        return written_revision
    return previous_approved_geometry_revision


def canonical_snapshot_bytes(snapshot: Mapping[str, object]) -> bytes:
    """Canonical JSON (sorted keys, no whitespace, UTF-8) of a revert snapshot."""

    return json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def snapshot_checksum_sha256(snapshot: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_snapshot_bytes(snapshot)).hexdigest()


__all__ = [
    "BLOCKING_REASON_MESSAGES",
    "BOARD_REJECT_CANONICAL",
    "CORRECTION_TRANSACTION_CELL_ACTIONS",
    "DEFAULT_GEOMETRY_CORRECTION_LIST_LIMIT",
    "GEOMETRY_CORRECTION_NOT_FOUND",
    "GEOMETRY_CORRECTION_REVERTED",
    "GEOMETRY_REVERTED_ACTION",
    "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT",
    "GEOMETRY_REVERT_RENDERER_UNAVAILABLE",
    "GEOMETRY_REVERT_RENDER_FAILED",
    "GEOMETRY_REVERT_REQUEST_INVALID",
    "MAX_GEOMETRY_CORRECTION_LIST_LIMIT",
    "MAX_GEOMETRY_REVERT_ACTOR_LENGTH",
    "REVERTED_SOURCE_GEOMETRY_STATUS",
    "SNAPSHOT_SCHEMA_VERSION",
    "GeometryCorrectionKind",
    "PreviousCellDecision",
    "RejectionRevertFacts",
    "RejectionTarget",
    "RestoredCellDecision",
    "RevertBlockingReason",
    "RevertEligibilityFacts",
    "blocking_reason_message",
    "canonical_snapshot_bytes",
    "decode_board_rejection_reason",
    "encode_board_rejection_reason",
    "evaluate_rejection_revert_eligibility",
    "evaluate_revert_eligibility",
    "image_admission_blocks_revert",
    "predicted_status_after_slot_revert",
    "restore_cell_decision",
    "restored_approved_geometry_revision",
    "restored_assignment_source",
    "snapshot_checksum_sha256",
]
