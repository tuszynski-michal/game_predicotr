"""Internal admission proof and all-slot finalization; C2 supplies admission UI/API."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.sequence_takeover import (
    ReplacementClaimBinding,
    SequenceReservation,
)
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.source_replacement_guards import (
    RESERVED,
    require_active_source,
    reservation,
)


@dataclass(frozen=True)
class ReplacementAdmission:
    game: UUID
    batch: UUID
    entry: UUID
    source: UUID
    job: UUID
    sha256: str
    sequences: tuple[int, ...]
    revision: int


def admitted_source(
    session: Session, game: UUID, source: UUID, job: UUID
) -> ReplacementAdmission | None:
    """Read proof from the entry, never trust an import payload or a client-provided flag."""
    require_active_source(session, game, source)
    rows = (
        session.execute(
            text("""SELECT e.id,e.batch_id,e.revision,e.document,e.source_sha256,
      s.checksum_sha256,s.import_job_id FROM source_replacement_entries e
      JOIN source_images s ON s.game_id=e.game_id AND s.id=:source
      WHERE e.game_id=:game AND e.phase IN
       ('replacement_staged','importing','awaiting_review')
      AND e.document->'replacementAdmission'->>'sourceId'=CAST(:source AS text)"""),
            {"game": game, "source": source},
        )
        .mappings()
        .all()
    )
    if not rows:
        return None
    if len(rows) != 1:
        raise SourceReplacementError(RESERVED, "Niejednoznaczny dowód importu zamiennika.")
    row = rows[0]
    pin = row["document"]["replacementAdmission"]
    sequences = pin.get("sequenceNumbers")
    if (
        pin.get("schemaVersion") != "source-replacement-admission-v1"
        or pin.get("gameId") != str(game)
        or pin.get("batchId") != str(row["batch_id"])
        or pin.get("entryId") != str(row["id"])
        or pin.get("importJobId") != str(job)
        or row["import_job_id"] != job
        or pin.get("sourceSha256") != row["checksum_sha256"]
        or row["source_sha256"] == row["checksum_sha256"]
        or pin.get("entryRevision") != row["revision"]
        or not isinstance(sequences, list)
        or not sequences
        or any(type(n) is not int or n < 1 for n in sequences)
        or sorted(set(sequences)) != sequences
        or sequences != row["document"].get("sequence_numbers")
    ):
        raise SourceReplacementError(RESERVED, "Dowód importu zamiennika nie pasuje do źródła.")
    slots = (
        session.execute(
            text("""SELECT * FROM source_replacement_slots
      WHERE game_id=:game AND entry_id=:entry ORDER BY sequence_number"""),
            {"game": game, "entry": row["id"]},
        )
        .mappings()
        .all()
    )
    if [r["sequence_number"] for r in slots] != sequences or any(
        r["batch_id"] != row["batch_id"]
        or r["new_source_id"] != source
        or r["new_sha256"] != row["checksum_sha256"]
        for r in slots
    ):
        raise SourceReplacementError(RESERVED, "Rezerwacje nie pasują do całego zdjęcia.")
    return ReplacementAdmission(
        game,
        row["batch_id"],
        row["id"],
        source,
        job,
        row["checksum_sha256"],
        tuple(sequences),
        row["revision"],
    )


def authorize_working_source(
    session: Session, *, game: UUID, source: UUID, job: UUID
) -> ReplacementAdmission | None:
    """Internal C2 adapter: proof authorizes geometry work, never current visibility.

    Retain the replacement before any provisional review or geometry is written.
    C2 also calls this when persisting admission, before exposing its work source.
    The normalized reference survives restored and removal of active slots.
    """
    acquire_sequence_ownership_lock(session, game_id=game)
    proof = admitted_source(session, game, source, job)
    if proof is not None:
        session.execute(
            text("""INSERT INTO source_replacement_sources(game_id,entry_id,source_id)
          VALUES(:game,:entry,:source) ON CONFLICT DO NOTHING"""),
            {"game": game, "entry": proof.entry, "source": source},
        )
    return proof


def replacement_claim(
    session: Session, *, game: UUID, source: UUID, job: UUID, sequence: int, review: UUID
) -> tuple[SequenceReservation | None, ReplacementClaimBinding | None]:
    slot = reservation(session, game, sequence)
    if slot is None:
        return None, None
    proof = authorize_working_source(session, game=game, source=source, job=job)
    valid = proof is not None and proof.entry == slot["entry_id"] and sequence in proof.sequences
    facts = SequenceReservation(
        str(game),
        str(slot["batch_id"]),
        str(slot["entry_id"]),
        str(slot["new_source_id"]) if slot["new_source_id"] else None,
        slot["new_sha256"],
        str(slot["bound_review_id"]) if slot["bound_review_id"] else None,
        str(review) if valid and slot["state"] == "reserved" else None,
    )
    binding = (
        None
        if not valid or proof is None
        else ReplacementClaimBinding(
            str(game), str(proof.batch), str(proof.entry), str(source), proof.sha256, str(review)
        )
    )
    return facts, binding


def bind_complete_source(session: Session, *, game: UUID, source: UUID, job: UUID) -> bool:
    """Bind only existing reviews, all together. Incomplete geometry stays provisional."""
    from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks

    acquire_sequence_ownership_lock(session, game_id=game)
    proof = authorize_working_source(session, game=game, source=source, job=job)
    if proof is None:
        return False
    acquire_image_sequence_locks(session, game_id=game, sequence_numbers=proof.sequences)
    session.flush()
    rows = (
        session.execute(
            text("""SELECT r.id,r.sequence_number,b.completeness_status
      FROM image_review_items r JOIN recognized_boards b
       ON b.game_id=r.game_id AND b.id=r.recognized_board_id
      WHERE r.game_id=:game AND b.source_image_id=:source AND r.import_job_id=:job
       AND r.status IN ('pending','accepted','corrected') ORDER BY r.sequence_number
      FOR UPDATE OF r,b"""),
            {"game": game, "source": source, "job": job},
        )
        .mappings()
        .all()
    )
    numbers = [r["sequence_number"] for r in rows]
    if len(set(numbers)) != len(numbers) or any(n not in proof.sequences for n in numbers):
        raise SourceReplacementError(RESERVED, "Niejednoznaczne plansze zamiennika.")
    if numbers != list(proof.sequences) or any(
        r["completeness_status"] != "complete" for r in rows
    ):
        return False
    slots = (
        session.execute(
            text("""SELECT * FROM source_replacement_slots
      WHERE game_id=:game AND entry_id=:entry ORDER BY sequence_number FOR UPDATE"""),
            {"game": game, "entry": proof.entry},
        )
        .mappings()
        .all()
    )
    if any(
        slot["bound_review_id"] not in (None, row["id"])
        for slot, row in zip(slots, rows, strict=True)
    ):
        raise SourceReplacementError(RESERVED, "Rezerwacja wskazuje inne review.")
    for row in rows:
        session.execute(
            text("""UPDATE source_replacement_slots SET state='pending_bound',
          bound_review_id=:review,revision=revision+1 WHERE game_id=:game
          AND entry_id=:entry AND sequence_number=:seq AND bound_review_id IS NULL"""),
            {
                "game": game,
                "entry": proof.entry,
                "seq": row["sequence_number"],
                "review": row["id"],
            },
        )
    session.execute(
        text(
            "UPDATE source_replacement_entries SET phase='awaiting_review', "
            "revision=revision+1,document=jsonb_set(document,"
            "'{replacementAdmission,entryRevision}', "
            "to_jsonb(revision+1)) WHERE game_id=:game AND id=:entry AND phase='importing' "
            "AND document ? 'replacementStaging'"
        ),
        {"game": game, "entry": proof.entry},
    )
    return True
