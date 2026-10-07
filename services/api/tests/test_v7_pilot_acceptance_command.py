"""Preserved CLI operations recover immutable history before mutable preflight."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.domain.v7_selection_delivery import V7DeliveryConflict, payload_fingerprint
from game_predictor_api.storage.models import V7PilotAcceptanceModel
from game_predictor_api.storage.v7_pilot_acceptances import (
    apply_v7_pilot_acceptance,
    execute_v7_pilot_acceptance,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
cli = importlib.import_module("scripts.apply_v7_pilot_acceptance")


class HistoricalSession:
    def __init__(self, row):
        self.row = row

    def execute(self, query):
        class Owner:
            def scalar_one(self):
                return True

        return Owner()

    def get(self, model, operation_id, **kwargs):
        assert operation_id == self.row.operation_id
        return self.row

    def scalar(self, query):
        raise AssertionError("Historical replay must not reach current generation or paths.")


def test_historical_command_skips_later_generation_and_current_artifact_drift():
    operation = uuid4()
    receipt = {"historical": "immutable body"}
    row = V7PilotAcceptanceModel(
        operation_id=operation,
        resulting_generation=1,
        request_fingerprint=payload_fingerprint({"expectedGeneration": 0, "receipt": receipt}),
    )
    session = HistoricalSession(row)

    def current_drift():
        raise AssertionError("Mutable current inventory/artifact drift must not block history.")

    execution = execute_v7_pilot_acceptance(
        session,
        operation_id=operation,
        expected_generation=0,
        receipt=receipt,
        prepare_new=current_drift,
    )
    assert execution.receipt is row and execution.replayed is True
    assert (
        apply_v7_pilot_acceptance(
            session, operation_id=operation, expected_generation=0, receipt=receipt
        )
        is row
    )
    with pytest.raises(V7DeliveryConflict) as error:
        execute_v7_pilot_acceptance(
            session,
            operation_id=operation,
            expected_generation=0,
            receipt={"historical": "changed body"},
            prepare_new=current_drift,
        )
    assert error.value.code == "V7_PILOT_OPERATION_ID_CONFLICT"


@pytest.mark.parametrize("revision", [True, "0", 0.0, {}])
def test_cli_strict_expected_generation(tmp_path, revision):
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "operationId": str(uuid4()),
                "expectedGeneration": revision,
                "receipt": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        cli.read_request(request)


def test_cli_apply_requires_exact_separate_decision_before_any_connection(tmp_path, monkeypatch):
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "operationId": str(uuid4()),
                "expectedGeneration": 0,
                "receipt": {"operatorDecisionReference": "exact reviewed decision"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_load", lambda: {"phase": "ready"})

    def forbidden(*args, **kwargs):
        raise AssertionError("Decision mismatch must precede connections/current IO.")

    monkeypatch.setattr(cli, "_engine", forbidden)
    with pytest.raises(ValueError, match="exact independently"):
        cli.execute(request, apply=True, decision_reference="other decision")
