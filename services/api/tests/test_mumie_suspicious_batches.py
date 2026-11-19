import json
from contextlib import closing
from uuid import uuid4

import pytest
from game_predictor_api.domain import mumie_suspicious_batch as policy
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.schemas.grid_reinference import GridReinferencePrepare
from pydantic import ValidationError

from scripts.mumie_suspicious_queue import driver_lock, finish, ledger, reserve, status


def test_ranked_batches_pause_at_boundary_and_recover_after_lost_reply(tmp_path):
    path = tmp_path / "queue.sqlite3"
    with closing(ledger(path)) as db, db:
        for seq in range(1, 104):
            pin = {"review": str(uuid4()), "sequence": seq, "score": float(seq // 3)}
            db.execute(
                "INSERT INTO boards(sequence,score,pin) VALUES(?,?,?)",
                (seq, pin["score"], json.dumps(pin)),
            )
        db.commit()
        assert reserve(db) is None
        db.execute("UPDATE control SET sealed=1")
        db.commit()
        batch = reserve(db)
        assert batch
        members = [
            json.loads(r[0])
            for r in db.execute(
                "SELECT pin FROM boards WHERE batch=? ORDER BY score DESC,sequence", (batch,)
            )
        ]
        assert (
            len(members) == 100 and members[0]["sequence"] == 102 and members[-1]["sequence"] == 4
        )
        with closing(ledger(path)) as other, other:
            other.execute("UPDATE control SET paused=1")
    with closing(ledger(path)) as db:
        assert reserve(db) == batch
        finish(db, batch, members, {members[0]["review"]: "automatic_written"}, "report-sha")
        assert reserve(db) is None
        assert status(db)["boards"] == {
            "automatic_written": 1,
            "protected_or_stale": 99,
            "waiting": 3,
        }
        with db:
            db.execute("UPDATE control SET paused=0")
        second = reserve(db)
        assert second and second != batch
        tail = [
            json.loads(r[0]) for r in db.execute("SELECT pin FROM boards WHERE batch=?", (second,))
        ]
        with pytest.raises(ValueError):
            finish(db, second, tail, {members[0]["review"]: "automatic_written"}, "bad")
        finish(db, second, tail, {}, "second-sha")
        assert status(db)["finished"] and reserve(db) is None


def test_driver_exclusion_released_on_close(tmp_path):
    with (
        driver_lock(tmp_path / "lock"),
        pytest.raises(RuntimeError),
        driver_lock(tmp_path / "lock"),
    ):
        pass
    with driver_lock(tmp_path / "lock"):
        pass


def test_opt_in_is_private_bounded_and_closed_to_http():
    command = {
        "suspiciousBatch": [{"sequence": 9, "score": 3.2, "review": "a"}],
        "idempotencyKey": str(uuid4()),
        "modelVersionId": str(policy.VERSION),
        "executionScope": "pilot",
        "selector": {"categories": ["unconfirmed"]},
    }
    assert policy.require_batch(policy.GAME, command) == command["suspiciousBatch"]
    with pytest.raises(ValidationError):
        GridReinferencePrepare.model_validate(command)
    for game, changes in (
        (uuid4(), {}),
        (policy.GAME, {"modelVersionId": str(uuid4())}),
        (policy.GAME, {"executionScope": "broader"}),
        (policy.GAME, {"selector": {"categories": ["all_automatic"]}}),
        (policy.GAME, {"suspiciousBatch": []}),
        (policy.GAME, {"suspiciousBatch": command["suspiciousBatch"] * 101}),
        (policy.GAME, {"suspiciousBatch": command["suspiciousBatch"] * 2}),
    ):
        with pytest.raises(JobConflictError):
            policy.require_batch(game, {**command, **changes})


def test_only_the_frozen_suspicious_geometry_can_be_replaced():
    from game_predictor_api.domain.grid_cut_suspicion import assess_grid_cut

    nodes = [{"x": float(x * 30), "y": float(y * 10)} for y in range(4) for x in range(6)]
    pin = {
        "sequence": 1,
        "position": 0,
        "board": "b",
        "source": "s",
        "job": "j",
        "review": "r",
        "resolution": 12,
        "revision": 4,
        "score": assess_grid_cut(nodes).score,
    }
    board = {
        "id": "b",
        "source_image_id": "s",
        "geometry_revision": 4,
        "approved_geometry_revision": None,
        "asset_mode": "virtual_source",
        "completeness_status": "complete",
        "unavailable_cell_indices": [],
        "board_geometry": {"latticeNodes": nodes},
    }
    review = {"id": "r", "status": "pending", "import_job_id": "j", "resolution_revision": 12}
    target = {
        "board": board,
        "review": review,
        "kind": "automatic",
        "positionIndex": 0,
        "sequenceNumber": 1,
        "cells": [],
    }
    assert policy.matches_snapshot(pin, target)
    for changed in (
        {"source_image_id": "other"},
        {"geometry_revision": 5},
        {"approved_geometry_revision": 4},
        {"completeness_status": "partial"},
        {"unavailable_cell_indices": [2]},
    ):
        assert not policy.matches_snapshot(pin, {**target, "board": {**board, **changed}})
    for changed in (
        {"kind": "grid_issue"},
        {"cells": [{"quality_issue": "blurry"}]},
        {"review": {**review, "status": "corrected"}},
        {"positionIndex": 1},
    ):
        assert not policy.matches_snapshot(pin, {**target, **changed})
