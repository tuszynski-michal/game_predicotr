"""Durable staging/job admission and discovery binding in the caller's transaction."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_sequence_canonical import BrowserSequenceManifest
from game_predictor_api.domain.source_replacement_admission import (
    admission_error,
    selected_replacement_files,
)
from game_predictor_api.domain.source_replacement_retirement import scope_digest
from game_predictor_api.domain.symbol_readability import digest
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_api.storage.source_replacement_guards import require_active_sha

PIN_KEY = "source_replacement"


def validate_ordinary_staging(
    session: Session, *, game: UUID, manifest: BrowserSequenceManifest
) -> None:
    repo = SourceReplacementRepository(session)
    repo.bind(game)
    acquire_sequence_ownership_lock(session, game_id=game)
    for file in manifest.files:
        require_active_sha(session, game, file.checksum_sha256)
        if file.sequence_range is None:
            continue
        rows = repo.rows(
            "SELECT entry_id,batch_id FROM source_replacement_slots WHERE game_id=:game "
            "AND sequence_number BETWEEN :start AND :end LIMIT 1",
            game=game,
            start=file.sequence_range[0],
            end=file.sequence_range[1],
        )
        if rows:
            from game_predictor_api.domain.source_replacement import SourceReplacementError

            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_RESERVED",
                "Zakres jest zarezerwowany. Użyj importu zamiennika.",
                details={
                    "batchId": str(rows[0]["batch_id"]),
                    "entryId": str(rows[0]["entry_id"]),
                    "manifestUrl": (
                        f"/api/v1/admin/games/{game}/board-sources/{rows[0]['batch_id']}"
                    ),
                },
            )


def immutable_entry(session: Session, game: UUID, batch: UUID, entry: UUID) -> dict[str, Any]:
    document = session.scalar(
        text("SELECT document FROM source_replacement_batches WHERE game_id=:game AND id=:batch"),
        {"game": game, "batch": batch},
    )
    matches = [] if document is None else [e for e in document["entries"] if e["id"] == str(entry)]
    if len(matches) != 1:
        raise admission_error("NOT_FOUND", "Nie znaleziono niezmiennego wpisu planu.")
    return dict(matches[0])


def _entry(session: Session, game: UUID, batch: UUID, entry: UUID) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                "SELECT * FROM source_replacement_entries WHERE game_id=:game "
                "AND batch_id=:batch AND id=:entry FOR UPDATE"
            ),
            {"game": game, "batch": batch, "entry": entry},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise admission_error("NOT_FOUND", "Nie znaleziono wpisu planu.")
    return dict(row)


def _write_document(
    session: Session, game: UUID, entry: UUID, document: dict[str, Any], phase: str
) -> None:
    session.execute(
        text(
            "UPDATE source_replacement_entries SET document=CAST(:doc AS jsonb), "
            "phase=:phase WHERE game_id=:game AND id=:entry"
        ),
        {"game": game, "entry": entry, "doc": json.dumps(document), "phase": phase},
    )


def _fresh_entry(
    session: Session, game: UUID, pin: dict[str, Any], file: dict[str, Any]
) -> dict[str, Any]:
    batch, entry = UUID(pin["batchId"]), UUID(file["entryId"])
    row = _entry(session, game, batch, entry)
    planned = immutable_entry(session, game, batch, entry)
    if (
        scope_digest(planned) != file["scopeDigest"]
        or planned["sequence_numbers"] != file["sequenceNumbers"]
        or planned["source_sha256"] != file["oldSha256"]
    ):
        raise admission_error("PLAN_DRIFT", "Wybór nie pasuje do niezmiennego planu.")
    existing = row["document"].get("replacementStaging")
    if existing is not None:
        if any(existing.get(key) != value for key, value in file.items()) or (
            existing.get("manifestChecksumSha256") != pin["manifestChecksumSha256"]
        ):
            raise admission_error(
                "ADMISSION_INVALID", "Pin pliku nie pasuje do zapisanego dopuszczenia."
            )
        if (
            existing["selectionDigest"] != pin["selectionDigest"]
            or existing["uploadId"] != pin["uploadId"]
        ):
            raise admission_error("ADMISSION_EXISTS", "Kontynuuj istniejący import tego zdjęcia.")
        if row["phase"] not in {"importing", "awaiting_review"}:
            raise admission_error("ADMISSION_CLOSED", "Ten import zamiennika jest już zamknięty.")
    elif row["phase"] != "gap_open" or row["revision"] != file["revision"]:
        raise admission_error("REVISION_CONFLICT", "Luka ma inną fazę lub rewizję.")
    require_active_sha(session, game, file["checksumSha256"])
    slots = (
        session.execute(
            text(
                "SELECT * FROM source_replacement_slots WHERE game_id=:game "
                "AND entry_id=:entry ORDER BY sequence_number"
            ),
            {"game": game, "entry": entry},
        )
        .mappings()
        .all()
    )
    if [s["sequence_number"] for s in slots] != file["sequenceNumbers"] or any(
        s["batch_id"] != batch
        or (existing is None and (s["state"] != "reserved" or s["new_source_id"] is not None))
        or s["new_sha256"] not in (None, file["checksumSha256"])
        for s in slots
    ):
        raise admission_error("RESERVED", "Rezerwacje nie pasują do całego zdjęcia.")
    # The SHA fence is global within this game. Never hide another current photo.
    own_job = None if existing is None else existing["importJobId"]
    sources = session.execute(
        text(
            "SELECT s.id,s.import_job_id, "
            "EXISTS(SELECT 1 FROM image_review_items r JOIN recognized_boards b "
            "ON b.game_id=r.game_id AND b.id=r.recognized_board_id WHERE r.game_id=s.game_id "
            "AND b.source_image_id=s.id AND r.status IN ('pending','accepted','corrected')) "
            "OR EXISTS(SELECT 1 FROM image_board_geometry_pending p WHERE p.game_id=s.game_id "
            "AND p.source_image_id=s.id AND p.status='pending') AS live, "
            "EXISTS(SELECT 1 FROM image_source_geometry_revisions g WHERE g.game_id=s.game_id "
            "AND g.source_image_id=s.id) AS attested, "
            "EXISTS(SELECT 1 FROM image_source_geometry_revisions g WHERE g.game_id=s.game_id "
            "AND g.source_image_id=s.id AND (g.sequence_range_start<>:start OR "
            "g.sequence_range_end<>:end "
            "OR g.sequence_attestation_checksum_sha256 IS NULL)) AS foreign_range "
            "FROM source_images s WHERE s.game_id=:game AND s.checksum_sha256=:sha"
        ),
        {
            "game": game,
            "sha": file["checksumSha256"],
            "start": file["rangeStart"],
            "end": file["rangeEnd"],
        },
    ).mappings()
    if any(
        str(s["import_job_id"]) != own_job
        and (s["live"] or not s["attested"] or s["foreign_range"])
        for s in sources
    ):
        raise admission_error(
            "SHA_SCOPE_CONFLICT", "SHA nowego zdjęcia jest już użyte poza tym wpisem."
        )
    return row


def validate_staging(
    session: Session,
    *,
    game: UUID,
    selection: dict[str, Any],
    manifest: BrowserSequenceManifest,
    upload: UUID,
) -> dict[str, Any]:
    """Read-only fresh validation of server-read uploaded metadata, never client byte claims."""
    repo = SourceReplacementRepository(session)
    repo.bind(game)
    acquire_sequence_ownership_lock(session, game_id=game)
    files = selected_replacement_files(selection, game)
    actual = {f.relative_path: f for f in manifest.files}
    if len(actual) != len(manifest.files) or set(actual) != {f["fileName"] for f in files}:
        raise admission_error(
            "FILE_SCOPE_CONFLICT", "Staging musi zawierać dokładnie wybrane zdjęcia."
        )
    for file in files:
        source = actual[file["fileName"]]
        if source.checksum_sha256 != file["checksumSha256"] or source.sequence_range != (
            file["rangeStart"],
            file["rangeEnd"],
        ):
            raise admission_error("FILE_SCOPE_CONFLICT", "Wysłany plik ma inny SHA lub zakres.")
        file["sizeBytes"] = source.size_bytes
    pin = {
        "schemaVersion": "source-replacement-staging-v1",
        "gameId": str(game),
        "batchId": selection["request"]["batchId"],
        "uploadId": str(upload),
        "manifestChecksumSha256": manifest.checksum_sha256,
        "selectionDigest": digest({"selection": selection, "manifest": manifest.checksum_sha256}),
        "files": files,
    }
    for file in files:
        _fresh_entry(session, game, pin, file)
    return pin


def bind_job_admission(session: Session, job: Any) -> None:
    pin = job.input_payload.get(PIN_KEY)
    if pin is None:
        return
    game = job.game_id
    if (
        game is None
        or pin["schemaVersion"] != "source-replacement-staging-v1"
        or pin["gameId"] != str(game)
        or pin["uploadId"] != job.input_payload.get("source_selection_id")
        or pin["manifestChecksumSha256"] != job.input_payload.get("source_manifest_sha256")
    ):
        raise admission_error("ADMISSION_INVALID", "Job nie pasuje do dopuszczonego stagingu.")
    SourceReplacementRepository(session).bind(game, write=True)
    acquire_sequence_ownership_lock(session, game_id=game)
    rows = [(file, _fresh_entry(session, game, pin, file)) for file in pin["files"]]
    for file, row in rows:
        doc = dict(row["document"])
        prior = doc.get("replacementStaging")
        if prior is not None:
            if prior["importJobId"] != str(job.id):
                raise admission_error("ADMISSION_EXISTS", "Kontynuuj istniejący job zamiennika.")
            continue
        doc["replacementStaging"] = {
            **file,
            "selectionDigest": pin["selectionDigest"],
            "uploadId": pin["uploadId"],
            "manifestChecksumSha256": pin["manifestChecksumSha256"],
            "importJobId": str(job.id),
        }
        _write_document(session, game, row["id"], doc, "importing")
        session.execute(
            text(
                "UPDATE source_replacement_entries SET revision=revision+1 "
                "WHERE game_id=:game AND id=:entry"
            ),
            {"game": game, "entry": row["id"]},
        )
        session.execute(
            text(
                "UPDATE source_replacement_slots SET new_sha256=:sha,revision=revision+1 "
                "WHERE game_id=:game AND entry_id=:entry"
            ),
            {"game": game, "entry": row["id"], "sha": file["checksumSha256"]},
        )


def materialize_admission(session: Session, *, game: UUID, job: UUID, source: Any) -> None:
    """Called after source INSERT+flush, including discovery rehydration."""
    payload = session.scalar(
        text("SELECT input_payload FROM public.jobs WHERE id=:job AND game_id=:game"),
        {"job": job, "game": game},
    )
    pin = None if payload is None else payload.get(PIN_KEY)
    if pin is None:
        return
    acquire_sequence_ownership_lock(session, game_id=game)
    matches = [
        f
        for f in pin["files"]
        if f["checksumSha256"] == source.checksum_sha256 and f["fileName"] == source.relative_path
    ]
    if len(matches) != 1 or source.import_job_id != job:
        raise admission_error(
            "ADMISSION_INVALID", "Źródło workera nie pasuje do dopuszczonego pliku."
        )
    file = matches[0]
    row = _fresh_entry(session, game, pin, file)
    staged = row["document"].get("replacementStaging")
    if staged is None or staged["importJobId"] != str(job):
        raise admission_error("ADMISSION_INVALID", "Brak zapisanego dopuszczenia joba.")
    doc = dict(row["document"])
    existing = doc.get("replacementAdmission")
    if existing is not None and existing["sourceId"] != str(source.id):
        raise admission_error("ADMISSION_EXISTS", "Wpis ma już inne robocze źródło.")
    proof = {
        "schemaVersion": "source-replacement-admission-v1",
        "gameId": str(game),
        "batchId": pin["batchId"],
        "entryId": str(row["id"]),
        "sourceId": str(source.id),
        "importJobId": str(job),
        "sourceSha256": source.checksum_sha256,
        "entryRevision": row["revision"],
        "sequenceNumbers": file["sequenceNumbers"],
    }
    doc["replacementAdmission"] = proof
    _write_document(session, game, row["id"], doc, row["phase"])
    session.execute(
        text(
            "UPDATE source_replacement_slots SET new_source_id=:source WHERE game_id=:game "
            "AND entry_id=:entry AND new_source_id IS NULL"
        ),
        {"game": game, "entry": row["id"], "source": source.id},
    )
    from game_predictor_api.storage.source_replacement_binding import authorize_working_source

    if authorize_working_source(session, game=game, source=source.id, job=job) is None:
        raise admission_error(
            "ADMISSION_INVALID", "Nie udało się związać całego roboczego zdjęcia."
        )


def require_open_admission(session: Session, *, game: UUID, job: UUID) -> None:
    """A late worker must not create an orphan after the final reservation release."""
    closed = session.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM source_replacement_entries "
            "WHERE game_id=:game AND "
            "document->'replacementStaging'->>'importJobId'=CAST(:job AS text) "
            "AND phase NOT IN ('importing','awaiting_review'))"
        ),
        {"game": game, "job": job},
    )
    if closed:
        raise admission_error("ADMISSION_CLOSED", "Import zamiennika został już zamknięty.")
