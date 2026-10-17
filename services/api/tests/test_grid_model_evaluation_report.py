"""TASK-0997 report v2, per-game gate policy and the D-559 publication barrier."""

from __future__ import annotations

import copy
import json
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_model_evaluation import (
    GridEvaluationReportError,
    build_report,
    decide_game,
    require_report,
)
from game_predictor_api.domain.grid_model_publication import require_evaluation_evidence
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
)
from game_predictor_api.storage import grid_model_evaluation_repository as evidence_store
from game_predictor_api.storage.grid_model_registry_models import (
    GameGridModelAssignmentModel,
    GridModelCohortNoticeMarkModel,
    GridModelEvaluationCohortProofModel,
    GridModelEvaluationReportModel,
)
from sqlalchemy import delete, insert, update
from sqlalchemy.orm import Session
from test_grid_model_publication_and_activation import controls, execute, registry  # noqa: F401
from test_grid_model_registry import engine as registry_engine  # noqa: F401

GROUP = "77777777-7777-4777-8777-777777777777"


def metrics(
    *, photos=5, complete=5, correct=45, matched=45, false=0, macro=0.01, expected=45, duplicates=0
):
    return {
        "photos": photos,
        "photo_complete_correct": complete,
        "photo_complete_correct_rate": complete / photos if photos else None,
        "boards_expected": expected,
        "boards_correct": correct,
        "board_correct_rate": correct / expected if expected else None,
        "boards_matched": matched,
        "detection_recall": matched / expected if expected else None,
        "false_boards": false,
        "duplicate_predictions": duplicates,
        "image_macro": macro,
        "nme_p95": 0.01,
        "max_node_error_p95": 0.02,
    }


def role(base, candidate, photos=5):
    return {
        "photos": photos,
        "inputSha256": "a" * 64,
        "base": base,
        "candidate": candidate,
        "recordings": [{"groupId": GROUP, "base": base, "candidate": candidate}],
        "detail": {"path": "grid-model-evaluations/job/game-ROLE.json", "sha256": "b" * 64},
    }


def manifest(cohort=None):
    baseline = historical_catalogue()[0]
    payload = copy.deepcopy(baseline)
    payload.update(
        versionId=str(uuid4()),
        familyId=str(uuid4()),
        baseVersionId=baseline["versionId"],
        cohortId=str(cohort or uuid4()),
        admission="not_evaluated",
    )
    return payload


def report_for(candidate, games, *, parity=True, base_sha=None):
    """``games`` maps a game ID to (cohort ID, VALIDATION role, REGRESSION role)."""
    training = next(
        game for game, (cohort, *_ignored) in games.items() if cohort == candidate["cohortId"]
    )
    return build_report(
        manifest=candidate,
        base_manifest_sha256=base_sha or descriptor_sha256(historical_catalogue()[0]),
        training_game_id=training,
        parity={"passed": parity, "bundleSha256": "c" * 64},
        cohorts=[
            {"gameId": game, "cohortId": cohort, "manifestSha256": "d" * 64}
            for game, (cohort, *_ignored) in games.items()
        ],
        measured={
            game: {
                "mode": "grid-only",
                "roles": {"VALIDATION": validation, "REGRESSION": regression},
            }
            for game, (_cohort, validation, regression) in games.items()
        },
    )


def two_games(candidate, other_validation=None, other_regression=None):
    base = metrics(correct=40, complete=3)
    improved = metrics(correct=42, complete=4)
    same = metrics()
    return {
        str(uuid4()): (candidate["cohortId"], role(base, improved), role(same, same)),
        str(uuid4()): (
            str(uuid4()),
            other_validation or role(same, same),
            other_regression or role(same, same),
        ),
    }


def test_improvement_in_training_game_and_no_regression_elsewhere_passes():
    candidate = manifest()
    report = report_for(candidate, two_games(candidate))
    assert report["verdict"] == "PASS"
    assert report["requiredGameIds"] == sorted(report["requiredGameIds"])
    assert {game["validation"] for game in report["games"]} == {"pass"}
    parsed = require_report(
        canonical_json(report), manifest=candidate, base_sha256=report["baseManifestSha256"]
    )
    assert parsed == report


def test_an_extra_duplicate_detection_is_a_regression():
    candidate = manifest()
    worse = role(metrics(), metrics(duplicates=1))
    report = report_for(candidate, two_games(candidate, other_regression=worse))
    assert report["verdict"] == "REVISE"
    other = next(game for game in report["games"] if game["cohortId"] != candidate["cohortId"])
    assert other["reasons"] == ["REGRESSION_REGRESSED:duplicate_predictions"]


def test_regression_of_any_game_blocks_the_shared_pass():
    candidate = manifest()
    worse = role(metrics(), metrics(correct=44, matched=44, macro=0.02))
    report = report_for(candidate, two_games(candidate, other_regression=worse))
    assert report["verdict"] == "REVISE"
    other = next(game for game in report["games"] if game["cohortId"] != candidate["cohortId"])
    assert other["regression"] == "fail"
    assert "REGRESSION_REGRESSED:boards_matched" in other["reasons"]
    assert "REGRESSION_REGRESSED:image_macro" in other["reasons"]


def test_a_missing_detection_has_a_cost_and_unknown_quality_is_not_zero_error():
    # One undetected board lowers matched/correct and costs 1 in image-macro.
    missing = metrics(correct=44, matched=44, complete=4, macro=0.01 + 1 / 9 / 5)
    decision = decide_game(
        mode="grid-only",
        training=False,
        parity_passed=True,
        roles={"VALIDATION": role(metrics(), missing), "REGRESSION": role(metrics(), metrics())},
    )
    assert decision["validation"] == "fail"
    assert "VALIDATION_REGRESSED:boards_matched" in decision["reasons"]
    unknown = metrics(macro=None)
    decision = decide_game(
        mode="grid-only",
        training=False,
        parity_passed=True,
        roles={"VALIDATION": role(metrics(), unknown), "REGRESSION": role(metrics(), metrics())},
    )
    assert "VALIDATION_REGRESSED:image_macro" in decision["reasons"]


def test_training_game_must_strictly_improve_its_target_metric():
    candidate = manifest()
    games = two_games(candidate)
    training = next(game for game, value in games.items() if value[0] == candidate["cohortId"])
    games[training] = (
        candidate["cohortId"],
        role(metrics(), metrics()),
        role(metrics(), metrics()),
    )
    report = report_for(candidate, games)
    assert report["verdict"] == "REVISE"
    game = next(item for item in report["games"] if item["gameId"] == training)
    assert game["reasons"] == ["VALIDATION_NOT_IMPROVED:boards_correct"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"photos": 4}, "COVERAGE_PHOTOS_BELOW_MINIMUM:VALIDATION"),
        ({"candidate_photos": 4}, "COVERAGE_INCOMPLETE:VALIDATION"),
        ({"parity": False}, "CANDIDATE_PARITY_FAILED"),
    ],
)
def test_missing_data_or_parity_is_not_evaluable(change, reason):
    candidate = manifest()
    games = two_games(candidate)
    other = next(game for game, value in games.items() if value[0] != candidate["cohortId"])
    cohort, validation, regression = games[other]
    if "photos" in change:
        small = metrics(photos=4, complete=4, expected=36, correct=36, matched=36)
        validation = role(small, small, photos=4)
    if "candidate_photos" in change:
        partial = metrics(photos=4, complete=4, expected=36, correct=36, matched=36)
        validation = role(metrics(), partial)
        validation["recordings"][0]["candidate"] = partial
    games[other] = (cohort, validation, regression)
    report = report_for(candidate, games, parity=change.get("parity", True))
    assert report["verdict"] == "NOT_EVALUABLE"
    assert any(reason in game["reasons"] for game in report["games"])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(verdict="PASS" if r["verdict"] != "PASS" else "REVISE"),
        lambda r: r["games"][0].update(validation="fail"),
        lambda r: r["games"][0].update(reasons=["HAND_WRITTEN"]),
        lambda r: r["games"][0]["roles"]["REGRESSION"]["candidate"].update(boards_matched=1),
        lambda r: r.update(extra=True),
        lambda r: r.update(cohorts=list(reversed(r["cohorts"]))),
        lambda r: r.update(policyVersion="other"),
        lambda r: r["policy"].update(minimumControlPhotos=1),
        lambda r: r.update(
            trainingGameId=next(
                e["gameId"] for e in r["cohorts"] if e["gameId"] != r["trainingGameId"]
            )
        ),
        lambda r: r["games"][0]["roles"]["VALIDATION"].update(
            detail={"path": "../x", "sha256": "b" * 64}
        ),
    ],
)
def test_reader_recomputes_every_decision_and_rejects_tampering(mutation):
    candidate = manifest()
    report = report_for(candidate, two_games(candidate))
    changed = json.loads(canonical_json(report))
    mutation(changed)
    with pytest.raises(GridEvaluationReportError):
        require_report(
            canonical_json(changed), manifest=candidate, base_sha256=report["baseManifestSha256"]
        )


def test_only_a_measured_pass_is_publication_evidence():
    candidate = manifest()
    base_sha = descriptor_sha256(historical_catalogue()[0])
    for games, accepted in (
        (two_games(candidate), True),
        (two_games(candidate, other_regression=role(metrics(), metrics(false=1))), False),
    ):
        report = report_for(candidate, games)
        arguments = {
            "report_id": uuid4(),
            "report_json": canonical_json(report),
            "report_sha256": descriptor_sha256(report),
            "producer": "server:grid-model-evaluator-v1",
            "invalidated": False,
            "manifest": candidate,
            "base_sha256": base_sha,
            "game_id": None,
        }
        if accepted:
            evidence = require_evaluation_evidence(**arguments)
            assert [entry["gameId"] for entry in evidence.cohorts] == report["requiredGameIds"]
        else:
            with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
                require_evaluation_evidence(**arguments)
    with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
        require_evaluation_evidence(**{**arguments, "producer": "client:untrusted"})


def _seed_v2(c, session, other_game_entry=True):
    games = {
        str(c.game): (
            c.candidate["cohortId"],
            role(metrics(correct=40), metrics(correct=42)),
            role(metrics(), metrics()),
        )
    }
    if other_game_entry:
        games[str(c.other)] = (str(uuid4()), role(metrics(), metrics()), role(metrics(), metrics()))
    report = report_for(c.candidate, games)
    key = uuid4()
    session.add(
        GridModelEvaluationReportModel(
            id=key,
            version_id=UUID(c.candidate["versionId"]),
            producer="server:grid-model-evaluator-v1",
            report_json=canonical_json(report),
            report_sha256=descriptor_sha256(report),
        )
    )
    session.flush()
    return key, report


def _proof(session, key, entry, count):
    session.add(
        GridModelEvaluationCohortProofModel(
            id=uuid4(),
            report_id=key,
            game_id=UUID(entry["gameId"]),
            cohort_id=UUID(entry["cohortId"]),
            manifest_sha256=entry["manifestSha256"],
            notice_count=count,
            storage_generation=2,
            bind_receipt_sha256="e" * 64,
            eligibility_sha256="f" * 64,
            actor="server:grid-model-evaluator-v1",
        )
    )
    session.flush()


def _bridge(c):
    with c.engine.begin() as connection:
        GridModelCohortNoticeMarkModel.__table__.create(connection)
        GridModelEvaluationCohortProofModel.__table__.create(connection)
        connection.exec_driver_sql(
            "CREATE TABLE public.game_storage_locations "
            "(game_id CHAR(32) PRIMARY KEY, generation INTEGER NOT NULL, status TEXT NOT NULL)"
        )
        for game in (c.game, c.other):
            connection.execute(
                insert(evidence_store._LOCATIONS).values(
                    game_id=game, generation=2, status="active"
                )
            )


def test_cohort_proofs_gate_publication_activation_and_default(controls):  # noqa: F811
    c = controls
    _bridge(c)
    with Session(c.engine) as session:
        service = registry(session, c.root)
        key, report = _seed_v2(c, session)
        execute(service, "publish", c.baseline["versionId"])
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED") as error:
            execute(service, "publish", c.candidate["versionId"], evaluation=key)
        assert error.value.details["gameId"] == report["cohorts"][0]["gameId"]
        for entry in report["cohorts"]:
            _proof(session, key, entry, 0)
        execute(service, "publish", c.candidate["versionId"], evaluation=key)
        execute(service, "activate", c.candidate["versionId"], game=c.game, expected=1)
        # A later notice in any evaluated game makes the proof stale for every control.
        other = next(entry for entry in report["cohorts"] if entry["gameId"] == str(c.other))
        session.add(
            GridModelCohortNoticeMarkModel(
                id=1, game_id=UUID(other["gameId"]), cohort_id=UUID(other["cohortId"])
            )
        )
        session.flush()
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_STALE"):
            execute(service, "set_default", c.candidate["versionId"], expected=0)
        assert (
            service.view(service.repository.version(UUID(c.candidate["versionId"])))[
                "eligibilityReasonCode"
            ]
            == "GRID_MODEL_EVALUATION_STALE"
        )
        _proof(session, key, other, 1)
        execute(service, "set_default", c.candidate["versionId"], expected=0)
        session.rollback()


def test_publication_requires_every_game_of_the_family(controls):  # noqa: F811
    c = controls
    _bridge(c)
    with Session(c.engine) as session:
        service = registry(session, c.root)
        key, report = _seed_v2(c, session, other_game_entry=False)
        for entry in report["cohorts"]:
            _proof(session, key, entry, 0)
        session.add(
            GameGridModelAssignmentModel(
                game_id=c.other,
                version_id=UUID(c.baseline["versionId"]),
                revision=1,
                training_family_id=UUID(c.candidate["familyId"]),
            )
        )
        session.flush()
        execute(service, "publish", c.baseline["versionId"])
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED") as error:
            execute(service, "publish", c.candidate["versionId"], evaluation=key)
        assert error.value.details == {"gameIds": [str(c.other)]}
        session.rollback()


@pytest.mark.parametrize(
    "change",
    [
        lambda game: update(evidence_store._LOCATIONS)
        .where(evidence_store._LOCATIONS.c.game_id == game)
        .values(status="deleting"),
        lambda game: delete(evidence_store._LOCATIONS).where(
            evidence_store._LOCATIONS.c.game_id == game
        ),
        lambda game: update(evidence_store._LOCATIONS)
        .where(evidence_store._LOCATIONS.c.game_id == game)
        .values(generation=3),
    ],
)
def test_a_deleted_or_moved_game_store_never_keeps_its_proof_current(controls, change):  # noqa: F811
    c = controls
    _bridge(c)
    with Session(c.engine) as session:
        service = registry(session, c.root)
        key, report = _seed_v2(c, session)
        for entry in report["cohorts"]:
            _proof(session, key, entry, 0)
        execute(service, "publish", c.baseline["versionId"])
        execute(service, "publish", c.candidate["versionId"], evaluation=key)
        session.execute(change(c.other))
        session.flush()
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_STALE") as error:
            execute(service, "set_default", c.candidate["versionId"], expected=0)
        assert error.value.details["gameId"] == str(c.other)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_STALE"):
            execute(service, "activate", c.candidate["versionId"], game=c.game, expected=1)
        session.rollback()
