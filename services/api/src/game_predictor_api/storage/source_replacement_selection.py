"""Source selection and historical badges, using the shared current-source fences."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_reviews import (
    ImageReviewItem,
    ImageSequenceSourceCandidate,
    ImageSequenceSourceSelection,
    SourceReplacementState,
    SourceSelectionState,
)
from game_predictor_api.storage.models import (
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSequenceSourceOverrideEventModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.source_replacement_guards import (
    current_clause,
    current_review_clause,
    reservation,
    source_current_clause,
)


def _source_states(
    session: Session, game: UUID, sources: Sequence[UUID]
) -> dict[UUID, SourceReplacementState]:
    if not sources:
        return {}
    # Phase only changes the historical label. The permanent shared ID/SHA fence
    # decides whether the source is retired, also after restoration.
    active: dict[UUID, bool] = dict(
        session.execute(
            text("""SELECT s.id,
      NOT EXISTS(SELECT 1 FROM source_replacement_retired r WHERE r.game_id=s.game_id
      AND (r.source_id=s.id OR r.source_sha256=s.checksum_sha256))
      FROM source_images s WHERE s.game_id=:game AND s.id=ANY(CAST(:sources AS uuid[]))"""),
            {"game": game, "sources": sources},
        ).all()
    )
    states: dict[UUID, SourceReplacementState] = {
        source: "active" if allowed else "retired" for source, allowed in active.items()
    }
    retired = [source for source, state in states.items() if state == "retired"]
    if retired:
        restored = session.execute(
            text("""SELECT DISTINCT s.id FROM source_images s
          JOIN source_replacement_retired r ON r.game_id=s.game_id
           AND (r.source_id=s.id OR r.source_sha256=s.checksum_sha256)
          JOIN source_replacement_entries e ON e.game_id=r.game_id AND e.id=r.entry_id
          WHERE s.game_id=:game AND s.id=ANY(CAST(:sources AS uuid[]))
           AND e.phase='restored'"""),
            {"game": game, "sources": retired},
        ).scalars()
        states.update((source, "replaced") for source in restored)
    return states


def annotate_review_sources(
    session: Session, items: Sequence[ImageReviewItem]
) -> tuple[ImageReviewItem, ...]:
    if not items:
        return ()
    states = _source_states(session, items[0].game_id, [item.source_image_id for item in items])
    allowed = set(
        session.scalars(
            select(ImageReviewItemModel.id).where(
                ImageReviewItemModel.game_id == items[0].game_id,
                ImageReviewItemModel.id.in_([item.id for item in items]),
                current_review_clause(ImageReviewItemModel.id),
            )
        )
    )
    return tuple(
        replace(item, source_state=states[item.source_image_id], selectable=item.id in allowed)
        for item in items
    )


def sequence_source_selection(
    session: Session, game: UUID, sequence: int
) -> ImageSequenceSourceSelection | None:
    slot = reservation(session, game, sequence)
    source_allowed = source_current_clause(
        game, SourceImageModel.id, SourceImageModel.checksum_sha256
    )
    review_allowed = current_clause(
        game,
        SourceImageModel.id,
        SourceImageModel.checksum_sha256,
        sequence,
        ImageReviewItemModel.id,
    )
    rows = session.execute(
        select(ImageReviewItemModel, RecognizedBoardModel, SourceImageModel, review_allowed)
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .outerjoin(
            ImageLayoutStagingRowModel,
            ImageLayoutStagingRowModel.review_item_id == ImageReviewItemModel.id,
        )
        .where(
            ImageReviewItemModel.game_id == game,
            func.coalesce(
                ImageLayoutStagingRowModel.sequence_number,
                ImageReviewItemModel.sequence_number,
                RecognizedBoardModel.sequence_number,
            )
            == sequence,
            or_(
                ImageReviewItemModel.status.in_(("accepted", "corrected")),
                ~source_allowed,
                ImageReviewItemModel.id == (slot["bound_review_id"] if slot else None),
            ),
        )
        .order_by(
            RecognizedBoardModel.board_confidence.desc(),
            RecognizedBoardModel.sequence_confidence.desc(),
            (SourceImageModel.width * SourceImageModel.height).desc(),
            ImageReviewItemModel.id,
        )
    ).all()
    # Even a prematurely accepted provisional review cannot masquerade as current.
    rows = [row for row in rows if not (slot and row[2].id == slot["new_source_id"] and not row[3])]
    if not rows and slot is None:
        return None
    states = _source_states(session, game, [row[2].id for row in rows])
    override = session.scalar(
        select(ImageSequenceSourceOverrideEventModel)
        .where(
            ImageSequenceSourceOverrideEventModel.game_id == game,
            ImageSequenceSourceOverrideEventModel.sequence_number == sequence,
        )
        .order_by(ImageSequenceSourceOverrideEventModel.revision.desc())
        .limit(1)
    )
    canonical = session.scalar(
        select(ImageSequenceCanonicalModel).where(
            ImageSequenceCanonicalModel.game_id == game,
            ImageSequenceCanonicalModel.sequence_number == sequence,
        )
    )
    eligible = {
        item.id
        for item, _board, source, allowed in rows
        if allowed and states[source.id] == "active"
    }
    manual = None if override is None else override.selected_review_item_id
    state: SourceSelectionState
    if slot is not None:
        selected = slot["bound_review_id"] if slot["state"] == "pending_bound" else None
        selected = selected if selected in eligible else None
        state = "pending_bound" if selected is not None else "reserved_gap"
        manual = None
    else:
        canonical_id = None if canonical is None else canonical.review_item_id
        selected = next(
            (
                identifier
                for identifier in [canonical_id, manual, *(row[0].id for row in rows)]
                if identifier in eligible
            ),
            None,
        )
        manual = manual if manual in eligible else None
        state = "available" if selected is not None else "history_only"
    candidates = tuple(
        ImageSequenceSourceCandidate(
            review_item_id=item.id,
            recognized_board_id=board.id,
            import_job_id=source.import_job_id,
            sequence_number=sequence,
            source_checksum_sha256=source.checksum_sha256,
            source_relative_path=source.relative_path,
            width=source.width,
            height=source.height,
            board_confidence=board.board_confidence,
            sequence_confidence=board.sequence_confidence,
            geometry_revision=board.geometry_revision,
            automatic_rank=index,
            quality_score=round(
                board.board_confidence * 0.45
                + board.sequence_confidence * 0.35
                + min(source.width * source.height / 2_073_600, 1.0) * 0.20,
                6,
            ),
            selected=item.id == selected,
            selected_manually=manual is not None and item.id == manual,
            source_state=states[source.id],
            selectable=slot is None and item.id in eligible,
        )
        for index, (item, board, source, _allowed) in enumerate(rows, start=1)
    )
    batch = None if slot is None else cast(UUID, slot["batch_id"])
    return ImageSequenceSourceSelection(
        game_id=game,
        sequence_number=sequence,
        candidates=candidates,
        manual_override_review_item_id=manual,
        override_revision=0 if override is None else override.revision,
        state=state,
        replacement_batch_id=batch,
        replacement_entry_id=None if slot is None else slot["entry_id"],
        replacement_manifest_url=None
        if batch is None
        else f"/api/v1/admin/games/{game}/board-sources/{batch}",
    )
