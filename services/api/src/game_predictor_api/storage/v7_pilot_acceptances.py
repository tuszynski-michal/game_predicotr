"""Owner-only atomic activation command; ordinary selection API has no write entry point."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.v7_pilot_acceptance import validate_pilot_acceptance
from game_predictor_api.domain.v7_selection_delivery import V7DeliveryConflict, payload_fingerprint
from game_predictor_api.storage.models import (
    SemiAutomaticV7ActivationGateModel,
    V7PilotAcceptanceModel,
)


@dataclass(frozen=True, slots=True)
class V7PilotAcceptanceExecution:
    receipt: V7PilotAcceptanceModel
    replayed: bool


def apply_v7_pilot_acceptance(
    session: Session,
    *,
    operation_id: UUID,
    expected_generation: int,
    receipt: dict[str, object],
) -> V7PilotAcceptanceModel:
    """Preserve the existing owner command contract and replay semantics."""
    return execute_v7_pilot_acceptance(
        session, operation_id=operation_id, expected_generation=expected_generation, receipt=receipt
    ).receipt


def execute_v7_pilot_acceptance(
    session: Session,
    *,
    operation_id: UUID,
    expected_generation: int,
    receipt: dict[str, object],
    prepare_new: Callable[[], None] | None = None,
) -> V7PilotAcceptanceExecution:
    """Caller owns the transaction; exact replay precedes generation validation."""
    if type(expected_generation) is not int or expected_generation < 0:
        raise ValueError("Expected generation must be a nonnegative integer.")
    owner = session.execute(
        text(
            "SELECT current_user = pg_get_userbyid(c.relowner) "
            "FROM pg_class c WHERE c.oid = "
            "'public.semi_automatic_selection_v7_activation_gate'::regclass"
        )
    ).scalar_one()
    if not owner:
        raise V7DeliveryConflict(
            "V7_PILOT_OWNER_REQUIRED", "Only the schema owner may apply receipts."
        )
    request_fingerprint = payload_fingerprint(
        {"expectedGeneration": expected_generation, "receipt": receipt}
    )

    def replay() -> V7PilotAcceptanceModel | None:
        existing = session.get(V7PilotAcceptanceModel, operation_id, populate_existing=True)
        if existing is not None and existing.request_fingerprint != request_fingerprint:
            raise V7DeliveryConflict("V7_PILOT_OPERATION_ID_CONFLICT", "Activation body changed.")
        return existing

    existing = replay()
    if existing is not None:
        return V7PilotAcceptanceExecution(existing, replayed=True)
    database_name = session.scalar(select(func.current_database()))
    validate_pilot_acceptance(receipt, str(database_name))
    if prepare_new is not None:
        # Replay precedes current inventory/artifact checks; hashing precedes row locks.
        prepare_new()
    gate = session.scalar(
        select(SemiAutomaticV7ActivationGateModel)
        .where(SemiAutomaticV7ActivationGateModel.singleton.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # A concurrent identical apply may have committed while this command waited on gate.
    existing = replay()
    if existing is not None:
        return V7PilotAcceptanceExecution(existing, replayed=True)
    if gate is None or gate.pilot_generation != expected_generation:
        raise V7DeliveryConflict("V7_PILOT_GENERATION_CHANGED", "Activation generation changed.")
    fingerprint = payload_fingerprint(receipt)
    if (
        session.scalar(
            select(V7PilotAcceptanceModel.operation_id).where(
                V7PilotAcceptanceModel.receipt_fingerprint == fingerprint
            )
        )
        is not None
    ):
        raise V7DeliveryConflict("V7_PILOT_RECEIPT_ALREADY_APPLIED", "Receipt already applied.")
    result = V7PilotAcceptanceModel(
        operation_id=operation_id,
        request_fingerprint=request_fingerprint,
        receipt_fingerprint=fingerprint,
        receipt=receipt,
        expected_generation=expected_generation,
        resulting_generation=expected_generation + 1,
    )
    session.add(result)
    gate.pilot_status = "active"
    gate.pilot_generation = result.resulting_generation
    gate.pilot_mode = "semi_automatic"
    gate.pilot_geometry_family_id = str(receipt["geometryFamilyId"])
    gate.pilot_source_game_ref = (
        None if receipt["sourceGameRef"] is None else str(receipt["sourceGameRef"])
    )
    gate.pilot_source_policy = str(receipt.get("sourcePolicy", "exact_sources"))
    gate.pilot_profile_fingerprint = str(receipt["profileFingerprint"])
    gate.pilot_observer_fingerprint = str(receipt["observerFingerprint"])
    gate.pilot_ocr_model_fingerprint = str(receipt["ocrModelFingerprint"])
    bindings = receipt["sourceBindings"]
    assert isinstance(bindings, list)
    gate.pilot_source_bindings = bindings
    gate.pilot_acceptance_receipt_fingerprint = fingerprint
    gate.pilot_accepted_at = datetime.fromisoformat(str(receipt["acceptedAt"]))
    gate.pilot_accepted_by = str(receipt["actor"])
    session.flush()
    return V7PilotAcceptanceExecution(result, replayed=False)
