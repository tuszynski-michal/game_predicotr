"""Whole partial-control evaluator, restart and a genuinely different assigned baseline."""

import copy
import dataclasses
import hashlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_correction_evaluation import CHECKPOINT_RULE, require_report
from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_worker.images.grid_model_evaluation_handler import GridModelEvaluationJobHandler
from test_grid_model_evaluation import Context, colour

pytest_plugins = ["test_grid_model_evaluation"]


def correction(s, screen_eligible=False, policy="application-grid-corrections-v1"):
    for fixture in s.store.games.values():
        for source in fixture.sources:
            source["targets"] = source["targets"][:3]
            source["screenEligible"] = screen_eligible
        fixture.publish(
            change=lambda root: root.update(
                schemaVersion="application-grid-snapshot-v2",
                policyVersion=policy,
            )
        )
    selection = {
        "rule": CHECKPOINT_RULE,
        "role": "VALIDATION",
        "step": 7,
        "metrics": {"boardCorrectRate": 1.0, "normalizedError": 0.0},
        "earlyStopping": {"patience": 4, "evaluationsWithoutImprovement": 0, "stopped": False},
    }
    bundle = json.dumps(
        {"parity": {"passed": True}, "provenance": {"checkpointSelection": selection}}
    ).encode()
    (s.root / s.candidate["managedDirectory"] / "bundle.json").write_bytes(bundle)
    for entry in s.candidate["files"]:
        if entry["name"] == "bundle.json":
            entry.update(sha256=hashlib.sha256(bundle).hexdigest(), sizeBytes=len(bundle))
    payload = copy.deepcopy(s.job.input_payload)
    payload.update(
        evaluation_kind="grid-correction-evaluation-v1",
        manifest_sha256=descriptor_sha256(s.candidate),
        checkpoint_selection=selection,
        scope={
            "currentGameId": s.training,
            "trainingGameIds": [s.training],
            "priorVerifiedGameIds": [s.other],
            "priorScopeDocumented": True,
            "exclusions": [],
        },
    )
    for pin in payload["cohorts"]:
        pin["manifest_sha256"] = s.store.games[pin["game_id"]].manifest_pin["sha256"]
    return dataclasses.replace(s.job, input_payload=payload)


def engine_factory(s, missing=()):
    def factory(directory, _sha):
        def analyse(rgb):
            count = 0 if directory.name != "candidate" and colour(rgb) in missing else 3
            return [SimpleNamespace(nodes=s.labels.copy()) for _ in range(count)]

        return SimpleNamespace(analyse=analyse)

    return factory


@pytest.mark.parametrize("screen_eligible", [False, True])
@pytest.mark.parametrize(
    "policy", ["application-grid-corrections-v1", "application-grid-corrections-v2"]
)
def test_partial_both_roles_whole_job_report_and_restart(scenario, screen_eligible, policy):
    s = scenario
    job = correction(s, screen_eligible, policy)
    worker = GridModelEvaluationJobHandler(
        s.store, s.root, engine_factory=engine_factory(s, [s.keys[s.training]["REGRESSION"][0]])
    )
    context = Context(job)
    worker(context, job)
    report_json, sha = next(iter(s.store.reports.values()))
    report = require_report(
        report_json, manifest=s.candidate, base_sha256=descriptor_sha256(s.base)
    )
    assert report["verdict"] == "PASS"
    for game in report["games"]:
        for role in game["roles"].values():
            assert role["photos"] == 5 and role["candidate"]["boards_expected"] == 15
            assert role["candidate"]["partial_photos"] == 5
            assert role["candidate"]["false_boards"] is None
    resumed = dataclasses.replace(job, checkpoint_payload=context.states[-1])
    worker(Context(resumed), resumed)
    assert next(iter(s.store.reports.values())) == (report_json, sha)


def test_actual_assigned_baseline_does_not_replace_candidate_parent(scenario):
    from game_predictor_api.domain.grid_assigned_comparison import require_report as assigned_report

    s = scenario
    job = correction(s)
    baseline = {**s.base, "versionId": str(uuid4()), "managedDirectory": "models/assigned"}
    payload = dict(job.input_payload)
    payload.pop("scope")
    payload.pop("checkpoint_selection")
    payload.update(
        evaluation_kind="grid-assigned-comparison-v1",
        baseline_version_id=baseline["versionId"],
        baseline_manifest_sha256=descriptor_sha256(baseline),
        assignment_revision=3,
        comparison_command={},
        cohorts=[pin for pin in payload["cohorts"] if pin["game_id"] == s.training],
    )
    job = dataclasses.replace(job, input_payload=payload)
    seen = []

    def catalogue(candidate_id, base_id):
        seen.append(base_id)
        return s.candidate, baseline, descriptor_sha256(baseline)

    s.store.catalogue = catalogue
    worker = GridModelEvaluationJobHandler(s.store, s.root, engine_factory=engine_factory(s))
    worker(Context(job), job)
    report_json, _ = next(iter(s.store.reports.values()))
    report = assigned_report(
        report_json,
        manifest=s.candidate,
        baseline_sha256=descriptor_sha256(baseline),
        expected_baseline_version_id=baseline["versionId"],
        expected_assignment_revision=3,
        expected_game_id=s.training,
    )
    assert report["verdict"] == "PASS" and seen == [UUID(baseline["versionId"])]
    assert s.candidate["baseVersionId"] == s.base["versionId"] != baseline["versionId"]


def test_screen_report_v4_keeps_every_partial_regression_target_and_replays(scenario):
    from game_predictor_api.domain.grid_correction_evaluation import SCREEN_CHECKPOINT_RULE
    from game_predictor_api.schemas.grid_model_evaluations import (
        GridScreenCorrectionEvaluationReport,
    )

    s = scenario
    originals = {game: copy.deepcopy(fixture.sources) for game, fixture in s.store.games.items()}
    job = correction(s)
    for game, fixture in s.store.games.items():
        for index, source in enumerate(fixture.sources):
            if source["role"] != "REGRESSION":
                source.update(copy.deepcopy(originals[game][index]))
                source["screenEligible"] = True
        fixture.publish(
            mode="screen+grid",
            change=lambda root: root.update(
                schemaVersion="application-grid-snapshot-v3",
                policyVersion="application-grid-corrections-v3",
            ),
        )
    payload = copy.deepcopy(job.input_payload)
    selection = payload["checkpoint_selection"]
    selection.update(
        rule=SCREEN_CHECKPOINT_RULE,
        selectionInputSha256="c" * 64,
        metricStateVersion="photo-board-checkpoint-state-v1",
    )
    selection["metrics"]["photoCorrectRate"] = 1.0
    bundle = json.dumps(
        {"parity": {"passed": True}, "provenance": {"checkpointSelection": selection}}
    ).encode()
    (s.root / s.candidate["managedDirectory"] / "bundle.json").write_bytes(bundle)
    for entry in s.candidate["files"]:
        if entry["name"] == "bundle.json":
            entry.update(sha256=hashlib.sha256(bundle).hexdigest(), sizeBytes=len(bundle))
    payload["manifest_sha256"] = descriptor_sha256(s.candidate)
    for pin in payload["cohorts"]:
        pin["manifest_sha256"] = s.store.games[pin["game_id"]].manifest_pin["sha256"]
    job = dataclasses.replace(job, input_payload=payload)
    validation = {key for roles in s.keys.values() for key in roles["VALIDATION"]}
    missing = s.keys[s.training]["REGRESSION"][0]

    def factory(directory, sha):
        def analyse(rgb):
            count = 9 if colour(rgb) in validation else 3
            if directory.name != "candidate" and colour(rgb) == missing:
                count = 0
            return [SimpleNamespace(nodes=s.labels.copy()) for _ in range(count)]

        return SimpleNamespace(analyse=analyse)

    worker = GridModelEvaluationJobHandler(s.store, s.root, engine_factory=factory)
    context = Context(job)
    worker(context, job)
    report_json, sha = next(iter(s.store.reports.values()))
    report = require_report(
        report_json, manifest=s.candidate, base_sha256=descriptor_sha256(s.base)
    )
    GridScreenCorrectionEvaluationReport.model_validate(report)
    assert report["schemaVersion"] == "grid-model-evaluation-read-v4"
    assert report["verdict"] == "PASS"
    for game in report["games"]:
        reg = game["roles"]["REGRESSION"]["candidate"]
        assert reg["photos"] == 5 and reg["boards_expected"] == 15 and reg["full_photos"] == 0
        assert reg["false_boards"] is None
    restarted = dataclasses.replace(job, checkpoint_payload=context.states[-1])
    worker(Context(restarted), restarted)
    assert next(iter(s.store.reports.values())) == (report_json, sha)
