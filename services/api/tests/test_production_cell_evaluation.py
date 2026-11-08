"""D591 gate evidence: fixed populations, no instance or game compensation."""

from copy import deepcopy
from typing import Any
from uuid import UUID

import pytest
from game_predictor_api.domain.grid_correction_evaluation import build_report
from game_predictor_api.domain.grid_model_evaluation import GridEvaluationReportError
from game_predictor_api.domain.grid_model_publication import require_evaluation_evidence
from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256
from game_predictor_api.domain.production_cell_evaluation import (
    BASE_VERSION_ID,
    ContentGameEvidence,
    attach_content,
    decide_game,
    require_report,
)
from pydantic import ValidationError
from test_grid_correction_evaluation import fixture as historical_fixture
from test_grid_correction_evaluation import metrics, role, uid


def evidence(game: str = uid(5)) -> dict[str, Any]:
    def counts(preserved: int, usable: int) -> dict[str, int]:
        return dict(
            preserved=preserved,
            borderline=0,
            clipped=675 - preserved,
            missing=0,
            wrongCells=0,
            ties=0,
            foreignSymbols=0,
            ambiguousBoards=0,
            usableBoards=usable,
        )

    per_role = dict(
        state="ready",
        reasonCodes=[],
        photos=5,
        fullPhotos=5,
        slots=675,
        visible=675,
        unknown=0,
        occluded=0,
        outOfFrame=0,
        referenceSha256="a" * 64,
        base=counts(660, 10),
        candidate=counts(675, 11),
        degradedInstances=0,
        newWrongCells=0,
        newTies=0,
        newForeignSymbols=0,
        newMatchAmbiguities=0,
    )
    return dict(
        gameId=game,
        state="ready",
        reasonCodes=[],
        u=0.02,
        delta=0.002,
        measurementSha256="b" * 64,
        classifierSnapshotSha256s=["c" * 64],
        renderConfigurationSha256s=["d" * 64],
        freshRegression=True,
        roles={name: deepcopy(per_role) for name in ("VALIDATION", "REGRESSION")},
    )


def geometry() -> dict[str, Any]:
    return {
        name: role(metrics(full=True), metrics(full=True, correct=13))
        for name in ("VALIDATION", "REGRESSION")
    }


def decision(
    content: dict[str, Any],
    roles: dict[str, Any] | None = None,
    *,
    training: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    return decide_game(
        training=training,
        parity_passed=kwargs.get("parity", True),
        roles=geometry() if roles is None else roles,
        content=ContentGameEvidence.model_validate(content),
        base_version_id=kwargs.get("base", BASE_VERSION_ID),
    )


@pytest.mark.parametrize("name", ["VALIDATION", "REGRESSION"])
@pytest.mark.parametrize(
    "new_error",
    ["degradedInstances", "newWrongCells", "newTies", "newForeignSymbols", "newMatchAmbiguities"],
)
def test_instance_regression_cannot_be_compensated(name: str, new_error: str) -> None:
    content = evidence()
    data = content["roles"][name]
    data[new_error] = 1
    if new_error == "degradedInstances":
        data["candidate"].update(preserved=674, clipped=1)
    else:
        total = {
            "newWrongCells": "wrongCells",
            "newTies": "ties",
            "newForeignSymbols": "foreignSymbols",
            "newMatchAmbiguities": "ambiguousBoards",
        }[new_error]
        data["base"][total] = 2
        data["candidate"][total] = 1
    result = decision(content)
    assert result[name.lower()] == "fail"
    assert f"{name}_REGRESSED:{new_error}" in result["reasons"]
    # Aggregate preservation and usable boards improved, yet the new error blocks.
    assert content["roles"][name]["candidate"]["preserved"] > 660


@pytest.mark.parametrize("name", ["VALIDATION", "REGRESSION"])
@pytest.mark.parametrize("error,expected", [(0.022, "pass"), (0.022000000001, "fail")])
def test_nme_delta_is_inclusive_and_role_local(name: str, error: float, expected: str) -> None:
    roles = geometry()
    roles[name]["candidate"]["normalized_error"] = error
    assert decision(evidence(), roles)[name.lower()] == expected


@pytest.mark.parametrize("name", ["VALIDATION", "REGRESSION"])
@pytest.mark.parametrize(
    "metric",
    [
        "boards_correct",
        "boards_matched",
        "false_boards",
        "duplicate_predictions",
        "photo_complete_correct",
    ],
)
def test_geometry_regression_blocks_even_with_content_gain(name: str, metric: str) -> None:
    roles = geometry()
    before, after = roles[name]["base"], roles[name]["candidate"]
    if metric == "boards_correct":
        after.update(boards_correct=11, board_correct_rate=11 / 45)
    elif metric == "boards_matched":
        after.update(boards_matched=44, detection_recall=44 / 45)
    elif metric == "photo_complete_correct":
        before.update(photo_complete_correct=1, photo_complete_correct_rate=0.2)
    else:
        after[metric] = 1
    assert decision(evidence(), roles)[name.lower()] == "fail"


def test_gain_is_required_in_current_game_reg_only() -> None:
    content = evidence()
    content["roles"]["REGRESSION"]["candidate"]["usableBoards"] = 10
    assert decision(content)["regression"] == "fail"
    assert decision(content)["validation"] == "pass"
    assert decision(content, training=False)["regression"] == "pass"


def test_reject_all_is_missing_not_an_improvement() -> None:
    content, roles = evidence(), geometry()
    for name in ("VALIDATION", "REGRESSION"):
        content["roles"][name]["candidate"].update(
            preserved=0, borderline=0, clipped=0, missing=675, usableBoards=0
        )
        content["roles"][name]["degradedInstances"] = 660
        roles[name]["candidate"].update(
            boards_correct=0,
            boards_matched=0,
            board_correct_rate=0.0,
            detection_recall=0.0,
            normalized_error=1.0,
        )
    result = decision(content, roles)
    assert result["validation"] == result["regression"] == "fail"
    assert result["coverage"] == "complete"


@pytest.mark.parametrize("name", ["VALIDATION", "REGRESSION"])
def test_candidate_cannot_drop_reference_targets(name: str) -> None:
    roles = geometry()
    roles[name]["candidate"].update(
        boards_expected=40,
        boards_matched=40,
        full_photos=4,
        partial_photos=1,
        board_correct_rate=13 / 40,
    )
    result = decision(evidence(), roles)
    assert result["coverage"] == "incomplete"
    assert f"CONTENT_COVERAGE_INCOMPLETE:{name}" in result["reasons"]


def test_usable_boards_cannot_exceed_correct_geometry() -> None:
    content = evidence()
    content["roles"]["REGRESSION"]["candidate"]["usableBoards"] = 14
    # Geometry has only 13 correct boards. Counts must not fabricate the +1 proof.
    result = decision(content)
    assert result["regression"] != "pass"


@pytest.mark.parametrize("field", ["unknown", "occluded", "outOfFrame"])
def test_nonvisible_labels_cannot_supply_fifteen_preserved(field: str) -> None:
    content = evidence()
    data = content["roles"]["REGRESSION"]
    data.update(visible=14, unknown=0, occluded=0, outOfFrame=0)
    data[field] = 661
    for model in ("base", "candidate"):
        data[model].update(preserved=14, clipped=0, usableBoards=0)
    data["candidate"]["usableBoards"] = 1
    with pytest.raises(ValidationError, match="CONTENT_COUNTS_INVALID"):
        ContentGameEvidence.model_validate(content)


@pytest.mark.parametrize("name", ["VALIDATION", "REGRESSION"])
@pytest.mark.parametrize("unknown,expected", [(60, "pass"), (61, "not_evaluable")])
def test_unknown_limit_has_whole_role_denominator(name: str, unknown: int, expected: str) -> None:
    content, roles = evidence(), geometry()
    data = content["roles"][name]
    data.update(slots=600, visible=600 - unknown, unknown=unknown, fullPhotos=4)
    for model, usable in (("base", 10), ("candidate", 11)):
        data[model].update(preserved=600 - unknown, clipped=0, usableBoards=usable)
        roles[name][model].update(
            boards_expected=40,
            boards_matched=40,
            full_photos=4,
            partial_photos=1,
            board_correct_rate=roles[name][model]["boards_correct"] / 40,
        )
    if name == "REGRESSION":
        # Full-photo prerequisite independently blocks REG; use a 750-slot population.
        data.update(
            slots=750,
            visible=750 - (75 if unknown == 60 else 76),
            unknown=75 if unknown == 60 else 76,
            fullPhotos=5,
            photos=6,
        )
        for model in ("base", "candidate"):
            data[model]["preserved"] = data["visible"]
            roles[name][model].update(
                photos=6,
                full_photos=5,
                partial_photos=1,
                boards_expected=50,
                boards_matched=50,
                board_correct_rate=roles[name][model]["boards_correct"] / 50,
            )
        roles[name]["photos"] = 6
    assert decision(content, roles)[name.lower()] == expected


@pytest.mark.parametrize(
    "mutation",
    ["old_reg", "four_full", "missing_uncertainty", "role_unready", "wrong_base", "parity"],
)
def test_missing_required_proof_is_not_evaluable(mutation: str) -> None:
    content = evidence()
    kwargs: dict[str, Any] = {}
    if mutation == "old_reg":
        content["freshRegression"] = False
    elif mutation == "four_full":
        content["roles"]["REGRESSION"]["fullPhotos"] = 4
    elif mutation == "missing_uncertainty":
        content.update(
            state="not_evaluable",
            reasonCodes=["MEASUREMENT_MISSING"],
            u=None,
            delta=None,
            measurementSha256=None,
        )
    elif mutation == "role_unready":
        content["roles"]["VALIDATION"].update(state="not_evaluable", reasonCodes=["LABELS_MISSING"])
    elif mutation == "wrong_base":
        kwargs["base"] = uid(999)
    else:
        kwargs["parity"] = False
    assert decision(content, **kwargs)["coverage"] == "incomplete"


def test_partial_validation_cannot_claim_whole_photo_correctness() -> None:
    content, roles = evidence(), geometry()
    data = content["roles"]["VALIDATION"]
    data.update(fullPhotos=0, slots=225, visible=225)
    for model in ("base", "candidate"):
        data[model].update(preserved=225, clipped=0)
    roles["VALIDATION"] = role(metrics(), metrics(correct=13))
    assert decision(content, roles)["validation"] == "pass"
    roles["VALIDATION"]["candidate"]["photo_complete_correct"] = 1
    with pytest.raises(GridEvaluationReportError, match="Partial photos"):
        decision(content, roles)


def reports() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest, old = historical_fixture()
    manifest["baseVersionId"] = BASE_VERSION_ID
    raw = build_report(
        manifest=manifest,
        base_manifest_sha256="c" * 64,
        training_game_id=old["trainingGameId"],
        parity=old["parity"],
        cohorts=old["cohorts"],
        scope=old["scope"],
        checkpoint_selection=old["checkpointSelection"],
        measured={
            game: {"mode": "grid-only", "roles": geometry()} for game in old["requiredGameIds"]
        },
    )
    return manifest, raw, attach_content(raw, [evidence(game) for game in raw["requiredGameIds"]])


def test_report_roundtrip_and_dispatch_preserve_legacy_exactly() -> None:
    manifest, raw, content = reports()
    original = canonical_json(raw)
    assert content["rawQuality"] == raw
    assert (
        require_report(canonical_json(content), manifest=manifest, base_sha256="c" * 64) == content
    )
    for report in (raw, content):
        checked = require_evaluation_evidence(
            report_id=UUID(int=88),
            report_json=canonical_json(report),
            report_sha256=descriptor_sha256(report),
            producer=report["producer"],
            invalidated=False,
            manifest=manifest,
            base_sha256="c" * 64,
            game_id=UUID(uid(5)),
        )
        assert checked.games == frozenset(UUID(game) for game in raw["requiredGameIds"])
    assert canonical_json(raw) == original


def test_prior_game_failure_cannot_be_averaged_with_current_gain() -> None:
    _, raw, _ = reports()
    contents = [evidence(game) for game in raw["requiredGameIds"]]
    contents[1]["roles"]["VALIDATION"]["newWrongCells"] = 1
    contents[1]["roles"]["VALIDATION"]["candidate"]["wrongCells"] = 1
    result = attach_content(raw, contents)
    assert result["games"][0]["regression"] == "pass"
    assert result["games"][1]["validation"] == "fail"
    assert result["verdict"] != "PASS"


@pytest.mark.parametrize(
    "counter",
    ["degradedInstances", "newWrongCells", "newTies", "newForeignSymbols", "newMatchAmbiguities"],
)
def test_new_error_cannot_exceed_candidate_errors(counter: str) -> None:
    content = evidence()
    # Candidate has no error in any of these categories, so a new error is impossible.
    content["roles"]["VALIDATION"][counter] = 1
    with pytest.raises(ValidationError):
        ContentGameEvidence.model_validate(content)


def test_delta_belongs_to_each_game_not_global_average() -> None:
    manifest, raw, _ = reports()
    measured = {}
    for game in raw["requiredGameIds"]:
        roles = geometry()
        roles["VALIDATION"]["candidate"]["normalized_error"] = 0.0215
        measured[game] = {"mode": "grid-only", "roles": roles}
    raw = build_report(
        manifest=manifest,
        base_manifest_sha256="c" * 64,
        training_game_id=raw["trainingGameId"],
        parity=raw["parity"],
        cohorts=raw["cohorts"],
        scope=raw["scope"],
        checkpoint_selection=raw["checkpointSelection"],
        measured=measured,
    )
    contents = [evidence(game) for game in raw["requiredGameIds"]]
    contents[1]["delta"] = 0.001
    result = attach_content(raw, contents)
    assert result["games"][0]["validation"] == "pass"
    assert result["games"][1]["validation"] == "fail"
    assert "VALIDATION_REGRESSED:normalized_error" in result["games"][1]["reasons"]


@pytest.mark.parametrize(
    "field",
    ["delta", "u", "measurementSha256", "classifierSnapshotSha256s", "renderConfigurationSha256s"],
)
def test_ready_requires_measurement_and_production_snapshots(field: str) -> None:
    content = evidence()
    content[field] = [] if field.endswith("s") else None
    with pytest.raises(ValidationError):
        ContentGameEvidence.model_validate(content)


@pytest.mark.parametrize(
    "mutation",
    ["missing_game", "wrong_game", "missing_role", "counter", "decision", "base", "raw_metric"],
)
def test_closed_report_rejects_missing_or_reinterpreted_evidence(mutation: str) -> None:
    manifest, _, report = reports()
    if mutation == "missing_game":
        report["contentEvaluation"].pop()
    elif mutation == "wrong_game":
        report["contentEvaluation"][1]["gameId"] = uid(999)
    elif mutation == "missing_role":
        del report["contentEvaluation"][0]["roles"]["VALIDATION"]
    elif mutation == "counter":
        report["contentEvaluation"][0]["roles"]["VALIDATION"]["candidate"]["preserved"] -= 1
    elif mutation == "decision":
        report["games"][0]["regression"] = "fail"
    elif mutation == "base":
        report["baseVersionId"] = uid(999)
    else:
        report["rawQuality"]["games"][0]["roles"]["REGRESSION"]["candidate"]["boards_correct"] = 0
    with pytest.raises(GridEvaluationReportError):
        require_report(canonical_json(report), manifest=manifest, base_sha256="c" * 64)


@pytest.mark.parametrize(
    "small_role,expected", [("VALIDATION", "pass"), ("REGRESSION", "not_evaluable")]
)
def test_five_photo_minimum_is_reg_only_not_an_extra_a_gate(small_role: str, expected: str) -> None:
    content, roles = evidence(), geometry()
    small_metrics = {
        **metrics(correct=2),
        "photos": 1,
        "partial_photos": 1,
        "boards_expected": 3,
        "boards_matched": 3,
        "board_correct_rate": 2 / 3,
    }
    roles[small_role] = {**role(small_metrics, deepcopy(small_metrics)), "photos": 1}
    content["roles"][small_role].update(
        photos=1,
        fullPhotos=0,
        slots=45,
        visible=45,
    )
    for model, usable in (("base", 1), ("candidate", 2)):
        content["roles"][small_role][model].update(
            preserved=45,
            clipped=0,
            usableBoards=usable,
        )
    # A has one photo/three boards and the same measured population on both sides.
    # REG still has five full photos/45 boards, so the content gate can pass.
    # Putting that small population in REG must continue to fail closed.
    result = decision(content, roles)
    assert result["validation"] == result["regression"] == expected
    if small_role == "VALIDATION":
        assert content["roles"]["REGRESSION"]["fullPhotos"] == 5
        assert result["reasons"] == []
    else:
        assert "CONTENT_COVERAGE_INCOMPLETE:REGRESSION" in result["reasons"]
        assert "CONTENT_FRESH_REGRESSION_REQUIRED" in result["reasons"]
