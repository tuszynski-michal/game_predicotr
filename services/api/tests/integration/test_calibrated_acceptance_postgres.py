"""Synthetic numeric observations + real registry, PG prewrite and cold lookup.

No image inference or real quality claim: seeded reports exercise admission only.
"""

import hashlib
import io
import json
import os
import runpy
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.canonical_source import decode_canonical_source_bytes
from game_predictor_api.domain.full_board_calibration import (
    AXES,
    AssessedTarget,
    CalibrationPlan,
    FeatureVector,
    ReferenceTarget,
    assess_regression,
    make_plan,
    seal_b,
)
from game_predictor_api.domain.full_board_calibration_report import (
    LIMITATIONS,
    AutomaticCalibration,
    attach_calibration,
)
from game_predictor_api.domain.grid_correction_evaluation import CHECKPOINT_RULE, build_report
from game_predictor_api.domain.grid_model_registry import canonical_json, historical_catalogue
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest
from game_predictor_api.storage.full_board_calibration_evidence import (
    load_frozen_assessment,
    require_calibration_evidence,
    snapshot_assessment_references,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_model_evaluation_repository import (
    append_proof,
    storage_location,
    store_report,
)
from game_predictor_api.storage.grid_model_registry_models import (
    GridModelEvaluationInvalidationModel,
)
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel
from game_predictor_api.storage.models import JobModel
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from PIL import Image
from test_grid_correction_evaluation import roles
from test_v3_engine_acceptance_postgres import (
    current_partition_budget,  # noqa: F401
    database,  # noqa: F401
    execution,
    snapshot_state,
)


def frozen_fixture(session, manifest, game, root):
    fixture_class = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "worker/tests/test_grid_cohort_dataset.py")
    )["SnapshotFixture"]
    fixture = fixture_class(root)
    fixture.game, fixture.cohort = str(game), manifest["cohortId"]
    fixture.directory = f"data/grid-training-cohorts/{game}/{fixture.cohort}"
    for purpose, count in (("A", 1), ("B", 30), (None, 30)):
        for _ in range(count):
            source = fixture.source("REGRESSION" if purpose is None else "VALIDATION")
            if purpose != "A":
                second = deepcopy(source["targets"][0])
                second.update(positionIndex=1, sequenceNumber=18)
                source["targets"].append(second)
            # Distinct tiny real rasters, not saturation aliases above fixture source25.
            stream = io.BytesIO()
            index = len(fixture.sources)
            Image.new("RGB", (64, 48), ((index % 8) * 30, (index // 8) * 30, 90)).save(
                stream, format="JPEG", quality=100, subsampling=0
            )
            content = stream.getvalue()
            source_sha = hashlib.sha256(content).hexdigest()
            canonical = decode_canonical_source_bytes(
                content, expected_source_checksum_sha256=source_sha
            ).source
            source["sourceIdentity"].update(
                checksum_sha256=source_sha,
                normalized_pixel_checksum_sha256=canonical.normalized_pixel_checksum_sha256,
            )
            source["original"] = fixture.pin(
                f"{fixture.directory}/originals/calibration-{len(fixture.sources)}.jpg", content
            )
            source.update(
                validationPurpose=purpose,
                purposeProofSha256="d" * 64,
                assessmentPolicy="human-labeled-targets-v1" if purpose != "A" else None,
            )
    split = {
        "schemaVersion": "grid-correction-split-v4",
        "purposeCounts": {
            "VALIDATION-A": {"photos": 1, "boards": 1, "fullPhotos": 0},
            "VALIDATION-B": {"photos": 30, "boards": 60, "fullPhotos": 0},
        },
        "sources": [
            dict(
                sourceId=s["sourceId"],
                role=s["role"],
                validationPurpose=s["validationPurpose"],
                representative=True,
                purposeProofSha256="d" * 64,
                eligibleBoards=len(s["targets"]),
                componentIds=[],
            )
            for s in fixture.sources
        ],
    }
    split["sha256"] = digest(split)
    snapshot = fixture.publish(
        change=lambda value: value.update(
            schemaVersion="application-grid-snapshot-v4",
            policyVersion="application-grid-corrections-v4",
            photoSplit=split,
            familyId=manifest["familyId"],
        )
    )
    session.add(
        GridTrainingCohortModel(
            game_id=game,
            id=UUID(fixture.cohort),
            status="frozen",
            document=snapshot.manifest,
            manifest_path=fixture.manifest_pin["path"],
            manifest_sha256=snapshot.manifest_sha256,
            summary={},
            created_by="fixture",
        )
    )
    session.flush()
    return snapshot, snapshot_assessment_references(snapshot)


def calibrated_report(session, manifest, game, root):
    snapshot, frozen = frozen_fixture(session, manifest, game, root)
    base = next(p for p in historical_catalogue() if p["versionId"] == manifest["baseVersionId"])
    vector = FeatureVector(values=dict.fromkeys(AXES, 0.5))
    plan = make_plan(
        [
            ReferenceTarget(
                gameId=game,
                sourceRepresentativeSha256="a" * 64,
                positionIndex=0,
                role="VALIDATION-A",
                humanGood=True,
                features=vector,
            )
        ],
        game_id=game,
        candidate_sha=digest(manifest),
        baseline_sha=digest(base),
        routing_sha="c" * 64,
        role_proof_sha=frozen.role_proof_sha256,
        b_assessment_sha=frozen.references["B"],
        regression_assessment_sha=frozen.references["REGRESSION"],
    )

    def targets(role):
        return [
            AssessedTarget(
                gameId=game,
                sourceId=UUID(source_id),
                sourceRepresentativeSha256=pixel_sha,
                positionIndex=slot,
                groundTruthSha256=gt_sha,
                baselineGood=bool(slot),
                candidateGood=True,
                candidateCropped=False,
                baselinePreT0Accepted=True,
                baselineT0Accepted=bool(slot),
                candidateFeatures=vector,
            )
            for source_id, pixel_sha, slot, gt_sha in frozen.targets[role]
        ]

    b, reg = targets("B"), targets("REGRESSION")
    sealed = seal_b(plan, b)
    result = assess_regression(plan, sealed, reg)
    assert result["state"] == "qualified"
    profile = dict(
        version="full-board-auto-profile-v1",
        gameId=str(game),
        candidateManifestSha256=digest(manifest),
        planSha256=plan.sha256,
        sealedSha256=sealed["sha256"],
        routingSha256=plan.routingSha256,
        configuration=sealed["configuration"],
        gameLogAspectReference=None,
        assessmentScope="labelled_targets",
    )
    profile["sha256"] = digest(profile)
    body = {
        "plan": {
            "plan": plan.model_dump(mode="json"),
            "plannedComparisons": 60,
            "plannedConfigurations": 1,
            "bTargets": 60,
            "bSources": 30,
            "regressionTargets": 60,
            "regressionSources": 30,
            "cohortId": str(frozen.cohort_id),
            "cohortManifestSha256": frozen.manifest_sha256,
            "referenceAssessmentSha256": frozen.references["A"],
            "gameLogAspectReference": None,
        },
        "b": {
            "planSha256": plan.sha256,
            "targets": [t.model_dump(mode="json") for t in b],
            "sealed": sealed,
        },
        "regressionTargets": [t.model_dump(mode="json") for t in reg],
        "result": result,
        "profile": profile,
        "roleProofSha256": plan.roleProofSha256,
    }
    path = root / "grid-model-evaluations" / f"{game}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(canonical_json({"payload": body, "sha256": digest(body)}), encoding="utf-8")
    automatic = AutomaticCalibration(
        gameId=game,
        state="qualified",
        reasonCodes=[],
        b=sealed["b"],
        regression=result["regression"],
        profile=profile,
        evidence={
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        plannedConfigurations=1,
        plannedComparisons=60,
        roleProofSha256=plan.roleProofSha256,
        limitations=LIMITATIONS,
    ).model_dump(mode="json")
    cohort = {
        "gameId": str(game),
        "cohortId": manifest["cohortId"],
        "manifestSha256": snapshot.manifest_sha256,
    }
    quality = build_report(
        manifest=manifest,
        base_manifest_sha256=digest(base),
        training_game_id=str(game),
        parity={"passed": True, "bundleSha256": "2" * 64},
        cohorts=[cohort],
        measured={str(game): {"mode": "grid-only", "roles": roles()}},
        scope={
            "currentGameId": str(game),
            "trainingGameIds": [str(game)],
            "priorVerifiedGameIds": [],
            "priorScopeDocumented": True,
            "exclusions": [],
        },
        checkpoint_selection={
            "rule": CHECKPOINT_RULE,
            "role": "VALIDATION",
            "step": 10,
            "metrics": {"boardCorrectRate": 0.8, "normalizedError": 0.02},
            "earlyStopping": {"patience": 3, "evaluationsWithoutImprovement": 1, "stopped": False},
        },
    )
    report = attach_calibration(quality, [automatic])
    identifier = uuid4()
    store_report(
        session,
        report_id=identifier,
        version_id=UUID(manifest["versionId"]),
        producer=report["producer"],
        report_json=canonical_json(report),
        report_sha256=digest(report),
    )
    append_proof(
        session,
        report_id=identifier,
        game_id=game,
        cohort_id=UUID(manifest["cohortId"]),
        manifest_sha256=cohort["manifestSha256"],
        count=0,
        storage_generation=storage_location(session, game)["generation"],
        bind_receipt_sha256="3" * 64,
        eligibility_sha256="4" * 64,
        actor="fixture",
    )
    return identifier


def test_qualified_v4_real_reader_prewrite_cold_retry_then_currentness_drift(database, tmp_path):  # noqa: F811
    from game_predictor_api.domain.jobs import JobType, create_job
    from game_predictor_api.domain.neural_grid_operation_pin import CAPABILITY_PREFLIGHT_POLICY
    from game_predictor_api.storage.job_repository import job_record_from_domain

    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy="v3-engine-acceptance-v4",
        crop_policy="neural-auto-crop-v2",
        evaluated_game=True,
        calibrated_report=calibrated_report,
        workflow_recheck=True,
    )
    assert snapshot_state(factory, game, seed)[0] == "needs_review"
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed)[0] == "accepted"
    with game_storage_scope(game), factory() as session:
        row = session.get(JobModel, seed.import_job_id)
        pin = row.input_payload["neural_grid_operation_pin"]
        assert pin["automaticQualification"]["state"] == "qualified"
        expected = digest(pin)
        model_snapshot = row.input_payload["neural_grid_proposal"]
        from game_predictor_api.storage.grid_model_registry import (
            SqlAlchemyGridModelRegistryRepository,
        )

        record, _ = SqlAlchemyGridModelRegistryRepository(session).evaluation(
            UUID(pin["automaticQualification"]["reportId"])
        )
        report = json.loads(record.report_json)
        frozen = load_frozen_assessment(session, tmp_path, report, game)
    automatic = report["automaticCalibration"][0]
    evidence_path = tmp_path / automatic["evidence"]["path"]
    original = evidence_path.read_bytes()
    original_body = json.loads(original)["payload"]
    # Recompute every internal checksum/count/result after dropping/replacing a
    # target; only the independently DB-pinned snapshot distinguishes the forgery.
    for role in ("B", "REGRESSION"):
        for fault in ("removed", "replaced", "duplicate"):
            body = deepcopy(original_body)
            selected = body["b"]["targets"] if role == "B" else body["regressionTargets"]
            if fault == "removed":
                selected.pop()
            elif fault == "replaced":
                selected[0]["groundTruthSha256"] = "9" * 64
            else:
                selected[0] = deepcopy(selected[1])
            plan = CalibrationPlan.model_validate(body["plan"]["plan"])
            body["b"]["sealed"] = seal_b(
                plan, [AssessedTarget.model_validate(t) for t in body["b"]["targets"]]
            )
            body["result"] = assess_regression(
                plan,
                body["b"]["sealed"],
                [AssessedTarget.model_validate(t) for t in body["regressionTargets"]],
            )
            result = body["result"]
            forged = deepcopy(automatic)
            forged.update(
                state=result["state"],
                reasonCodes=result["reasonCodes"],
                b=body["b"]["sealed"]["b"],
                regression=result["regression"],
            )
            if result["state"] == "qualified":
                body["profile"]["sealedSha256"] = body["b"]["sealed"]["sha256"]
                body["profile"]["sha256"] = digest(
                    {k: v for k, v in body["profile"].items() if k != "sha256"}
                )
            else:
                body["profile"] = None
            forged["profile"] = body["profile"]
            evidence_path.write_text(
                canonical_json({"payload": body, "sha256": digest(body)}), encoding="utf-8"
            )
            forged["evidence"]["sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            with pytest.raises(ValueError, match="CALIBRATION_FROZEN_TARGET_SET_CHANGED"):
                require_calibration_evidence(
                    tmp_path,
                    forged,
                    frozen=frozen,
                    candidate_sha=report["manifestSha256"],
                    baseline_sha=report["baseManifestSha256"],
                )
    evidence_path.write_bytes(original)
    validate_payload = {
        "schema_version": 2,
        "validation_kind": "page_geometry_preflight",
        "preflight_policy_version": CAPABILITY_PREFLIGHT_POLICY,
        "source_selection_id": str(uuid4()),
        "source_manifest_sha256": "a" * 64,
        "source_directory": str(tmp_path),
        "source_display_name": "v4 cold retry",
        "neural_grid_proposal": model_snapshot,
        "neural_grid_operation_pin": pin,
    }
    validation = create_job(JobType.VALIDATE, game_id=game, input_payload=validate_payload)
    with game_storage_scope(game), factory.begin() as session:
        session.add(job_record_from_domain(validation))
    # A new process reads the exact IMPORT request under the real admission lock.
    code = """import os
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import JobModel
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_api.domain.v3_engine_acceptance import acceptance_for_operation_pin
from game_predictor_api.storage.neural_grid_operation_qualification import recheck_operation_pin
g=UUID(os.environ["FIXTURE_GAME"])
with game_storage_scope(g), Session(create_engine(os.environ["FIXTURE_DB"])) as s, s.begin():
 for kind,key in ((JobType.IMPORT,"FIXTURE_JOB"),(JobType.VALIDATE,"FIXTURE_VALIDATE")):
  row=s.get(JobModel,UUID(os.environ[key]))
  pin=SqlAlchemyJobRepository(s).find_neural_operation_pin(game_id=g,job_type=kind,input_payload=row.input_payload)
  assert descriptor_sha256(pin)==os.environ["FIXTURE_PIN"]
  assert acceptance_for_operation_pin(pin)=="v3-engine-acceptance-v4"
  blockers=recheck_operation_pin(s,pin=pin,model_snapshot=row.input_payload["neural_grid_proposal"],game_id=g)
  assert bool(blockers)==(os.environ.get("FIXTURE_DRIFT")=="1"),blockers
 print("cold exact IMPORT+VALIDATE pair/currentness PASS")
"""
    cold = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            "FIXTURE_DB": database.url,
            "FIXTURE_GAME": str(game),
            "FIXTURE_JOB": str(seed.import_job_id),
            "FIXTURE_VALIDATE": str(validation.id),
            "FIXTURE_PIN": expected,
        },
    )
    assert cold.returncode == 0, cold.stdout + cold.stderr
    with game_storage_scope(game), factory.begin() as session:
        session.add(
            GridModelEvaluationInvalidationModel(
                id=uuid4(),
                report_id=UUID(pin["automaticQualification"]["reportId"]),
                reason="drift",
                actor="fixture",
            )
        )
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed)[0] == "needs_review"
    drift = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            "FIXTURE_DB": database.url,
            "FIXTURE_GAME": str(game),
            "FIXTURE_JOB": str(seed.import_job_id),
            "FIXTURE_VALIDATE": str(validation.id),
            "FIXTURE_PIN": expected,
            "FIXTURE_DRIFT": "1",
        },
    )
    assert drift.returncode == 0, drift.stdout + drift.stderr
