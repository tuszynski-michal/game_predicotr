"""Shared replacement fences. Historical reads deliberately do not use these filters."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    RecognizedBoardModel,
)

RETIRED = "SOURCE_REPLACEMENT_RETIRED"
RESERVED = "SOURCE_REPLACEMENT_RESERVED"
REFERENCED = "SOURCE_REPLACEMENT_REFERENCED"


def source_current_clause(game: Any, source: Any, sha: Any) -> ColumnElement[bool]:
    return func.public.source_replacement_source_current_v1(game, source, sha)


def current_clause(
    game: Any, source: Any, sha: Any, sequence: Any, review: Any
) -> ColumnElement[bool]:
    return func.public.source_replacement_current_v1(game, source, sha, sequence, review)


def current_review_clause(review_id: Any) -> ColumnElement[bool]:
    """An uncorrelated exclusion set also works for projected cells and count rebuilds."""
    excluded = select(
        func.public.source_replacement_excluded_reviews_v1(func.game_data_v2.current_game_id_v1())
    )
    return review_id.not_in(excluded)


def require_active_source(session: Session, game: UUID, source: UUID) -> None:
    retired = session.scalar(
        text("""SELECT EXISTS(SELECT 1 FROM source_images s
          JOIN source_replacement_retired r ON r.game_id=s.game_id
           AND (r.source_id=s.id OR r.source_sha256=s.checksum_sha256)
          WHERE s.game_id=:game AND s.id=:source)"""),
        {"game": game, "source": source},
    )
    if retired:
        raise SourceReplacementError(RETIRED, "Wycofane źródło zachowuje wyłącznie historię.")


def require_active_sha(session: Session, game: UUID, sha: str) -> None:
    if session.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM source_replacement_retired "
            "WHERE game_id=:game AND source_sha256=:sha)"
        ),
        {"game": game, "sha": sha},
    ):
        raise SourceReplacementError(RETIRED, "Wycofane źródło zachowuje wyłącznie historię.")


def require_current_review(session: Session, game: UUID, review: UUID) -> None:
    row = session.execute(
        select(RecognizedBoardModel.source_image_id)
        .join(
            ImageReviewItemModel,
            ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
        )
        .where(ImageReviewItemModel.game_id == game, ImageReviewItemModel.id == review)
    ).first()
    if row is None:
        return  # The owning command supplies its established not-found error.
    require_active_source(session, game, row[0])
    if session.scalar(
        select(ImageReviewItemModel.id).where(
            ImageReviewItemModel.game_id == game,
            ImageReviewItemModel.id == review,
            ~current_review_clause(ImageReviewItemModel.id),
        )
    ):
        raise SourceReplacementError(RESERVED, "Rezerwacja wymaga powiązanego zamiennika.")


def require_sequence_binding(
    session: Session, *, game: UUID, source: UUID, sequence: int, review: UUID | None
) -> None:
    """A late sequence assignment must check the requested position, not the old one."""
    require_active_source(session, game, source)
    allowed = session.scalar(
        text("""SELECT public.source_replacement_current_v1(
      game_id,id,checksum_sha256,:seq,CAST(:review AS uuid)) FROM source_images
      WHERE game_id=:game AND id=:source"""),
        {"game": game, "source": source, "seq": sequence, "review": review},
    )
    if allowed is False:
        raise SourceReplacementError(RESERVED, "Rezerwacja wymaga dokładnie powiązanego review.")


def require_cohort_sources(session: Session, game: UUID, cohort: UUID) -> None:
    """New use/recovery only; frozen history reads deliberately never call this."""
    rows = session.execute(
        text("""SELECT s.id FROM grid_training_cohort_members m
      JOIN source_images s ON s.game_id=m.game_id AND s.id=m.source_id
      WHERE m.game_id=:game AND m.cohort_id=:cohort
      AND NOT public.source_replacement_source_current_v1(s.game_id,s.id,s.checksum_sha256)
      ORDER BY s.id"""),
        {"game": game, "cohort": cohort},
    ).scalars()
    for source in rows:
        require_active_source(session, game, source)
        raise SourceReplacementError(
            RESERVED, "Roboczy zamiennik nie jest dostępnym źródłem kohorty."
        )


def referenced_sources(session: Session, game: UUID, sources: Sequence[UUID] | None = None) -> bool:
    restriction = "" if sources is None else " AND source_id=ANY(CAST(:sources AS uuid[]))"
    return bool(
        session.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM source_replacement_sources WHERE game_id=:game"
                + restriction
                + ")"
            ),
            {"game": game, "sources": list(sources or ())},
        )
    )


def require_unreferenced_sources(
    session: Session, game: UUID, sources: Sequence[UUID] | None = None
) -> None:
    if referenced_sources(session, game, sources):
        raise SourceReplacementError(
            REFERENCED, "Manifest wymiany zachowuje źródło i jego historię."
        )


def reservation(session: Session, game: UUID, sequence: int) -> dict[str, Any] | None:
    row = (
        session.execute(
            text(
                "SELECT * FROM source_replacement_slots "
                "WHERE game_id=:game AND sequence_number=:seq"
            ),
            {"game": game, "seq": sequence},
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def referenced_artifact(session: Session, relative: str) -> bool:
    """Exact paths, their directories and pinned execution/cohort identities are retained."""
    import re

    identities = [part for part in relative.split("/") if re.fullmatch(r"[0-9a-f-]{32,64}", part)]
    return bool(
        session.scalar(
            text("""SELECT EXISTS(
      SELECT 1 FROM source_replacement_entries e
      WHERE position(:path in e.document::text)>0
       OR EXISTS(SELECT 1 FROM unnest(CAST(:ids AS text[])) i
         WHERE position(i in e.document::text)>0)
      UNION ALL SELECT 1 FROM source_replacement_sources r JOIN source_images s
       ON s.game_id=r.game_id AND s.id=r.source_id
      WHERE position(s.relative_path in :path)>0
       OR starts_with(s.relative_path,rtrim(:path,'/') || '/')
       OR s.file_execution_key=ANY(CAST(:ids AS text[]))
       OR EXISTS(SELECT 1 FROM public.jobs j WHERE j.id=s.import_job_id
        AND j.input_payload->>'source_selection_id'=ANY(CAST(:ids AS text[])))
      UNION ALL SELECT 1 FROM verified_training_cohorts c
       WHERE c.artifact_relative_path=:path
          OR starts_with(c.artifact_relative_path, rtrim(:path,'/') || '/')
      UNION ALL SELECT 1 FROM symbol_model_iterations m
       CROSS JOIN LATERAL unnest(ARRAY[m.dataset_manifest_relative_path,
         m.checkpoint_relative_path,m.candidate_manifest_relative_path,
         m.gate_report_relative_path,m.origin_manifest_relative_path]) p
       WHERE p=:path OR starts_with(p,rtrim(:path,'/') || '/')
      UNION ALL SELECT 1 FROM public.grid_model_versions v
       WHERE v.manifest_json::jsonb->>'managedDirectory'=:path
          OR starts_with(v.manifest_json::jsonb->>'managedDirectory',rtrim(:path,'/') || '/')
          OR starts_with(:path,(v.manifest_json::jsonb->>'managedDirectory') || '/'))"""),
            {"path": relative, "ids": identities},
        )
    )
