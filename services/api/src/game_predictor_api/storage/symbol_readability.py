"""Routed durable quality workflow; each request commits its command receipt atomically."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.symbol_readability import (
    GAME_ID,
    ReadabilityWorkflowError,
    digest,
    identity_is_current,
)
from game_predictor_api.schemas.symbol_readability import (
    ReadabilityCommandRequest,
    ReadabilityLabelRequest,
    ReadabilityStartRequest,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock

SNAPSHOT_SQL = """SELECT to_jsonb(c) || jsonb_build_object(
  'cell_id',c.id,'source_id',s.id,'source_sha256',s.checksum_sha256,
'source_path',s.relative_path,'normalized_pixel_checksum_sha256',s.normalized_pixel_checksum_sha256,
  'board_geometry_revision',b.geometry_revision,
  'board_source_geometry_revision_id',b.source_geometry_revision_id,
  'board_status',r.status,'symbol_class',COALESCE(sym.code,c.prediction_symbol_code,'unknown'))
AS snapshot
 FROM image_symbol_review_cells c
 JOIN recognized_boards b ON b.id=c.recognized_board_id AND b.game_id=c.game_id
 JOIN image_review_items r ON r.id=c.review_item_id AND r.game_id=c.game_id
 JOIN source_images s ON s.id=b.source_image_id AND s.game_id=c.game_id
 LEFT JOIN public.symbols sym ON sym.id=c.assigned_symbol_id AND sym.game_id=c.game_id
 WHERE c.game_id=:game AND r.status<>'rejected' """


class SqlAlchemyReadabilityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def acquire_write_lock(self, game: UUID) -> None:
        acquire_sequence_ownership_lock(self.session, game_id=game)

    def bind(self, game_id: UUID, *, write: bool = False) -> None:
        if game_id != GAME_ID:
            raise ReadabilityWorkflowError(
                "READABILITY_GAME_UNSUPPORTED", "Detektor dotyczy wyłącznie 777a2."
            )
        GameStorageRouter().bind(
            self.session,
            game_id,
            intent=GameStorageIntent.WRITE if write else GameStorageIntent.READ,
        )
        self.session.execute(text("SET LOCAL statement_timeout='30s'"))

    def row(
        self, table: str, game: UUID, identifier: UUID, *, lock: bool = False
    ) -> dict[str, Any]:
        if table not in {"runs", "models"}:
            raise ValueError(table)
        value = (
            self.session.execute(
                text(
                    f"SELECT * FROM symbol_readability_{table} "
                    "WHERE game_id=:game AND id=:id" + (" FOR UPDATE" if lock else "")
                ),
                {"game": game, "id": identifier},
            )
            .mappings()
            .first()
        )
        if value is None:
            raise ReadabilityWorkflowError(
                "READABILITY_NOT_FOUND", "Nie znaleziono operacji jakości."
            )
        return dict(value)

    @staticmethod
    def public_run(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: row[key]
            for key in (
                "id",
                "kind",
                "status",
                "revision",
                "job_id",
                "model_id",
                "inventory_fingerprint",
                "item_count",
                "processed_count",
                "error_code",
                "error_message",
            )
        }

    @staticmethod
    def public_model(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: row[key]
            for key in (
                "id",
                "pilot_run_id",
                "status",
                "revision",
                "job_id",
                "fingerprint",
                "report",
                "accepted",
                "error_code",
                "error_message",
            )
        }

    def workspace(self, game: UUID) -> dict[str, Any]:
        self.bind(game)
        return {
            "runs": [
                self.public_run(dict(r))
                for r in self.session.execute(
                    text(
                        "SELECT * FROM symbol_readability_runs WHERE game_id=:game ORDER BY "
                        "created_at DESC,id DESC LIMIT 100"
                    ),
                    {"game": game},
                ).mappings()
            ],
            "models": [
                self.public_model(dict(r))
                for r in self.session.execute(
                    text(
                        "SELECT * FROM symbol_readability_models WHERE game_id=:game ORDER "
                        "BY id DESC LIMIT 100"
                    ),
                    {"game": game},
                ).mappings()
            ],
        }

    def command(
        self, game: UUID, key: UUID, body: object, action: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        self.bind(game, write=True)
        self.acquire_write_lock(game)
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"readability:{game}:{key}"},
        )
        prior = (
            self.session.execute(
                text(
                    "SELECT * FROM symbol_readability_commands WHERE game_id=:game AND "
                    "idempotency_key=:key"
                ),
                {"game": game, "key": key},
            )
            .mappings()
            .first()
        )
        sha = digest(body)
        if prior is not None:
            if prior["command_sha256"] != sha:
                raise ReadabilityWorkflowError(
                    "READABILITY_IDEMPOTENCY_CONFLICT", "Klucz reprezentuje inne polecenie."
                )
            return dict(prior["response"]["result"])
        response = action()
        self.session.execute(
            text(
                "INSERT INTO "
                "symbol_readability_commands(game_id,idempotency_key,command_sha256,r"
                "esponse) "
                "VALUES(:game,:key,:sha,CAST(:response AS jsonb))"
            ),
            {
                "game": game,
                "key": key,
                "sha": sha,
                "response": json.dumps({"result": response, "command": body}, default=str),
            },
        )
        return response

    def start(self, game: UUID, request: ReadabilityStartRequest) -> dict[str, Any]:
        def execute() -> dict[str, Any]:
            if request.kind == "scan":
                if request.model_id is None:
                    raise ReadabilityWorkflowError(
                        "READABILITY_MODEL_REQUIRED", "Skan wymaga odebranego modelu."
                    )
                model = self.row("models", game, request.model_id, lock=True)
                pilot = self.row("runs", game, model["pilot_run_id"], lock=True)
                self._require_pilot_current(game, pilot["id"])
                if (
                    not model["accepted"]
                    or model["report"].get("status") != "PASS"
                    or model["report"].get("fullScanAllowed") is not True
                    or pilot["revision"] != model["pilot_revision"]
                ):
                    raise ReadabilityWorkflowError(
                        "READABILITY_ACCEPTANCE_REQUIRED", "Wymagane PASS i aktualny odbiór modelu."
                    )
            elif request.model_id is not None:
                raise ReadabilityWorkflowError(
                    "READABILITY_MODEL_UNEXPECTED", "Pilot nie wymaga detektora."
                )
            identifier = uuid4()
            job = self.new_job(game, "prepare" if request.kind == "pilot" else "scan", identifier)
            self.session.execute(
                text(
                    "INSERT INTO "
                    "symbol_readability_runs(game_id,id,kind,status,job_id,model_id,seed)"
                    " "
                    "VALUES(:game,:id,:kind,'created',:job,:model,:seed)"
                ),
                {
                    "game": game,
                    "id": identifier,
                    "kind": request.kind,
                    "job": job,
                    "model": request.model_id,
                    "seed": request.seed,
                },
            )
            return self.public_run(self.row("runs", game, identifier))

        return self.command(
            game, request.idempotency_key, {"start": request.model_dump(mode="json")}, execute
        )

    def new_job(self, game: UUID, action: str, identifier: UUID) -> UUID:
        job = SqlAlchemyJobRepository(self.session).add_job(
            create_job(
                JobType.SYMBOL_READABILITY,
                game_id=game,
                input_payload={
                    "schema_version": 1,
                    "workflow": "symbol_readability",
                    "action": action,
                    "identifier": str(identifier),
                },
            )
        )
        return job.id

    def fit(self, game: UUID, run_id: UUID, request: ReadabilityCommandRequest) -> dict[str, Any]:
        def execute() -> dict[str, Any]:
            run = self.row("runs", game, run_id, lock=True)
            self._revision(run, request.expected_revision)
            if run["kind"] != "pilot" or run["status"] != "completed":
                raise ReadabilityWorkflowError(
                    "READABILITY_PILOT_NOT_READY", "Najpierw przygotuj i oznacz pilot."
                )
            rows = (
                self.session.execute(
                    text(
                        "SELECT * FROM symbol_readability_items WHERE game_id=:game AND "
                        "run_id=:run ORDER BY cell_id"
                    ),
                    {"game": game, "run": run_id},
                )
                .mappings()
                .all()
            )
            if len(rows) != 800 or any(
                not r["processed"] or r["state"] in {"skipped", "error", "stale"} for r in rows
            ):
                raise ReadabilityWorkflowError(
                    "READABILITY_PILOT_STOP", "Wymagane 600 poprawnych pól pilota i 200 pól audytu."
                )
            self._refresh_stale(game, run_id)
            if self.session.scalar(
                text(
                    "SELECT count(*) FROM symbol_readability_items WHERE game_id=:game "
                    "AND run_id=:run AND state='stale'"
                ),
                {"game": game, "run": run_id},
            ):
                raise ReadabilityWorkflowError(
                    "READABILITY_CROP_STALE", "Piksele pilota zmieniły się; przygotuj nowy pilot."
                )
            identifier = uuid4()
            job = self.new_job(game, "fit", identifier)
            self.session.execute(
                text(
                    "INSERT INTO "
                    "symbol_readability_models(game_id,id,pilot_run_id,pilot_revision,job"
                    "_id,status) "
                    "VALUES(:game,:id,:run,:revision,:job,'created')"
                ),
                {
                    "game": game,
                    "id": identifier,
                    "run": run_id,
                    "revision": run["revision"],
                    "job": job,
                },
            )
            return self.public_model(self.row("models", game, identifier))

        return self.command(
            game,
            request.idempotency_key,
            {"fit": str(run_id), **request.model_dump(mode="json")},
            execute,
        )

    def accept(
        self, game: UUID, model_id: UUID, request: ReadabilityCommandRequest
    ) -> dict[str, Any]:
        def execute() -> dict[str, Any]:
            model = self.row("models", game, model_id, lock=True)
            self._revision(model, request.expected_revision)
            run = self.row("runs", game, model["pilot_run_id"], lock=True)
            if (
                model["status"] != "completed"
                or not model["fingerprint"]
                or not model["artifact_path"]
                or model["report"].get("status") != "PASS"
                or model["pilot_revision"] != run["revision"]
            ):
                raise ReadabilityWorkflowError(
                    "READABILITY_GATE_REQUIRED", "Model nie ma aktualnego PASS pilota."
                )
            self._refresh_stale(game, run["id"])
            if self.session.scalar(
                text(
                    "SELECT count(*) FROM symbol_readability_items WHERE game_id=:game "
                    "AND run_id=:run AND state='stale'"
                ),
                {"game": game, "run": run["id"]},
            ):
                raise ReadabilityWorkflowError("READABILITY_CROP_STALE", "Pilot zmienił piksele.")
            self.session.execute(
                text(
                    "UPDATE symbol_readability_models SET "
                    "accepted=true,revision=revision+1, "
                    "report=report || jsonb_build_object("
                    "'operatorAccepted',true,'fullScanAllowed',true) "
                    "WHERE game_id=:game AND id=:id"
                ),
                {"game": game, "id": model_id},
            )
            return self.public_model(self.row("models", game, model_id))

        return self.command(
            game,
            request.idempotency_key,
            {"accept": str(model_id), **request.model_dump(mode="json")},
            execute,
        )

    @staticmethod
    def _revision(row: Mapping[str, Any], expected: int) -> None:
        if row["revision"] != expected:
            raise ReadabilityWorkflowError(
                "READABILITY_REVISION_CONFLICT", "Dane zmieniły się. Odśwież widok."
            )

    def current(self, game: UUID, cell_id: UUID, *, lock: bool = False) -> dict[str, Any] | None:
        row = (
            self.session.execute(
                text(SNAPSHOT_SQL + " AND c.id=:cell" + (" FOR UPDATE OF c,b,r,s" if lock else "")),
                {"game": game, "cell": cell_id},
            )
            .mappings()
            .first()
        )
        return None if row is None else dict(row["snapshot"])

    def _refresh_stale(self, game: UUID, run: UUID) -> None:
        self.acquire_write_lock(game)
        # SQL identity checks are intentionally independent of review approval/name changes.
        self.session.execute(
            text("""UPDATE symbol_readability_items i SET state='stale',overlap=NULL,
          reasons='["crop_identity_changed"]'::jsonb WHERE i.game_id=:game AND i.run_id=:run
          AND state<>'stale' AND NOT EXISTS (
            SELECT 1 FROM image_symbol_review_cells c
            JOIN recognized_boards b ON b.id=c.recognized_board_id AND b.game_id=c.game_id
            JOIN image_review_items r ON r.id=c.review_item_id AND r.game_id=c.game_id
            JOIN source_images s ON s.id=b.source_image_id AND s.game_id=c.game_id
            WHERE c.game_id=i.game_id AND c.id=i.cell_id AND r.status<>'rejected'
            AND c.geometry_revision=b.geometry_revision
            AND c.source_geometry_revision_id IS NOT DISTINCT FROM b.source_geometry_revision_id
            AND c.geometry_revision=(i.snapshot->>'geometry_revision')::int
            AND c.source_geometry_revision_id::text IS NOT DISTINCT FROM
i.snapshot->>'source_geometry_revision_id'
            AND s.id::text=i.snapshot->>'source_id' AND
s.checksum_sha256=i.snapshot->>'source_sha256'
            AND c.crop_sample_id IS NOT DISTINCT FROM i.snapshot->>'crop_sample_id'
            AND c.crop_checksum_sha256 IS NOT DISTINCT FROM i.snapshot->>'crop_checksum_sha256'
            AND c.render_spec_checksum_sha256 IS NOT DISTINCT FROM
i.snapshot->>'render_spec_checksum_sha256'
            AND c.rendered_pixel_checksum_sha256 IS NOT DISTINCT FROM
i.snapshot->>'rendered_pixel_checksum_sha256'
            AND c.render_identity_v2_sha256 IS NOT DISTINCT FROM
i.snapshot->>'render_identity_v2_sha256')"""),
            {"game": game, "run": run},
        )

    def _require_pilot_current(self, game: UUID, run: UUID) -> None:
        self._refresh_stale(game, run)
        if self.session.scalar(
            text(
                "SELECT count(*) FROM symbol_readability_items "
                "WHERE game_id=:game AND run_id=:run AND state='stale'"
            ),
            {"game": game, "run": run},
        ):
            raise ReadabilityWorkflowError(
                "READABILITY_CROP_STALE", "Piksele pilota zmieniły się po odbiorze modelu."
            )

    def label(self, game: UUID, run_id: UUID, request: ReadabilityLabelRequest) -> dict[str, Any]:
        def execute() -> dict[str, Any]:
            self.acquire_write_lock(game)
            # Board/cell locks precede the run lock, matching the ordinary review mutation.
            if len({t.cell_id for t in request.targets}) != len(request.targets):
                raise ReadabilityWorkflowError(
                    "READABILITY_DUPLICATE_TARGET", "Powtórzone pole w poleceniu."
                )
            current = {
                t.cell_id: self.current(game, t.cell_id, lock=True)
                for t in sorted(request.targets, key=lambda t: str(t.cell_id))
            }
            self.row("runs", game, run_id, lock=True)
            for target in request.targets:
                item = (
                    self.session.execute(
                        text(
                            "SELECT * FROM symbol_readability_items WHERE game_id=:game AND "
                            "run_id=:run AND cell_id=:cell FOR UPDATE"
                        ),
                        {"game": game, "run": run_id, "cell": target.cell_id},
                    )
                    .mappings()
                    .first()
                )
                if item is None or not item["processed"]:
                    raise ReadabilityWorkflowError(
                        "READABILITY_ITEM_NOT_READY", "Pole nie zostało przygotowane."
                    )
                self._revision(dict(item), target.expected_revision)
                if item["identity"] != target.expected_identity or not identity_is_current(
                    item["snapshot"], current[target.cell_id]
                ):
                    raise ReadabilityWorkflowError(
                        "READABILITY_CROP_STALE", "Piksele pola zmieniły się."
                    )
                snapshot = current[target.cell_id]
                assert snapshot is not None
                if request.state == "unreadable" and snapshot.get("quality_issue") != "unreadable":
                    SymbolCellReviewMutationService(
                        SqlAlchemySymbolCellReviewMutationRepository(self.session)
                    ).mark_unreadable(
                        game_id=game,
                        cell_review_id=target.cell_id,
                        expected_revision=snapshot["revision"],
                        expected_geometry_revision=snapshot["geometry_revision"],
                        expected_crop_sample_id=snapshot["crop_sample_id"],
                        expected_crop_checksum_sha256=snapshot["crop_checksum_sha256"],
                        actor="local-admin",
                    )
                self.session.execute(
                    text(
                        "UPDATE symbol_readability_items SET "
                        "state=:state,overlap=:overlap,sharp=:sharp,"
                        "similar_readable=:similar,ever_labelled=true,revision=revision+1 "
                        "WHERE game_id=:game AND run_id=:run AND cell_id=:cell"
                    ),
                    {
                        "game": game,
                        "run": run_id,
                        "cell": target.cell_id,
                        "state": request.state,
                        "overlap": request.overlap,
                        "sharp": request.sharp,
                        "similar": request.similar_readable,
                    },
                )
                from game_predictor_api.storage.source_replacement_decisions import (
                    append_quality_decision,
                )

                append_quality_decision(
                    self.session,
                    game=game,
                    key=request.idempotency_key,
                    run=run_id,
                    cell=target.cell_id,
                    revision=target.expected_revision + 1,
                    state=request.state,
                    overlap=request.overlap,
                    snapshot=snapshot,
                    prior_item=dict(item),
                )
            self.session.execute(
                text(
                    "UPDATE symbol_readability_runs SET revision=revision+1 WHERE "
                    "game_id=:game AND id=:run"
                ),
                {"game": game, "run": run_id},
            )
            return self.public_run(self.row("runs", game, run_id))

        return self.command(
            game,
            request.idempotency_key,
            {"label": str(run_id), **request.model_dump(mode="json")},
            execute,
        )

    def page(
        self,
        game: UUID,
        run_id: UUID,
        *,
        offset: int = 0,
        state: str | None = None,
        historical: bool | None = None,
        problem: str | None = None,
    ) -> dict[str, Any]:
        self.bind(game, write=True)
        self.row("runs", game, run_id)
        self._refresh_stale(game, run_id)
        params = {
            "game": game,
            "run": run_id,
            "offset": offset,
            "state": state,
            "historical": historical,
            "problem": problem,
        }
        scope = """game_id=:game AND run_id=:run AND (CAST(:state AS text) IS NULL OR state=:state)
          AND (CAST(:historical AS boolean) IS NULL OR historical_unreadable=:historical)
          AND (CAST(:problem AS text) IS NULL OR (:problem='overlap' AND
            (overlap=true OR reasons @> '["overlap_score"]'::jsonb))
            OR (:problem='unreadable' AND
            (state='unreadable' OR reasons @> '["unreadable_score"]'::jsonb)))"""
        counts = (
            self.session.execute(
                text(
                    "SELECT count(*) AS fields,count(DISTINCT "
                    "snapshot->>'recognized_board_id') AS boards,"
                    "count(DISTINCT source_id) AS sources,count(*) FILTER(WHERE "
                    "state='unreadable') AS confirmed_fields,"
                    "count(DISTINCT snapshot->>'recognized_board_id') FILTER(WHERE "
                    "state='unreadable') AS confirmed_boards,"
                    "count(DISTINCT source_id) FILTER(WHERE state='unreadable') AS "
                    "confirmed_sources FROM symbol_readability_items WHERE " + scope
                ),
                params,
            )
            .mappings()
            .one()
        )
        rows = (
            self.session.execute(
                text(
                    "SELECT * FROM symbol_readability_items WHERE "
                    + scope
                    + " ORDER BY candidate DESC,rank_margin DESC NULLS "
                    "LAST,rank_secondary DESC NULLS "
                    "LAST,sequence_number,cell_index,cell_id LIMIT 251 OFFSET :offset"
                ),
                params,
            )
            .mappings()
            .all()
        )
        return {
            **dict(counts),
            "items": [self.public_item(dict(row)) for row in rows[:250]],
            "next_offset": offset + 250 if len(rows) > 250 else None,
        }

    @staticmethod
    def public_item(row: Mapping[str, Any]) -> dict[str, Any]:
        snapshot = row["snapshot"]
        return {
            **{
                k: snapshot[k]
                for k in (
                    "review_item_id",
                    "recognized_board_id",
                    "import_job_id",
                    "row_index",
                    "column_index",
                    "geometry_revision",
                    "crop_checksum_sha256",
                    "render_spec_checksum_sha256",
                )
            },
            **{
                k: row[k]
                for k in (
                    "cell_id",
                    "source_id",
                    "sequence_number",
                    "cell_index",
                    "identity",
                    "revision",
                    "state",
                    "overlap",
                    "sharp",
                    "similar_readable",
                    "historical_unreadable",
                    "sample_kind",
                    "overlap_score",
                    "unreadable_score",
                    "candidate",
                    "reasons",
                )
            },
        }

    def csv(self, game: UUID, run: UUID) -> str:
        self.bind(game, write=True)
        self.row("runs", game, run)
        self._refresh_stale(game, run)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            ["sequence_number", "cell_index", "source_id", "historical_unreadable", "overlap"]
        )
        for row in self.session.execute(
            text(
                "SELECT sequence_number,cell_index,source_id,historical_unreadable,overlap "
                "FROM symbol_readability_items WHERE game_id=:game AND run_id=:run "
                "AND state='unreadable' "
                "ORDER BY sequence_number,cell_index,cell_id"
            ),
            {"game": game, "run": run},
        ).yield_per(250):
            writer.writerow(row)
        return output.getvalue()
