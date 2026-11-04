"""Controlled CPU fixtures: geometry, original-photo assessment and durable rescue."""

import copy
import os
import subprocess
import sys

import numpy as np
import pytest
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.geometry_core.rescue import GridRescueVariantV1
from game_predictor_worker.images.grid_cohort_dataset import (
    GridAssessmentDataset,
    GridBoardDataset,
    GridCohortDatasetError,
)
from game_predictor_worker.images.grid_rescue_runtime import RescueAttemptStore
from game_predictor_worker.images.grid_rescue_strategy import execute_path
from game_predictor_worker.training_core.grid_training_admission import (
    SCREEN_GRID_CORRECTIONS_V1,
    CohortCounts,
    estimate_cohort_cost,
    rescue_cost_factors,
)
from test_grid_cohort_dataset import SnapshotFixture


def detection(position=0, *, bad=True):
    x, y = (position % 3) * 100 + 10, (position // 3) * 90 + 10
    nodes = np.array(
        [(x + column * 10, y + row * 15) for row in range(4) for column in range(6)],
        dtype=np.float32,
    )
    item = BoardDetection(0.99, nodes[[0, 5, 23, 18]].copy())
    item.nodes = nodes
    item.raw_nodes = nodes.copy()
    item.reasons = ["NEURAL_GRID_FIT_OUTLIERS"] if bad else []
    return item


def variant():
    return GridRescueVariantV1(
        screen={"longSide": 1024, "trainCanvas": (1024, 768)}, board={"margin": 0.2}
    )


def test_new_trigger_requires_a_new_validated_routing_proof():
    baseline = [detection(position) for position in range(9)]

    def forbidden(*args):
        pytest.fail("An unvalidated routing callback must not spend inference budget.")

    result = execute_path(
        baseline,
        width=400,
        height=400,
        variant=variant(),
        path="combined",
        detect=forbidden,
        recrop=forbidden,
        trigger=lambda *args: True,
    )
    assert result.reasons == ("GRID_RESCUE_ROUTING_PROOF_REQUIRED",)
    assert result.redetect_calls == 0 and not result.crop_calls


@pytest.mark.parametrize("path", ["screen_only", "board_only", "combined"])
def test_actual_paths_use_the_correct_independent_overrides(path):
    value = variant()
    baseline = [detection(position, bad=position == 4) for position in range(9)]
    calls = []

    def detect(geometry):
        calls.append(("screen", geometry.longSide))
        return [detection(position, bad=False) for position in range(9)]

    def recrop(position, found, geometry):
        calls.append(("board", position, None if geometry is None else geometry.margin))
        return detection(position, bad=False)

    result = execute_path(
        baseline,
        width=400,
        height=400,
        variant=value,
        path=path,
        detect=detect,
        recrop=recrop,
        expected_positions=set(range(9)),
    )
    assert result.redetect_calls == (path != "board_only")
    assert result.crop_calls == {4: 1}
    assert calls == ([] if path == "board_only" else [("screen", 1024)]) + [
        ("board", 4, None if path == "screen_only" else 0.2)
    ]
    assert result.detections[4].reasons == []
    assert all(result.detections[i] is baseline[i] for i in range(9) if i != 4)


def test_ambiguous_slots_do_not_spend_budget_and_trigger_is_explicit():
    baseline = [detection(0), detection(0)]

    def forbidden(*args):
        raise AssertionError("Ambiguity must not run another network.")

    result = execute_path(
        baseline,
        width=400,
        height=400,
        variant=variant(),
        path="combined",
        detect=forbidden,
        recrop=forbidden,
    )
    assert result.reasons == ("GRID_RESCUE_SLOT_BINDING_REQUIRED",)
    baseline = [detection(i, bad=False) for i in range(9)]
    result = execute_path(
        baseline,
        width=400,
        height=400,
        variant=variant(),
        path="combined",
        detect=forbidden,
        recrop=forbidden,
    )
    assert result.reasons == ("GRID_RESCUE_NOT_TRIGGERED",)


def test_reservation_survives_new_process_and_changed_variant_cannot_renew_it(tmp_path):
    store = RescueAttemptStore(tmp_path, {"operation": "one", "source": "a", "variant": "old"})

    def interrupted():
        raise RuntimeError("after reservation before response")

    with pytest.raises(RuntimeError):
        store.attempt("redetect", {"geometry": 1024}, interrupted)
    script = """import sys
from pathlib import Path
from game_predictor_worker.images.grid_rescue_runtime import RescueAttemptStore
s=RescueAttemptStore(Path(sys.argv[1]),{'operation':'one','source':'a','variant':'old'})
def forbidden():
 raise AssertionError('budget renewed after restart')
assert s.attempt('redetect',{'geometry':1024},forbidden) is None
print(s.summary(())['attempts'][0]['state'])
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert result.stdout.strip() == "consumed_without_result"
    with pytest.raises(ValueError, match="CHECKPOINT_INVALID"):
        RescueAttemptStore(tmp_path, {"operation": "one", "source": "a", "variant": "new"}).attempt(
            "redetect", {"geometry": 1024}, lambda: []
        )


def test_completed_attempt_reuses_result_and_detects_corruption(tmp_path):
    store = RescueAttemptStore(tmp_path, {"operation": "one", "source": "a"})
    first = store.attempt("crop-4", {"geometry": 0.2}, lambda: [detection(4, bad=False)])

    def forbidden():
        raise AssertionError("lost API response must reuse completed work")

    second = RescueAttemptStore(tmp_path, store.identity).attempt(
        "crop-4", {"geometry": 0.2}, forbidden
    )
    np.testing.assert_array_equal(first[0].nodes, second[0].nodes)
    summary = store.summary(())
    assert summary["attempts"][0]["state"] == "completed"
    assert summary["attempts"][0]["resultSha256"] is not None
    (tmp_path / "crop-4.result.json").write_text("{}")
    with pytest.raises(ValueError, match="CHECKPOINT_INVALID"):
        store.attempt("crop-4", {"geometry": 0.2}, forbidden)


@pytest.mark.parametrize(
    "crash", ["before_fsync", "before_reserve_publish", "after_reserve", "before_result_publish"]
)
def test_atomic_receipts_survive_process_death_without_renewing_spent_budget(tmp_path, crash):
    script = """import os,sys
from pathlib import Path
from game_predictor_worker.images.grid_rescue_runtime import RescueAttemptStore
root, crash=Path(sys.argv[1]),sys.argv[2]
link,fsync=os.link,os.fsync
def publish(source,target):
 reserve=crash=='before_reserve_publish' and str(target).endswith('.reserved.json')
 result=crash=='before_result_publish' and str(target).endswith('.result.json')
 if reserve or result:
  os._exit(71)
 return link(source,target)
def sync(fd):
 if crash=='before_fsync': os._exit(71)
 return fsync(fd)
os.link,os.fsync=publish,sync
def calculate():
 with (root/'calculated').open('ab') as stream:
  stream.write(b'one');stream.flush();fsync(stream.fileno())
 if crash=='after_reserve': os._exit(71)
 return []
RescueAttemptStore(root,{'source':'same','pin':'same'}).attempt('redetect',{'geometry':1024},calculate)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), crash],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 71, child.stderr
    store = RescueAttemptStore(tmp_path, {"source": "same", "pin": "same"})
    calls = []
    result = store.attempt("redetect", {"geometry": 1024}, lambda: calls.append("one") or [])
    if crash in ("before_fsync", "before_reserve_publish"):
        assert calls == ["one"] and result == []
        assert not (tmp_path / "calculated").exists()  # no CPU before publication
        assert store.summary(())["attempts"][0]["state"] == "completed"
    else:
        assert calls == [] and result is None
        assert (tmp_path / "calculated").read_bytes() == b"one"
        assert store.summary(())["attempts"][0]["state"] == "consumed_without_result"


def test_baseline_interrupted_publication_and_alias_do_not_create_rescue_budget(
    monkeypatch, tmp_path
):
    import game_predictor_worker.images.grid_rescue_runtime as runtime

    identity = {"sourceSha256": "same", "pin": {"model": "same"}, "positions": [0, 1]}
    store = RescueAttemptStore(tmp_path, identity)
    link = runtime.os.link

    def interrupted(*args):
        raise RuntimeError("before baseline publication")

    monkeypatch.setattr(runtime.os, "link", interrupted)
    with pytest.raises(RuntimeError):
        store.baseline(lambda: [detection(0)])
    assert not (tmp_path / "baseline.json").exists()
    monkeypatch.setattr(runtime.os, "link", link)
    store.baseline(lambda: [detection(0)])
    stored = (tmp_path / "baseline.json").read_bytes()
    alias = RescueAttemptStore(tmp_path, {**identity, "positions": [4, 5]})
    alias.baseline(lambda: pytest.fail("Alias baseline must not be recalculated"))
    assert alias.position_alias and alias.identity == identity
    with pytest.raises(ValueError, match="SLOT_BINDING"):
        alias.attempt("crop-4", {}, lambda: pytest.fail("No alias rescue tokens"))
    assert alias.summary(())["attempts"] == []
    assert (tmp_path / "baseline.json").read_bytes() == stored
    for field, value in (("sourceSha256", "foreign"), ("pin", {"model": "foreign"})):
        with pytest.raises(ValueError, match="CHECKPOINT_INVALID"):
            RescueAttemptStore(tmp_path, {**identity, field: value}).baseline(lambda: [])


@pytest.mark.parametrize("content", ["", '{"identity":', "{}"])
def test_foreign_corrupt_receipts_are_not_treated_as_valid_crash_recovery(tmp_path, content):
    (tmp_path / "redetect.reserved.json").write_text(content)
    with pytest.raises(ValueError):
        RescueAttemptStore(tmp_path, {"source": "same"}).attempt(
            "redetect", {}, lambda: pytest.fail("Corrupt receipt renewed budget")
        )


def test_partial_regression_is_retained_but_optimizer_and_legacy_stay_full(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    source = fixture.source("REGRESSION")
    source["targets"] = [
        {**copy.deepcopy(source["targets"][0]), "positionIndex": i, "sequenceNumber": 17 + i}
        for i in range(3)
    ]
    snapshot = fixture.publish(
        mode="screen+grid",
        change=lambda root: root.update(
            schemaVersion="application-grid-snapshot-v3",
            policyVersion="application-grid-corrections-v3",
        ),
    )
    assert len(GridAssessmentDataset(snapshot, "REGRESSION")) == 3
    assert len(GridAssessmentDataset(snapshot, "REGRESSION").indexed()) == 1
    with pytest.raises(GridCohortDatasetError, match="nine full"):
        len(GridBoardDataset(snapshot, "REGRESSION"))
    with pytest.raises(GridCohortDatasetError):
        GridAssessmentDataset(snapshot, "VALIDATION")


def test_variant_cost_is_explicit_and_never_increases_the_step_budget():
    counts = CohortCounts(
        mode="screen+grid",
        train_photos=15,
        train_boards=135,
        train_full_photos=15,
        validation_photos=5,
        validation_boards=45,
        regression_photos=5,
        regression_boards=15,
    )
    base = estimate_cohort_cost(SCREEN_GRID_CORRECTIONS_V1, counts)
    changed = estimate_cohort_cost(
        SCREEN_GRID_CORRECTIONS_V1, counts, rescue_variant=variant().model_dump(mode="json")
    )
    assert changed.planned_steps < base.planned_steps
    assert changed.estimated_run_seconds > base.estimated_run_seconds
    assert rescue_cost_factors(variant().model_dump())[2] > 1
