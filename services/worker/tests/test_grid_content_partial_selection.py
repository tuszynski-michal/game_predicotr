"""Real frozen partial A across selection/calibration, with explicit inference fixtures."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_worker.images import grid_content_experiment_data as data
from game_predictor_worker.images.full_board_calibration_run import FullBoardCalibrationRun
from game_predictor_worker.images.grid_cohort_dataset import (
    GridBoardDataset,
    GridCohortDatasetError,
)
from game_predictor_worker.images.grid_model_evaluation_handler import (
    GridModelEvaluationJobHandler,
    _write_atomic,
)
from game_predictor_worker.images.grid_rescue_strategy import completeness_routing
from game_predictor_worker.images.production_cell_run import ProductionContentRun
from test_grid_model_evaluation import Context
from test_production_cell_frozen_pipeline import Engine, frozen_fixture
from test_production_cell_observations import board_preset


def partial_snapshot(root, *, content=True, train=False):
    fixture, old, rows = frozen_fixture(root)
    split = deepcopy(old.manifest["photoSplit"])
    if not content:
        split.pop("contentSampling")
    if train:
        source = fixture.source("TRAIN")
        source.update(validationPurpose=None, purposeProofSha256="d" * 64)
        split["sources"].append(
            {
                "sourceId": source["sourceId"],
                "role": "TRAIN",
                "validationPurpose": None,
                "purposeProofSha256": "d" * 64,
                "representative": True,
                "eligibleBoards": 1,
                "componentIds": [],
            }
        )
    split["sha256"] = digest({key: value for key, value in split.items() if key != "sha256"})
    snapshot = fixture.publish(
        mode="screen+grid",
        change=lambda doc: doc.update(
            schemaVersion="application-grid-snapshot-v4",
            policyVersion="application-grid-corrections-v4",
            photoSplit=split,
        ),
    )
    return fixture, snapshot, rows


@pytest.mark.parametrize("arm", ["R0", "R2"])
def test_partial_a_actual_selection_calibration_and_minima_stay_bound(tmp_path, monkeypatch, arm):
    fixture, snapshot, rows = partial_snapshot(tmp_path)
    nodes = np.asarray([[p["x"], p["y"]] for p in rows[0]["targets"][0]["nodes"]], np.float32)

    class Predict(Engine):
        def detect(self, rgb, **kwargs):
            return self.analyse(rgb)

        def recrop(self, rgb, detection, **kwargs):
            return self.analyse(rgb)[0]

    base, candidate = Predict(nodes), Predict(nodes)
    base.settings.board = candidate.settings.board = board_preset(0.15)
    routing = completeness_routing(
        {"policy": "validation-purpose-a-v1", "sha256": "c" * 64}, candidate.settings.board
    )
    monkeypatch.setattr(data, "torch_engine", lambda *a: candidate)
    selection = data.ContentSelectionEvaluator(
        [snapshot],
        base,
        SimpleNamespace(board=candidate.settings.board),
        "cpu",
        arm,
        lambda: 200,
        lambda: None,
        routing,
    )(None)
    assert selection["games"][0]["quality"]["candidate"]["boards_expected"] == 1
    assert selection["games"][0]["auxiliary"]["candidateUsablePhotos"] == 0
    engines = (base, data.ContentAssessmentEngine(candidate, routing) if arm == "R2" else candidate)
    job = SimpleNamespace(
        id=uuid4(),
        input_payload={"evaluation_kind": "grid-correction-evaluation-v1"},
        cancel_requested_at=None,
    )
    calibration = FullBoardCalibrationRun(
        root=tmp_path,
        job_id=job.id,
        snapshot=snapshot,
        candidate_sha="a" * 64,
        baseline_sha="b" * 64,
        engines=engines,
        write=_write_atomic,
    )
    assert {s["sourceId"] for s, _ in calibration.rows["A"]} == {rows[0]["sourceId"]}
    assert {s["sourceId"] for s, _ in calibration.rows["B"]} == {rows[1]["sourceId"]}
    production = ProductionContentRun(snapshot)
    handler = GridModelEvaluationJobHandler(None, tmp_path, threads=1)
    context = Context(job)
    state = {"units": {}, "reportSha256": None, "proven": []}
    groups = {s["sourceId"]: s["sourceId"] for s in rows}
    entry = {"game_id": fixture.game, "cohort_id": fixture.cohort}
    for role in ("VALIDATION", "REGRESSION"):
        if role == "REGRESSION":
            calibration.prepare_b(lambda _: None)
        handler._measure_unit(
            context, job, state, 1, entry, role, snapshot, groups, engines, calibration, production
        )
    result = calibration.finish()
    assert result["state"] == "unqualified" and result["profile"] is None
    assert any(reason.startswith("CALIBRATION_MINIMUM:") for reason in result["reasonCodes"])
    assert production.finish(tmp_path, job.id)["roles"]["REGRESSION"]["fullPhotos"] == 0


def test_partial_gate_never_enables_legacy_train_or_b(tmp_path):
    _, legacy, _ = partial_snapshot(tmp_path / "legacy", content=False)
    with pytest.raises(GridCohortDatasetError) as denied:
        GridBoardDataset(legacy, "VALIDATION").indexed()
    assert denied.value.code == "FULL_PHOTO_REQUIRED"
    _, snapshot, rows = partial_snapshot(tmp_path / "new", train=True)
    with pytest.raises(GridCohortDatasetError) as denied:
        GridBoardDataset(snapshot, "TRAIN").indexed()
    assert denied.value.code == "FULL_PHOTO_REQUIRED"
    reader = GridBoardDataset(snapshot, "VALIDATION")
    assert {s["sourceId"] for s, _ in reader.indexed()} == {rows[0]["sourceId"]}
    reader.validation_purpose = "B"
    with pytest.raises(GridCohortDatasetError) as denied:
        reader.indexed()
    assert denied.value.code == "FULL_PHOTO_REQUIRED"
