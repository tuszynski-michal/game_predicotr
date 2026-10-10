"""Pure pilot/source binding and immutable decision regressions."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.domain.v7_selection_delivery import (
    V7DeliveryConflict,
    V7OutputDecision,
    V7PilotGate,
    V7PilotSnapshot,
    payload_fingerprint,
)


def test_gate_is_blocked_without_full_accepted_identity(tmp_path: Path) -> None:
    for gate in (V7PilotGate(), V7PilotGate(status="active"), _gate(tmp_path, accepted=False)):
        assert not gate.enabled
        with pytest.raises(V7DeliveryConflict):
            gate.snapshot_for(tmp_path, "a" * 64)


def _gate(root: Path, *, accepted: bool = True) -> V7PilotGate:
    return V7PilotGate(
        status="active",
        generation=3,
        geometry_family_id="family-v2",
        source_game_ref="777",
        profile_fingerprint="1" * 64,
        observer_fingerprint="2" * 64,
        ocr_model_fingerprint="3" * 64,
        receipt_fingerprint="4" * 64,
        accepted=accepted,
        source_bindings=(
            {
                "sourceRoot": str(root.resolve()),
                "sourceFingerprint": "a" * 64,
                "geometryFamilyId": "family-v2",
                "sourceGameRef": "777",
            },
        ),
    )


def test_exact_root_inventory_game_family_and_generation(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    snapshot = gate.snapshot_for(tmp_path, "a" * 64)
    assert V7PilotSnapshot.from_payload(snapshot.as_payload()) == snapshot
    for altered in (
        replace(gate, generation=4),
        replace(gate, source_game_ref="other"),
        replace(gate, geometry_family_id="other"),
        replace(gate, ocr_model_fingerprint="f" * 64),
    ):
        with pytest.raises(V7DeliveryConflict):
            altered.require_snapshot(snapshot, tmp_path, "a" * 64)
    child = tmp_path / "777"
    child.mkdir()
    for root, fingerprint in ((child, "a" * 64), (tmp_path, "b" * 64)):
        with pytest.raises(V7DeliveryConflict):
            gate.snapshot_for(root, fingerprint)


def test_manual_decision_body_round_trip_and_confirmation() -> None:
    decision = V7OutputDecision(uuid4(), 5, 2, "a" * 64, "manual_no_ocr", 2, 8, True, True)
    assert V7OutputDecision.from_payload(decision.as_payload()) == decision
    fingerprint = payload_fingerprint(decision.as_payload())
    assert payload_fingerprint(dict(reversed(list(decision.as_payload().items())))) == fingerprint
    assert payload_fingerprint(replace(decision, range_end=7).as_payload()) != fingerprint
    with pytest.raises(V7DeliveryConflict):
        replace(decision, operator_confirmed_range=False)
    with pytest.raises(ValueError):
        replace(decision, kind="automatic_first")
    with pytest.raises(ValueError):
        replace(decision, kind="manual_replace")
