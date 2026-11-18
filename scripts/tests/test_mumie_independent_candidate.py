from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import mumie_grid_pilot as pilot


@pytest.mark.parametrize(
    ("schema", "marker", "job_mode", "accept"),
    [
        (2, pilot.GAME, "from_scratch", True),
        (2, None, "from_scratch", False),
        (2, "other-game", "from_scratch", False),
        (2, pilot.GAME, "assigned_weights", False),
        (1, None, None, True),
    ],
)
def test_blind_candidate_requires_matching_independent_training_evidence(
    monkeypatch, schema, marker, job_mode, accept
):
    manifest = {
        "versionId": "candidate",
        "baseVersionId": "comparison",
        "provenance": {
            "runId": "run",
            "weightInitialization": "from_scratch",
            "independentGameId": marker,
        },
    }
    candidate = {"manifest": manifest}
    monkeypatch.setattr(pilot, "model", lambda *args: candidate)
    study = {
        "schema": schema,
        "base": {"active": "comparison"},
        "frozenAt": "2026-11-17T00:00:00+00:00",
        "requiredIndependentGameId": pilot.GAME,
    }
    run = SimpleNamespace(
        created_at=datetime(2026, 11, 18, tzinfo=UTC),
        input_payload={
            "weight_initialization": job_mode,
            "private_learning": {"gameId": pilot.GAME},
        },
    )
    replies = iter([SimpleNamespace(one=lambda: run), SimpleNamespace(first=lambda: None)])
    conn = SimpleNamespace(execute=lambda *args: next(replies))
    if accept:
        assert pilot.decision_evidence(conn, study, "candidate", Path(".")) == (
            candidate,
            False,
            None,
        )
    else:
        with pytest.raises(ValueError, match="niezależnym"):
            pilot.decision_evidence(conn, study, "candidate", Path("."))
