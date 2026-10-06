from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.neural_grid_proposal import (
    NEURAL_GRID_REVIEW_REASON,
    NeuralGridProposalError,
    NeuralGridSnapshot,
    associate_expected_slots,
    build_neural_source_binding,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
    proposal_checksum_sha256,
    validate_neural_source_binding,
    validate_neural_source_proposal,
)


def proposal(count: int = 5, *, end: int = 105, maximum: int = 500000) -> dict[str, object]:
    version = grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1).current
    detections = []
    for index in range(count):
        left, top = (index % 3) * 150 + 10.125, (index // 3) * 100 + 10.375
        nodes = [
            {"x": left + column * 20.25, "y": top + row * 20.125}
            for row in range(4)
            for column in range(6)
        ]
        # Retain a real internal-node deviation that a four-corner warp would lose.
        nodes[8]["x"] += 0.3125
        quads = lattice_cell_quads(nodes, width=500, height=300)
        detections.append(
            {
                "detectionId": chr(97 + index),
                "score": 0.91,
                "latticeNodes": nodes,
                "cellQuads": [quad.to_dict() for quad in quads],
                "cellVisibility": lattice_visibility(quads, width=500, height=300),
                "structurallyValid": True,
                "reasonCodes": [NEURAL_GRID_REVIEW_REASON],
            }
        )
    return build_neural_source_proposal(
        game_id=str(uuid4()),
        source_selection_id=str(uuid4()),
        source_checksum_sha256="a" * 64,
        source_width=500,
        source_height=300,
        original_range=AttestedSequenceRange(start=end - 4, end=end),
        snapshot=NeuralGridSnapshot.for_game(maximum, version),
        detections=detections,
    )


def test_exact_five_slot_proposal_keeps_float_nodes_and_remains_review() -> None:
    value = proposal()
    binding = associate_expected_slots(value)
    assert binding is not None
    assert binding["confirmedRange"] == {"sequenceRangeStart": 101, "sequenceRangeEnd": 105}
    assert binding["assignments"] == [
        {"detectionId": chr(97 + i), "positionIndex": i} for i in range(5)
    ]
    assert binding["missingPositionIndexes"] == []
    assert value["detections"][0]["latticeNodes"][8]["x"] == 50.9375  # type: ignore[index]
    assert "humanApproved" not in value


def test_missing_middle_requires_explicit_binding_and_preserves_sequence104() -> None:
    value = proposal(4)
    assert associate_expected_slots(value) is None
    binding = build_neural_source_binding(
        value,
        confirmed_range=AttestedSequenceRange(start=101, end=105),
        assignments=[
            {"detectionId": "a", "positionIndex": 0},
            {"detectionId": "b", "positionIndex": 1},
            {"detectionId": "c", "positionIndex": 3},
            {"detectionId": "d", "positionIndex": 4},
        ],
    )
    assert binding["missingPositionIndexes"] == [2]
    assert binding["assignments"][2]["positionIndex"] + 101 == 104  # type: ignore[index]


def test_out_of_bounds_filename_requires_explicit_range_confirmation() -> None:
    value = proposal(6, end=500004)
    assert associate_expected_slots(value) is None
    binding = build_neural_source_binding(
        value,
        confirmed_range=AttestedSequenceRange(start=500000, end=500000),
        assignments=[{"detectionId": "a", "positionIndex": 0}],
    )
    assert binding["originalRange"] == {"sequenceRangeStart": 500000, "sequenceRangeEnd": 500004}
    assert binding["confirmedRange"] == {"sequenceRangeStart": 500000, "sequenceRangeEnd": 500000}
    assert binding["ignoredDetectionIds"] == ["b", "c", "d", "e", "f"]


@pytest.mark.parametrize(
    "mutation", ["source", "model", "nodes", "visibility", "quads", "duplicate", "version"]
)
def test_proposal_drift_and_resigned_inconsistent_shapes_fail(mutation: str) -> None:
    value = deepcopy(proposal())
    if mutation == "source":
        value["sourceWidth"] = 501
    elif mutation == "model":
        value["engineSnapshot"]["model"]["presetFingerprint"] = "b" * 64  # type: ignore[index]
    elif mutation == "nodes":
        value["detections"][0]["latticeNodes"][0]["x"] = float("nan")  # type: ignore[index]
    elif mutation == "visibility":
        value["detections"][0]["cellVisibility"][0] = "outside"  # type: ignore[index]
    elif mutation == "quads":
        value["detections"][0]["cellQuads"][0][0]["x"] = 44.0  # type: ignore[index]
    elif mutation == "duplicate":
        value["detections"][1]["detectionId"] = "a"  # type: ignore[index]
    else:
        value["contractVersion"] = "neural-source-proposal-v2"
    if mutation not in {"source", "nodes"}:
        value["proposalChecksumSha256"] = proposal_checksum_sha256(value)
    with pytest.raises((NeuralGridProposalError, ValueError)):
        validate_neural_source_proposal(value)


@pytest.mark.parametrize(
    "mutation", ["stale", "duplicate", "position", "missing", "extra", "range", "bool"]
)
def test_binding_cannot_shift_drop_or_double_assign_slots(mutation: str) -> None:
    value = proposal()
    binding = deepcopy(associate_expected_slots(value))
    assert binding is not None
    if mutation == "stale":
        binding["proposalChecksumSha256"] = "f" * 64
    elif mutation == "duplicate":
        binding["assignments"][1]["detectionId"] = "a"  # type: ignore[index]
    elif mutation == "position":
        binding["assignments"][1]["positionIndex"] = 0  # type: ignore[index]
    elif mutation == "missing":
        binding["missingPositionIndexes"] = [1]
    elif mutation == "extra":
        binding["ignoredDetectionIds"] = ["phantom"]
    elif mutation == "bool":
        binding["assignments"][0]["positionIndex"] = False  # type: ignore[index]
    else:
        binding["confirmedRange"] = {"sequenceRangeStart": 1, "sequenceRangeEnd": 5}
    with pytest.raises(NeuralGridProposalError):
        validate_neural_source_binding(binding, value)


def test_partial_and_outside_visibility_uses_real_cells() -> None:
    nodes = [
        {"x": column * 20.5 - 90, "y": row * 20.25 - 10} for row in range(4) for column in range(6)
    ]
    quads = lattice_cell_quads(nodes, width=100, height=100)
    visible = lattice_visibility(quads, width=100, height=100)
    assert visible[:4] == ["outside"] * 4
    assert visible[4] == "partial"
    assert visible[9] == "partial"


def test_overlapping_exact_count_and_invalid_detection_do_not_auto_bind() -> None:
    value = proposal()
    value["detections"][1]["latticeNodes"] = deepcopy(value["detections"][0]["latticeNodes"])  # type: ignore[index]
    value["detections"][1]["cellQuads"] = deepcopy(value["detections"][0]["cellQuads"])  # type: ignore[index]
    value["proposalChecksumSha256"] = proposal_checksum_sha256(value)
    assert associate_expected_slots(value) is None


def test_neural_profile_cannot_replace_legacy777() -> None:
    version = grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_777_V2).current
    with pytest.raises(NeuralGridProposalError):
        NeuralGridSnapshot.for_game(500000, version)


def test_rotated_source_uses_board_axes_and_ignores_detection_list_order() -> None:
    value = proposal()
    for detection in value["detections"]:
        nodes = detection["latticeNodes"]
        for point in nodes:
            x, y = point["x"], point["y"]
            point["x"] = x + 0.2 * y
            point["y"] = 0.5 * x + y
        quads = lattice_cell_quads(nodes, width=500, height=300)
        detection["cellQuads"] = [quad.to_dict() for quad in quads]
        detection["cellVisibility"] = lattice_visibility(quads, width=500, height=300)
    value["detections"] = [value["detections"][index] for index in [0, 1, 3, 2, 4]]
    value["proposalChecksumSha256"] = proposal_checksum_sha256(value)
    binding = associate_expected_slots(value)
    assert binding is not None
    assert binding["assignments"] == [
        {"detectionId": chr(97 + i), "positionIndex": i} for i in range(5)
    ]


def test_incomplete_first_row_with_same_detection_count_requires_explicit_binding() -> None:
    value = proposal()
    detection = value["detections"][2]
    nodes = detection["latticeNodes"]
    for point in nodes:
        point["y"] += 100
    quads = lattice_cell_quads(nodes, width=500, height=300)
    detection["cellQuads"] = [quad.to_dict() for quad in quads]
    detection["cellVisibility"] = lattice_visibility(quads, width=500, height=300)
    value["proposalChecksumSha256"] = proposal_checksum_sha256(value)
    assert associate_expected_slots(value) is None
