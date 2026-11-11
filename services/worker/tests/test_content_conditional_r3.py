"""Conditional R3 is a new pinned policy; historical required-arm semantics remain closed."""

import json
from copy import deepcopy

import pytest
from game_predictor_worker.training_core.grid_content_experiment import (
    R3_ADMISSION_POLICY,
    advance_state,
    init_state,
    require_plan,
    require_state,
    select_winner,
    selection_record,
    skip_unready_r3,
    start_arm,
)
from game_predictor_worker.training_core.grid_training_admission import digest
from test_grid_content_experiment import closed_plan, game
from test_grid_content_experiment_workflow import LostResponse, WorkflowFixture


def conditional(plan):
    result = {**plan, "r3AdmissionPolicy": R3_ADMISSION_POLICY}
    result["sha256"] = digest({key: value for key, value in result.items() if key != "sha256"})
    return require_plan(result)


def completed_three(plan):
    state = init_state(plan, "a" * 64)
    for arm in ("R0", "R1", "R2"):
        state = start_arm(plan, state, arm, feasible_seconds=1000)
        state = advance_state(
            plan,
            state,
            arm,
            completed_steps=1200,
            charged_seconds=100,
            checkpoint_sha256="b" * 64,
            selection=selection_record([game(damaged=1, usable=8)], arm, 1200),
            complete=True,
        )
    return state


def test_new_policy_retains_failed_a_proposal_and_never_claims_r3_training():
    plan = conditional(closed_plan())
    state = completed_three(plan)
    with pytest.raises(ValueError, match="R3_NOT_ELIGIBLE"):
        skip_unready_r3(plan, state, human_labels_ready=True)
    skipped = skip_unready_r3(plan, state, human_labels_ready=False)
    result = select_winner(plan, skipped)
    assert result["selectedArm"] == "R0"
    assert result["arms"]["R0"]["selection"]["gatePassed"] is False
    assert result["arms"]["R3"] == {
        "status": "skipped_not_ready",
        "completedSteps": 0,
        "chargedSeconds": 0.0,
        "checkpointSha256": None,
        "selection": None,
    }
    assert result["r3SkipReason"] == "CONTENT_EXPERIMENT_R3_LABELS_REQUIRED"
    assert result["chargedSeconds"] == state["chargedSeconds"] == 300
    assert require_state(plan, json.loads(json.dumps(result))) == result
    with pytest.raises(ValueError, match="START_INVALID"):
        start_arm(plan, result, "R3", feasible_seconds=1000, human_labels_ready=True)


def test_legacy_plan_cannot_gain_optional_r3_by_resigning_state():
    legacy = closed_plan()
    state = completed_three(legacy)
    with pytest.raises(ValueError, match="R3_NOT_ELIGIBLE"):
        skip_unready_r3(legacy, state, human_labels_ready=False)
    with pytest.raises(ValueError, match="REQUIRED_ARM_INCOMPLETE"):
        select_winner(legacy, state)
    forged = deepcopy(state)
    forged["arms"]["R3"]["status"] = "skipped_not_ready"
    forged["sha256"] = digest({key: value for key, value in forged.items() if key != "sha256"})
    with pytest.raises(ValueError, match="STATE_INVALID"):
        require_state(legacy, forged)


def test_conditional_r3_skip_survives_lost_export_response_without_new_budget(
    tmp_path, monkeypatch
):
    fixture = WorkflowFixture(tmp_path, monkeypatch, r2_fail=True, labels=False)
    fixture.plan = conditional(fixture.plan)
    fixture.plan["exportEvaluationPolicy"] = "full-a-content-v1"
    fixture.plan["sha256"] = digest(
        {key: value for key, value in fixture.plan.items() if key != "sha256"}
    )
    fixture.spec["contentExperiment"] = fixture.plan
    import game_predictor_worker.images.grid_content_consistency as consistency

    verified = []
    monkeypatch.setattr(
        consistency,
        "verify_content_export",
        lambda evaluator, *args, **kwargs: verified.append(
            (evaluator.arm, kwargs["selected"]["step"])
        ),
    )
    fixture.lost_response = True
    with pytest.raises(LostResponse):
        fixture.invoke()
    first = fixture.ledger()
    assert first["state"]["arms"]["R3"]["status"] == "skipped_not_ready"
    assert first["state"]["r3SkipReason"] == "CONTENT_EXPERIMENT_R3_LABELS_REQUIRED"
    assert [arm for arm, _ in fixture.train_calls] == ["R0", "R1", "R2"]
    fixture.resume()
    result = fixture.invoke()
    assert result["steps"] == 3600
    assert fixture.ledger()["state"] == first["state"]
    assert fixture.final_exports == fixture.bank_calls == 1 and fixture.cached_exports == 1
    assert fixture.spec["budget"]["remainingSteps"] == 1200
    assert fixture.spec["budget"]["remainingSeconds"] < 7200
    assert verified == [("R0", 200), ("R1", 200), ("R2", 200), ("R0", 200)]
