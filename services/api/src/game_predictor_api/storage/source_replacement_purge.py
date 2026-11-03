"""One confirmed photograph: remove its operational graph, never models/cohorts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.source_replacement_retirement import scope_digest
from game_predictor_api.domain.symbol_readability import digest
from game_predictor_api.storage.cleanup_repository import (
    SqlAlchemyCleanupRepository,
    _with_crop_siblings,
)
from game_predictor_api.storage.grid_reinference_retention import detach_grid_source_links
from game_predictor_api.storage.source_purge_retention import SourcePurgeRetention, lock_purge_games
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_api.storage.source_replacement_retirement import SourceRetirement

# Incoming FK classification is exercised against pg_constraint by the PG regression.
DELETE_TABLES = {
    "image_geometry_shadow_results",
    "board_render_manifests",
    "image_review_queue_items",
    "image_review_resolution_events",
    "image_symbol_review_events",
    "image_symbol_review_bulk_targets",
    "image_sequence_source_override_events",
    "image_board_geometry_revisions",
    "image_board_geometry_review_events",
    "image_board_geometry_pending",
    "image_layout_staging_rows",
    "image_symbol_prediction_revisions",
    "image_sequence_canonical",
    "image_board_search_candidates",
    "image_board_search_fast_documents",
    "image_symbol_review_cells",
    "image_review_items",
    "recognized_boards",
    "image_source_geometry_revisions",
}
DETACHED_TABLES = {
    "verified_training_cohort_items",
    "verified_training_cohort_cells",
    "symbol_reference_images",
}
EPHEMERAL_PARENTS = {
    "recognized_boards",
    "image_review_items",
    "image_symbol_review_cells",
    "image_source_geometry_revisions",
    "image_board_geometry_revisions",
    "image_symbol_prediction_revisions",
}


def fail(code: str, message: str) -> None:
    raise SourceReplacementError("SOURCE_REPLACEMENT_PURGE_" + code, message)


class SourcePurge:
    def __init__(
        self, repository: SourceReplacementRepository, cleanup: SqlAlchemyCleanupRepository
    ) -> None:
        self.repo, self.cleanup, self.session = repository, cleanup, repository.session

    def receipt(self, game: UUID, request: Any) -> dict[str, Any] | None:
        self.repo.bind(game, write=True)
        checksum = digest({"game": str(game), "command": request.model_dump(mode="json")})
        rows = self.repo.rows(
            "SELECT command_sha256,response FROM source_replacement_commands "
            "WHERE game_id=:game AND idempotency_key=:key",
            game=game,
            key=request.idempotency_key,
        )
        if not rows:
            return None
        if rows[0]["command_sha256"] != checksum:
            fail("IDEMPOTENCY_CONFLICT", "Klucz reprezentuje inne polecenie.")
        return rows[0]["response"]

    def prepare(
        self, game: UUID, request: Any
    ) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...], dict[str, int]]:
        lock_purge_games(self.session)
        self.repo.bind(game, write=True)
        retirement = SourceRetirement(self.repo)
        row = retirement._entry(game, request.batch_id, request.entry_id)
        retirement._planned(row, request.expected_revision)
        if row["document"].get("compact_schema") != "source-replacement-compact-v1":
            fail("LEGACY_PLAN", "Usuwanie wymaga nowego planu fizycznego usunięcia.")
        fresh = self.repo._preview(game, [UUID(str(row["source_id"]))])["entries"][0]
        retirement._exclude_proven_derivations(game, request.batch_id, fresh)
        if fresh["retired"]:
            fail("LEGACY_RETIRED", "Źródło już wycofano w trybie zachowania historii.")
        sources = [UUID(s) for s in fresh["source_ids"]]
        self._busy(game, sources)
        if fresh["blockers"]:
            fail("BLOCKED", ", ".join(fresh["blockers"]))
        if scope_digest(fresh) != scope_digest(row["document"]):
            fail("PLAN_DRIFT", "Źródło zmieniło się; zapisz nowy plan.")
        self._classified_fks()
        boards = tuple(UUID(str(b["id"])) for b in fresh["boards"])
        reviews = tuple(
            self.cleanup._ids(
                "SELECT id FROM image_review_items WHERE game_id=:game "
                "AND recognized_board_id IN :boards",
                game=game,
                boards=boards,
            )
        )
        source_rows = [
            (
                UUID(str(s["id"])),
                s["relative_path"],
                s["checksum_sha256"],
                s["file_execution_key"],
                UUID(str(s["import_job_id"])),
            )
            for s in fresh["sources"]
        ]
        paths = self.cleanup._board_source_artifact_paths(
            source_ids=tuple(sources),
            board_ids=boards,
            review_item_ids=reviews,
            cohort_ids=(),
            model_ids=(),
            release_ids=(),
            verified_export_ids=(),
            source_rows=source_rows,
        )
        # Reference images are independent catalog assets, not purge candidates.
        paths = _with_crop_siblings(paths)
        registry_paths = self.session.scalars(
            text(
                "SELECT p FROM public.source_image_crops c "
                "CROSS JOIN LATERAL "
                "unnest(ARRAY[c.crop_relative_path,c.attestation_relative_path]) p "
                "WHERE c.original_checksum_sha256 IN (SELECT checksum_sha256 FROM source_images "
                "WHERE game_id=:game AND id=ANY(CAST(:sources AS uuid[])))"
            ),
            {"game": game, "sources": sources},
        )
        paths = tuple(sorted(set(paths) | {str(path) for path in registry_paths if path}))
        params = {"game": game, "sources": sources}
        metadata = {
            "source_tombstones": len(sources),
            "grid_frozen_members": int(
                self.session.scalar(
                    text(
                        "SELECT count(*) FROM grid_training_cohort_members "
                        "WHERE game_id=:game AND source_id=ANY(CAST(:sources AS uuid[]))"
                    ),
                    params,
                )
                or 0
            ),
            "symbol_frozen_items": int(
                self.session.scalar(
                    text(
                        "SELECT count(*) FROM verified_training_cohort_items "
                        "WHERE game_id=:game AND source_image_id=ANY(CAST(:sources AS uuid[]))"
                    ),
                    params,
                )
                or 0
            ),
            "symbol_frozen_cells": int(
                self.session.scalar(
                    text(
                        "SELECT count(*) FROM verified_training_cohort_cells "
                        "WHERE game_id=:game AND source_image_id=ANY(CAST(:sources AS uuid[]))"
                    ),
                    params,
                )
                or 0
            ),
        }
        metadata["human_decisions"] = int(
            self.session.scalar(
                text("""SELECT count(*) FROM symbol_readability_decisions d
          WHERE d.game_id=:game AND d.cell_id IN(SELECT c.id FROM image_symbol_review_cells c
          JOIN recognized_boards b ON b.game_id=c.game_id AND b.id=c.recognized_board_id
          WHERE c.game_id=:game AND b.source_image_id=ANY(CAST(:sources AS uuid[])))"""),
                params,
            )
            or 0
        )
        fresh["_purge_cell_ids"] = list(
            self.session.scalars(
                text(
                    "SELECT c.id FROM image_symbol_review_cells c JOIN recognized_boards b "
                    "ON b.game_id=c.game_id AND b.id=c.recognized_board_id WHERE c.game_id=:game "
                    "AND b.source_image_id=ANY(CAST(:sources AS uuid[]))"
                ),
                params,
            )
        )
        return row, fresh, paths, metadata

    def shared(self, paths: tuple[str, ...], game: UUID, sources: list[UUID]) -> set[str]:
        with self.cleanup._cross_game_reader() as reader:
            return SourcePurgeRetention.retained(reader, paths, sources, game)

    def _classified_fks(self) -> None:
        rows = self.repo.rows(
            """SELECT child.relname AS child,c.conname FROM pg_constraint c
          JOIN pg_class child ON child.oid=c.conrelid JOIN pg_class parent ON parent.oid=c.confrelid
          JOIN pg_namespace n ON n.oid=parent.relnamespace
          WHERE c.contype='f' AND c.conparentid=0 AND n.nspname='game_data_v2'
          AND parent.relname=ANY(CAST(:parents AS text[]))""",
            parents=sorted(EPHEMERAL_PARENTS),
        )
        unknown = [
            r["child"]
            for r in rows
            if r["child"] not in DELETE_TABLES | DETACHED_TABLES | {"source_replacement_slots"}
        ]
        if unknown:
            fail(
                "DEPENDENCY_UNKNOWN",
                "Niesklasyfikowane powiązanie: " + ", ".join(sorted(set(unknown))),
            )

    def _busy(self, game: UUID, sources: list[UUID]) -> None:
        p = {"game": game, "sources": sources}
        checks = {
            "IMPORT_UNFINISHED": """SELECT EXISTS(SELECT 1 FROM public.jobs j WHERE
              j.status IN ('created','processing','waiting_for_review') AND (j.id IN
              (SELECT import_job_id FROM source_images WHERE game_id=:game AND
              id=ANY(CAST(:sources AS uuid[])))
              OR j.input_payload->>'managed_source_job_id' IN (SELECT import_job_id::text FROM
              source_images
                WHERE game_id=:game AND id=ANY(CAST(:sources AS uuid[])))))""",
            "MODEL_BUSY": """SELECT EXISTS(SELECT 1 FROM symbol_model_iterations m
              WHERE m.game_id=:game
              AND m.status NOT IN ('candidate_ready','rejected','failed','cancelled') AND
              m.cohort_id IN
              (SELECT cohort_id FROM verified_training_cohort_items WHERE game_id=:game
                AND source_image_id=ANY(CAST(:sources AS uuid[])) UNION SELECT cohort_id FROM
               verified_training_cohort_cells WHERE game_id=:game
               AND source_image_id=ANY(CAST(:sources AS uuid[]))))""",
            "REVIEW_BUSY": """SELECT EXISTS(SELECT 1 FROM reviewer_work_assignments a
              WHERE a.game_id=:game
              AND a.closed_at IS NULL AND a.lease_expires_at>now() AND a.import_job_id IN
              (SELECT import_job_id FROM source_images WHERE game_id=:game
               AND id=ANY(CAST(:sources AS uuid[]))))""",
            "GRID_BUSY": """SELECT EXISTS(SELECT 1 FROM public.jobs j WHERE j.game_id=:game
              AND j.status IN ('created','processing','waiting_for_review') AND j.job_type::text
              LIKE '%grid%'
              AND (EXISTS(SELECT 1 FROM unnest(CAST(:sources AS uuid[])) s WHERE
              position(s::text in j.input_payload::text)>0)
               OR EXISTS(SELECT 1 FROM grid_training_cohort_members m WHERE m.game_id=:game
                 AND m.source_id=ANY(CAST(:sources AS uuid[]))
                 AND position(m.cohort_id::text in j.input_payload::text)>0)))""",
        }
        for code, query in checks.items():
            if self.session.scalar(text(query), p):
                fail(
                    code,
                    "Źródło ma niezakończony import lub aktywnego konsumenta. "
                    "Zakończ wskazaną pracę przed usunięciem.",
                )

    def execute(
        self,
        game: UUID,
        request: Any,
        row: dict[str, Any],
        fresh: dict[str, Any],
        purge: dict[str, Any],
    ) -> dict[str, Any]:
        checksum = digest({"game": str(game), "command": request.model_dump(mode="json")})
        p = {
            "game": game,
            "sources": fresh["source_ids"],
            "seq": fresh["sequence_numbers"],
            "entry": request.entry_id,
            "batch": request.batch_id,
            "at": datetime.now(UTC),
        }
        for seq in p["seq"]:
            self.session.execute(
                text("""INSERT INTO source_replacement_slots
              (game_id,sequence_number,entry_id,batch_id,state,revision,document)
              VALUES(:game,:n,:entry,:batch,'reserved',1,CAST(:doc AS jsonb))"""),
                {
                    **p,
                    "n": seq,
                    "doc": json.dumps(
                        {
                            "sequenceNumber": seq,
                            "retirementCommandKey": str(request.idempotency_key),
                        }
                    ),
                },
            )
        for source in p["sources"]:
            self.session.execute(
                text("""INSERT INTO source_replacement_retired
              (game_id,source_id,entry_id,source_sha256,document)
              VALUES(:game,:source,:entry,:sha,CAST(:doc AS jsonb))"""),
                {
                    **p,
                    "source": source,
                    "sha": fresh["source_sha256"],
                    "doc": json.dumps(
                        {
                            "action": "source_replacement_purged",
                            "commandKey": str(request.idempotency_key),
                            "scopeDigest": scope_digest(row["document"]),
                            "prior": {"sequence_numbers": p["seq"]},
                        }
                    ),
                },
            )
        counts = self._delete_graph(game, [UUID(s) for s in p["sources"]])
        purge["deletedRecords"] = counts
        doc = {**row["document"], "purge": purge}
        self.session.execute(
            text("""UPDATE source_replacement_entries SET phase='gap_open',revision=revision+1,
          document=CAST(:doc AS jsonb) WHERE game_id=:game AND id=:entry"""),
            {**p, "doc": json.dumps(doc)},
        )
        self.session.execute(
            text(
                "UPDATE source_replacement_batches SET status='gap_open',revision=revision+1 "
                "WHERE game_id=:game AND id=:batch"
            ),
            p,
        )
        retirement = SourceRetirement(self.repo)
        before = {str(j["id"]) for j in retirement._derive_jobs(game)}
        retirement._invalidate(game)
        self.session.flush()
        derivations = [
            {
                "id": str(j["id"]),
                "digest": digest(j),
                "payloadDigest": digest(j["input_payload"]),
                "job": json.loads(json.dumps(j, default=str)),
            }
            for j in retirement._derive_jobs(game)
            if str(j["id"]) not in before
        ]
        result = {
            "game_id": str(game),
            "batch_id": str(request.batch_id),
            "entry_id": str(request.entry_id),
            "revision": row["revision"] + 1,
            "phase": "gap_open",
            "scope_digest": scope_digest(row["document"]),
            "createdDerivations": derivations,
            "purge": purge,
        }
        self.session.execute(
            text("""INSERT INTO source_replacement_commands
          (game_id,idempotency_key,command_sha256,batch_id,response)
          VALUES(:game,:key,:sha,:batch,CAST(:doc AS jsonb))"""),
            {**p, "key": request.idempotency_key, "sha": checksum, "doc": json.dumps(result)},
        )
        return result

    def _delete_graph(self, game: UUID, sources: list[UUID]) -> dict[str, int]:
        p: dict[str, Any] = {"game": game, "sources": sources}
        for name, query in {
            "boards": "SELECT id FROM recognized_boards WHERE game_id=:game AND "
            "source_image_id=ANY(CAST(:sources AS uuid[]))",
            "reviews": "SELECT id FROM image_review_items WHERE game_id=:game "
            "AND recognized_board_id=ANY(CAST(:boards AS uuid[]))",
            "cells": "SELECT id FROM image_symbol_review_cells WHERE "
            "game_id=:game AND review_item_id=ANY(CAST(:reviews AS uuid[]))",
        }.items():
            p[name] = list(self.session.scalars(text(query), p))
        detach_grid_source_links(self.session, game, sources)
        self.session.execute(
            text(
                "UPDATE image_symbol_review_cells SET prediction_revision_id=NULL "
                "WHERE game_id=:game AND id=ANY(CAST(:cells AS uuid[]))"
            ),
            p,
        )
        counts: dict[str, int] = {}
        order = [
            ("image_sequence_canonical", "source_image_id", "sources"),
            ("image_board_search_candidates", "recognized_board_id", "boards"),
            ("image_board_search_fast_documents", "recognized_board_id", "boards"),
            ("image_symbol_review_bulk_targets", "cell_review_id", "cells"),
            ("image_symbol_review_events", "cell_review_id", "cells"),
            ("image_symbol_prediction_revisions", "review_item_id", "reviews"),
            ("image_sequence_source_override_events", "selected_review_item_id", "reviews"),
            ("image_layout_staging_rows", "review_item_id", "reviews"),
            ("image_review_resolution_events", "review_item_id", "reviews"),
            ("image_board_geometry_review_events", "recognized_board_id", "boards"),
            ("image_board_geometry_revisions", "recognized_board_id", "boards"),
            ("image_board_geometry_pending", "source_image_id", "sources"),
            ("image_symbol_review_cells", "id", "cells"),
            ("image_review_items", "id", "reviews"),
            ("board_render_manifests", "recognized_board_id", "boards"),
            ("recognized_boards", "id", "boards"),
            ("image_geometry_shadow_results", "source_image_id", "sources"),
            ("image_source_geometry_revisions", "source_image_id", "sources"),
        ]
        for table, column, key in order:
            result = self.session.execute(
                text(
                    f"DELETE FROM {table} WHERE game_id=:game "
                    f"AND {column}=ANY(CAST(:{key} AS uuid[]))"
                ),
                p,
            )
            counts[table] = result.rowcount
        # image_review_queue_items follows review DELETE through the existing
        # projection trigger; its counters must not be reset game-wide.
        self.session.execute(
            text(
                "UPDATE image_geometry_rollout_states SET last_source_image_id=NULL "
                "WHERE game_id=:game AND last_source_image_id=ANY(CAST(:sources AS uuid[]))"
            ),
            p,
        )
        self.session.execute(
            text(
                "UPDATE source_images SET purged_at=now(),status='rejected' "
                "WHERE game_id=:game AND id=ANY(CAST(:sources AS uuid[]))"
            ),
            p,
        )
        for table in ("image_page_geometry_overrides", "image_sequence_alternatives"):
            result = self.session.execute(
                text(
                    f"DELETE FROM {table} WHERE game_id=:game "
                    "AND source_checksum_sha256 IN (SELECT checksum_sha256 FROM source_images "
                    "WHERE game_id=:game AND id=ANY(CAST(:sources AS uuid[])))"
                ),
                p,
            )
            counts[table] = result.rowcount
        # Keep the small execution identity required by source tombstones. Remove
        # checkpoints only when no other live photo in any routed game uses them.
        keys = list(
            self.session.scalars(
                text(
                    "SELECT DISTINCT file_execution_key FROM source_images "
                    "WHERE game_id=:game AND id=ANY(CAST(:sources AS uuid[])) "
                    "AND file_execution_key IS NOT NULL"
                ),
                p,
            )
        )
        with self.cleanup._cross_game_reader() as reader:
            shared = set(
                reader.scalars(
                    text(
                        "SELECT file_execution_key FROM game_data_v2.source_images "
                        "WHERE purged_at IS NULL AND NOT(game_id=:game AND "
                        "id=ANY(CAST(:sources AS uuid[]))) "
                        "AND file_execution_key=ANY(CAST(:keys AS text[]))"
                    ),
                    {**p, "keys": keys},
                )
            )
            live_shas = set(
                reader.scalars(
                    text(
                        "SELECT DISTINCT checksum_sha256 FROM game_data_v2.source_images "
                        "WHERE purged_at IS NULL AND NOT(game_id=:game AND "
                        "id=ANY(CAST(:sources AS uuid[]))) "
                        "AND checksum_sha256 IN (SELECT checksum_sha256 FROM "
                        "game_data_v2.source_images "
                        "WHERE game_id=:game AND id=ANY(CAST(:sources AS uuid[])))"
                    ),
                    p,
                )
            )
        result = self.session.execute(
            text(
                "DELETE FROM public.source_image_crops WHERE original_checksum_sha256 IN "
                "(SELECT checksum_sha256 FROM source_images WHERE game_id=:game "
                "AND id=ANY(CAST(:sources AS uuid[]))) "
                "AND NOT(original_checksum_sha256=ANY(CAST(:live AS text[])))"
            ),
            {**p, "live": list(live_shas)},
        )
        counts["source_image_crops"] = result.rowcount
        unused = [key for key in keys if key not in shared]
        for table in ("image_pipeline_stage_results", "image_pipeline_terminal_manifests"):
            result = self.session.execute(
                text(f"DELETE FROM {table} WHERE file_execution_key=ANY(CAST(:keys AS text[]))"),
                {"keys": unused},
            )
            counts[table] = result.rowcount
        return counts
