"""Worker boundary regressions; small fixtures do not claim operator model quality."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from game_predictor_worker.images.grid_content_experiment_data import auxiliary, verify_inputs
from game_predictor_worker.images.grid_content_experiment_run import ArmControl, ExperimentLedger
from game_predictor_worker.training_core.grid_content_experiment import start_arm
from test_grid_content_experiment import closed_plan


def test_final_validation_renews_lease_without_reserving_step_4801(tmp_path, monkeypatch):
    from game_predictor_worker.images import grid_training_child as child

    clock = [0.0]
    renewals = []
    monkeypatch.setattr(child.time, "monotonic", lambda: clock[0])
    control = child.ChildControl(
        {"budget": {"remainingSeconds": 100, "remainingSteps": 4800}, "resume": None},
        tmp_path,
        SimpleNamespace(renew=lambda record: renewals.append(record) or record),
        "lease",
    )
    monkeypatch.setattr(control, "_supervisor_alive", lambda: True)
    monkeypatch.setattr(
        control, "_wait_for_allowance", lambda step: pytest.fail("reserved step 4801")
    )
    control.counter["step"] = 4800
    clock[0] = 30.0
    ledger = SimpleNamespace(
        state={"arms": {"R3": {"completedSteps": 1200}}},
        charge=lambda arm: None,
    )
    ArmControl(control, ledger, "R3").check()
    assert renewals == ["lease"] and control.counter["step"] == 4800
    clock[0] = 100.0
    with pytest.raises(child.TrainingInterrupted, match="RUN_BUDGET_EXHAUSTED"):
        ArmControl(control, ledger, "R3").check()


def test_old_receipt_identity_is_not_extended_or_given_a_new_budget(tmp_path):
    # Literal pre-T4 receipt encoding, independent from the current writer.
    import hashlib

    from game_predictor_worker.images.grid_rescue_runtime import RescueAttemptStore

    identity = {"operation": "old", "source": "a", "variant": "legacy"}
    request = {"geometry": 1024}
    body = {"identity": identity, "payload": {"state": "reserved", "request": request}}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    receipt = json.dumps(
        {**body, "sha256": hashlib.sha256(encoded).hexdigest()},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path = tmp_path / "redetect.reserved.json"
    path.write_bytes(receipt)
    store = RescueAttemptStore(tmp_path, identity)
    assert store.attempt("redetect", request, lambda: pytest.fail("renewed legacy budget")) is None
    report = store.summary(())
    assert report["preprocessingContract"] == "neural-grid-rescue-preprocessing-v1"
    assert report["identity"] == identity
    assert "preprocessingContract" not in store.identity
    assert path.read_bytes() == receipt
    assert report["attempts"][0]["state"] == "consumed_without_result"
    with pytest.raises(ValueError, match="GRID_RESCUE_CHECKPOINT_INVALID"):
        RescueAttemptStore(
            tmp_path, {**identity, "preprocessingContract": "neural-grid-content-preprocessing-v1"}
        ).attempt("redetect", request, lambda: pytest.fail("renewed changed-contract budget"))


def test_union_damage_counts_one_fixed_cell_once_and_ignores_unknown():
    before = {
        "finalContentState": "preserved",
        "wrongCell": False,
        "tie": False,
        "foreignFullSymbol": False,
    }
    after = {
        "finalContentState": "clipped",
        "wrongCell": True,
        "tie": True,
        "foreignFullSymbol": True,
    }
    photo = {
        "fullGeometry": False,
        "boards": [
            {
                "base": {"usable": True, "matchAmbiguous": False},
                "candidate": {"usable": False, "matchAmbiguous": True},
                "cells": [
                    {"contentState": "visible", "base": before, "candidate": after},
                    {"contentState": "unknown"},
                ],
            }
        ],
    }
    result = auxiliary([photo])
    assert result["newDamagedInstances"] == 1
    assert result["newClipped"] == 1
    assert result["baselineUsablePhotos"] == result["candidateUsablePhotos"] == 0


def test_each_a_checkpoint_uses_current_weights_and_new_photo_local_one_plus_one_budget():
    import numpy as np
    from game_predictor_worker.images.grid_content_experiment_data import ContentAssessmentEngine
    from game_predictor_worker.images.grid_rescue_strategy import completeness_routing
    from test_production_cell_observations import board_preset
    from test_screen_rescue_contract import detection

    class Engine:
        epoch = 1

        def __init__(self):
            self.calls = []

        def analyse(self, rgb):
            self.calls.append(("base", self.epoch))
            return [detection(i, bad=i == 4) for i in range(9)]

        def detect(self, rgb, *, geometry):
            self.calls.append(("screen", self.epoch, geometry.longSide))
            return [detection(i, bad=False) for i in range(9)]

        def recrop(self, rgb, found, *, geometry):
            self.calls.append(("board", self.epoch, geometry.canvas))
            found.score = 0.6 + self.epoch * 0.1
            return found

    core = Engine()
    engine = ContentAssessmentEngine(
        core,
        completeness_routing(
            {"policy": "validation-purpose-a-v1", "sha256": "a" * 64}, board_preset()
        ),
    )
    pixels = np.zeros((400, 400, 3), np.uint8)
    first = engine.analyse(pixels)
    assert engine.last_result.redetect_calls == 1 and engine.last_result.crop_calls == {4: 1}
    core.epoch = 2
    second = engine.analyse(pixels)
    assert engine.last_result.redetect_calls == 1 and engine.last_result.crop_calls == {4: 1}
    assert first[4].score == pytest.approx(0.7) and second[4].score == pytest.approx(0.8)
    assert core.calls == [
        ("base", 1),
        ("screen", 1, 1280),
        ("board", 1, (480, 288)),
        ("base", 2),
        ("screen", 2, 1280),
        ("board", 2, (480, 288)),
    ]


def test_ledger_charges_setup_and_restart_gap_and_persists_before_parent_pointer(tmp_path):
    plan, bank = closed_plan(), {"sha256": "b" * 64}
    clock = [30.0]
    ledger = ExperimentLedger(
        tmp_path / "ledger.json",
        plan,
        bank,
        {"budget": {"chargedSeconds": 10}},
        lambda: clock[0],
        started=0,
    )
    assert ledger.arm_seconds("R0") == 40
    ledger.value["state"] = start_arm(plan, ledger.state, "R0", feasible_seconds=1000)

    class Parent:
        def checkpoint_published(self, path, sha, step):
            stored = json.loads(ledger.path.read_bytes())
            assert stored["checkpoints"]["R0"]["localStep"] == step == 200
            assert stored["state"]["arms"]["R0"]["checkpointSha256"] == sha

    ArmControl(Parent(), ledger, "R0").checkpoint_published(tmp_path / "x.pt", "c" * 64, 200)
    assert ledger.state["arms"]["R0"]["chargedSeconds"] == 40
    spec = {"budget": {"chargedSeconds": 75}}
    restarted = ExperimentLedger(ledger.path, plan, bank, spec, lambda: 100)
    assert restarted.arm_seconds("R0") == 75
    restarted.charge("R0")
    assert restarted.state["arms"]["R0"]["completedSteps"] == 200
    assert restarted.state["chargedSeconds"] == 75
    files = tmp_path / "pins.json"
    files.write_text(json.dumps({"plan": plan, "bank": bank, "spec": spec}), encoding="utf-8")
    code = """import json,sys
from pathlib import Path
from game_predictor_worker.images.grid_content_experiment_run import ExperimentLedger
p=json.loads(Path(sys.argv[1]).read_text())
l=ExperimentLedger(Path(sys.argv[2]),p['plan'],p['bank'],p['spec'],lambda:100)
assert l.state['chargedSeconds']==75 and l.state['arms']['R0']['completedSteps']==200
print('cold-ledger-pass')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(files), str(ledger.path)],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert "cold-ledger-pass" in result.stdout


def test_server_proof_is_bound_to_used_frozen_source_and_role(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "api" / "tests"))
    from test_grid_content_experiment_inputs import inputs_fixture

    args, inputs, plan = inputs_fixture()
    split = deepcopy(args["split"])
    rows = [
        {
            "sourceId": p["sourceId"],
            "used": True,
            "role": p["role"],
            "sourceIdentity": {
                "checksum_sha256": p["sourceSha256"],
                "normalized_pixel_checksum_sha256": p["pixelSha256"],
            },
        }
        for p in split["sources"]
    ]
    snapshot = SimpleNamespace(
        manifest={"gameId": args["game"], "photoSplit": split},
        manifest_sha256=plan["cohorts"][0]["manifestSha256"],
        sources=lambda: iter(rows),
    )
    verify_inputs(plan, inputs, [snapshot])
    # Legal closure at preview differs from the historical split's older registry proof.
    assert (
        inputs["trainEligibility"]["games"][0]["sources"][0]["closure"]["proofSha256"]
        != split["sources"][0]["registryProofSha256"]
    )
    rows[0]["role"] = "VALIDATION"
    with pytest.raises(ValueError, match="CONTENT_EXPERIMENT_TRAIN_ROSTER_CHANGED"):
        verify_inputs(plan, inputs, [snapshot])
    rows[0]["role"] = "TRAIN"
    rows[0]["used"] = False
    with pytest.raises(ValueError, match="CONTENT_EXPERIMENT_TRAIN_ROSTER_CHANGED"):
        verify_inputs(plan, inputs, [snapshot])
