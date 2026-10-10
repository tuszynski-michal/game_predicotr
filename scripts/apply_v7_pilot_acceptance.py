"""Preview or explicitly apply one canonical owner-only V7 acceptance operation.

Default is a read-only preview. Apply requires the preserved UUID/body and an
exact decision reference supplied separately. No ordinary API activation route.
Run with an external process timeout <=120 seconds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast
from uuid import UUID

from game_predictor_api.domain.v7_pilot_acceptance import validate_pilot_acceptance
from game_predictor_api.domain.v7_selection_delivery import (
    V7PilotGate,
    V7SourcePolicy,
    payload_fingerprint,
)
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from game_predictor_api.storage.v7_pilot_acceptances import execute_v7_pilot_acceptance
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_pilot_configuration import V7PilotArtifacts
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from scripts.prepare_v7_reviewed_pilot import DATABASE, ROOT, _check_owner, _engine, _load


def candidate_gate(receipt: dict[str, object], generation: int) -> V7PilotGate:
    """Local validation candidate, never a persisted or runtime authorization."""
    return V7PilotGate(
        status="active",
        generation=generation,
        accepted=True,
        geometry_family_id=str(receipt["geometryFamilyId"]),
        source_game_ref=None if receipt["sourceGameRef"] is None else str(receipt["sourceGameRef"]),
        source_policy=cast(V7SourcePolicy, receipt.get("sourcePolicy", "exact_sources")),
        profile_fingerprint=str(receipt["profileFingerprint"]),
        observer_fingerprint=str(receipt["observerFingerprint"]),
        ocr_model_fingerprint=str(receipt["ocrModelFingerprint"]),
        source_bindings=tuple(cast(list[dict[str, object]], receipt["sourceBindings"])),
        receipt_fingerprint=payload_fingerprint(receipt),
        acceptance_receipt=receipt,
    )


def read_request(path: Path) -> tuple[UUID, int, dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {
        "operationId",
        "expectedGeneration",
        "receipt",
    }:
        raise ValueError("Acceptance request requires the exact canonical operation schema.")
    operation = UUID(str(value["operationId"]))
    generation = value["expectedGeneration"]
    receipt = value["receipt"]
    if str(operation) != value["operationId"] or type(generation) is not int or generation < 0:
        raise ValueError("Invalid operation UUID/generation.")
    if not isinstance(receipt, dict):
        raise ValueError("Missing canonical acceptance receipt.")
    return operation, generation, cast(dict[str, object], receipt)


def execute(
    path: Path, *, apply: bool = False, decision_reference: str | None = None
) -> dict[str, object]:
    settings = _load()
    if settings["phase"] != "ready":
        raise ValueError("Owner operation requires the ready isolated runtime/schema.")
    operation, generation, receipt = read_request(path)
    if apply and (
        not decision_reference or decision_reference != receipt["operatorDecisionReference"]
    ):
        raise ValueError("Apply requires the exact independently supplied decision reference.")
    main = ROOT.parents[2]
    candidate = candidate_gate(receipt, generation + 1)
    current_validated = False

    def prepare_new() -> None:
        nonlocal current_validated
        validate_pilot_acceptance(receipt, DATABASE)
        V7PilotArtifacts(
            main / ".runtime",
            main / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
            acceptance_scope=str(receipt["scope"]),
        ).validate(candidate)
        for binding in candidate.source_bindings:
            root = Path(str(binding["sourceRoot"]))
            manifest = build_local_source_manifest(
                root, selection_id=operation, display_name=root.name
            )
            candidate.snapshot_for(root, manifest.source_fingerprint)
        current_validated = True

    engine = _engine(make_url(str(settings["ownerDatabaseUrl"])))
    try:
        with engine.connect() as connection:
            _check_owner(connection, settings)
            connection.rollback()
            with Session(connection) as session, session.begin():
                if apply:
                    execution = execute_v7_pilot_acceptance(
                        session,
                        operation_id=operation,
                        expected_generation=generation,
                        receipt=receipt,
                        prepare_new=prepare_new,
                    )
                    resulting_generation = execution.receipt.resulting_generation
                    replayed = execution.replayed
                else:
                    prepare_new()
                    resulting_generation = None
                    replayed = False
                gate = SqlAlchemySemiAutomaticSelectionRepository(session).get_v7_pilot_gate()
                return {
                    "status": "applied" if apply else "preview",
                    "scope": receipt["scope"],
                    "operationId": str(operation),
                    "expectedGeneration": generation,
                    "resultingGeneration": resulting_generation,
                    "currentGateStatus": gate.status,
                    "currentGateGeneration": gate.generation,
                    "receiptFingerprint": payload_fingerprint(receipt),
                    "sourceBindings": list(candidate.source_bindings),
                    "sourcePolicy": candidate.source_policy,
                    "replayed": replayed,
                    "actualArtifactsValidated": current_validated,
                    "actualSourceInventoriesValidated": current_validated
                    and bool(candidate.source_bindings),
                    "automaticAllowed": False,
                    "countsTowardT12": False,
                    "gateChanged": apply and not replayed,
                    "operatorOutputsWritten": False,
                }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("request", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--decision-reference")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                execute(args.request, apply=args.apply, decision_reference=args.decision_reference)
            )
        )
    except Exception as error:
        result = {"status": "refused", "errorType": type(error).__name__}
        if isinstance(error, DBAPIError):
            result["sqlState"] = str(getattr(error.orig, "sqlstate", "unknown"))
        else:
            result["code"] = str(getattr(error, "code", "V7_ACCEPTANCE_REFUSED"))
        print(json.dumps(result))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
