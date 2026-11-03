"""Working-photo access and explicit final human confirmation, never automatic approval."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from game_predictor_api.domain.source_replacement_admission import admission_error
from game_predictor_api.domain.symbol_readability import crop_identity, digest, identity_is_current
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_api.storage.source_replacement_admission import _entry, immutable_entry
from game_predictor_api.storage.source_replacement_binding import admitted_source
from game_predictor_api.storage.source_replacement_retirement import SourceRetirement
from game_predictor_api.storage.symbol_readability import SNAPSHOT_SQL


class SourceReplacementRestore:
    def __init__(self, repository: SourceReplacementRepository) -> None:
        self.repo = repository
        self.session = repository.session

    def working(self, game: UUID, batch: UUID, entry: UUID) -> dict[str, Any]:
        self.repo.bind(game)
        acquire_sequence_ownership_lock(self.session, game_id=game)
        row = _entry(self.session, game, batch, entry)
        return self._working(game, row)

    def _working(self, game: UUID, row: dict[str, Any]) -> dict[str, Any]:
        doc = row["document"]
        stage = doc.get("replacementStaging")
        pin = doc.get("replacementAdmission")
        source = None if pin is None else UUID(pin["sourceId"])
        job = None if stage is None else UUID(stage["importJobId"])
        result = {
            "game_id": game,
            "batch_id": row["batch_id"],
            "entry_id": row["id"],
            "revision": row["revision"],
            "phase": row["phase"],
            "source_id": source,
            "import_job_id": job,
            "slots": [],
            "readability": [],
            "ready_to_restore": False,
        }
        if source is None or job is None or row["phase"] not in {"importing", "awaiting_review"}:
            return result
        proof = admitted_source(self.session, game, source, job)
        if proof is None:
            raise admission_error("ADMISSION_INVALID", "Brak dowodu roboczego zdjęcia.")
        slots = self.repo.rows(
            "SELECT sl.sequence_number, r.id AS review_item_id, p.id AS pending_geometry_id, "
            "COALESCE(r.status,p.status,'missing') AS status, "
            "(c.review_item_id IS NOT NULL AND c.review_item_id=sl.bound_review_id "
            "AND c.source_image_id=:source AND c.import_job_id=:job "
            "AND r.status IN ('accepted','corrected')) AS canonical "
            "FROM source_replacement_slots sl LEFT JOIN recognized_boards b ON "
            "b.game_id=sl.game_id "
            "AND b.source_image_id=:source AND b.sequence_number=sl.sequence_number "
            "LEFT JOIN image_review_items r ON r.game_id=b.game_id AND r.recognized_board_id=b.id "
            "AND r.import_job_id=:job AND r.status<>'superseded' "
            "LEFT JOIN image_board_geometry_pending p ON p.game_id=sl.game_id AND "
            "p.source_image_id=:source "
            "AND p.sequence_number=sl.sequence_number AND p.status IN "
            "('pending','resolved','rejected') "
            "LEFT JOIN image_sequence_canonical c ON c.game_id=sl.game_id AND "
            "c.sequence_number=sl.sequence_number "
            "WHERE sl.game_id=:game AND sl.entry_id=:entry ORDER BY sl.sequence_number",
            game=game,
            entry=row["id"],
            source=source,
            job=job,
        )
        planned = immutable_entry(self.session, game, row["batch_id"], row["id"])
        targets = {(r["sequence_number"], r["cell_index"]) for r in planned.get("reasons", [])}
        snapshots = [
            r["snapshot"]
            for r in self.repo.rows(
                SNAPSHOT_SQL + " AND s.id=:source ORDER BY c.sequence_number,c.cell_index",
                game=game,
                source=source,
            )
        ]
        cells = [
            s
            for s in snapshots
            if (s["sequence_number"], s["cell_index"]) in targets and identity_is_current(s, s)
        ]
        result["slots"] = slots
        result["readability"] = [
            {
                "cell_id": s["cell_id"],
                "review_item_id": s["review_item_id"],
                "sequence_number": s["sequence_number"],
                "cell_index": s["cell_index"],
                "identity": crop_identity(s),
                "revision": s["revision"],
            }
            for s in cells
        ]
        result["ready_to_restore"] = bool(
            targets
            and len(cells) == len(targets)
            and len(slots) == len(proof.sequences)
            and all(s["canonical"] for s in slots)
        )
        return result

    def restore(self, game: UUID, request: Any) -> dict[str, Any]:
        self.repo.bind(game, write=True)
        acquire_sequence_ownership_lock(self.session, game_id=game)
        command = request.model_dump(mode="json")
        checksum = digest({"action": "restore", "game": str(game), "command": command})
        receipts = self.repo.rows(
            "SELECT command_sha256,response FROM source_replacement_commands "
            "WHERE game_id=:game AND idempotency_key=:key",
            game=game,
            key=request.idempotency_key,
        )
        if receipts:
            if receipts[0]["command_sha256"] != checksum:
                raise admission_error("IDEMPOTENCY_CONFLICT", "Klucz reprezentuje inne polecenie.")
            return dict(receipts[0]["response"]["result"])
        row = _entry(self.session, game, request.batch_id, request.entry_id)
        if row["revision"] != request.expected_revision:
            raise admission_error("REVISION_CONFLICT", "Wpis ma inną rewizję.")
        if not request.confirmed or not request.actor.strip():
            raise admission_error("READABILITY_REQUIRED", "Potwierdź czytelność nowych pól.")
        view = self._working(game, row)
        if not view["ready_to_restore"]:
            raise admission_error(
                "REVIEW_INCOMPLETE", "Każda plansza nowego zdjęcia wymaga zatwierdzenia."
            )
        expected = {(str(c["cell_id"]), c["identity"], c["revision"]) for c in view["readability"]}
        actual = {
            (str(c.cell_id), c.identity, c.revision) for c in request.readability if c.readable
        }
        if actual != expected or len(request.readability) != len(expected):
            raise admission_error(
                "READABILITY_STALE", "Wskazane piksele lub ich oceny zmieniły się."
            )
        source, job = view["source_id"], view["import_job_id"]
        numbers = [slot["sequence_number"] for slot in view["slots"]]
        acquire_image_sequence_locks(self.session, game_id=game, sequence_numbers=numbers)
        # The ownership fence covers human decisions, geometry and late worker projection.
        self.repo.rows(
            "SELECT id FROM source_images WHERE game_id=:game AND id=:source FOR UPDATE",
            game=game,
            source=source,
        )
        snapshots = [
            r["snapshot"]
            for r in self.repo.rows(
                SNAPSHOT_SQL + " AND c.id=ANY(CAST(:ids AS uuid[])) ORDER BY c.id",
                game=game,
                ids=[str(c.cell_id) for c in request.readability],
            )
        ]
        canonical_ids = [str(s["review_item_id"]) for s in view["slots"]]
        orphans = self.repo.rows(
            "SELECT to_jsonb(r) AS prior FROM image_review_items r JOIN recognized_boards b "
            "ON b.game_id=r.game_id AND b.id=r.recognized_board_id WHERE r.game_id=:game "
            "AND b.source_image_id=:source AND NOT(r.id=ANY(CAST(:ids AS uuid[]))) FOR "
            "UPDATE OF r,b",
            game=game,
            source=source,
            ids=canonical_ids,
        )
        if any(r["prior"]["status"] in {"accepted", "corrected"} for r in orphans):
            raise admission_error(
                "ORPHAN_CONFLICT", "Zdjęcie ma dodatkowe rozstrzygnięcie poza bindingiem."
            )
        now = datetime.now(UTC)
        for record in orphans:
            prior = record["prior"]
            if prior["status"] != "pending":
                continue
            resolved = {
                "action": "superseded",
                "reason": "source_replacement_admission_closed",
                "batchId": str(request.batch_id),
                "entryId": str(request.entry_id),
                "sequenceNumber": prior["sequence_number"],
                "previous": prior,
            }
            params = {
                "game": game,
                "id": prior["id"],
                "event": uuid4(),
                "key": uuid4(),
                "revision": prior["resolution_revision"] + 1,
                "value": json.dumps(resolved),
                "sha": digest(resolved),
                "actor": request.actor,
                "now": now,
            }
            self.session.execute(
                text(
                    "INSERT INTO image_review_resolution_events "
                    "(game_id,id,review_item_id,revision,idempotency_key,action,command_sha256,"
                    "resolved_value,resolved_by,created_at) "
                    "VALUES(:game,:event,:id,:revision,:key,'superseded',:sha,CAST(:value "
                    "AS jsonb),:actor,:now)"
                ),
                params,
            )
            self.session.execute(
                text(
                    "UPDATE image_review_items SET "
                    "status='superseded',resolved_value=CAST(:value AS jsonb), "
                    "resolved_by=:actor,resolved_at=:now,resolution_revision=:revision "
                    "WHERE game_id=:game AND id=:id"
                ),
                params,
            )
            self.session.execute(
                text(
                    "DELETE FROM image_layout_staging_rows WHERE game_id=:game AND "
                    "review_item_id=:id"
                ),
                params,
            )
        pending_before = self.repo.rows(
            "SELECT to_jsonb(p) AS prior FROM image_board_geometry_pending p "
            "WHERE game_id=:game AND source_image_id=:source AND status IN "
            "('pending','rejected') FOR UPDATE",
            game=game,
            source=source,
        )
        self.session.execute(
            text(
                "UPDATE image_board_geometry_pending SET "
                "status='superseded',superseded_at=:now,updated_at=:now "
                "WHERE game_id=:game AND source_image_id=:source AND status IN "
                "('pending','rejected')"
            ),
            {"game": game, "source": source, "now": now},
        )
        result = {
            "game_id": str(game),
            "batch_id": str(request.batch_id),
            "entry_id": str(request.entry_id),
            "revision": row["revision"] + 1,
            "phase": "restored",
            "source_id": str(source),
        }
        doc = dict(row["document"])
        doc["restoration"] = {
            "commandKey": str(request.idempotency_key),
            "actor": request.actor,
            "readability": snapshots,
            "orphanReviews": orphans,
            "orphanGeometry": pending_before,
            "canonicalReviewIds": canonical_ids,
            "importJobId": str(job),
        }
        self.session.execute(
            text(
                "UPDATE source_replacement_entries SET phase='restored',revision=revision+1, "
                "document=CAST(:doc AS jsonb),failure_code=NULL WHERE game_id=:game AND id=:entry"
            ),
            {"game": game, "entry": request.entry_id, "doc": json.dumps(doc, default=str)},
        )
        self.session.execute(
            text("DELETE FROM source_replacement_slots WHERE game_id=:game AND entry_id=:entry"),
            {"game": game, "entry": request.entry_id},
        )
        SourceRetirement(self.repo)._invalidate(game)
        self.session.execute(
            text(
                "UPDATE source_replacement_batches SET revision=revision+1,status=CASE "
                "WHEN NOT EXISTS "
                "(SELECT 1 FROM source_replacement_entries WHERE game_id=:game AND "
                "batch_id=:batch AND phase NOT IN ('restored','cancelled')) "
                "THEN 'restored' ELSE status END WHERE game_id=:game AND id=:batch"
            ),
            {"game": game, "batch": request.batch_id},
        )
        self.session.execute(
            text(
                "INSERT INTO "
                "source_replacement_commands(game_id,idempotency_key,command_sha256,"
                "batch_id,response) "
                "VALUES(:game,:key,:sha,:batch,CAST(:response AS jsonb))"
            ),
            {
                "game": game,
                "key": request.idempotency_key,
                "sha": checksum,
                "batch": request.batch_id,
                "response": json.dumps(
                    {"result": result, "proof": doc["restoration"]}, default=str
                ),
            },
        )
        return result
