from copy import deepcopy
from dataclasses import replace

import pytest
from game_predictor_api.domain.neural_crop_policy import NEURAL_AUTO_CROP_POLICY
from game_predictor_api.domain.neural_grid_proposal import associate_expected_slots
from game_predictor_api.domain.v3_engine_acceptance import (
    V3_ENGINE_ACCEPTANCE_ACTOR,
    V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY,
    V3_ENGINE_ACCEPTANCE_POLICY,
    V3EnginePosition,
    pin_v3_engine_acceptance_policy,
    qualify_v3_engine_acceptance,
)
from game_predictor_worker.images.neural_pending_geometry import neural_pending_payload
from game_predictor_worker.vision_lab.production_geometry import LabelFacts, classify_label_level
from test_neural_grid_proposal import proposal


def facts():
    value = proposal()
    binding = associate_expected_slots(value)
    return {
        "policy": V3_ENGINE_ACCEPTANCE_POLICY,
        "proposal": value,
        "binding": binding,
        "model_snapshot": value["engineSnapshot"],
        "game_id": value["gameId"],
        "source_checksum_sha256": value["sourceChecksumSha256"],
        "width": 500,
        "height": 300,
        "active_slots": list(range(5)),
        "sequence_start": 101,
        "sequence_end": 105,
        "positions": [
            V3EnginePosition(
                index,
                101 + index,
                {
                    "quad": [item["latticeNodes"][i] for i in (0, 5, 23, 18)],
                    "latticeNodes": deepcopy(item["latticeNodes"]),
                    "detectionId": item["detectionId"],
                    "neuralExecutionPolicy": NEURAL_AUTO_CROP_POLICY,
                    "neuralProposalChecksumSha256": value["proposalChecksumSha256"],
                    "neuralProposalBinding": deepcopy(binding),
                },
                True,
                True,
                True,
                False,
            )
            for index, item in enumerate(value["detections"])
        ],
        "deferred": False,
        "source_current": True,
    }


def test_complete_bound_result_is_engine_accepted_without_human_fields():
    value = facts()
    before = deepcopy(value)
    assert qualify_v3_engine_acceptance(**value) == ()
    assert value == before
    assert "approved_geometry_revision" not in value["positions"][0].geometry


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("missing", "POSITION_CONFLICT"),
        ("duplicate", "POSITION_CONFLICT"),
        ("slots", "POSITION_CONFLICT"),
        ("deferred", "DEFERRED"),
        ("complete", "PARTIAL"),
        ("current_revision", "REVISION_CONFLICT"),
        ("current_owner", "OWNER_CONFLICT"),
        ("sequence", "OWNER_CONFLICT"),
        ("grid_issue", "GRID_ISSUE"),
        ("source_current", "SOURCE_OR_MODEL_DRIFT"),
        ("model_snapshot", "SOURCE_OR_MODEL_DRIFT"),
        ("game_id", "SOURCE_OR_MODEL_DRIFT"),
        ("source_checksum_sha256", "SOURCE_OR_MODEL_DRIFT"),
        ("width", "SOURCE_OR_MODEL_DRIFT"),
        ("binding", "PROVENANCE_INVALID"),
        ("nodes", "GEOMETRY_INVALID"),
        ("policy", "POLICY_UNSUPPORTED"),
    ],
)
def test_fail_closed_qualification(fault, reason):
    value = facts()
    if fault == "missing":
        value["positions"].pop()
    elif fault == "duplicate":
        value["positions"].append(value["positions"][0])
    elif fault == "slots":
        value["active_slots"] = [0, 1, 3, 4]
    elif fault in ("complete", "current_revision", "current_owner", "grid_issue", "sequence"):
        value["positions"][0] = replace(
            value["positions"][0], **{fault: True if fault == "grid_issue" else None}
        )
    elif fault in ("deferred", "source_current"):
        value[fault] = fault == "deferred"
    elif fault == "nodes":
        # A different but valid full lattice must not impersonate the proposal.
        value["positions"][0].geometry["latticeNodes"][8]["x"] += 1
    elif fault == "binding":
        value["binding"]["proposalChecksumSha256"] = "f" * 64
    else:
        value[fault] = "drift" if fault != "width" else 501
    assert "V3_ACCEPTANCE_" + reason in qualify_v3_engine_acceptance(**value)


def test_new_pin_changes_neural_fingerprint_but_never_rewrites_legacy_payload():
    legacy = {"neural_grid_execution_policy_version": NEURAL_AUTO_CROP_POLICY}
    before = deepcopy(legacy)
    assert pin_v3_engine_acceptance_policy(legacy, "a" * 64) == "a" * 64
    assert legacy == before
    neural = {"neural_grid_proposal": facts()["model_snapshot"]}
    digest = pin_v3_engine_acceptance_policy(neural, "a" * 64)
    assert digest != "a" * 64
    assert neural[V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY] == V3_ENGINE_ACCEPTANCE_POLICY
    assert digest == pin_v3_engine_acceptance_policy(deepcopy(neural), "a" * 64)


def test_legacy_roundtrip_retains_payload_and_new_evidence_changes_only_new_geometry_hash():
    value = facts()
    manual = {
        "sourceChecksumSha256": value["source_checksum_sha256"],
        "canonicalWidth": 500,
        "canonicalHeight": 300,
        "engineId": "manual_v1",
        "globalInitialization": {"existing": "unchanged"},
        "boards": [{"positionIndex": index} for index in range(5)],
    }
    entry = {"neuralProposal": value["proposal"], "neuralProposalBinding": value["binding"]}
    legacy = neural_pending_payload(manual, entry, automatic_crops=True)
    replay = neural_pending_payload(
        deepcopy(manual), deepcopy(entry), automatic_crops=True, engine_acceptance_policy=None
    )
    assert legacy == replay
    new = neural_pending_payload(
        manual, entry, automatic_crops=True, engine_acceptance_policy=V3_ENGINE_ACCEPTANCE_POLICY
    )
    old_geometry, new_geometry = legacy["structuredGeometry"], new["structuredGeometry"]
    assert old_geometry["resultChecksumSha256"] != new_geometry["resultChecksumSha256"]
    assert old_geometry["boards"] == new_geometry["boards"]
    assert old_geometry["globalInitialization"] == {"existing": "unchanged"}
    assert (
        new_geometry["globalInitialization"]["v3EngineAcceptance"]["proposal"] == value["proposal"]
    )
    assert neural_pending_payload(manual, entry, automatic_crops=True) == legacy


def test_engine_accepted_geometry_does_not_become_human_training_truth():
    label = classify_label_level(
        LabelFacts(
            geometry_revision=0,
            approved_geometry_revision=None,
            approved_by=None,
            revision_authors=[],
            source_geometry_source="auto",
            source_status="accepted",
            source_created_by=V3_ENGINE_ACCEPTANCE_ACTOR,
        )
    )
    assert label.level == "U" and label.approval_actor is None
    # The actual exporter also refuses an exact lattice before assigning any
    # label level unless a current human geometry approval exists.
    from uuid import UUID

    from game_predictor_worker.vision_lab.production_geometry import ProductionGeometryError

    from scripts.vision_lab_geometry_export import _build_row

    value = facts()
    board = {
        "source_revision_id": "present",
        "position_index": 0,
        "manifest_present": True,
        "manifest_topology": {"rows": 3, "columns": 5},
        "grid_rows": 3,
        "grid_columns": 5,
        "manifest_coordinate_space": "exif-normalized-rgb-pixels-v1",
        "manifest_cell_indices": list(range(15)),
        "manifest_cell_quads": value["proposal"]["detections"][0]["cellQuads"],
        "unavailable_cell_indices": [],
        "board_geometry": value["positions"][0].geometry,
        "geometry_revision": 0,
        "approved_geometry_revision": None,
        "geometry_approved_by": None,
        "source_lattice_nodes": value["positions"][0].geometry["latticeNodes"],
        "source_status": "accepted",
        "source_geometry_source": "auto",
        "source_created_by": V3_ENGINE_ACCEPTANCE_ACTOR,
    }
    with pytest.raises(ProductionGeometryError) as error:
        _build_row(UUID(value["game_id"]), {"active_board_slots": [0]}, board, None, {})
    assert error.value.code == "NEURAL_GEOMETRY_HUMAN_APPROVAL_REQUIRED"
