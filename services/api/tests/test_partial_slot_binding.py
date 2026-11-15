"""D-615: page-anchored partial slot binding on real Mumie A2 detections."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.neural_crop_policy import (
    NEURAL_AUTO_CROP_POLICY,
    SYMBOL_REVIEW_CROP_POLICY,
    neural_auto_crop_blockers,
    neural_auto_crop_evidence,
)
from game_predictor_api.domain.neural_grid_proposal import (
    NEURAL_GRID_REVIEW_REASON,
    NeuralGridSnapshot,
    associate_expected_slots,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
    validate_neural_source_binding,
)
from game_predictor_api.domain.v3_engine_acceptance import (
    V3_ENGINE_ACCEPTANCE_POLICY,
    V3EnginePosition,
    qualify_v3_engine_acceptance,
)
from game_predictor_worker.images.neural_pending_geometry import neural_pending_payload

FIXTURE = Path(__file__).parent / "fixtures" / "neural_partial_slot_binding_mumie_a2.json"
SOURCES = {item["source"]: item for item in json.loads(FIXTURE.read_text("utf-8"))["sources"]}


def _detection(
    index: int, nodes: list[dict[str, float]] | None, *, width: int, height: int
) -> dict[str, object]:
    if nodes is None:
        return {
            "detectionId": f"d{index}",
            "score": 0.5,
            "latticeNodes": None,
            "cellQuads": [],
            "cellVisibility": ["unknown"] * 15,
            "structurallyValid": False,
            "reasonCodes": [NEURAL_GRID_REVIEW_REASON, "NEURAL_GRID_STRUCTURE_INVALID"],
        }
    quads = lattice_cell_quads(nodes, width=width, height=height)
    return {
        "detectionId": f"d{index}",
        "score": 0.8,
        "latticeNodes": nodes,
        "cellQuads": [quad.to_dict() for quad in quads],
        "cellVisibility": lattice_visibility(quads, width=width, height=height),
        "structurallyValid": True,
        "reasonCodes": [NEURAL_GRID_REVIEW_REASON],
    }


def _proposal(
    width: int,
    height: int,
    sequence: tuple[int, int],
    detections: list[list[dict[str, float]] | None],
) -> dict[str, object]:
    version = grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1).current
    return build_neural_source_proposal(
        game_id=str(uuid4()),
        source_selection_id=str(uuid4()),
        source_checksum_sha256="b" * 64,
        source_width=width,
        source_height=height,
        original_range=AttestedSequenceRange(start=sequence[0], end=sequence[1]),
        snapshot=NeuralGridSnapshot.for_game(500000, version),
        detections=[
            _detection(index, nodes, width=width, height=height)
            for index, nodes in enumerate(detections)
        ],
    )


def _real(name: str) -> dict[str, object]:
    item = SOURCES[name]
    return _proposal(
        item["width"],
        item["height"],
        tuple(item["range"]),
        [
            None if not detection["valid"] else [{"x": x, "y": y} for x, y in detection["nodes"]]
            for detection in item["detections"]
        ],
    )


def _page(
    slots: list[int], *, board_count: int = 9, extra: list[tuple[float, float]] = ()
) -> dict[str, object]:
    """Synthetic 3 × 3 page: boards 120 × 60 px every 150 × 100 px."""
    origins = [((slot % 3) * 150 + 10.0, (slot // 3) * 100 + 10.0) for slot in slots]
    origins.extend(extra)
    lattices = [
        [
            {"x": left + column * 24.0, "y": top + row * 20.0}
            for row in range(4)
            for column in range(6)
        ]
        for left, top in origins
    ]
    return _proposal(500, 400, (101, 100 + board_count), lattices)


def _positions(binding: dict[str, object]) -> dict[int, str]:
    return {
        item["positionIndex"]: item["detectionId"]  # type: ignore[index]
        for item in binding["assignments"]  # type: ignore[union-attr]
    }


@pytest.mark.parametrize(
    ("name", "missing", "ignored"),
    [
        # The network missed the visible corner board 246594 (slot 2).
        ("seq_246592-246600.jpg", [2], []),
        # One structurally invalid detection leaves its slot missing.
        ("seq_431191-431199.jpg", [1], ["d1"]),
        ("seq_439435-439443.jpg", [2], ["d3"]),
        # The frame cuts the first board of the top row.
        ("seq_442972-442980.jpg", [0], []),
        # End of the range: five boards; detections on empty page slots are ignored.
        ("seq_499996-500000.jpg", [], ["d5", "d6", "d7"]),
    ],
)
def test_real_pages_anchored_by_three_rows_and_columns_bind_partially(
    name: str, missing: list[int], ignored: list[str]
) -> None:
    value = _real(name)
    binding = associate_expected_slots(value)
    assert binding is not None
    validate_neural_source_binding(binding, value)
    assert binding["confirmedRange"] == binding["originalRange"]
    assert binding["missingPositionIndexes"] == missing
    assert binding["ignoredDetectionIds"] == ignored


def test_real_corner_miss_keeps_every_other_board_on_its_own_sequence() -> None:
    binding = associate_expected_slots(_real("seq_246592-246600.jpg"))
    assert binding is not None
    assert _positions(binding) == {
        0: "d0",
        1: "d1",
        3: "d2",
        4: "d3",
        5: "d4",
        6: "d5",
        7: "d6",
        8: "d7",
    }


@pytest.mark.parametrize(
    "name",
    [
        # A false detection in the paytable above the boards adds a fourth row.
        "seq_304732-304740.jpg",
        "seq_304741-304749.jpg",
        # The right column is outside the photo: two columns cannot be placed.
        "seq_305785-305793.jpg",
    ],
)
def test_real_pages_without_a_fully_anchored_lattice_stay_manual(name: str) -> None:
    assert associate_expected_slots(_real(name)) is None


def test_exact_inventory_is_unchanged_and_wins_over_the_partial_rule() -> None:
    binding = associate_expected_slots(_page(list(range(9))))
    assert binding is not None
    assert binding["missingPositionIndexes"] == []
    assert _positions(binding) == {index: f"d{index}" for index in range(9)}


def test_two_missing_slots_bind_but_three_do_not() -> None:
    two = associate_expected_slots(_page([0, 2, 3, 4, 5, 6, 8]))
    assert two is not None
    assert two["missingPositionIndexes"] == [1, 7]
    # Rows and columns stay anchored, but three slots would be missing.
    assert associate_expected_slots(_page([0, 1, 2, 3, 7, 8])) is None


def test_missing_row_or_column_cannot_be_placed() -> None:
    assert associate_expected_slots(_page([3, 4, 5, 6, 7, 8])) is None
    assert associate_expected_slots(_page([0, 1, 3, 4, 6, 7])) is None


def test_second_detection_on_an_occupied_slot_is_ambiguous() -> None:
    assert associate_expected_slots(_page([0, 1, 2, 3, 4, 5, 6, 8], extra=[(330.0, 112.0)])) is None


def test_off_lattice_detection_between_rows_is_ambiguous() -> None:
    # Missing slot 4 leaves room for a detection halfway between rows 0 and 1.
    assert associate_expected_slots(_page([0, 1, 2, 3, 5, 6, 7, 8], extra=[(160.0, 75.0)])) is None


def _partial_corner_page() -> tuple[dict[str, object], dict[str, object]]:
    value = _page([0, 1, 3, 4, 5, 6, 7, 8])
    binding = associate_expected_slots(value)
    assert binding is not None and binding["missingPositionIndexes"] == [2]
    return value, binding


def _detection_at(value: dict[str, object], binding: dict[str, object], position: int) -> object:
    detection_id = _positions(binding).get(position)
    return next(
        (item for item in value["detections"] if item["detectionId"] == detection_id),  # type: ignore[union-attr,index]
        None,
    )


@pytest.mark.parametrize("policy", [NEURAL_AUTO_CROP_POLICY, SYMBOL_REVIEW_CROP_POLICY])
def test_crop_gate_qualifies_assigned_slots_of_a_partial_binding(policy: str) -> None:
    value, binding = _partial_corner_page()
    for position in (0, 1, 3, 8):
        assert (
            neural_auto_crop_blockers(
                policy=policy,
                detection=_detection_at(value, binding, position),
                binding=binding,
                position=position,
                width=500,
                height=400,
            )
            == ()
        )
    assert neural_auto_crop_blockers(
        policy=policy, detection=None, binding=binding, position=2, width=500, height=400
    ) == ("NEURAL_GRID_SLOT_DETECTION_MISSING",)


@pytest.mark.parametrize("fault", ["unlisted", "overlap", "type", "absent"])
def test_crop_gate_requires_assigned_and_missing_slots_to_partition_the_range(fault: str) -> None:
    value, binding = _partial_corner_page()
    broken = deepcopy(binding)
    if fault == "unlisted":
        broken["missingPositionIndexes"] = []
    elif fault == "overlap":
        broken["missingPositionIndexes"] = [0, 2]
    elif fault == "type":
        broken["missingPositionIndexes"] = ["2"]
    else:
        broken.pop("missingPositionIndexes")
    assert neural_auto_crop_blockers(
        policy=NEURAL_AUTO_CROP_POLICY,
        detection=_detection_at(value, binding, 0),
        binding=broken,
        position=0,
        width=500,
        height=400,
    ) == ("NEURAL_GRID_SLOT_BINDING_REQUIRED",)


def test_pending_payload_crops_assigned_slots_and_defers_only_the_missing_one() -> None:
    value, binding = _partial_corner_page()
    payload = neural_pending_payload(
        {
            "sourceChecksumSha256": value["sourceChecksumSha256"],
            "canonicalWidth": 500,
            "canonicalHeight": 400,
            "engineId": "manual_v1",
            "globalInitialization": {},
            "boards": [{"positionIndex": index} for index in range(9)],
        },
        {"neuralProposal": value, "neuralProposalBinding": binding},
        automatic_crops=True,
        execution_policy=NEURAL_AUTO_CROP_POLICY,
    )
    structured = payload["structuredGeometry"]
    boards = {board["positionIndex"]: board for board in structured["boards"]}  # type: ignore[index]
    assert boards[2]["disposition"] == "needs_manual_review"
    assert boards[2]["sequenceNumber"] == 103
    assert "NEURAL_GRID_SLOT_DETECTION_MISSING" in boards[2]["reasonCodes"]
    assert {
        position for position, board in boards.items() if board["disposition"] == "automatic"
    } == {0, 1, 3, 4, 5, 6, 7, 8}
    assert boards[3]["sequenceNumber"] == 104


def _acceptance(
    deferred: list[int], *, drop: int | None = None, placeholder: bool = False
) -> tuple[str, ...]:
    value, binding = _partial_corner_page()
    detections = {item["detectionId"]: item for item in value["detections"]}  # type: ignore[union-attr,index]
    positions = [
        V3EnginePosition(
            position,
            101 + position,
            {
                "quad": [detections[detection_id]["latticeNodes"][i] for i in (0, 5, 23, 18)],
                "latticeNodes": deepcopy(detections[detection_id]["latticeNodes"]),
                "detectionId": detection_id,
                "neuralExecutionPolicy": NEURAL_AUTO_CROP_POLICY,
                "neuralAcceptanceEvidence": neural_auto_crop_evidence(detections[detection_id]),
                "neuralProposalChecksumSha256": value["proposalChecksumSha256"],
                "neuralProposalBinding": deepcopy(binding),
            },
            True,
            True,
            True,
            False,
        )
        for position, detection_id in sorted(_positions(binding).items())
        if position != drop
    ]
    if placeholder:
        # A board kept for the missing slot has no engine geometry at all.
        positions.append(V3EnginePosition(2, 103, None, False, True, True, False))
    return qualify_v3_engine_acceptance(
        policy=V3_ENGINE_ACCEPTANCE_POLICY,
        proposal=value,
        binding=binding,
        model_snapshot=value["engineSnapshot"],
        game_id=value["gameId"],  # type: ignore[arg-type]
        source_checksum_sha256=value["sourceChecksumSha256"],  # type: ignore[arg-type]
        width=500,
        height=400,
        active_slots=list(range(9)),
        sequence_start=101,
        sequence_end=109,
        positions=positions,
        deferred_positions=deferred,
        source_current=True,
    )


@pytest.mark.parametrize("placeholder", [False, True])
def test_engine_accepts_assigned_slots_while_the_missing_slot_stays_deferred(
    placeholder: bool,
) -> None:
    assert _acceptance([], placeholder=placeholder) == ()
    assert _acceptance([2], placeholder=placeholder) == ()


def test_deferred_assigned_slot_or_absent_assigned_board_still_block() -> None:
    assert "V3_ACCEPTANCE_DEFERRED" in _acceptance([0])
    assert "V3_ACCEPTANCE_POSITION_CONFLICT" in _acceptance([], drop=4)
