"""Game-scoped durable manifests, commands and source receipts for D-551."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.application.grid_reinference import (
    ACCEPTANCE_POLICY,
    CONTRACT,
    PAGE_SIZE,
    RUNTIME_POLICY,
    canonical,
    command_transition,
    conflict,
    digest,
    now_text,
    receipt_replay,
)
from game_predictor_api.application.grid_reinference_stats import (
    SCOPE_FIELDS,
    STATS_POLICY,
    add_counts,
    empty_effect,
    empty_scope,
    frozen_target_counts,
    refresh_effect_gap,
    stats_enabled,
)
from game_predictor_api.domain.jobs import (
    Job,
    JobStatus,
    JobType,
    create_job,
    request_job_cancellation,
    requeue_job,
)
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceOperationModel as Operation,
)
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceSourceModel as Source,
)
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceTargetModel as Target,
)
from game_predictor_api.storage.job_admission import acquire_job_admission
from game_predictor_api.storage.job_repository import (
    apply_job_to_record,
    job_from_record,
    job_record_from_domain,
)
from game_predictor_api.storage.models import GameModel, JobModel


def is_grid_reinference(job: Job) -> bool:
    return (
        job.job_type is JobType.IMAGE_GRID_REINFERENCE
        and job.input_payload.get("inference_kind") == CONTRACT
    )


class SqlAlchemyGridReinferenceRepository:
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self.session, self.artifact_root = session, artifact_root

    def bind(self, game_id: UUID, *, write: bool = True) -> None:
        GameStorageRouter().bind(
            self.session,
            game_id,
            intent=GameStorageIntent.WRITE if write else GameStorageIntent.READ,
        )
        self.session.execute(text("SET LOCAL statement_timeout='30s'"))

    def key_lock(self, scope: str) -> None:
        key = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], "big", signed=True)
        self.session.execute(text("SET LOCAL lock_timeout='5s'"))
        self.session.execute(select(func.pg_advisory_xact_lock(key)))

    def record(self, game_id: UUID, operation_id: UUID, *, lock: bool = False) -> Operation:
        self.bind(game_id, write=lock)
        query = select(Operation).where(Operation.game_id == game_id, Operation.id == operation_id)
        if lock:
            query = query.with_for_update()
        record = self.session.scalar(query.execution_options(populate_existing=True))
        if record is None:
            conflict("NOT_FOUND", "The operation does not belong to this game.")
        return record

    @staticmethod
    def view(record: Operation, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
        d = record.document
        return {
            key: d.get(key)
            for key in (
                "gameId",
                "operationId",
                "jobId",
                "state",
                "phase",
                "revision",
                "manifestSha256",
                "reportSha256",
                "sourceCount",
                "targetCount",
                "processedSources",
                "outcomes",
                "sourceStatusCounts",
                "modelSnapshot",
                "runtimePolicy",
                "acceptancePolicy",
                "membershipCapturedAt",
                "preparationStartedAt",
                "preparationFinishedAt",
            )
        } | {
            "receipt": receipt,
            "executionScope": d.get("executionScope", "pilot"),
            "selector": d.get("command", {}).get("selector", {}),
            "pilotAcknowledgement": d.get("pilotAck"),
            "executionQuarantine": d.get("executionQuarantine"),
            "statsPolicy": d.get("statsPolicy"),
            "scopeStats": d.get("scopeStats") if d.get("manifestSha256") else None,
            "effectStats": d.get("effectStats"),
        }

    def get(self, game_id: UUID, operation_id: UUID) -> dict[str, Any]:
        return self.view(self.record(game_id, operation_id))

    def list_operations(
        self,
        game_id: UUID,
        cursor: str | None,
        limit: int,
        compatible_with_operation_id: UUID | None = None,
    ) -> dict[str, Any]:
        self.bind(game_id, write=False)
        if not 1 <= limit <= 50:
            conflict("CURSOR_INVALID", "Operation pages require a limit between 1 and 50.")
        signature = None
        if compatible_with_operation_id is not None:
            signature = self.record(game_id, compatible_with_operation_id).document[
                "scopeSignature"
            ]
        context = [
            str(game_id),
            str(compatible_with_operation_id) if compatible_with_operation_id else None,
            signature,
        ]
        last_id = None
        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                if decoded["version"] != 1 or decoded["context"] != context:
                    raise ValueError
                last_id = UUID(decoded["lastId"])
            except (ValueError, KeyError, TypeError, UnicodeError):
                conflict(
                    "CURSOR_INVALID", "The operation cursor belongs to another game or filter."
                )
        query = select(Operation).where(Operation.game_id == game_id)
        if last_id is not None:
            query = query.where(Operation.id < last_id)
        if compatible_with_operation_id is not None:
            query = query.where(
                Operation.document["state"].as_string() == "completed",
                Operation.document["executionScope"].as_string() == "pilot",
                Operation.document["sourceCount"].as_integer() <= 100,
                Operation.document["reportSha256"].as_string().is_not(None),
                Operation.document["scopeSignature"].as_string() == signature,
            )
        rows = list(self.session.scalars(query.order_by(Operation.id.desc()).limit(limit + 1)))
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            next_cursor = base64.urlsafe_b64encode(
                canonical(
                    {
                        "version": 1,
                        "context": context,
                        "lastId": str(page[-1].id),
                    }
                ).encode()
            ).decode()
        return {"items": [self.view(row) for row in page], "nextCursor": next_cursor}

    def model(self, game_id: UUID, version_id: str | None) -> tuple[dict[str, Any], int]:
        game = self.session.get(GameModel, game_id)
        if game is None or game.code == "7":
            conflict("GAME_PROTECTED", "Historical 777 cannot enter V3 reinference.")
        repository = SqlAlchemyGridModelRegistryRepository(self.session)
        repository.lock()
        assignment, _ = repository.assignment(game_id)
        resolver = SqlAlchemyGridProfileSnapshotResolver(self.session, self.artifact_root)
        if version_id is None or (
            assignment is not None and version_id == str(assignment.version_id)
        ):
            snapshot = resolver.resolve_neural_grid_proposal(game_id=game_id)
            if snapshot is None:
                conflict("FORMAT_UNSUPPORTED", "The game does not use V3.")
        else:
            registry = GridModelRegistryService(
                repository, GridModelArtifactInspector(self.artifact_root)
            )
            view, _ = registry.control.eligible(UUID(version_id), game_id=game_id)
            snapshot = NeuralGridSnapshot.from_catalogue(
                game_id=str(game_id),
                game_configuration=str(game.shape_geometry_configuration),
                expected_layout_count=game.expected_layout_count,
                descriptor=view["manifest"],
            ).to_payload()
        assert snapshot is not None
        return snapshot, 0 if assignment is None else assignment.revision

    def prepare(self, game_id: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]:
        self.key_lock(f"{game_id}:grid-prepare:{command['idempotencyKey']}")
        self.bind(game_id)
        old = self.session.scalar(
            select(Operation).where(
                Operation.game_id == game_id,
                Operation.idempotency_key == UUID(command["idempotencyKey"]),
            )
        )
        if old is not None:
            if old.command_sha256 != digest(command):
                conflict("IDEMPOTENCY_CONFLICT", "The prepare key has different content.")
            return self.view(old, old.document["prepareReceipt"])
        snapshot, revision = self.model(game_id, command.get("modelVersionId"))
        acquire_job_admission(self.session, game_id)
        operation_id = uuid4()
        job = create_job(
            JobType.IMAGE_GRID_REINFERENCE,
            game_id=game_id,
            input_payload={
                "schema_version": 3,
                "inference_kind": CONTRACT,
                "operation_id": str(operation_id),
                "model_snapshot": snapshot,
                "runtime_policy": RUNTIME_POLICY,
                "acceptance_policy": ACCEPTANCE_POLICY,
                "stats_policy": STATS_POLICY,
            },
        )
        signature = digest(
            {
                "gameId": str(game_id),
                "selector": command["selector"],
                "model": snapshot,
                "runtime": RUNTIME_POLICY,
                "writePolicy": CONTRACT,
                "acceptancePolicy": ACCEPTANCE_POLICY,
            }
        )
        receipt = {
            "kind": "prepare",
            "operationId": str(operation_id),
            "jobId": str(job.id),
            "actor": actor,
            "commandSha256": digest(command),
            "at": now_text(),
        }
        document = {
            "gameId": str(game_id),
            "operationId": str(operation_id),
            "jobId": str(job.id),
            "state": "preparing",
            "phase": "prepare",
            "revision": 0,
            "command": command,
            "modelSnapshot": snapshot,
            "acceptancePolicy": ACCEPTANCE_POLICY,
            "runtimePolicy": RUNTIME_POLICY,
            "assignmentRevision": revision,
            "executionScope": command["executionScope"],
            "scopeSignature": signature,
            "prepareReceipt": receipt,
            "actor": actor,
            "receipts": {},
            "membershipCapturedAt": None,
            "preparationStartedAt": now_text(),
            "preparationFinishedAt": None,
            "prepareCursor": 0,
            "processedSources": 0,
            "sourceCount": 0,
            "targetCount": 0,
            "outcomes": {},
            "sourceStatusCounts": {},
            "manifestSha256": None,
            "reportSha256": None,
            "statsPolicy": STATS_POLICY,
            "scopeStats": empty_scope(),
            "effectStats": empty_effect(),
        }
        record = Operation(
            game_id=game_id,
            id=operation_id,
            idempotency_key=UUID(command["idempotencyKey"]),
            command_sha256=digest(command),
            job_id=job.id,
            document=document,
        )
        self.session.add(job_record_from_domain(job))
        self.session.flush()
        self.session.add(record)
        self.session.flush()
        return self.view(record, receipt)

    def execute(
        self, game_id: UUID, operation_id: UUID, kind: str, command: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        self.key_lock(f"{game_id}:{operation_id}:{kind}:{command['idempotencyKey']}")
        initial = self.record(game_id, operation_id)
        replay = receipt_replay(initial.document, kind, command)
        if replay is not None:
            return self.view(initial, replay)
        if kind == "start":
            repository = SqlAlchemyGridModelRegistryRepository(self.session)
            repository.lock()
            snapshot, revision = self.model(
                game_id, initial.document["command"].get("modelVersionId")
            )
            if digest(snapshot) != digest(initial.document["modelSnapshot"]) or (
                initial.document["command"].get("modelVersionId") is None
                and revision != initial.document["assignmentRevision"]
            ):
                conflict("MODEL_CONFLICT", "The preview model assignment changed.")
        if kind in {"start", "resume", "cancel"}:
            acquire_job_admission(
                self.session, game_id, exclude_job_id=initial.job_id, require_idle=kind != "cancel"
            )
        job_record = self.session.scalar(
            select(JobModel).where(JobModel.id == initial.job_id).with_for_update(key_share=True)
        )
        assert job_record is not None
        stats_enabled(initial.document, job_record.input_payload)
        record = self.record(game_id, operation_id, lock=True)
        document = copy.deepcopy(record.document)
        replay = receipt_replay(document, kind, command)
        if replay is not None:
            return self.view(record, replay)
        pilot = None
        if kind == "pilot-ack":
            pilot = self.record(game_id, UUID(command["pilotOperationId"])).document
        receipt = command_transition(document, kind, command, actor=actor, pilot=pilot)
        job = job_from_record(job_record)
        if kind in {"start", "resume"}:
            if job.status not in {
                JobStatus.WAITING_FOR_REVIEW,
                JobStatus.CANCELLED,
                JobStatus.FAILED,
            }:
                conflict("PHASE_CONFLICT", "The job is not resumable.")
            apply_job_to_record(job_record, requeue_job(job))
        elif kind == "cancel":
            updated = request_job_cancellation(job)
            apply_job_to_record(job_record, updated)
            if updated.status is JobStatus.CANCELLED:
                document["state"] = "cancelled"
        record.document = document
        self.session.flush()
        return self.view(record, receipt)

    def targets(
        self, game_id: UUID, operation_id: UUID, cursor: str | None, limit: int
    ) -> dict[str, Any]:
        record = self.record(game_id, operation_id)
        if not 1 <= limit <= PAGE_SIZE or record.document["manifestSha256"] is None:
            conflict("CURSOR_INVALID", "A final manifest and a bounded page are required.")
        ordinal = 0
        if cursor:
            try:
                op, sha, raw = cursor.split(":")
                ordinal = int(raw)
                if (
                    op != str(operation_id)
                    or sha != record.document["manifestSha256"]
                    or ordinal < 0
                ):
                    raise ValueError
            except ValueError:
                conflict("CURSOR_INVALID", "The cursor belongs to another manifest.")
        rows = list(
            self.session.scalars(
                select(Target)
                .where(
                    Target.game_id == game_id,
                    Target.operation_id == operation_id,
                    Target.ordinal > ordinal,
                )
                .order_by(Target.ordinal)
                .limit(limit + 1)
            )
        )
        page = rows[:limit]
        return {
            "items": [
                {
                    "targetResultId": str(row.target_result_id),
                    "sourceImageId": str(row.source_image_id),
                    "positionIndex": row.position_index,
                    "ordinal": row.ordinal,
                    "snapshot": row.snapshot,
                    "outcome": row.outcome,
                    "result": row.result,
                }
                for row in page
            ],
            "nextCursor": f"{operation_id}:{record.document['manifestSha256']}:{page[-1].ordinal}"
            if len(rows) > limit
            else None,
        }

    def worker_record(self, job: Job) -> Operation:
        if not is_grid_reinference(job) or job.game_id is None:
            conflict("PAYLOAD_INVALID", "The worker payload is not selected reinference.")
        # The job lease is always the first row lock of the worker transaction.
        record = self.session.scalar(
            select(JobModel).where(JobModel.id == job.id).with_for_update(key_share=True)
        )
        assert record is not None and job.lease_token is not None
        from datetime import UTC, datetime

        from game_predictor_api.domain.jobs import require_active_job_lease

        require_active_job_lease(
            job_from_record(record), lease_token=job.lease_token, checked_at=datetime.now(UTC)
        )
        operation = self.record(
            job.game_id, UUID(str(job.input_payload["operation_id"])), lock=True
        )
        if (
            operation.job_id != job.id
            or operation.document["modelSnapshot"] != job.input_payload["model_snapshot"]
            or operation.document["acceptancePolicy"] != job.input_payload["acceptance_policy"]
            or operation.document["runtimePolicy"] != job.input_payload["runtime_policy"]
            or operation.document["runtimePolicy"] != RUNTIME_POLICY
            or operation.document["acceptancePolicy"] != ACCEPTANCE_POLICY
        ):
            conflict("PAYLOAD_INVALID", "The operation and immutable job pin differ.")
        stats_enabled(operation.document, job.input_payload)
        return operation

    def capture(self, operation: Operation) -> None:
        d = copy.deepcopy(operation.document)
        if d["membershipCapturedAt"] is not None:
            return
        selector = d["command"]["selector"]
        categories = selector["categories"]
        params = {
            "game": operation.game_id,
            "op": operation.id,
            "deferred": "deferred" in categories,
            "issue": "grid_issue" in categories,
            "automatic": "all_automatic" in categories,
            "unconfirmed": "unconfirmed" in categories,
            "start": selector.get("sequenceStart"),
            "end": selector.get("sequenceEnd"),
        }
        imports = selector.get("importJobIds", [])
        import_filter = ""
        if imports:
            import_filter = " AND s.import_job_id = ANY(CAST(:imports AS uuid[]))"
            params["imports"] = imports
        limit = " LIMIT 100" if d["executionScope"] == "pilot" else ""
        # Statement snapshot fixes occurrence membership, never a UUID high watermark.
        sql = (
            """INSERT INTO grid_reinference_sources
        (game_id,operation_id,ordinal,source_image_id,live_source_image_id,document)
        SELECT :game,:op,row_number() OVER(ORDER BY s.import_job_id,jf.order_index,s.id),s.id,s.id,
jsonb_build_object('source',to_jsonb(s),'importJobId',s.import_job_id,'fileExecutionKey',s.file_execution_key)
        FROM source_images s JOIN public.jobs j ON j.id=s.import_job_id
        JOIN image_import_job_files jf ON jf.job_id=s.import_job_id AND
jf.file_execution_key=s.file_execution_key
        WHERE j.game_id=:game AND s.game_id=:game """
            + import_filter
            + """
        AND ((:deferred AND EXISTS(SELECT 1 FROM image_board_geometry_pending p WHERE
p.game_id=:game AND p.source_image_id=s.id AND p.status='pending' AND (CAST(:start AS bigint) IS
NULL OR p.sequence_number BETWEEN :start AND :end)))
        OR EXISTS(SELECT 1 FROM recognized_boards b JOIN image_review_items r ON
r.recognized_board_id=b.id
        WHERE b.game_id=:game AND b.source_image_id=s.id AND r.status<>'superseded'
        AND (CAST(:start AS bigint) IS NULL OR b.sequence_number BETWEEN :start AND :end)
        AND ((:automatic) OR (:unconfirmed AND b.approved_geometry_revision IS NULL) OR (:issue
AND EXISTS(
        SELECT 1 FROM image_symbol_review_cells c WHERE c.game_id=:game AND
c.review_item_id=r.id AND c.quality_issue='grid_issue' AND c.review_state='pending' AND
c.geometry_revision=b.geometry_revision AND
c.source_geometry_revision_id=b.source_geometry_revision_id AND
c.asset_mode='virtual_source')))))
        ORDER BY s.import_job_id,jf.order_index,s.id"""
            + limit
        )
        self.session.execute(text(sql), params)
        d["sourceCount"] = self.session.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.game_id == operation.game_id, Source.operation_id == operation.id)
        )
        if d.get("statsPolicy") == STATS_POLICY:
            d["scopeStats"]["sourceOccurrenceCount"] = d["sourceCount"]
        d["membershipCapturedAt"] = now_text()
        operation.document = d
        self.session.flush()

    def source_targets(
        self, game_id: UUID, source_image_id: UUID, selector: dict[str, Any]
    ) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text("""SELECT to_jsonb(b) AS board,to_jsonb(r) AS review,
        (SELECT coalesce(jsonb_agg(to_jsonb(c) ORDER BY c.cell_index),'[]') FROM
image_symbol_review_cells c WHERE c.game_id=:game AND c.review_item_id=r.id) AS cells,
        (SELECT to_jsonb(o) FROM image_sequence_canonical o WHERE o.game_id=:game AND
o.sequence_number=b.sequence_number) AS owner
        FROM recognized_boards b JOIN image_review_items r ON r.recognized_board_id=b.id
        WHERE b.game_id=:game AND b.source_image_id=:source ORDER BY b.position_index"""),
            {"game": game_id, "source": source_image_id},
        ).mappings()
        foreign_rows = self.session.execute(
            text("""
            SELECT DISTINCT ON (r.sequence_number) r.sequence_number,
              jsonb_build_object('review_item_id',r.id,'recognized_board_id',b.id,
                'source_image_id',b.source_image_id,'import_job_id',r.import_job_id,
                'status',r.status,'resolution_revision',r.resolution_revision,
                'geometry_revision',b.geometry_revision) AS owner
            FROM image_review_items r JOIN recognized_boards b ON b.id=r.recognized_board_id
            WHERE r.game_id=:game AND b.source_image_id<>:source
              AND r.status IN ('pending','accepted','corrected') AND b.status<>'rejected'
              AND r.sequence_number IN (
                SELECT sequence_number FROM recognized_boards
                  WHERE game_id=:game AND source_image_id=:source
                UNION SELECT sequence_number FROM image_board_geometry_pending
                  WHERE game_id=:game AND source_image_id=:source)
            ORDER BY r.sequence_number,r.created_at,r.id
        """),
            {"game": game_id, "source": source_image_id},
        ).mappings()
        foreign_by_sequence = {row["sequence_number"]: row["owner"] for row in foreign_rows}
        selected = []
        categories = selector["categories"]
        for row in rows:
            board, review, cells, owner = row["board"], row["review"], row["cells"], row["owner"]
            sequence = board["sequence_number"]
            if selector.get("sequenceStart") is not None and not (
                sequence is not None
                and selector["sequenceStart"] <= sequence <= selector["sequenceEnd"]
            ):
                continue
            issue = any(
                cell["quality_issue"] == "grid_issue"
                and cell["review_state"] == "pending"
                and cell["geometry_revision"] == board["geometry_revision"]
                and cell["source_geometry_revision_id"] == board["source_geometry_revision_id"]
                and cell["asset_mode"] == "virtual_source"
                for cell in cells
            )
            if not (
                (issue and "grid_issue" in categories)
                or "all_automatic" in categories
                or ("unconfirmed" in categories and board["approved_geometry_revision"] is None)
            ):
                continue
            selected.append(
                {
                    "board": board,
                    "review": review,
                    "cells": cells,
                    "owner": owner,
                    "pending": None,
                    "kind": "grid_issue" if issue else "automatic",
                    "foreignOwner": foreign_by_sequence.get(sequence),
                    "positionIndex": board["position_index"],
                    "sequenceNumber": sequence,
                }
            )
        if "deferred" in categories:
            pending = self.session.execute(
                text(
                    """
SELECT to_jsonb(p) AS pending FROM image_board_geometry_pending p WHERE p.game_id=:game
AND p.source_image_id=:source AND p.status='pending' ORDER BY p.position_index
                    """
                ),
                {"game": game_id, "source": source_image_id},
            ).mappings()
            existing = {target["positionIndex"] for target in selected}
            for row in pending:
                p = row["pending"]
                if p["position_index"] in existing:
                    continue
                if (
                    selector.get("sequenceStart") is not None
                    and not selector["sequenceStart"]
                    <= p["sequence_number"]
                    <= selector["sequenceEnd"]
                ):
                    continue
                owner = self.session.execute(
                    text(
                        """
SELECT to_jsonb(o) FROM image_sequence_canonical o WHERE o.game_id=:game AND
o.sequence_number=:seq
                        """
                    ),
                    {"game": game_id, "seq": p["sequence_number"]},
                ).scalar()
                selected.append(
                    {
                        "board": None,
                        "review": None,
                        "cells": [],
                        "owner": owner,
                        "pending": p,
                        "kind": "deferred",
                        "foreignOwner": foreign_by_sequence.get(p["sequence_number"]),
                        "positionIndex": p["position_index"],
                        "sequenceNumber": p["sequence_number"],
                    }
                )
        return selected

    def prepare_page(self, operation: Operation) -> bool:
        d = copy.deepcopy(operation.document)
        capacity = None
        if d.get("statsPolicy") == STATS_POLICY:
            pin = NeuralGridSnapshot.from_payload(d["modelSnapshot"])
            manifest = d["modelSnapshot"].get("catalogueManifest")
            # The legacy neural-source contract fixes 3x5. Catalogue pins
            # explicitly carry their validated topology, parsed once per page.
            capacity = (
                15
                if manifest is None
                else (manifest["topology"]["boardRows"] * manifest["topology"]["boardColumns"])
            )
            assert pin.expected_layout_count > 0
        rows = list(
            self.session.scalars(
                select(Source)
                .where(
                    Source.game_id == operation.game_id,
                    Source.operation_id == operation.id,
                    Source.ordinal > d["prepareCursor"],
                )
                .order_by(Source.ordinal)
                .limit(PAGE_SIZE)
            )
        )
        for source in rows:
            geometry = self.session.execute(
                text(
                    """
SELECT to_jsonb(g) FROM image_source_geometry_revisions g WHERE g.game_id=:game AND
g.source_image_id=:source ORDER BY g.revision DESC LIMIT 1
                    """
                ),
                {"game": operation.game_id, "source": source.source_image_id},
            ).scalar_one_or_none()
            source.document = {**source.document, "geometryContext": geometry}
            for snapshot in self.source_targets(
                operation.game_id, source.source_image_id, d["command"]["selector"]
            ):
                snapshot["source"] = source.document["source"]
                snapshot["geometryContext"] = geometry
                snapshot["modelSnapshot"] = d["modelSnapshot"]
                snapshot["schemaVersion"] = "grid-reinference-target-result-v1"
                snapshot["acceptancePolicy"] = d["acceptancePolicy"]
                snapshot["runtimePolicy"] = d["runtimePolicy"]
                if capacity is not None:
                    add_counts(
                        d["scopeStats"],
                        frozen_target_counts(
                            snapshot,
                            cell_capacity=capacity,
                            protected=target_protection(snapshot) is not None,
                        ),
                        SCOPE_FIELDS,
                    )
                ordinal = source.ordinal * 10 + snapshot["positionIndex"] + 1
                self.session.add(
                    Target(
                        game_id=operation.game_id,
                        operation_id=operation.id,
                        ordinal=ordinal,
                        source_ordinal=source.ordinal,
                        source_image_id=source.source_image_id,
                        position_index=snapshot["positionIndex"],
                        target_result_id=uuid5(
                            operation.id, f"{source.source_image_id}:{snapshot['positionIndex']}"
                        ),
                        snapshot=snapshot,
                        fingerprint_sha256=digest(target_fence(snapshot)),
                        outcome=None,
                        result=None,
                    )
                )
                d["targetCount"] += 1
            d["prepareCursor"] = source.ordinal
        operation.document = d
        self.session.flush()
        return len(rows) < PAGE_SIZE

    def finalize_preparation(self, operation: Operation) -> None:
        d = copy.deepcopy(operation.document)
        hasher = hashlib.sha256()
        for row in self.session.execute(
            select(Target.ordinal, Target.snapshot)
            .where(Target.game_id == operation.game_id, Target.operation_id == operation.id)
            .order_by(Target.ordinal)
            .execution_options(yield_per=PAGE_SIZE)
        ):
            hasher.update((canonical([row.ordinal, row.snapshot]) + "\n").encode())
        if d.get("statsPolicy") == STATS_POLICY:
            # Only immutable members of this operation; no current game scan,
            # Python-wide UUID sets, or repeated per-target existence queries.
            self.session.execute(text("SET LOCAL statement_timeout='30s'"))
            totals = (
                self.session.execute(
                    text("""
SELECT count(DISTINCT t.snapshot->'board'->>'id') AS boards,
 count(DISTINCT c->>'id') FILTER (WHERE
   c->'geometry_revision' = t.snapshot->'board'->'geometry_revision'
   AND c->'source_geometry_revision_id' = t.snapshot->'board'->'source_geometry_revision_id'
 ) AS cells,
 count(DISTINCT c->>'id') FILTER (WHERE
   c->'geometry_revision' = t.snapshot->'board'->'geometry_revision'
   AND c->'source_geometry_revision_id' = t.snapshot->'board'->'source_geometry_revision_id'
   AND c->>'source_available' = 'true'
 ) AS available
FROM grid_reinference_targets t
LEFT JOIN LATERAL jsonb_array_elements(t.snapshot->'cells') c ON true
WHERE t.game_id=:game AND t.operation_id=:operation
            """),
                    {"game": operation.game_id, "operation": operation.id},
                )
                .mappings()
                .one()
            )
            d["scopeStats"].update(
                existingBoardCount=totals["boards"],
                existingCellCount=totals["cells"],
                availableCellCount=totals["available"],
            )
        d.update(
            state="prepared",
            manifestSha256=hasher.hexdigest(),
            preparationFinishedAt=now_text(),
            revision=d["revision"] + 1,
        )
        refresh_effect_gap(d)
        operation.document = d
        self.session.flush()


def target_fence(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Only current domain identity, not timestamps or the occurrence's job status."""
    board, review, pending = snapshot["board"], snapshot["review"], snapshot["pending"]
    return {
        "board": None
        if board is None
        else {
            key: board.get(key)
            for key in (
                "id",
                "source_image_id",
                "position_index",
                "sequence_number",
                "source_geometry_revision_id",
                "geometry_checksum_sha256",
                "geometry_revision",
                "approved_geometry_revision",
                "geometry_approved_by",
                "status",
                "board_geometry",
            )
        },
        "review": None
        if review is None
        else {
            key: review.get(key)
            for key in ("id", "resolution_revision", "status", "resolved_value", "resolved_by")
        },
        "pending": None
        if pending is None
        else {
            key: pending.get(key)
            for key in (
                "id",
                "game_id",
                "import_job_id",
                "source_image_id",
                "recognized_board_id",
                "review_item_id",
                "position_index",
                "sequence_number",
                "source_checksum_sha256",
                "status",
                "reason_code",
                "processing_manifest_checksum_sha256",
                "pipeline_fingerprint_sha256",
                "expected_geometry_revision",
                "expected_review_resolution_revision",
                "resolved_geometry_revision",
            )
        },
        "cells": [
            {
                key: cell.get(key)
                for key in (
                    "id",
                    "revision",
                    "geometry_revision",
                    "source_geometry_revision_id",
                    "quality_issue",
                    "review_state",
                    "assignment_source",
                    "assigned_symbol_id",
                    "rendered_pixel_checksum_sha256",
                    "approved_rendered_pixel_checksum_sha256",
                    "approved_crop_checksum_sha256",
                    "source_available",
                )
            }
            for cell in snapshot["cells"]
        ],
        "owner": None
        if snapshot["owner"] is None
        else {
            key: snapshot["owner"].get(key)
            for key in (
                "game_id",
                "sequence_number",
                "review_item_id",
                "recognized_board_id",
                "import_job_id",
                "source_image_id",
                "status",
                "resolution_revision",
                "geometry_revision",
                "board_checksum_sha256",
            )
        },
        "foreignOwner": snapshot.get("foreignOwner"),
    }


def source_fence(source: dict[str, Any]) -> dict[str, Any]:
    return {
        key: source.get(key)
        for key in (
            "id",
            "import_job_id",
            "file_execution_key",
            "checksum_sha256",
            "normalized_pixel_checksum_sha256",
            "width",
            "height",
            "raw_width",
            "raw_height",
            "oriented_width",
            "oriented_height",
            "exif_orientation",
            "coordinate_space",
            "normalization_adapter_version",
        )
    }


def target_protection(snapshot: dict[str, Any]) -> str | None:
    if snapshot["kind"] == "grid_issue":
        return None  # Proposal only; this never authorizes an automatic write.
    board, review, owner = snapshot["board"], snapshot["review"], snapshot["owner"]
    if snapshot.get("foreignOwner") is not None:
        return "foreign_live_owner"
    if owner is not None and (
        board is None
        or owner["recognized_board_id"] != board["id"]
        or owner["review_item_id"] != review["id"]
    ):
        return "foreign_owner"
    if board is not None and (
        board["approved_geometry_revision"] is not None
        or review["status"] in {"rejected", "superseded"}
    ):
        return "human_geometry_or_inactive"
    if any(
        cell["review_state"] == "approved"
        or cell["assignment_source"] in {"human", "board_decision"}
        for cell in snapshot["cells"]
    ):
        return "human_cell_decision"
    return None


def authorize_generic_retry(session: Session, job: Job) -> None:
    """A generic retry may resume work, but cannot authorize new inference."""
    from game_predictor_api.storage.job_admission import admit_job

    admit_job(session, job)
    require_grid_retry_authorization(session, job)


def require_grid_retry_authorization(session: Session, job: Job) -> None:
    """Pure authorization read after the caller's admission, including recovery."""
    if not is_grid_reinference(job):
        return
    assert job.game_id is not None
    GameStorageRouter().bind(session, job.game_id, intent=GameStorageIntent.WRITE)
    record = session.scalar(
        select(Operation).where(Operation.game_id == job.game_id, Operation.job_id == job.id)
    )
    if record is None:
        conflict("NOT_FOUND", "The reinference operation is missing.")
    d = record.document
    if (
        d.get("executionQuarantine") is not None
        or d["state"] in {"prepared", "frozen"}
        or (d["phase"] == "infer" and d.get("startSha256") != d["manifestSha256"])
    ):
        conflict(
            "START_REQUIRED",
            "Explicit start and pilot acknowledgement cannot be bypassed by retry.",
        )


def synchronize_grid_job(session: Session, job: Job) -> None:
    """Atomic counterpart of worker lease terminal/waiting transitions."""
    if not is_grid_reinference(job) or job.status is JobStatus.PROCESSING:
        return
    assert job.game_id is not None
    GameStorageRouter().bind(session, job.game_id, intent=GameStorageIntent.WRITE)
    record = session.scalar(
        select(Operation)
        .where(Operation.game_id == job.game_id, Operation.job_id == job.id)
        .with_for_update()
    )
    if record is None:
        conflict("NOT_FOUND", "The reinference operation is missing.")
    d = copy.deepcopy(record.document)
    # Invalid pins must reject execution/success, while failure and cancel
    # still release the job lease instead of rolling terminal cleanup back.
    new_stats = (
        stats_enabled(d, job.input_payload)
        if job.status in {JobStatus.WAITING_FOR_REVIEW, JobStatus.COMPLETED, JobStatus.CREATED}
        else False
    )
    if (
        d.get("statsPolicy") == STATS_POLICY
        and job.input_payload.get("stats_policy") == STATS_POLICY
    ):
        refresh_effect_gap(d)
    if job.status is JobStatus.WAITING_FOR_REVIEW:
        SqlAlchemyGridReinferenceRepository(session, Path(".")).finalize_preparation(record)
        return
    if job.status is JobStatus.COMPLETED:
        if d["phase"] != "infer" or d["processedSources"] != d["sourceCount"]:
            conflict("PHASE_CONFLICT", "Incomplete inference cannot finish successfully.")
        d["state"] = "completed"
        d["reportSha256"] = digest(
            {
                "manifest": d["manifestSha256"],
                "outcomes": d["outcomes"],
                "processed": d["processedSources"],
                "sourceStatusCounts": d.get("sourceStatusCounts", {}),
            }
        )
        if new_stats:
            d["reportSha256"] = digest(
                {
                    "manifest": d["manifestSha256"],
                    "outcomes": d["outcomes"],
                    "processed": d["processedSources"],
                    "sourceStatusCounts": d.get("sourceStatusCounts", {}),
                    "statsPolicy": d["statsPolicy"],
                    "scopeStats": d["scopeStats"],
                    "effectStats": d["effectStats"],
                }
            )
    elif job.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
        d["state"] = job.status.value
        if job.status is JobStatus.FAILED and job.error_code == "GRID_REINFERENCE_START_REQUIRED":
            d["executionQuarantine"] = {
                "code": job.error_code,
                "at": job.finished_at.isoformat() if job.finished_at else now_text(),
            }
    elif job.status is JobStatus.CREATED:
        if d["phase"] == "infer" and d.get("startSha256") != d["manifestSha256"]:
            conflict("START_REQUIRED", "Inference has no authorized start.")
        d["state"] = "preparing" if d["phase"] == "prepare" else "queued"
    record.document = d
