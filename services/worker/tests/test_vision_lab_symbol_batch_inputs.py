"""Qualified feedback inference gates without changing legacy batch defaults."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from game_predictor_worker.vision_lab import symbol_batch, symbol_feedback
from game_predictor_worker.vision_lab import symbol_batch_inputs as module
from game_predictor_worker.vision_lab.annotations import write_atomic
from game_predictor_worker.vision_lab.run_contracts import (
    Artifact,
    RunState,
    StartRunRequest,
    TrainingConfiguration,
)
from game_predictor_worker.vision_lab.snapshot import canonical, sha
from game_predictor_worker.vision_lab.symbol_models import (
    PREPROCESSING,
    compare,
    evaluate_frozen_fusion,
    model_pair,
)
from test_vision_lab_symbol_batch_labels import pack as review_pack
from test_vision_lab_symbol_feedback import cohort as feedback_cohort


def test_legacy_context_keeps_bindings_and_unknown_exclusion_guard(tmp_path, monkeypatch):
    inputs = SimpleNamespace(
        payload={"live_bindings": {"original": "hash"}, "photo_pixel_groups": {"pixel": []}}
    )
    monkeypatch.setattr(module.SymbolTrainingAdapter, "validate", lambda _self: inputs)
    context = module.batch_inputs(tmp_path / "training", 2)
    assert context.inputs is inputs and context.live == inputs.payload["live_bindings"]
    assert (
        context.photo_pixels == ["pixel"] and not context.external_sources and not context.protected
    )
    catalog = SimpleNamespace(sources={"known": SimpleNamespace(sha256="hash")})
    assert module.exclusion_hashes(context, catalog, {"known"}) == {"hash"}
    with pytest.raises(ValueError, match="EXCLUSION_CATALOG_MISMATCH"):
        module.exclusion_hashes(context, catalog, {"unknown"})


def test_feedback_context_resolves_moved_sources_and_excludes_complete_recording(
    tmp_path, monkeypatch
):
    pack = review_pack.__wrapped__(tmp_path, monkeypatch)
    cohort = feedback_cohort.__wrapped__(pack, tmp_path, monkeypatch)
    manifest = symbol_feedback.freeze(
        cohort.base, cohort.pack, cohort.catalog, cohort.qualification, cohort.output
    )
    current = cohort.source.parent.with_name("moved-recording")
    cohort.source.parent.rename(current)
    location = symbol_feedback.bind_source_location(manifest, current, "operator location")
    context = module.batch_inputs(manifest, 3)
    assert str(cohort.source) not in context.live
    assert context.live[str(current / cohort.source.name)] == sha(current / cohort.source.name)
    assert context.live[str(location)] == sha(location) and current in context.protected
    assert context.photo_pixels == sorted(context.inputs.payload["photo_partitions"])
    excluded = symbol_batch.excluded_sources(context.inputs.payload)
    hashes = module.exclusion_hashes(context, SimpleNamespace(sources=cohort.sources), excluded)
    assert {r["sha256"] for r in context.inputs.payload["folder_rows"]} <= hashes
    assert cohort.inputs.payload["assignments"]["diag"] == "development"
    assert context.inputs.payload["assignments"]["diag"] == "diagnostic_test"


def test_fresh_geometry_is_explicit_and_old_v2_default_is_preserved(tmp_path, monkeypatch):
    args = [
        tmp_path / name
        for name in ["root", "folder", "training", "runs", "comparison", "geometry", "catalog"]
    ]
    with pytest.raises(ValueError, match="GEOMETRY_REFERENCE_REQUIRED"):
        symbol_batch.freeze(*args, 60, generation=2)
    with pytest.raises(ValueError, match="FEEDBACK_QUALIFICATION_REQUIRED"):
        symbol_batch.freeze(*args, 60, generation=3)
    with pytest.raises(ValueError, match="GEOMETRY_MODE_INVALID"):
        symbol_batch.freeze(*args, 60, generation=1, fresh_geometry=True)

    def reached(*_args):
        raise RuntimeError("explicit fresh geometry admitted")

    monkeypatch.setattr(symbol_batch, "batch_inputs", reached)
    with pytest.raises(RuntimeError, match="explicit fresh geometry admitted"):
        symbol_batch.freeze(*args, 60, generation=2, fresh_geometry=True)


@pytest.fixture
def evidence(tmp_path):
    classes = ["10", "J", "Q", "K", "A", "Ra", "Sarkofag", "Mumia", "Faraon", "Sfinks"]
    labels = [
        index
        for index, count in enumerate([12, 4, 10, 9, 11, 5, 12, 8, 9, 4])
        for _ in range(count)
    ]
    logits = np.eye(10)[labels] * 8
    logits[26] = np.eye(10)[2] * 8  # Retain the single frozen K/Q conflict.

    def prediction(manifest):
        return {
            "manifest_id": manifest,
            "classes": classes,
            "labels": labels,
            "sample_ids": [f"sample-{i}" for i in range(84)],
            "logits": logits.tolist(),
        }

    base = "a" * 64
    cohort = "c" * 64
    old = prediction(base)
    current = prediction(cohort)
    reports = {model: {"predictions": deepcopy(current)} for model in model_pair(3)}
    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    states, pins = {}, {}
    for index, model in enumerate(model_pair(1)):
        report = baseline_root / (str(index) + ".json")
        report.write_bytes(canonical({"metrics": {"predictions": old}}))
        artifact = Artifact(relative_path=report.name, sha256=sha(report))
        request = StartRunRequest(
            request_id="baseline-" + str(index),
            manifest_id=base,
            model_version=model,
            preprocessing_version=PREPROCESSING[model],
            seed=20261005,
            purpose="train",
            configuration=TrainingConfiguration(),
        )
        run = RunState(
            id="baseline-" + str(index),
            request=request,
            fingerprint="frozen",
            status="succeeded",
            lease="past-lease",
            created_at=1,
            launch_deadline=2,
            report=artifact,
        )
        states[run.id] = run.model_dump()
        pins[str(report)] = sha(report)
    state = baseline_root / "state.json"
    write_atomic(state, {"runs": states})
    pins[str(state)] = sha(state)
    control = tmp_path / "input.meta"
    control.write_text("current source binding")
    pins[str(control)] = sha(control)
    calibration = compare(*[reports[model]["predictions"] for model in model_pair(3)])
    payload = {
        "format": "mumie-symbol-feedback-iteration-v1",
        "manifest_id": cohort,
        "calibration": calibration,
        "validation": evaluate_frozen_fusion(current, current, calibration),
        "baseline_validation": evaluate_frozen_fusion(old, old, compare(old, old)),
        "pair_qualified": True,
        "qualification": dict.fromkeys(["rgb", "gray", "fusion"], True),
        "input_hashes": pins,
    }
    path = tmp_path / "qualification.json"
    write_atomic(path, payload)
    context = module.BatchInputs(
        SimpleNamespace(
            manifest_id=cohort, payload={"base_manifest": str(tmp_path / (base + ".json"))}
        ),
        {},
        {},
        [],
        [],
    )
    return SimpleNamespace(
        path=path,
        payload=payload,
        reports=reports,
        calibration=calibration,
        context=context,
        control=control,
        required={str(control): sha(control)},
    )


def qualify(fixture):
    return module.feedback_qualification(
        fixture.path, fixture.context, fixture.reports, fixture.calibration, fixture.required
    )


def test_qualified_evidence_recomputes_baseline_and_returns_actual_pins(evidence):
    before = evidence.path.read_bytes()
    pins = qualify(evidence)
    assert pins[str(evidence.path)] == sha(evidence.path)
    assert pins[str(evidence.control)] == sha(evidence.control)
    assert evidence.path.read_bytes() == before
    assert qualify(evidence) == pins


@pytest.mark.parametrize(
    "change",
    ["boolean", "class_regression", "labels", "baseline", "source", "unbound", "missing_baseline"],
)
def test_claimed_gate_cannot_hide_regression_drift_or_reference_change(evidence, change):
    p = evidence.payload
    if change == "boolean":
        p["pair_qualified"] = False
    elif change in {"class_regression", "labels"}:
        for report in evidence.reports.values():
            prediction = report["predictions"]
            if change == "class_regression":
                prediction["logits"][26] = (np.eye(10)[3] * 8).tolist()
                prediction["logits"][12] = (np.eye(10)[2] * 8).tolist()
            else:
                prediction["labels"] = list(prediction["labels"])
                prediction["labels"][0] = 1
        rgb, gray = [evidence.reports[model]["predictions"] for model in model_pair(3)]
        evidence.calibration = compare(rgb, gray)
        p["calibration"] = evidence.calibration
        p["validation"] = evaluate_frozen_fusion(rgb, gray, evidence.calibration)
    elif change == "baseline":
        p["baseline_validation"]["rgb"]["correct"] = 82
    elif change == "source":
        evidence.control.write_text("changed")
    elif change == "unbound":
        evidence.required[str(evidence.control)] = "f" * 64
    else:
        p["input_hashes"] = {
            name: checksum
            for name, checksum in p["input_hashes"].items()
            if Path(name).name != "state.json"
        }
    write_atomic(evidence.path, p)
    with pytest.raises(ValueError, match="FEEDBACK_"):
        qualify(evidence)
