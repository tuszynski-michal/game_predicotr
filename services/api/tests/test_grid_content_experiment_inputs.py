"""Positive ancestor evidence, protected copies and immutable experiment child commands."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from game_predictor_api.application.grid_correction_learning import GridCorrectionLearningService
from game_predictor_api.application.grid_training_runs import GridTrainingRunService
from game_predictor_api.domain.grid_content_experiment_inputs import (
    build_inputs,
    require_inputs,
    training_eligibility,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError, digest
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.schemas.grid_correction_learning import GridCorrectionLearningPreview
from game_predictor_api.schemas.jobs import GridTrainingJobPayload
from game_predictor_worker.training_core.grid_content_experiment import build_plan
from game_predictor_worker.training_core.grid_training_admission import SCREEN_GRID_CORRECTIONS_V1
from test_grid_training_runs import BASE, COHORT, GAME, Cohorts, Jobs, command


def inputs_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = {
        "versionId": BASE,
        "familyId": str(UUID(int=80)),
        "trainingArtifacts": [{"name": "weights.pt", "sha256": "e" * 64}],
    }
    ancestor = {"versionId": BASE, "manifestSha256": "a" * 64}
    providers = {
        BASE: {
            "schemaVersion": "recording-ancestor-provider-v1",
            "ancestor": ancestor,
            "complete": True,
            "recordingIdentityAvailable": True,
            "recordingGroups": [{"groupId": str(UUID(int=90)), "role": "TRAIN"}],
        }
    }
    sources, contexts = [], {}
    for number, role, purpose in (
        (1, "TRAIN", None),
        (2, "VALIDATION", "A"),
        (3, "VALIDATION", "B"),
        (4, "REGRESSION", None),
    ):
        identifier = str(UUID(int=number))
        sources.append(
            {
                "sourceId": identifier,
                "sourceSha256": digest([number, "bytes"]),
                "pixelSha256": digest([number, "pixels"]),
                "qualifiedLabelsSha256": digest([number, "labels"]),
                "eligibleBoards": 9,
                "representative": True,
                "buffer": False,
                "role": role,
                "validationPurpose": purpose,
                "registryProofSha256": "b" * 64,
            }
        )
        contexts[identifier] = {
            "sourceId": identifier,
            "componentIds": [str(UUID(int=100 + number))],
            "aliasComponentIds": [digest([number, "alias"])],
            "allowedRoles": [role],
            "priorRoles": [],
            "proofSha256": "c" * 64,
            "diagnosticExposed": False,
            "selectionExposed": False,
            "validationPurposes": [],
        }
    split = {
        "sha256": "d" * 64,
        "contentSampling": {"policy": "full-symbol-content-sampling-v1"},
        "sources": sources,
    }
    args = dict(
        game=str(GAME),
        base=base,
        base_sha256="a" * 64,
        lineage={"ancestors": [ancestor]},
        providers=providers,
        split=split,
        contexts=contexts,
    )
    proof = training_eligibility(**args)
    inputs = build_inputs([proof], [(str(GAME), split)])
    plan = build_plan(
        base_version_id=BASE,
        base_manifest_sha256="a" * 64,
        base_weights_sha256="e" * 64,
        cohorts=[{"gameId": str(GAME), "cohortId": str(COHORT), "manifestSha256": "c" * 64}],
        train_eligibility_sha256=inputs["trainEligibility"]["sha256"],
        selection_roster_sha256=inputs["selectionRoster"]["sha256"],
        calibration_roster_sha256=inputs["calibrationRoster"]["sha256"],
        regression_roster_sha256=inputs["regressionRoster"]["sha256"],
    )
    return args, inputs, plan


def test_complete_positive_proof_is_retained_and_bound_to_every_roster() -> None:
    args, inputs, plan = inputs_fixture()
    require_inputs(inputs, plan)
    proof = inputs["trainEligibility"]["games"][0]
    assert proof["lineage"] == args["lineage"]
    assert proof["ancestorReferences"][0]["complete"] is True
    assert len(proof["sources"]) == 1 and proof["sources"][0]["role"] == "TRAIN"
    assert inputs["selectionRoster"]["games"][0]["sources"][0]["sourceId"] == str(UUID(int=2))
    assert inputs["calibrationRoster"]["games"][0]["sources"][0]["sourceId"] == str(UUID(int=3))
    assert inputs["regressionRoster"]["games"][0]["sources"][0]["sourceId"] == str(UUID(int=4))


@pytest.mark.parametrize(
    "mutation",
    [
        "no_provider",
        "incomplete",
        "missing_ancestor",
        "ancestor",
        "unknown_closure",
        "holdout",
        "diagnostic",
        "selection",
    ],
)
def test_missing_or_protected_ancestry_never_becomes_unseen(mutation: str) -> None:
    args, _, _ = inputs_fixture()
    context = args["contexts"][str(UUID(int=1))]
    if mutation == "no_provider":
        args["providers"] = {}
    elif mutation == "incomplete":
        args["providers"][BASE]["complete"] = False
    elif mutation == "missing_ancestor":
        args["lineage"]["ancestors"].append(
            {"versionId": str(UUID(int=89)), "manifestSha256": "f" * 64}
        )
    elif mutation == "ancestor":
        context["componentIds"] = [str(UUID(int=90))]
    elif mutation == "unknown_closure":
        context["componentIds"] = []
    elif mutation == "holdout":
        context["priorRoles"] = ["REGRESSION"]
    else:
        context[mutation + "Exposed"] = True
    if mutation in ("no_provider", "incomplete", "missing_ancestor"):
        with pytest.raises(GridCohortError, match="incomplete or changed"):
            training_eligibility(**args)
    else:
        proof = training_eligibility(**args)
        assert proof["sources"] == [] and len(proof["excluded"]) == 1
        # Seen/unknown TRAIN stays in the split, but cannot be the entire bank pool.
        assert args["split"]["sources"][0]["role"] == "TRAIN"
        with pytest.raises(GridCohortError) as error:
            build_inputs([proof], [(str(GAME), args["split"])])
        assert error.value.code == "CONTENT_BANK_ANCESTOR_UNSEEN_TRAIN_REQUIRED"


def test_cross_game_or_role_pixel_copy_is_not_a_bank_source() -> None:
    args, _, _ = inputs_fixture()
    args["split"]["sources"][2]["pixelSha256"] = args["split"]["sources"][0]["pixelSha256"]
    with pytest.raises(GridCohortError) as error:
        build_inputs([training_eligibility(**args)], [(str(GAME), args["split"])])
    assert error.value.code == "CONTENT_BANK_CONTROL_ALIAS"


def test_role_roster_change_invalidates_closed_plan() -> None:
    _, inputs, plan = inputs_fixture()
    changed = deepcopy(inputs)
    changed["calibrationRoster"]["games"][0]["sources"].clear()
    with pytest.raises(GridCohortError):
        require_inputs(changed, plan)


def test_seen_rehearsal_and_control_only_game_do_not_require_new_bank_sources() -> None:
    args, _, _ = inputs_fixture()
    first = training_eligibility(**args)
    other = deepcopy(args)
    other["game"] = str(UUID(int=777))
    # This historical TRAIN remains legal rehearsal, but is excluded from the bank.
    other["contexts"][str(UUID(int=1))]["componentIds"] = [str(UUID(int=90))]
    second = training_eligibility(**other)
    assert second["sources"] == [] and second["trainingSourceIds"] == [str(UUID(int=1))]
    result = build_inputs(
        [first, second], [(args["game"], args["split"]), (other["game"], other["split"])]
    )
    require_inputs(result)
    # An explicit control-only cohort still contributes its A/B/REG roster and scope.
    other["split"]["sources"] = [s for s in other["split"]["sources"] if s["role"] != "TRAIN"]
    control = training_eligibility(**other)
    assert control["sources"] == [] and control["trainingSourceIds"] == []
    result = build_inputs(
        [first, control], [(args["game"], args["split"]), (other["game"], other["split"])]
    )
    assert len(result["regressionRoster"]["games"]) == 2


def test_missing_server_provider_blocks_preview_without_opening_database(tmp_path: Path) -> None:
    service = GridCorrectionLearningService(None, None, tmp_path)  # type: ignore[arg-type]
    preview = service.preview(
        GAME,
        {
            "trainingMode": "screen+grid",
            "policyVersion": "application-grid-corrections-v4",
            "validationAssignments": {},
            "contentExperiment": "full-symbol-content-experiment-v1",
        },
    )
    assert preview["blockers"] == ["CONTENT_BANK_ANCESTRY_UNRESOLVED"]
    assert preview["cost"] is None and not preview["canStart"]
    assert "EXPERIMENT_ARM_FEASIBILITY" in preview["pendingWorkerChecks"]
    assert (
        GridCorrectionLearningPreview.model_validate(preview).contentExperimentReadiness is not None
    )


class ExperimentCohorts(Cohorts):
    def __init__(self, args: dict[str, Any]) -> None:
        super().__init__(["GRID_RUN_COHORT_COST_EXCEEDS_BUDGET"])
        document = {
            "base": {"manifestSha256": "a" * 64, "manifest": args["base"]},
            "photoSplit": args["split"],
        }
        self.repository = SimpleNamespace(cohort=lambda *a: SimpleNamespace(document=document))

    def run_preview(self, game: UUID, cohort: UUID) -> dict[str, Any]:
        result = super().run_preview(game, cohort)
        result["selectedPresetId"] = SCREEN_GRID_CORRECTIONS_V1.preset_id
        return result

    def get(self, game: UUID, cohort: UUID) -> dict[str, Any]:
        return {
            **super().get(game, cohort),
            "mode": "screen+grid",
            "policyVersion": "application-grid-corrections-v4",
        }


def test_child_exact_plan_idempotency_resume_and_legacy_cost_are_separate() -> None:
    args, inputs, plan = inputs_fixture()
    jobs, cohorts = Jobs(), ExperimentCohorts(args)
    service = GridTrainingRunService(cohorts, jobs)  # type: ignore[arg-type]
    body = command(
        presetId=SCREEN_GRID_CORRECTIONS_V1.preset_id,
        presetFingerprint=SCREEN_GRID_CORRECTIONS_V1.fingerprint,
    )
    private = dict(content_experiment=plan, content_experiment_inputs=inputs)
    view = service.create(GAME, body, **private)
    assert service.create(GAME, body, **private) == view
    job = next(iter(jobs.rows.values()))
    payload = GridTrainingJobPayload.model_validate(job.input_payload)
    assert payload.planned_steps == 4800 and payload.seed == 20261108
    assert payload.content_experiment == plan and payload.content_experiment_inputs == inputs
    assert len(jobs.rows) == 1
    failed = replace(
        job, status=JobStatus.FAILED, checkpoint_payload={"budget": {"used_seconds": 123}}
    )
    jobs.save_job(failed)
    service.resume(GAME, job.id)
    assert jobs.rows[job.id].input_payload == job.input_payload
    assert jobs.rows[job.id].checkpoint_payload == failed.checkpoint_payload
    with pytest.raises(GridCohortError) as conflict:
        service.create(GAME, body)
    assert conflict.value.code == "GRID_RUN_IDEMPOTENCY_CONFLICT"
    cohorts.blockers.append("GRID_RUN_COHORT_NOT_QUALIFIED")
    with pytest.raises(GridCohortError) as blocked:
        service.create(
            GAME,
            command(presetId=body["presetId"], presetFingerprint=body["presetFingerprint"]),
            **private,
        )
    assert blocked.value.code == "GRID_RUN_COHORT_NOT_QUALIFIED"
