"""Rank compact cell IDs; hydrate only the next bounded page of snapshots."""

from collections.abc import Callable, Generator, Iterator
from typing import Any
from uuid import UUID

from game_predictor_api.domain.symbol_readability import ReadabilityWorkflowError
from game_predictor_api.storage.sequence_ownership_lock import (
    SequenceOwnershipLockMode,
    held_sequence_ownership_lock,
)
from game_predictor_api.storage.symbol_readability import (
    SNAPSHOT_CURRENT_SQL,
    SNAPSHOT_FROM_SQL,
    SNAPSHOT_SQL,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

PAGE_SIZE = 250
SOURCE_PAGE_SIZE = 128
ELIGIBLE_SQL = """ AND c.source_available AND c.asset_mode='virtual_source'
 AND c.geometry_revision=b.geometry_revision
 AND c.source_geometry_revision_id=b.source_geometry_revision_id """


def has_replacement_fences(session: Session, game: UUID) -> bool:
    """Caller holds the game sequence ownership fence for the whole inventory."""
    if (
        held_sequence_ownership_lock(session, game_id=game)
        is not SequenceOwnershipLockMode.EXCLUSIVE
    ):
        raise ReadabilityWorkflowError(
            "READABILITY_INVENTORY_LOCK_REQUIRED", "Przygotowanie próbki wymaga blokady gry."
        )
    return bool(
        session.scalar(
            text("""SELECT
 EXISTS(SELECT 1 FROM source_replacement_retired WHERE game_id=:game)
 OR EXISTS(SELECT 1 FROM source_replacement_slots WHERE game_id=:game)
 OR EXISTS(SELECT 1 FROM source_replacement_entries
           WHERE game_id=:game AND phase='restored')"""),
            {"game": game},
        )
    )


def candidate_ids_sql(*, audit: bool, replacement_fences: bool, bounded: bool = False) -> str:
    scope = SNAPSHOT_FROM_SQL + ELIGIBLE_SQL
    if replacement_fences:
        scope += SNAPSHOT_CURRENT_SQL
    if audit:
        return (
            "SELECT c.id AS cell_id FROM image_symbol_review_cells c "
            "WHERE c.game_id=:game AND c.source_available AND c.asset_mode='virtual_source' "
            "AND c.quality_issue IS NULL AND NOT EXISTS("
            "SELECT 1 FROM symbol_readability_items old WHERE old.game_id=c.game_id "
            "AND old.ever_labelled AND old.snapshot->>'rendered_pixel_checksum_sha256'"
            "=c.rendered_pixel_checksum_sha256) "
            "AND left(md5(:seed||c.id::text),2)=:prefix "
            "ORDER BY md5(:seed||c.id::text),c.id"
        )
    if bounded:
        scope += " AND s.id=ANY(CAST(:sources AS uuid[])) "
    return (
        "SELECT cell_id,position FROM (SELECT c.id AS cell_id,s.id AS source_id,"
        "row_number() OVER (PARTITION BY s.id,c.import_job_id,"
        "COALESCE(sym.code,c.prediction_symbol_code,'unknown') "
        "ORDER BY md5(:seed||c.id::text)) AS position "
        + scope
        + ") strata "
        + ("WHERE position>=:position " if bounded else "")
        + "ORDER BY position,md5(:seed||source_id::text),md5(:seed||cell_id::text)"
    )


def source_batches(rows: Iterator[Any]) -> Iterator[list[UUID]]:
    """Never split a source-hash tie across pages: cell hashes break that tie."""
    batch: list[UUID] = []
    prior_hash = None
    for source, source_hash in rows:
        if len(batch) >= SOURCE_PAGE_SIZE and source_hash != prior_hash:
            yield batch
            batch = []
        batch.append(source)
        prior_hash = source_hash
    if batch:
        yield batch


def candidate_id_pages(
    session: Session,
    game: UUID,
    seed: str,
    *,
    audit: bool,
    replacement_fences: bool,
    progress: Callable[[], None] | None = None,
) -> Generator[list[UUID], None, None]:
    if audit:
        # Ordered hexadecimal prefixes concatenate to exactly the original
        # global hash order, without sorting all seven million IDs at once.
        for prefix in range(256):
            if progress is not None:
                progress()
            stream = session.execute(
                text(candidate_ids_sql(audit=True, replacement_fences=replacement_fences)),
                {"game": game, "seed": seed, "prefix": f"{prefix:02x}"},
                execution_options={"stream_results": True, "yield_per": PAGE_SIZE},
            ).scalars()
            try:
                yield from (list(page) for page in stream.partitions(PAGE_SIZE))
            finally:
                stream.close()
        return
    position = 1
    while True:
        max_position = 0
        sources = session.execute(
            text(
                "SELECT id,md5(:seed||id::text) AS hash FROM source_images "
                "WHERE game_id=:game ORDER BY hash,id"
            ),
            {"game": game, "seed": seed},
            execution_options={"stream_results": True, "yield_per": SOURCE_PAGE_SIZE},
        )
        try:
            for batch in source_batches(iter(sources)):
                if progress is not None:
                    progress()
                rows = session.execute(
                    text(
                        candidate_ids_sql(
                            audit=False, replacement_fences=replacement_fences, bounded=True
                        )
                    ),
                    {"game": game, "seed": seed, "sources": batch, "position": position},
                ).all()
                max_position = max(max_position, max((int(row[1]) for row in rows), default=0))
                cells = [row[0] for row in rows if row[1] == position]
                for start in range(0, len(cells), PAGE_SIZE):
                    yield cells[start : start + PAGE_SIZE]
        finally:
            sources.close()
        if max_position <= position:
            return
        position += 1


def candidate_snapshots(
    session: Session,
    game: UUID,
    seed: str,
    *,
    audit: bool,
    replacement_fences: bool,
    progress: Callable[[], None] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Keep the previous exact ordering and reject vanished eligibility atomically."""
    stream = candidate_id_pages(
        session, game, seed, audit=audit, replacement_fences=replacement_fences, progress=progress
    )
    try:
        for cells in stream:
            snapshots = session.execute(
                text(
                    SNAPSHOT_SQL
                    + ELIGIBLE_SQL
                    + " AND c.id=ANY(CAST(:cells AS uuid[]))"
                    + (" AND c.quality_issue IS NULL" if audit else "")
                ),
                {"game": game, "cells": list(cells)},
            ).scalars()
            indexed = {str(row["cell_id"]): dict(row) for row in snapshots}
            for cell in cells:
                row = indexed.get(str(cell))
                if row is None:
                    if audit:
                        # The audit cursor sorts a cheap superset. Late eligibility
                        # filtering preserves the legacy eligible subsequence.
                        continue
                    raise ReadabilityWorkflowError(
                        "READABILITY_CROP_STALE", "Pole zmieniło się podczas przygotowania próbki."
                    )
                yield row
    finally:
        stream.close()
