"""Deterministic command state machine for selected grid reinference (D-551)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, NoReturn, Protocol, cast
from uuid import UUID

from game_predictor_api.domain.jobs import JobConflictError

CONTRACT = "grid-reinference-v1"
RUNTIME_POLICY = "grid-reinference-runtime-v1"
ACCEPTANCE_POLICY = "v3-engine-acceptance-v1"
SOURCE_DEADLINE_SECONDS = 30.0
PAGE_SIZE = 100
MAX_RECEIPTS = 128


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def now_text() -> str:
    return datetime.now(UTC).isoformat()


def conflict(code: str, message: str) -> NoReturn:
    raise JobConflictError(f"GRID_REINFERENCE_{code}", message)


def receipt_replay(
    document: dict[str, Any], kind: str, command: dict[str, Any]
) -> dict[str, Any] | None:
    key = f"{kind}:{command['idempotencyKey']}"
    previous = document["receipts"].get(key)
    if previous is not None and previous["commandSha256"] != digest(command):
        conflict("IDEMPOTENCY_CONFLICT", "This command key has different content.")
    return cast(dict[str, Any] | None, previous)


def command_transition(
    document: dict[str, Any],
    kind: str,
    command: dict[str, Any],
    *,
    actor: str,
    pilot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mutate one locked document; persistence owns admission and job transitions."""
    replay = receipt_replay(document, kind, command)
    if replay is not None:
        return replay
    if document["revision"] != command["expectedRevision"]:
        conflict("REVISION_CONFLICT", "The preview or operation revision changed.")
    if len(document["receipts"]) >= MAX_RECEIPTS:
        conflict("RECEIPT_LIMIT", "The operation command ledger is full.")
    if kind in {"freeze", "start"} and command["manifestSha256"] != document["manifestSha256"]:
        conflict("MANIFEST_CONFLICT", "The frozen target manifest changed.")
    state = document["state"]
    if kind == "freeze":
        if state != "prepared":
            conflict("PHASE_CONFLICT", "Only a prepared manifest can be frozen.")
        document["state"] = "frozen"
        document["freezeSha256"] = document["manifestSha256"]
    elif kind == "pilot-ack":
        if state not in {"prepared", "frozen"} or document["executionScope"] != "broader":
            conflict("PILOT_ACK_INVALID", "Acknowledgement requires a prepared broader scope.")
        if (
            pilot is None
            or pilot["state"] != "completed"
            or pilot["executionScope"] != "pilot"
            or pilot["sourceCount"] > 100
            or pilot["reportSha256"] != command["pilotReportSha256"]
            or pilot["scopeSignature"] != document["scopeSignature"]
        ):
            conflict("PILOT_REQUIRED", "A completed compatible pilot report is required.")
        document["pilotAck"] = {
            "pilotOperationId": command["pilotOperationId"],
            "reportSha256": command["pilotReportSha256"],
            "actor": actor,
            "at": now_text(),
        }
    elif kind == "start":
        if state != "frozen" or document["freezeSha256"] != document["manifestSha256"]:
            conflict("FREEZE_REQUIRED", "Freeze the prepared target manifest first.")
        if document["executionScope"] == "broader" and (
            document.get("pilotAck") is None or command.get("broadScopeConfirmed") is not True
        ):
            conflict(
                "PILOT_REQUIRED", "Acknowledge the pilot and explicitly confirm broader scope."
            )
        document.update(state="queued", phase="infer", startSha256=document["manifestSha256"])
    elif kind == "resume":
        if document.get("executionQuarantine") is not None:
            conflict("START_REQUIRED", "Quarantined work requires a new frozen operation.")
        if command["expectedPhase"] != document["phase"]:
            conflict("PHASE_CONFLICT", "The expected phase differs.")
        if state in {"prepared", "frozen"}:
            conflict("START_REQUIRED", "Explicit start is required before inference.")
        if state not in {"failed", "cancelled"}:
            conflict("PHASE_CONFLICT", "Only an interrupted operation can be resumed.")
        if (
            document["phase"] == "infer"
            and document.get("startSha256") != document["manifestSha256"]
        ):
            conflict("START_REQUIRED", "The frozen manifest has no authorized start.")
        document["state"] = "preparing" if document["phase"] == "prepare" else "queued"
    elif kind == "cancel":
        if state in {"completed", "cancelled", "failed"}:
            conflict("PHASE_CONFLICT", "The operation is already terminal.")
        document["state"] = "cancel_requested"
    else:
        conflict("COMMAND_INVALID", "Unknown grid reinference command.")
    document["revision"] += 1
    receipt = {
        "kind": kind,
        "commandSha256": digest(command),
        "actor": actor,
        "at": now_text(),
        "operationId": document["operationId"],
        "jobId": document["jobId"],
        "manifestSha256": document["manifestSha256"],
        "revision": document["revision"],
    }
    document["receipts"][f"{kind}:{command['idempotencyKey']}"] = receipt
    return receipt


class GridReinferenceRepository(Protocol):
    def list_operations(
        self,
        game_id: UUID,
        cursor: str | None,
        limit: int,
        compatible_with_operation_id: UUID | None,
    ) -> dict[str, Any]: ...
    def prepare(self, game_id: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]: ...
    def get(self, game_id: UUID, operation_id: UUID) -> dict[str, Any]: ...
    def execute(
        self, game_id: UUID, operation_id: UUID, kind: str, command: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...
    def targets(
        self, game_id: UUID, operation_id: UUID, cursor: str | None, limit: int
    ) -> dict[str, Any]: ...


class GridReinferenceService:
    def __init__(self, repository: GridReinferenceRepository) -> None:
        self.repository = repository

    def prepare(self, game_id: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]:
        return self.repository.prepare(game_id, command, actor)

    def get(self, game_id: UUID, operation_id: UUID) -> dict[str, Any]:
        return self.repository.get(game_id, operation_id)

    def list_operations(
        self,
        game_id: UUID,
        cursor: str | None,
        limit: int = 20,
        compatible_with_operation_id: UUID | None = None,
    ) -> dict[str, Any]:
        return self.repository.list_operations(game_id, cursor, limit, compatible_with_operation_id)

    def execute(
        self, game_id: UUID, operation_id: UUID, kind: str, command: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        return self.repository.execute(game_id, operation_id, kind, command, actor)

    def targets(
        self, game_id: UUID, operation_id: UUID, cursor: str | None, limit: int = PAGE_SIZE
    ) -> dict[str, Any]:
        return self.repository.targets(game_id, operation_id, cursor, limit)
