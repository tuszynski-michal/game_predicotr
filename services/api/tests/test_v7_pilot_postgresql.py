"""Opt-in real PostgreSQL regression confined by the owned pilot URL guards."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


@pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_R3_ISOLATED_POSTGRES") != "1",
    reason="Requires the explicitly prepared isolated TASK-0853 database/role.",
)
def test_real_runtime_role_compliance_and_locking_selects() -> None:
    from scripts.prepare_v7_reviewed_pilot import check

    # Includes the regclass/boolean-parameter query that failed only on real PG.
    result = check()
    assert result["compliant"] is True
    assert result["lockingSelects"] == "passed"
    assert result["gateUpdateColumns"] == ["singleton"]
    assert result["protectedMutationDenials"] == {
        "gate_status": "42501",
        "gate_generation": "42501",
        "singleton_constraint": "23514",
        "receipt_insert": "42501",
        "receipt_update": "42501",
        "receipt_delete": "42501",
        "receipt_truncate": "42501",
    }
