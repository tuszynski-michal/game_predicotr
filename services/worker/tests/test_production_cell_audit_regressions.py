"""R1 regressions on real frozen rosters and observers; no model qualification claim."""

import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from game_predictor_api.domain.input_edge_clearance import (
    InputEdgeReference,
    select_input_edge_threshold,
)
from game_predictor_worker.images.full_board_calibration_run import FullBoardCalibrationRun
from game_predictor_worker.images.grid_cohort_dataset import GridAssessmentDataset
from game_predictor_worker.images.grid_model_evaluation_handler import (
    GridModelEvaluationJobHandler,
    _write_atomic,
)
from game_predictor_worker.images.production_cell_run import ProductionContentRun
from game_predictor_worker.training_core.grid_correction_metrics import evaluate_photo
from game_predictor_worker.training_core.grid_evaluation import predictions
from test_production_cell_frozen_pipeline import Engine, frozen_fixture


@pytest.mark.parametrize("omitted", ["none", "one", "all", "pin"])
def test_fresh_regression_filters_copies_and_unlabelled_but_requires_every_eligible_source(
    tmp_path, omitted
):
    def configure(fixture, rows, split):
        original = rows[2]
        copy = fixture.source("REGRESSION", used=False)
        copy["sourceIdentity"] = deepcopy(original["sourceIdentity"])
        copy["targets"] = deepcopy(original["targets"])
        unlabelled = fixture.source("REGRESSION", used=False)
        unlabelled["targets"] = []
        for source, representative, eligible in ((copy, False, 1), (unlabelled, True, 0)):
            split["contentSampling"]["sourceIds"].append(source["sourceId"])
            split["sources"].append(
                {
                    "sourceId": source["sourceId"],
                    "role": "REGRESSION",
                    "validationPurpose": None,
                    "representative": representative,
                    "eligibleBoards": eligible,
                    "purposeProofSha256": "d" * 64,
                    "componentIds": [],
                }
            )
        if omitted in ("one", "all"):
            for source in rows[2:3] if omitted == "one" else rows[2:]:
                source["used"] = False
        if omitted == "pin":
            # Unknown selected roster membership must not silently disappear in the filter.
            split["sources"] = [p for p in split["sources"] if p["sourceId"] != copy["sourceId"]]

    fixture, snapshot, _ = frozen_fixture(tmp_path, regression_photos=5, configure=configure)
    run = ProductionContentRun(snapshot)
    job_id = uuid4()
    documents = {
        role: {"gameId": fixture.game, "jobId": str(job_id), "role": role, "photos": []}
        for role in ("VALIDATION", "REGRESSION")
    }
    result = run.finish(tmp_path, job_id, verified_details=documents)
    assert result["freshRegression"] is (omitted == "none")
    assert (
        len(list(GridAssessmentDataset(snapshot, "REGRESSION").indexed()))
        == {"none": 5, "one": 4, "all": 0, "pin": 5}[omitted]
    )
    # This isolated roster proof has no measured photos; it cannot weaken fullREG5 or qualify.
    assert result["roles"]["REGRESSION"]["state"] == "not_evaluable"
    assert result["roles"]["REGRESSION"]["fullPhotos"] == 0


@pytest.mark.parametrize("case", ["clean", "tie", "missing_input"])
def test_a_input_label_requires_bound_unambiguous_observer_evidence(tmp_path, case):
    fixture, snapshot, rows = frozen_fixture(tmp_path)
    nodes = np.asarray([[p["x"], p["y"]] for p in rows[0]["targets"][0]["nodes"]], np.float32)
    engines = Engine(nodes), Engine(nodes)
    calibration = FullBoardCalibrationRun(
        root=tmp_path,
        job_id=uuid4(),
        snapshot=snapshot,
        candidate_sha="a" * 64,
        baseline_sha="b" * 64,
        engines=engines,
        write=_write_atomic,
    )
    handler = GridModelEvaluationJobHandler(None, tmp_path, threads=1)
    photo = handler._photos(
        snapshot, "VALIDATION", {s["sourceId"]: s["sourceId"] for s in rows}, correction=True
    )[0]
    rgb, source_box = photo.load_with_support()
    photo = replace(photo, available_source_box=source_box)
    observed = {}
    for name, engine in zip(("base", "candidate"), engines, strict=True):
        found = engine.analyse(rgb)
        if case == "tie" and name == "candidate":
            found.append(deepcopy(found[0]))
        measured = evaluate_photo(
            photo.source_id,
            photo.group_id,
            list(photo.labels),
            predictions(found),
            full_geometry=photo.full_geometry,
        )
        observed[name] = found, measured, engine
    production = ProductionContentRun(snapshot).observer("VALIDATION")(photo, rgb, observed)
    candidate = production["boards"][0]["candidate"]
    if case == "tie":
        assert candidate["matchAmbiguous"] is True and candidate["inputEvidence"] is None
    if case == "missing_input":
        assert candidate["matchAmbiguous"] is False and candidate["inputEvidence"] is not None
        candidate["inputEvidence"] = (
            None  # authoritative missing input witness at observer boundary
        )
    observer = calibration.observer("VALIDATION")
    observer.production_observation = production
    assessment = observer(photo, rgb, observed)
    edge = InputEdgeReference.model_validate(assessment[0]["inputEdgeReference"])
    _, counts = select_input_edge_threshold([edge], calibration.routing_sha)
    assert counts["nTargets"] == (1 if case == "clean" else 0)
    assert (edge.referenceKind == "verified_content") is (case == "clean")
    assert len(observer.input_proofs) == (1 if case == "clean" else 0)


def test_worker_summarizes_exact_verified_documents_after_file_replacement(tmp_path):
    fixture, snapshot, _ = frozen_fixture(tmp_path)
    run = ProductionContentRun(snapshot)
    handler = GridModelEvaluationJobHandler(None, tmp_path, threads=1)
    job = SimpleNamespace(id=uuid4())
    state = {"units": {}}
    paths = []
    import hashlib

    for role in ("VALIDATION", "REGRESSION"):
        relative = f"grid-model-evaluations/{job.id}/{fixture.game}-{role}.json"
        payload = json.dumps(
            {"gameId": fixture.game, "jobId": str(job.id), "role": role, "photos": []}
        ).encode()
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        paths.append(path)
        state["units"][f"{fixture.game}:{role}"] = {
            "detail": {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
        }
    verified = handler._verify_details(job, state, [{"game_id": fixture.game}])
    for path in paths:
        path.write_bytes(b"replaced after checksum verification")
    result = run.finish(
        tmp_path,
        job.id,
        verified_details={
            role: verified[f"{fixture.game}:{role}"] for role in ("VALIDATION", "REGRESSION")
        },
    )
    assert result["roles"]["REGRESSION"]["photos"] == 0
    from game_predictor_worker.jobs.runtime import JobHandlerError

    with pytest.raises(JobHandlerError, match="differs"):
        handler._verify_details(job, state, [{"game_id": fixture.game}])
