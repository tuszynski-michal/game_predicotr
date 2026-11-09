"""Proposal processing never creates model qualification or human geometry truth."""

from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest
from game_predictor_api.domain.neural_crop_policy import SYMBOL_REVIEW_CROP_POLICY
from game_predictor_api.domain.neural_grid_operation_pin import (
    CALIBRATION_REQUIRED,
    GAME_EVALUATION_REQUIRED,
    make_operation_pin,
    operation_pin_blockers,
    require_operation_pin,
)
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.domain.v3_engine_acceptance import (
    SYMBOL_REVIEW_ENGINE_POLICY,
    acceptance_for_operation_pin,
    pin_v3_engine_acceptance_policy,
    qualify_v3_engine_acceptance,
)
from game_predictor_worker.images.neural_pending_geometry import neural_pending_payload
from test_v3_engine_acceptance import facts


def fixture():
    value = facts()
    snapshot = NeuralGridSnapshot.from_payload(value["model_snapshot"])
    pin = make_operation_pin(
        snapshot=snapshot,
        game_id=value["game_id"],
        rules_version_id=str(uuid4()),
        rows=3,
        columns=5,
        qualification={"state": "unqualified", "reasonCodes": [GAME_EVALUATION_REQUIRED]},
        automatic_qualification={"state": "unqualified", "reasonCodes": [CALIBRATION_REQUIRED]},
        for_symbol_review=True,
    )
    value["policy"] = SYMBOL_REVIEW_ENGINE_POLICY
    value["operation_pin"] = pin
    value["qualification_blockers"] = ()
    value["positions"] = [
        replace(
            position,
            geometry={**position.geometry, "neuralExecutionPolicy": SYMBOL_REVIEW_CROP_POLICY},
        )
        for position in value["positions"]
    ]
    return value, snapshot, pin


def test_valid_proposals_process_without_minting_qualification():
    value, snapshot, pin = fixture()
    before = deepcopy(pin)
    assert require_operation_pin(pin, snapshot=snapshot, game_id=value["game_id"]) == pin
    assert qualify_v3_engine_acceptance(**value) == ()
    assert operation_pin_blockers(
        pin, model_snapshot=value["model_snapshot"], game_id=value["game_id"]
    ) == (GAME_EVALUATION_REQUIRED,)
    assert pin == before and pin["automaticQualification"]["state"] == "unqualified"
    assert all("approved_geometry_revision" not in p.geometry for p in value["positions"])


def test_new_import_pins_review_purpose_and_crop_contract():
    value, _, pin = fixture()
    payload = {"neural_grid_proposal": value["model_snapshot"], "neural_grid_operation_pin": pin}
    from game_predictor_api.domain.neural_grid_operation_pin import OPERATION_PIN_KEY

    payload[OPERATION_PIN_KEY] = payload.pop("neural_grid_operation_pin")
    pin_v3_engine_acceptance_policy(payload, "a" * 64)
    assert acceptance_for_operation_pin(pin) == SYMBOL_REVIEW_ENGINE_POLICY
    assert payload["neural_grid_execution_policy_version"] == SYMBOL_REVIEW_CROP_POLICY


def test_worker_projects_real_cells_for_human_review():
    value, _, pin = fixture()
    result = neural_pending_payload(
        {
            "sourceChecksumSha256": value["source_checksum_sha256"],
            "canonicalWidth": value["width"],
            "canonicalHeight": value["height"],
            "boards": [{"positionIndex": i} for i in range(5)],
            "engineId": "fixture",
            "globalInitialization": {},
        },
        {"neuralProposal": value["proposal"], "neuralProposalBinding": value["binding"]},
        automatic_crops=True,
        execution_policy=SYMBOL_REVIEW_CROP_POLICY,
        engine_acceptance_policy=SYMBOL_REVIEW_ENGINE_POLICY,
        operation_pin=pin,
        qualification_blockers=(CALIBRATION_REQUIRED,),
    )
    assert all(board["finalQuad"] is not None for board in result["structuredGeometry"]["boards"])


def test_review_never_erases_technical_qualification_failures():
    value, _, _ = fixture()
    value["qualification_blockers"] = (CALIBRATION_REQUIRED, "NEURAL_GRID_TOPOLOGY_UNSUPPORTED")
    assert "NEURAL_GRID_TOPOLOGY_UNSUPPORTED" in qualify_v3_engine_acceptance(**value)


def test_fit_failure_still_blocks_review_rendering():
    from game_predictor_api.domain.neural_crop_policy import neural_auto_crop_blockers

    value, _, _ = fixture()
    detection = deepcopy(value["proposal"]["detections"][0])
    detection["reasonCodes"].append("NEURAL_GRID_FIT_FAILED")
    assert "NEURAL_GRID_FIT_FAILED" in neural_auto_crop_blockers(
        policy=SYMBOL_REVIEW_CROP_POLICY,
        detection=detection,
        binding=value["binding"],
        position=0,
        width=value["width"],
        height=value["height"],
    )


def test_review_rejects_a_calibrated_contract_instead_of_downgrading_it():
    value, snapshot, pin = fixture()
    calibrated = make_operation_pin(
        snapshot=snapshot,
        game_id=value["game_id"],
        rules_version_id=pin["topologyRulesVersionId"],
        rows=3,
        columns=5,
        qualification=pin["qualification"],
        automatic_qualification=pin["automaticQualification"],
    )
    assert calibrated["contractVersion"] == "neural-grid-operation-pin-v3"
    assert acceptance_for_operation_pin(calibrated) == "v3-engine-acceptance-v4"
    value["operation_pin"] = calibrated
    assert "NEURAL_GRID_OPERATION_POLICY_MISMATCH" in qualify_v3_engine_acceptance(**value)
    assert operation_pin_blockers(
        calibrated,
        model_snapshot=value["model_snapshot"],
        game_id=value["game_id"],
        for_symbol_review=True,
    ) == ("NEURAL_GRID_OPERATION_POLICY_MISMATCH",)


@pytest.mark.parametrize("blockers", [None, ("NEURAL_GRID_GAME_EVALUATION_UNCHECKED",)])
def test_review_requires_an_actual_technical_recheck(blockers):
    value, _, _ = fixture()
    value["qualification_blockers"] = blockers
    assert "NEURAL_GRID_GAME_EVALUATION_UNCHECKED" in qualify_v3_engine_acceptance(**value)


@pytest.mark.parametrize("fault", ["outside", "visibility"])
def test_review_rejects_missing_real_pixels(fault):
    from game_predictor_api.domain.neural_crop_policy import neural_auto_crop_blockers

    value, _, _ = fixture()
    detection = deepcopy(value["proposal"]["detections"][0])
    if fault == "outside":
        for point in detection["latticeNodes"]:
            point["x"] -= value["width"]
    else:
        detection["cellVisibility"][0] = "partial"
    assert "NEURAL_GRID_PIXELS_UNAVAILABLE" in neural_auto_crop_blockers(
        policy=SYMBOL_REVIEW_CROP_POLICY,
        detection=detection,
        binding=value["binding"],
        position=0,
        width=value["width"],
        height=value["height"],
    )


@pytest.mark.parametrize("fault", ["topology", "foreign_game"])
def test_review_recheck_rejects_incompatible_database_rules(fault):
    from types import SimpleNamespace
    from uuid import UUID

    from game_predictor_api.storage.neural_grid_operation_qualification import recheck_operation_pin

    value, _, pin = fixture()
    game = UUID(value["game_id"])
    rules = SimpleNamespace(
        game_id=uuid4() if fault == "foreign_game" else game,
        rows=4 if fault == "topology" else 3,
        columns=5,
    )
    assert recheck_operation_pin(
        SimpleNamespace(get=lambda *_: rules),
        pin=pin,
        model_snapshot=value["model_snapshot"],
        game_id=game,
        for_symbol_review=True,
    ) == ("NEURAL_GRID_TOPOLOGY_UNSUPPORTED",)


@pytest.mark.parametrize("fault", ["pin", "pixels", "owner"])
def test_review_keeps_identity_pixels_and_ownership_fences(fault):
    value, _, _ = fixture()
    if fault == "pin":
        value["operation_pin"]["pinSha256"] = "0" * 64
    if fault == "pixels":
        value["width"] = 1
    if fault == "owner":
        value["positions"][0] = replace(value["positions"][0], current_owner=False)
    assert qualify_v3_engine_acceptance(**value)
