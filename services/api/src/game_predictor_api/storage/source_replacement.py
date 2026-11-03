"Bounded exact source snapshots and transactional planned manifests; no retirement."

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.source_replacement import (
    SourceReplacementError,
    preview_document,
    qualification,
)
from game_predictor_api.domain.symbol_readability import digest, identity_is_current
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.symbol_readability import SNAPSHOT_SQL


class SourceReplacementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bind(self, game: UUID, *, write: bool = False) -> None:
        GameStorageRouter().bind(
            self.session,
            game,
            intent=(GameStorageIntent.WRITE if write else GameStorageIntent.READ),
        )
        self.session.execute(text("SET LOCAL statement_timeout='30s'"))
        self.session.execute(text("SET LOCAL lock_timeout='5s'"))

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in self.session.execute(text(sql), params).mappings()]

    def documents(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        rows = self.rows(sql + " LIMIT 10001", **params)
        if len(rows) > 10000:
            raise SourceReplacementError("SOURCE_REPLACEMENT_SCOPE_LIMIT", "Wybierz mniej źródeł.")
        return [row["document"] for row in rows]

    def candidates(self, game: UUID, offset: int) -> dict[str, Any]:
        self.bind(game)
        sources = self.rows(
            (
                """
SELECT s.id, s.checksum_sha256, s.relative_path,
min(b.sequence_number) AS first_sequence, max(b.sequence_number) AS
last_sequence           FROM source_images s JOIN recognized_boards b ON
b.source_image_id=s.id AND b.game_id=s.game_id WHERE s.game_id=:game AND
EXISTS(SELECT 1 FROM image_symbol_review_cells c WHERE c.game_id=s.game_id
AND c.recognized_board_id=b.id AND (c.quality_issue='unreadable' OR
EXISTS(SELECT 1 FROM symbol_readability_items i WHERE i.game_id=c.game_id
AND i.cell_id=c.id AND i.ever_labelled AND i.state='unreadable')))
GROUP BY s.id, s.checksum_sha256, s.relative_path ORDER BY s.id LIMIT 51
OFFSET :offset
"""
            ),
            game=game,
            offset=offset,
        )
        return {"items": sources[:50], "next_offset": offset + 50 if len(sources) > 50 else None}

    def preview(self, game: UUID, sources: list[UUID]) -> dict[str, Any]:
        self.bind(game)
        # Quality labels, geometry and ownership share this snapshot lock.
        acquire_sequence_ownership_lock(self.session, game_id=game)
        return self._preview(game, sources)

    def _preview(self, game: UUID, sources: list[UUID]) -> dict[str, Any]:
        selected = sorted(set(str(value) for value in sources))
        facts = self.documents(
            """
SELECT to_jsonb(s) AS document FROM source_images s           WHERE
s.game_id=:game AND s.id=ANY(CAST(:ids AS uuid[])) ORDER BY s.id
""",
            game=game,
            ids=selected,
        )
        if len(facts) != len(selected):
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_SOURCE_NOT_FOUND", "Nie znaleziono źródła tej gry."
            )
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for source in facts:
            if source["id"] in seen:
                continue
            entry = self._entry(game, source)
            seen.update(entry["source_ids"])
            entries.append(entry)
        entries.sort(key=lambda item: item["source_ids"][0])
        return preview_document(str(game), selected, entries)

    def _entry(self, game: UUID, source: dict[str, Any]) -> dict[str, Any]:
        # Every historical atestation is considered. Conflicting ranges fail closed.
        revisions = self.documents(
            (
                """
SELECT to_jsonb(r) AS document           FROM
image_source_geometry_revisions r JOIN source_images s           ON
s.game_id=r.game_id AND s.id=r.source_image_id WHERE r.game_id=:game AND
s.checksum_sha256=:sha ORDER BY r.source_image_id, r.revision
"""
            ),
            game=game,
            sha=source["checksum_sha256"],
        )
        own = [r for r in revisions if r["source_image_id"] == source["id"]]
        ranges = {(r["sequence_range_start"], r["sequence_range_end"]) for r in own}
        blockers: set[str] = set()
        scope = next(iter(ranges)) if len(ranges) == 1 else None
        if (
            scope is None
            or not own
            or any(not r["sequence_attestation_checksum_sha256"] for r in own)
        ):
            blockers.add("SOURCE_REPLACEMENT_RANGE_AMBIGUOUS")
        aliases = {source["id"]}
        if scope is not None:
            for revision in revisions:
                if (revision["sequence_range_start"], revision["sequence_range_end"]) == scope:
                    aliases.add(revision["source_image_id"])
            for alias in aliases:
                alias_revs = [r for r in revisions if r["source_image_id"] == alias]
                if any(
                    (r["sequence_range_start"], r["sequence_range_end"]) != scope
                    or not r["sequence_attestation_checksum_sha256"]
                    for r in alias_revs
                ):
                    blockers.add("SOURCE_REPLACEMENT_RANGE_AMBIGUOUS")
        ids = sorted(aliases)
        sources = self.documents(
            """
SELECT to_jsonb(s) AS document FROM source_images s           WHERE
s.game_id=:game AND s.id=ANY(CAST(:ids AS uuid[])) ORDER BY s.id
""",
            game=game,
            ids=ids,
        )
        if len(ids) > 100:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_SCOPE_LIMIT", "Zbyt wiele aliasów zdjęcia."
            )
        boards = self.documents(
            (
                """
SELECT to_jsonb(b) || jsonb_build_object(           'review_id', r.id,
'review_status', r.status, 'resolution_revision', r.resolution_revision,
'resolved_value', r.resolved_value) AS document FROM recognized_boards b
LEFT JOIN image_review_items r ON r.game_id=b.game_id AND
r.recognized_board_id=b.id WHERE b.game_id=:game AND
b.source_image_id=ANY(CAST(:ids AS uuid[])) ORDER BY b.sequence_number,
b.id, r.id
"""
            ),
            game=game,
            ids=ids,
        )
        slots = self.documents(
            (
                """
SELECT to_jsonb(p) AS document FROM image_board_geometry_pending p
WHERE p.game_id=:game AND p.source_image_id=ANY(CAST(:ids AS uuid[])) ORDER
BY p.id
"""
            ),
            game=game,
            ids=ids,
        )
        numbers = sorted(
            {b["sequence_number"] for b in [*boards, *slots] if b["sequence_number"] is not None}
        )
        if scope is not None and 0 < scope[1] - scope[0] + 1 <= 9:
            numbers = sorted(set(numbers) | set(range(scope[0], scope[1] + 1)))
            if any(number < scope[0] or number > scope[1] for number in numbers):
                blockers.add("SOURCE_REPLACEMENT_RANGE_AMBIGUOUS")
        else:
            blockers.add("SOURCE_REPLACEMENT_RANGE_AMBIGUOUS")
        if any(b["sequence_number"] is None for b in boards):
            blockers.add("SOURCE_REPLACEMENT_SEQUENCE_UNKNOWN")
        canonical = self.documents(
            (
                """
SELECT to_jsonb(c) AS document FROM image_sequence_canonical c
WHERE c.game_id=:game AND c.sequence_number=ANY(CAST(:seq AS bigint[]))
ORDER BY c.sequence_number
"""
            ),
            game=game,
            seq=numbers,
        )
        pending = self.documents(
            (
                """
SELECT to_jsonb(r) || jsonb_build_object('source_id', b.source_image_id) AS
document FROM image_review_items r JOIN recognized_boards b ON
b.game_id=r.game_id AND b.id=r.recognized_board_id           WHERE
r.game_id=:game AND r.status='pending' AND r.sequence_number=ANY(CAST(:seq
AS bigint[])) ORDER BY r.id
"""
            ),
            game=game,
            seq=numbers,
        )
        pending_geometry = self.documents(
            "SELECT to_jsonb(p) AS document FROM image_board_geometry_pending p "
            "WHERE p.game_id=:game AND p.status='pending' "
            "AND p.sequence_number=ANY(CAST(:seq AS bigint[])) ORDER BY p.id",
            game=game,
            seq=numbers,
        )
        foreign_pending = [r for r in pending if r["source_id"] not in aliases]
        foreign_pending.extend(r for r in pending_geometry if r["source_image_id"] not in aliases)
        if foreign_pending:
            blockers.add("SOURCE_REPLACEMENT_SLOT_PENDING_CONFLICT")
        if any(c["source_image_id"] not in aliases for c in canonical):
            blockers.add("SOURCE_REPLACEMENT_SLOT_OWNER_CONFLICT")
        reservations = self.documents(
            (
                """
SELECT to_jsonb(r) AS document FROM source_replacement_slots r
WHERE r.game_id=:game AND r.sequence_number=ANY(CAST(:seq AS bigint[]))
ORDER BY r.sequence_number
"""
            ),
            game=game,
            seq=numbers,
        )
        retired = self.documents(
            (
                """
SELECT to_jsonb(r) AS document FROM source_replacement_retired r
WHERE r.game_id=:game AND r.source_id=ANY(CAST(:ids AS uuid[])) ORDER BY
r.source_id
"""
            ),
            game=game,
            ids=ids,
        )
        if reservations or retired:
            blockers.add("SOURCE_REPLACEMENT_ALREADY_RESERVED_OR_RETIRED")
        current_ids = {c["review_item_id"] for c in canonical} | {
            r["id"]
            for r in pending
            if not any(c["sequence_number"] == r["sequence_number"] for c in canonical)
        }
        cells = self.rows(
            SNAPSHOT_SQL + " AND s.id=ANY(CAST(:ids AS uuid[])) ORDER BY c.id LIMIT 10001",
            game=game,
            ids=ids,
        )
        if len(cells) > 10000:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_SCOPE_LIMIT", "Zbyt wiele pól zdjęcia."
            )
        cell_ids = [cell["snapshot"]["cell_id"] for cell in cells]
        decisions_all = self.rows(
            (
                """
SELECT cell_id, ordinal, idempotency_key, run_id, item_revision, identity,
state, overlap, snapshot->'prior_quality_judgment' AS prior_quality_judgment
FROM symbol_readability_decisions WHERE
game_id=:game AND cell_id=ANY(CAST(:cells AS uuid[]))           ORDER BY
cell_id, ordinal LIMIT 10001
"""
            ),
            game=game,
            cells=cell_ids,
        )
        legacy_all = self.rows(
            (
                """
SELECT cell_id, run_id, revision, identity, state, overlap, ever_labelled
FROM symbol_readability_items WHERE game_id=:game AND
cell_id=ANY(CAST(:cells AS uuid[])) AND ever_labelled ORDER BY cell_id,
run_id LIMIT 10001
"""
            ),
            game=game,
            cells=cell_ids,
        )
        if len(decisions_all) > 10000 or len(legacy_all) > 10000:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_SCOPE_LIMIT", "Zbyt wiele ocen historycznych."
            )
        reasons = []
        evidence = []
        for cell in cells:
            snapshot = cell["snapshot"]
            if snapshot["review_item_id"] not in current_ids:
                continue
            if not identity_is_current(snapshot, snapshot):
                blockers.add("SOURCE_REPLACEMENT_CROP_STALE")
                continue
            decisions = [row for row in decisions_all if str(row["cell_id"]) == snapshot["cell_id"]]
            legacy = [row for row in legacy_all if str(row["cell_id"]) == snapshot["cell_id"]]
            result = qualification(snapshot, decisions, legacy)
            proof = {
                "cell_id": snapshot["cell_id"],
                "sequence_number": snapshot["sequence_number"],
                "cell_index": snapshot["cell_index"],
                "cell_revision": snapshot["revision"],
                "snapshot": snapshot,
                **result,
            }
            evidence.append(proof)
            if result["blocker"]:
                blockers.add(result["blocker"])
            if result["state"] == "unreadable" and not result["blocker"]:
                reasons.append(proof)
        if not reasons:
            blockers.add("SOURCE_REPLACEMENT_NO_CONFIRMED_REASON")
        dependencies = self._dependencies(game, ids)
        dependencies["pending_geometry"] = pending_geometry
        if dependencies["active_jobs"]:
            blockers.add("SOURCE_REPLACEMENT_ACTIVE_JOB")
        return {
            "source_ids": ids,
            "source_sha256": source["checksum_sha256"],
            "sources": sources,
            "range_start": scope[0] if scope else None,
            "range_end": scope[1] if scope else None,
            "sequence_numbers": numbers,
            "geometry_revisions": [r for r in revisions if r["source_image_id"] in aliases],
            "boards": boards,
            "pending_slots": slots,
            "canonical": canonical,
            "pending": pending,
            "reservations": reservations,
            "retired": retired,
            "evidence": evidence,
            "reasons": reasons,
            "dependencies": dependencies,
            "blockers": sorted(blockers),
        }

    def _dependencies(self, game: UUID, ids: list[str]) -> dict[str, Any]:
        queries = {
            "grid_cohorts": (
                """
SELECT to_jsonb(m) AS document FROM grid_training_cohort_members m WHERE
m.game_id=:game AND m.source_id=ANY(CAST(:ids AS uuid[])) ORDER BY
m.cohort_id, m.source_id
"""
            ),
            "symbol_cohorts": (
                """
SELECT to_jsonb(m) AS document FROM verified_training_cohort_items m WHERE
m.game_id=:game AND m.source_image_id=ANY(CAST(:ids AS uuid[])) ORDER BY
m.id
"""
            ),
            "active_jobs": (
                """
SELECT jsonb_build_object('id', j.id, 'status', j.status, 'job_type',
j.job_type) AS document FROM public.jobs j WHERE j.game_id=:game AND
j.status IN ('created', 'processing') ORDER BY j.id
"""
            ),
            "model_activations": (
                """
SELECT to_jsonb(m) AS document FROM game_symbol_model_activations m WHERE
m.game_id=:game ORDER BY m.id
"""
            ),
            "releases": (
                """
SELECT to_jsonb(m) AS document FROM mobile_release_games m WHERE
m.game_id=:game ORDER BY m.mobile_release_id
"""
            ),
        }
        return {name: self.documents(sql, game=game, ids=ids) for name, sql in queries.items()}

    def create(self, game: UUID, request: Any) -> dict[str, Any]:
        self.bind(game, write=True)
        acquire_sequence_ownership_lock(self.session, game_id=game)
        sha = digest(request.model_dump(mode="json"))
        prior = self.rows(
            (
                """
SELECT * FROM source_replacement_commands WHERE game_id=:game AND
idempotency_key=:key
"""
            ),
            game=game,
            key=request.idempotency_key,
        )
        if prior:
            if prior[0]["command_sha256"] != sha:
                raise SourceReplacementError(
                    "SOURCE_REPLACEMENT_IDEMPOTENCY_CONFLICT", "Klucz reprezentuje inne polecenie."
                )
            return dict(prior[0]["response"])
        if request.expected_revision != 0:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_REVISION_CONFLICT", "Nowy plan wymaga rewizji zero."
            )
        preview = self._preview(game, request.source_ids)
        if preview["preview_token"] != request.preview_token:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_PREVIEW_STALE", "Stan zmienił się. Odśwież podgląd."
            )
        if any(entry["blockers"] for entry in preview["entries"]):
            raise SourceReplacementError("SOURCE_REPLACEMENT_BLOCKED", "Podgląd zawiera blokery.")
        identifier = uuid4()
        document = {**preview, "id": str(identifier), "status": "planned", "revision": 1}
        document["entries"] = [
            {**entry, "id": str(uuid4()), "phase": "planned", "revision": 1}
            for entry in preview["entries"]
        ]
        # Convert UUID values from proof rows to an identical restart-safe representation.
        document = dict(json.loads(json.dumps(document, default=str)))
        self.session.execute(
            text(
                """
INSERT INTO source_replacement_batches(game_id, id, revision, status,
preview_token, document)           VALUES(:game, :id, 1, 'planned', :token,
CAST(:doc AS jsonb))
"""
            ),
            {
                "game": game,
                "id": identifier,
                "token": request.preview_token,
                "doc": json.dumps(document),
            },
        )
        for entry in document["entries"]:
            self.session.execute(
                text(
                    """
INSERT INTO source_replacement_entries(game_id, id, batch_id, source_id,
source_sha256, document)               VALUES(:game, :id, :batch, :source,
:sha, CAST(:doc AS jsonb))
"""
                ),
                {
                    "game": game,
                    "id": entry["id"],
                    "batch": identifier,
                    "source": entry["source_ids"][0],
                    "sha": entry["source_sha256"],
                    "doc": json.dumps(entry),
                },
            )
            for source_id in entry["source_ids"]:
                self.session.execute(
                    text("""
INSERT INTO source_replacement_sources                   (game_id, entry_id,
source_id) VALUES(:game, :entry, :source)
"""),
                    {"game": game, "entry": entry["id"], "source": source_id},
                )
        self.session.execute(
            text(
                """
INSERT INTO source_replacement_commands(game_id, idempotency_key,
command_sha256, batch_id, response)           VALUES(:game, :key, :sha,
:batch, CAST(:doc AS jsonb))
"""
            ),
            {
                "game": game,
                "key": request.idempotency_key,
                "sha": sha,
                "batch": identifier,
                "doc": json.dumps(document),
            },
        )
        return document

    def get(self, game: UUID, batch: UUID) -> dict[str, Any]:
        self.bind(game)
        rows = self.rows(
            """
SELECT document FROM source_replacement_batches WHERE game_id=:game AND
id=:id
""",
            game=game,
            id=batch,
        )
        if not rows:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_NOT_FOUND", "Nie znaleziono planu tej gry."
            )
        return dict(rows[0]["document"])

    def list(self, game: UUID) -> list[dict[str, Any]]:
        self.bind(game)
        return self.rows(
            (
                """
SELECT id, revision, status, preview_token, created_at FROM
source_replacement_batches WHERE game_id=:game ORDER BY created_at DESC, id
DESC LIMIT 100
"""
            ),
            game=game,
        )
