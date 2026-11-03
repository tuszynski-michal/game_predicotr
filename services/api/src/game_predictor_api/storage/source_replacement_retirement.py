"""One photo per transaction; immutable manifest precedes every current-state change."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import text

from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.source_replacement_retirement import (
    retirement_resolved_value,
    scope_digest,
)
from game_predictor_api.domain.symbol_readability import digest
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.super_game_input_version import record_super_game_input_change

if TYPE_CHECKING:
    from game_predictor_api.storage.source_replacement import SourceReplacementRepository


class SourceRetirement:
    def __init__(self, repository: SourceReplacementRepository) -> None:
        self.repo = repository
        self.session = repository.session

    def _entry(self, game: UUID, batch: UUID, entry: UUID) -> dict[str, Any]:
        rows = self.repo.rows(
            "SELECT * FROM source_replacement_entries WHERE game_id=:game "
            "AND batch_id=:batch AND id=:entry",
            game=game,
            batch=batch,
            entry=entry,
        )
        if not rows:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_NOT_FOUND", "Nie znaleziono wpisu planu."
            )
        return rows[0]

    def preview(self, game: UUID, request: Any) -> dict[str, Any]:
        self.repo.bind(game)
        acquire_sequence_ownership_lock(self.session, game_id=game)
        row = self._entry(game, request.batch_id, request.entry_id)
        return self._fresh(game, request, row)

    def _fresh(self, game: UUID, request: Any, row: dict[str, Any]) -> dict[str, Any]:
        self._planned(row, request.expected_revision)
        if row["document"].get("compact_schema"):
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_PURGE_REQUIRED", "Plan wymaga jawnego fizycznego usunięcia."
            )
        preview = self.repo._preview(game, [UUID(str(row["source_id"]))])
        fresh = preview["entries"][0]
        self._exclude_proven_derivations(game, request.batch_id, fresh)
        if fresh["blockers"]:
            # Preserve the actionable conflict, including foreign pending beneath canonical.
            conflict_rows = [*fresh["canonical"], *fresh["pending"]]
            resolution_urls = sorted(
                {
                    f"/api/v1/admin/image-review-items/{item.get('review_item_id', item.get('id'))}"
                    f"?gameId={game}&importJobId={item['import_job_id']}"
                    for item in conflict_rows
                }
            )
            code = (
                "SOURCE_REPLACEMENT_SLOT_PENDING_CONFLICT"
                if "SOURCE_REPLACEMENT_SLOT_PENDING_CONFLICT" in fresh["blockers"]
                else fresh["blockers"][0]
            )
            raise SourceReplacementError(
                code,
                "Podgląd jest zablokowany. Utwórz nowy plan po rozstrzygnięciu konfliktu.",
                details={
                    "blockers": fresh["blockers"],
                    "resolutionUrls": resolution_urls,
                    "pending": fresh["pending"],
                    "pendingGeometry": fresh["dependencies"]["pending_geometry"],
                },
            )
        if scope_digest(fresh) != scope_digest(row["document"]):
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_PLAN_DRIFT",
                "Źródło lub zależności zmieniły się. Wymagany nowy plan; zapisany snapshot "
                "pozostaje bez zmian.",
            )
        token = digest(
            {
                "action": "retire",
                "game": str(game),
                "batch": str(request.batch_id),
                "entry": str(request.entry_id),
                "revision": row["revision"],
                "snapshot": fresh,
            }
        )
        return {
            "game_id": str(game),
            "batch_id": str(request.batch_id),
            "entry_id": str(request.entry_id),
            "revision": row["revision"],
            "action": "retire",
            "preview_token": token,
            "entry": {**row["document"], "scope_digest": scope_digest(fresh)},
        }

    def _derive_jobs(self, game: UUID) -> list[dict[str, Any]]:
        return self.repo.rows(
            "SELECT id,game_id,job_type,input_key,input_payload FROM public.jobs "
            "WHERE game_id=:game AND job_type='super_game_series_derive' "
            "AND status IN ('created','processing') ORDER BY id LIMIT 10001",
            game=game,
        )

    def _exclude_proven_derivations(self, game: UUID, batch: UUID, fresh: dict[str, Any]) -> None:
        receipts = self.repo.rows(
            "SELECT response FROM source_replacement_commands WHERE game_id=:game AND "
            "batch_id=:batch",
            game=game,
            batch=batch,
        )
        proofs = {
            proof["id"]: proof["digest"]
            for receipt in receipts
            for proof in receipt["response"].get("createdDerivations", [])
        }
        allowed = {
            str(job["id"])
            for job in self._derive_jobs(game)
            if proofs.get(str(job["id"])) == digest(job)
        }
        jobs = fresh["dependencies"]["active_jobs"]
        fresh["dependencies"]["active_jobs"] = [
            job for job in jobs if str(job["id"]) not in allowed
        ]
        if not fresh["dependencies"]["active_jobs"]:
            fresh["blockers"] = [
                code for code in fresh["blockers"] if code != "SOURCE_REPLACEMENT_ACTIVE_JOB"
            ]

    @staticmethod
    def _planned(row: dict[str, Any], revision: int) -> None:
        if row["revision"] != revision:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_REVISION_CONFLICT", "Wpis ma inną rewizję."
            )
        if row["phase"] != "planned":
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_PHASE_CONFLICT", "Operacja wymaga fazy planned."
            )

    def execute(self, game: UUID, request: Any) -> dict[str, Any]:
        self.repo.bind(game, write=True)
        acquire_sequence_ownership_lock(self.session, game_id=game)
        checksum = digest({"game": str(game), "command": request.model_dump(mode="json")})
        receipt = self.repo.rows(
            "SELECT * FROM source_replacement_commands WHERE game_id=:game AND "
            "idempotency_key=:key",
            game=game,
            key=request.idempotency_key,
        )
        if receipt:
            if receipt[0]["command_sha256"] != checksum:
                raise SourceReplacementError(
                    "SOURCE_REPLACEMENT_IDEMPOTENCY_CONFLICT", "Klucz reprezentuje inne polecenie."
                )
            return dict(receipt[0]["response"])
        row = self._entry(game, request.batch_id, request.entry_id)
        self._planned(row, request.expected_revision)
        document = row["document"]
        acquire_image_sequence_locks(
            self.session, game_id=game, sequence_numbers=document["sequence_numbers"]
        )
        self.repo.rows(
            "SELECT id FROM source_images WHERE game_id=:game AND id=ANY(CAST(:ids AS "
            "uuid[])) ORDER BY id FOR UPDATE",
            game=game,
            ids=document["source_ids"],
        )
        self.repo.rows(
            "SELECT r.id FROM image_review_items r JOIN recognized_boards b ON "
            "b.game_id=r.game_id AND b.id=r.recognized_board_id "
            "WHERE r.game_id=:game AND b.source_image_id=ANY(CAST(:ids AS uuid[])) ORDER BY "
            "r.id FOR UPDATE OF r",
            game=game,
            ids=document["source_ids"],
        )
        self.repo.rows(
            "SELECT id FROM recognized_boards WHERE game_id=:game AND "
            "source_image_id=ANY(CAST(:ids AS uuid[])) ORDER BY id FOR UPDATE",
            game=game,
            ids=document["source_ids"],
        )
        self.repo.rows(
            "SELECT id FROM image_board_geometry_pending WHERE game_id=:game AND "
            "source_image_id=ANY(CAST(:ids AS uuid[])) ORDER BY id FOR UPDATE",
            game=game,
            ids=document["source_ids"],
        )
        if request.action == "retire":
            fresh = self._fresh(game, request, row)
            if fresh["preview_token"] != request.preview_token:
                raise SourceReplacementError(
                    "SOURCE_REPLACEMENT_PREVIEW_STALE", "Potwierdź świeży podgląd wycofania."
                )
            derivations = self._retire(game, row, request, checksum)
            phase = "gap_open"
        else:
            phase = "cancelled"
            derivations = []
        result = {
            "game_id": str(game),
            "batch_id": str(request.batch_id),
            "entry_id": str(request.entry_id),
            "revision": row["revision"] + 1,
            "phase": phase,
            "scope_digest": scope_digest(document),
            "createdDerivations": derivations,
        }
        self.session.execute(
            text(
                "UPDATE source_replacement_entries SET phase=:phase, revision=revision+1, "
                "failure_code=NULL "
                "WHERE game_id=:game AND id=:entry"
            ),
            {"game": game, "entry": request.entry_id, "phase": phase},
        )
        # Summary only: each entry remains authoritative for authorization and progress.
        self.session.execute(
            text(
                "UPDATE source_replacement_batches SET revision=revision+1, status=CASE "
                "WHEN EXISTS(SELECT 1 FROM source_replacement_entries WHERE game_id=:game AND "
                "batch_id=:batch AND phase='gap_open') THEN 'gap_open' "
                "WHEN NOT EXISTS(SELECT 1 FROM source_replacement_entries WHERE game_id=:game "
                "AND batch_id=:batch AND phase<>'cancelled') THEN 'cancelled' "
                "ELSE status END WHERE game_id=:game AND id=:batch"
            ),
            {"game": game, "batch": request.batch_id},
        )
        self.session.execute(
            text(
                "INSERT INTO "
                "source_replacement_commands(game_id,idempotency_key,command_sha256,"
                "batch_id,response) "
                "VALUES(:game,:key,:sha,:batch,CAST(:doc AS jsonb))"
            ),
            {
                "game": game,
                "key": request.idempotency_key,
                "sha": checksum,
                "batch": request.batch_id,
                "doc": json.dumps(result),
            },
        )
        return result

    def _retire(
        self, game: UUID, row: dict[str, Any], request: Any, checksum: str
    ) -> list[dict[str, Any]]:
        doc = row["document"]
        timestamp = datetime.now(UTC)
        provenance = {
            "schemaVersion": "source-replacement-retired-v1",
            "action": "source_replacement_retired",
            "gameId": str(game),
            "batchId": str(request.batch_id),
            "entryId": str(request.entry_id),
            "commandKey": str(request.idempotency_key),
            "commandSha256": checksum,
            "actor": "admin",
            "retiredAt": timestamp.isoformat(),
            "prior": doc,
        }
        for seq in doc["sequence_numbers"]:
            snapshot = {
                "sequenceNumber": seq,
                "priorCanonical": [c for c in doc["canonical"] if c["sequence_number"] == seq],
                "retirementCommandKey": str(request.idempotency_key),
            }
            self.session.execute(
                text(
                    "INSERT INTO "
                    "source_replacement_slots(game_id,sequence_number,entry_id,"
                    "batch_id,state,revision,document) "
                    "VALUES(:game,:seq,:entry,:batch,'reserved',1,CAST(:doc AS jsonb))"
                ),
                {
                    "game": game,
                    "seq": seq,
                    "entry": request.entry_id,
                    "batch": request.batch_id,
                    "doc": json.dumps(snapshot),
                },
            )
        for source in doc["source_ids"]:
            self.session.execute(
                text(
                    "INSERT INTO "
                    "source_replacement_retired(game_id,source_id,entry_id,"
                    "source_sha256,document,retired_at) "
                    "VALUES(:game,:source,:entry,:sha,CAST(:doc AS jsonb),:at)"
                ),
                {
                    "game": game,
                    "source": source,
                    "entry": request.entry_id,
                    "sha": doc["source_sha256"],
                    "doc": json.dumps({**provenance, "sourceId": source}),
                    "at": timestamp,
                },
            )
        for prior in doc["pending"]:
            value = retirement_resolved_value(
                prior,
                batch=str(request.batch_id),
                entry=str(request.entry_id),
                source_sha256=doc["source_sha256"],
            )
            params = {
                "game": game,
                "id": prior["id"],
                "revision": prior["resolution_revision"] + 1,
                "key": request.idempotency_key,
                "sha": checksum,
                "doc": json.dumps(value),
                "at": timestamp,
                "event": uuid4(),
            }
            self.session.execute(
                text(
                    "INSERT INTO "
                    "image_review_resolution_events(game_id,id,review_item_id,revision"
                    ",idempotency_key,action,command_sha256,resolved_value,resolved_by"
                    ",created_at) "
                    "VALUES(:game,:event,:id,:revision,:key,'superseded',:sha,CAST(:doc AS "
                    "jsonb),'admin',:at)"
                ),
                params,
            )
            self.session.execute(
                text(
                    "UPDATE image_review_items SET status='superseded', "
                    "resolution_revision=:revision, resolved_value=CAST(:doc AS jsonb), "
                    "resolved_by='admin',resolved_at=:at WHERE game_id=:game AND id=:id"
                ),
                params,
            )
            self.session.execute(
                text(
                    "UPDATE recognized_boards SET status='rejected' WHERE game_id=:game AND "
                    "id=:board"
                ),
                {"game": game, "board": prior["recognized_board_id"]},
            )
        params = {
            "game": game,
            "ids": doc["source_ids"],
            "seq": doc["sequence_numbers"],
            "at": timestamp,
        }
        self.session.execute(
            text(
                "UPDATE image_board_geometry_pending SET status='superseded',superseded_at=:at "
                "WHERE game_id=:game AND source_image_id=ANY(CAST(:ids AS uuid[])) AND "
                "status='pending'"
            ),
            params,
        )
        self.session.execute(
            text(
                "DELETE FROM image_sequence_canonical WHERE game_id=:game AND "
                "sequence_number=ANY(CAST(:seq AS bigint[]))"
            ),
            params,
        )
        self.session.execute(
            text(
                "DELETE FROM image_layout_staging_rows WHERE game_id=:game AND review_item_id IN "
                "(SELECT r.id FROM image_review_items r JOIN recognized_boards b ON "
                "b.id=r.recognized_board_id AND b.game_id=r.game_id "
                "WHERE r.game_id=:game AND b.source_image_id=ANY(CAST(:ids AS uuid[])))"
            ),
            params,
        )
        for table in ("image_board_search_candidates", "image_board_search_fast_documents"):
            self.session.execute(
                text(
                    f"DELETE FROM {table} WHERE game_id=:game "
                    "AND sequence_number=ANY(CAST(:seq AS bigint[]))"
                ),
                params,
            )
        before = {str(job["id"]) for job in self._derive_jobs(game)}
        self._invalidate(game)
        self.session.flush()
        return [
            {
                "id": str(job["id"]),
                "digest": digest(job),
                "job": json.loads(json.dumps(job, default=str)),
                "payloadDigest": digest(job["input_payload"]),
            }
            for job in self._derive_jobs(game)
            if str(job["id"]) not in before
        ]

    def _invalidate(self, game: UUID) -> None:
        from game_predictor_api.storage.board_search_projection_repository import (
            SqlAlchemyBoardSearchProjectionRepository,
        )

        SqlAlchemyBoardSearchProjectionRepository(self.session).start_rebuild(game)
        self.session.execute(
            text(
                "UPDATE image_symbol_review_states SET catalog_revision=catalog_revision+1, "
                "count_projection_status='unavailable' "
                "WHERE game_id=:game"
            ),
            {"game": game},
        )
        record_super_game_input_change(self.session, game, source="source_replacement_retirement")

    def export_request(self, game: UUID, batch: UUID, entries: list[UUID]) -> dict[str, Any]:
        self.repo.bind(game)
        acquire_sequence_ownership_lock(self.session, game_id=game)
        selected = sorted(set(entries), key=str)
        if not 1 <= len(selected) <= 50:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_SCOPE_LIMIT", "Wybierz od 1 do 50 luk."
            )
        values = []
        ranges = []
        for entry in selected:
            row = self._entry(game, batch, entry)
            if row["phase"] != "gap_open":
                raise SourceReplacementError(
                    "SOURCE_REPLACEMENT_PHASE_CONFLICT",
                    "Eksport wymaga wyłącznie wybranych otwartych luk.",
                )
            doc = row["document"]
            values.append(
                {
                    "entryId": str(entry),
                    "revision": row["revision"],
                    "digest": scope_digest(doc),
                    "sourceSha256": doc["source_sha256"],
                    "sequenceNumbers": doc["sequence_numbers"],
                }
            )
            ranges.append(
                {
                    "entryId": str(entry),
                    "sequenceStart": doc["range_start"],
                    "sequenceEnd": doc["range_end"],
                }
            )
        payload = {
            "schemaVersion": "source-replacement-request-v1",
            "gameId": str(game),
            "batchId": str(batch),
            "entries": values,
            "allowedRanges": ranges,
        }
        return {**payload, "digest": digest(payload)}
