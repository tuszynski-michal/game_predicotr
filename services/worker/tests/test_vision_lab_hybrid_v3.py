"""TASK-0803 hybrid_v3: agreement gate, engine contract, calibration and role guard."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from game_predictor_worker.vision_lab import hybrid_v3_calibration as calibration
from game_predictor_worker.vision_lab import hybrid_v3_gate as gate
from game_predictor_worker.vision_lab.contracts import Board, GeometryResult, Point, Topology
from game_predictor_worker.vision_lab.hybrid_v3_engine import (
    PHOTO_CONFIDENT,
    PHOTO_NEEDS_REVIEW,
    HybridV3Engine,
    reference_from_engine,
)
from game_predictor_worker.vision_lab.neural_grid_data import (
    LATTICE,
    BoardLabel,
    PhotoSample,
    grid_from_quad,
    lattice_homography,
    transform_points,
)
from game_predictor_worker.vision_lab.neural_grid_inference import BoardDetection
from game_predictor_worker.vision_lab.neural_grid_protocol import RoleForbiddenError

THRESHOLDS = gate.GateThresholds(min_quad_iou=0.9, max_node_error=0.02, max_fit_residual=0.005)


def quads(count, origin=(40.0, 30.0), size=(150.0, 90.0), gap=(30.0, 40.0), columns=3):
    result = []
    for index in range(count):
        row, column = divmod(index, columns)
        x = origin[0] + column * (size[0] + gap[0])
        y = origin[1] + row * (size[1] + gap[1])
        result.append(
            np.array(
                [
                    [x, y],
                    [x + size[0], y + 2],
                    [x + size[0] - 1, y + size[1]],
                    [x + 1, y + size[1]],
                ],
                dtype=np.float32,
            )
        )
    return result


def grids(count, **kwargs):
    return [grid_from_quad(q) for q in quads(count, **kwargs)]


def reference(nodes_list):
    return [gate.ReferenceBoard(i, n) for i, n in enumerate(nodes_list)]


def network(nodes_list, residual=0.001, failed=False):
    return [
        gate.NetworkBoard(nodes=n, fit_residual=residual, fit_inliers=24, fit_failed=failed)
        for n in nodes_list
    ]


def shifted_one_column(nodes):
    """The same board seen one column to the right (period jump)."""

    matrix = lattice_homography(nodes[[0, 5, 23, 18]])
    return transform_points(LATTICE + np.array([1.0, 0.0], np.float32), matrix)


# --- gate --------------------------------------------------------------------------------------


@pytest.mark.parametrize("count", [5, 9])
def test_hybrid_v3_agreeing_grids_are_confident_any_board_count(count):
    labels = grids(count)
    noisy = [n + np.float32(0.3) for n in labels]
    decision = gate.gate_photo(reference(labels), network(noisy), THRESHOLDS)
    assert decision.state == "confident" and decision.reasons == ()
    assert len(decision.boards) == count
    assert all(b.state == "confident" and b.node_source == "network" for b in decision.boards)
    assert [b.reference_index for b in decision.boards] == list(range(count))
    # Residual at or above the threshold: the reference nodes are the output.
    loose = gate.gate_photo(reference(labels), network(noisy, residual=0.005), THRESHOLDS)
    assert loose.state == "confident"
    assert all(b.node_source == "reference" for b in loose.boards)
    assert np.array_equal(loose.boards[0].nodes, labels[0])


def test_hybrid_v3_quad_shifted_by_one_column_needs_review():
    labels = grids(9)
    predicted = [n.copy() for n in labels]
    predicted[4] = shifted_one_column(labels[4])
    decision = gate.gate_photo(reference(labels), network(predicted), THRESHOLDS)
    assert decision.state == "needs_review"
    assert decision.reasons == (gate.BOARD_NEEDS_REVIEW,)
    board = next(b for b in decision.boards if b.reference_index == 4)
    assert board.state == "needs_review" and board.network_index == 4
    assert gate.QUAD_DISAGREEMENT in board.reasons and gate.NODE_DISAGREEMENT in board.reasons
    assert 0.5 <= board.quad_iou < 0.9
    assert board.node_source == "reference" and np.array_equal(board.nodes, labels[4])
    assert sum(b.state == "confident" for b in decision.boards) == 8


def test_hybrid_v3_node_disagreement_alone():
    labels = grids(3)
    predicted = [n.copy() for n in labels]
    diagonal = float(np.linalg.norm(labels[1][23] - labels[1][0]))
    predicted[1][8] += np.array([0.03 * diagonal, 0.0], np.float32)  # inner node only
    decision = gate.gate_photo(reference(labels), network(predicted), THRESHOLDS)
    board = decision.boards[1]
    assert board.reasons == (gate.NODE_DISAGREEMENT,)
    assert board.node_error_max == pytest.approx(0.03, rel=1e-3)
    relaxed = gate.GateThresholds(0.9, 0.04, 0.005)
    assert gate.gate_photo(reference(labels), network(predicted), relaxed).state == "confident"


def test_hybrid_v3_network_only_board_is_never_confident():
    labels = grids(4)
    extra = grid_from_quad(np.array([[900, 700], [1050, 700], [1050, 790], [900, 790]], np.float32))
    decision = gate.gate_photo(reference(labels), network([*labels, extra]), THRESHOLDS)
    assert decision.state == "needs_review"
    assert decision.reasons == (gate.BOARD_COUNT_MISMATCH, gate.BOARD_NEEDS_REVIEW)
    lone = [b for b in decision.boards if b.reference_index is None]
    assert len(lone) == 1 and lone[0].reasons == (gate.NETWORK_ONLY,)
    assert lone[0].state == "needs_review" and lone[0].node_source == "network"
    # A duplicate detection of a paired board is network-only as well.
    duplicate = gate.gate_photo(
        reference(labels), network([*labels, labels[2] + np.float32(1.0)]), THRESHOLDS
    )
    assert [b.reasons for b in duplicate.boards if b.reference_index is None] == [
        (gate.NETWORK_ONLY,)
    ]
    # Even with every threshold at its loosest, a network-only board stays in review.
    loosest = gate.GateThresholds(0.5, 1.0, 1.0)
    alone = gate.gate_photo([], network([extra]), loosest)
    assert alone.state == "needs_review" and alone.boards[0].state == "needs_review"


def test_hybrid_v3_reference_only_board_keeps_reference_nodes():
    labels = grids(5)
    decision = gate.gate_photo(reference(labels), network(labels[:4]), THRESHOLDS)
    assert decision.reasons == (gate.BOARD_COUNT_MISMATCH, gate.BOARD_NEEDS_REVIEW)
    missing = decision.boards[4]
    assert missing.reference_index == 4 and missing.network_index is None
    assert missing.reasons == (gate.REFERENCE_ONLY,)
    assert np.array_equal(missing.nodes, labels[4])


def test_hybrid_v3_weak_fit_and_invalid_board():
    labels = grids(2)
    weak = network(labels)
    weak[0] = gate.NetworkBoard(labels[0], 0.03, 6, fit_failed=True)
    decision = gate.gate_photo(reference(labels), weak, THRESHOLDS)
    assert decision.boards[0].reasons == (gate.NETWORK_FIT_WEAK,)
    assert decision.boards[1].state == "confident"
    nonfinite = network(labels)
    nonfinite[1] = gate.NetworkBoard(labels[1], float("inf"), 24, fit_failed=False)
    assert gate.gate_photo(reference(labels), nonfinite, THRESHOLDS).boards[1].reasons == (
        gate.NETWORK_FIT_WEAK,
    )
    folded = labels[1].copy()
    folded[[7, 8]] = folded[[8, 7]]  # two inner nodes swapped: cells fold
    invalid = gate.gate_photo(reference(labels), network([labels[0], folded]), THRESHOLDS)
    assert gate.BOARD_INVALID in invalid.boards[1].reasons
    assert invalid.state == "needs_review"
    no_grid = gate.gate_photo([gate.ReferenceBoard(0, None)], [], THRESHOLDS)
    assert no_grid.boards[0].reasons == (gate.REFERENCE_ONLY, gate.BOARD_INVALID)
    assert no_grid.boards[0].nodes is None


def test_hybrid_v3_board_count_mismatch_and_empty_photo():
    labels = grids(9)
    eight = gate.gate_photo(reference(labels[:8]), network(labels), THRESHOLDS)
    assert eight.state == "needs_review" and gate.BOARD_COUNT_MISMATCH in eight.reasons
    assert eight.reference_count == 8 and eight.network_count == 9
    assert len(eight.boards) == 9  # every board of both sources has a decision
    empty = gate.gate_photo([], [], THRESHOLDS)
    assert empty.state == "needs_review" and empty.reasons == (gate.NO_BOARDS,)


def test_hybrid_v3_reasons_are_a_closed_list():
    labels = grids(6)
    predicted = [n.copy() for n in labels]
    predicted[0] = shifted_one_column(labels[0])
    boards = network(predicted)
    boards[1] = gate.NetworkBoard(labels[1], None, 0, fit_failed=True)
    extra = grid_from_quad(np.array([[900, 700], [1050, 700], [1050, 790], [900, 790]], np.float32))
    decision = gate.gate_photo(reference(labels[:5]), [*boards, *network([extra])], THRESHOLDS)
    assert len(decision.boards) == 7  # 5 paired or reference-only + 2 network-only
    for board in decision.boards:
        assert set(board.reasons) <= set(gate.BOARD_REASONS)
        assert (board.state == "confident") == (not board.reasons)
    assert set(decision.reasons) <= set(gate.PHOTO_REASONS)


def test_hybrid_v3_thresholds_validated():
    with pytest.raises(ValueError, match="IOU"):
        gate.GateThresholds(0.4, 0.02, 0.005)
    with pytest.raises(ValueError, match="NODES"):
        gate.GateThresholds(0.9, 0.0, 0.005)


# --- engine -----------------------------------------------------------------------------------


class FakeNetwork:
    model_version = "neural-grid-v1:fake"

    def __init__(self, nodes_list, residual=0.001):
        self.nodes_list = nodes_list
        self.residual = residual

    def analyse(self, rgb):
        return [
            BoardDetection(
                score=0.9,
                screen_quad=n[[0, 5, 23, 18]],
                raw_nodes=n,
                nodes=n,
                fit_residual=self.residual,
                fit_inliers=24,
            )
            for n in self.nodes_list
        ]


class FixedEngine:
    model_version = "fixed"

    def __init__(self, nodes_list):
        self.nodes_list = nodes_list

    def detect(self, source_id, rgb, topology):
        return GeometryResult(
            source_id=source_id,
            topology=topology,
            model_version=self.model_version,
            status="detected",
            width=rgb.shape[1],
            height=rgb.shape[0],
            boards=[
                Board(
                    position_index=i,
                    status="needs_review",
                    nodes=[Point(x=float(x), y=float(y)) for x, y in n],
                )
                for i, n in enumerate(self.nodes_list)
            ],
        )


def test_hybrid_v3_engine_contract_states_and_reading_order():
    labels = grids(6, origin=(20.0, 20.0), size=(100.0, 60.0), gap=(25.0, 30.0))
    predicted = list(reversed([n + np.float32(0.2) for n in labels]))
    engine = HybridV3Engine(
        FakeNetwork(predicted), reference_from_engine(FixedEngine(labels)), THRESHOLDS
    )
    rgb = np.zeros((300, 400, 3), np.uint8)
    result = engine.detect("source", rgb, Topology())
    assert result.status == "detected" and result.reasons == [PHOTO_CONFIDENT]
    assert [b.position_index for b in result.boards] == list(range(6))
    assert all(b.status == "complete" and not b.reasons for b in result.boards)
    first = np.array([(p.x, p.y) for p in result.boards[0].nodes], np.float32)
    assert np.abs(first - labels[0]).max() < 0.5  # reading order, not detection order
    assert result.boards[0].nodes[0].provenance == "model"
    partial = HybridV3Engine(
        FakeNetwork(predicted[:5]), reference_from_engine(FixedEngine(labels)), THRESHOLDS
    ).detect("source", rgb, Topology())
    assert partial.reasons[0] == PHOTO_NEEDS_REVIEW
    assert "HYBRID_V3_BOARD_COUNT_MISMATCH" in partial.reasons
    review = [b for b in partial.boards if b.status == "needs_review"]
    assert len(review) == 1 and review[0].reasons == [gate.REFERENCE_ONLY]
    assert review[0].nodes[0].provenance == "baseline_proposal"
    unsupported = engine.detect("source", rgb, Topology(columns=3))
    assert unsupported.status == "unsupported" and not unsupported.boards


def test_hybrid_v3_engine_swap_without_changing_the_consumer(tmp_path):
    from game_predictor_worker.vision_lab.catalog import Catalog
    from game_predictor_worker.vision_lab.contracts import Source
    from PIL import Image

    rng = np.random.default_rng(3)
    image = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)
    path = tmp_path / "source.png"
    Image.fromarray(image).save(path)
    catalog = Catalog(None)
    catalog.sources["source"] = Source(
        id="source",
        game_id="777",
        game_name="777",
        filename="source.png",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        asset_id="asset",
        source_kind="folder",
        family_candidate="family",
        role="data",
    )
    catalog.paths["asset"] = path
    labels = grids(2, origin=(20.0, 20.0), size=(100.0, 60.0), gap=(25.0, 30.0))
    hybrid = HybridV3Engine(
        FakeNetwork(labels), reference_from_engine(FixedEngine(labels)), THRESHOLDS
    )
    for engine in (FixedEngine(labels), hybrid):
        result = catalog.detect("source", Topology(), engine=engine)
        assert len(result.boards) == 2
        assert all(len(b.cells) == 15 for b in result.boards)
        assert all(c.status == "available" for b in result.boards for c in b.cells)


# --- calibration -------------------------------------------------------------------------------


def _synthetic_photos():
    """Six photos: clean B and S photos, one S label shifted by a column, one missed board."""

    samples, network_records = [], {}
    for index in range(6):
        level = "B" if index < 3 else "S"
        labels = grids(5)
        predicted = [n + np.float32(0.25) for n in labels]
        if index == 4:
            predicted[2] = shifted_one_column(labels[2])  # label correction disagrees
        if index == 5:
            predicted = predicted[:4]
        image_id = f"img-{index}"
        samples.append(
            PhotoSample(
                image_id=image_id,
                role="development",
                level=level,
                path=Path("unused.jpg"),
                sha256="0" * 64,
                width=800,
                height=600,
                family_id="family",
                boards=tuple(BoardLabel(n, (), level) for n in labels),
            )
        )
        network_records[image_id] = {
            "error": None,
            "seconds": 0.0,
            "boards": calibration.network_record(network(predicted, residual=0.004)),
        }
    return samples, network_records


def test_hybrid_v3_calibration_is_deterministic_and_follows_the_rule():
    samples, records = _synthetic_photos()
    first = calibration.calibrate(calibration.prepare(samples, records))
    # Round trip through JSON, as the CLI cache does.
    again = calibration.calibrate(calibration.prepare(samples, json.loads(json.dumps(records))))
    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(
        again, sort_keys=True, default=str
    )
    assert len(first["curve"]) == 4 * 7 * 3
    selected = first["selected"]
    assert selected["feasible"]
    assert selected["all"]["photos_confident"] == 4 and selected["all"]["photo_coverage"] == 4 / 6
    # Tie-break: highest IoU, lowest node tolerance, residual closest to 0.005.
    assert selected["thresholds"] == {
        "min_quad_iou": 0.95,
        "max_node_error": 0.005,
        "max_fit_residual": 0.005,
    }
    assert selected["S"]["board_reasons"][gate.QUAD_DISAGREEMENT] == 1
    assert selected["S"]["board_reasons"][gate.REFERENCE_ONLY] == 1
    assert selected["S"]["photo_reasons"][gate.BOARD_COUNT_MISMATCH] == 1
    routing = first["routing_onnx_incorrect"]["S"]
    assert routing["incorrect_boards"] == 2 and routing["needs_review"] == 2
    assert routing["confident"] == 0
    assert first["onnx_incorrect_label_boards"] == {"S": 2}


def test_hybrid_v3_calibration_constraint_counts_network_errors():
    samples, records = _synthetic_photos()
    # Every predicted node moved by 2.5 % of the diagonal: NME 0.025 > 0.02, so the boards
    # are D-483-incorrect, yet they agree for node tolerances >= 0.03. Such points must be
    # infeasible whenever they make a board confident (even with reference nodes chosen).
    for record in records.values():
        for board in record["boards"]:
            nodes = np.asarray(board["nodes"], np.float32)
            diagonal = float(np.linalg.norm(nodes[23] - nodes[0]))
            board["nodes"] = (nodes + np.float32(0.025 * diagonal / np.sqrt(2))).tolist()
    result = calibration.calibrate(calibration.prepare(samples, records))
    infeasible = 0
    for row in result["curve"]:
        loose = row["thresholds"]["max_node_error"] >= 0.03
        assert row["feasible"] == (not loose or row["all"]["boards_confident"] == 0)
        infeasible += not row["feasible"]
    assert infeasible > 0
    assert result["selected"]["all"]["photos_confident"] == 0


def test_hybrid_v3_calibration_missing_network_output_is_an_error():
    samples, records = _synthetic_photos()
    records.pop("img-2")
    with pytest.raises(calibration.CalibrationError, match="NETWORK_OUTPUT_MISSING"):
        calibration.prepare(samples, records)


@pytest.mark.parametrize("roles", [("gold",), ("final_test",), ("unseen_game",), ("training",)])
def test_hybrid_v3_calibration_role_guard(tmp_path, roles):
    with pytest.raises(RoleForbiddenError):
        calibration.load_calibration_samples(tmp_path / "missing", roles)


def test_hybrid_v3_modules_torch_free():
    code = (
        "import sys\n"
        "import game_predictor_worker.vision_lab.hybrid_v3_gate\n"
        "import game_predictor_worker.vision_lab.hybrid_v3_engine\n"
        "import game_predictor_worker.vision_lab.hybrid_v3_calibration\n"
        "assert 'torch' not in sys.modules, 'torch imported'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


BUNDLE = (
    Path.home()
    / "Documents"
    / "game_predictor_vision_data"
    / "neural-grid-runs"
    / "43933ac8d7d443c8b9079630a83de2e6"
    / "exports"
    / "2cd19738367121e6-round3"
)


@pytest.mark.skipif(not (BUNDLE / "bundle.json").exists(), reason="run-1 ONNX bundle absent")
def test_hybrid_v3_onnx_cpu_engine_contract():
    from game_predictor_worker.vision_lab.neural_grid_inference import onnx_engine

    network_engine = onnx_engine(BUNDLE, threads=2)
    engine = HybridV3Engine(network_engine, lambda source, rgb, topology: [], THRESHOLDS)
    rgb = np.full((780, 1520, 3), 114, np.uint8)
    result = engine.detect("blank", rgb, Topology())
    # Nothing confident without a reference: every network board (if any) is in review.
    assert result.reasons[0] == PHOTO_NEEDS_REVIEW
    assert all(b.status != "complete" for b in result.boards)
    assert result.model_version.startswith("hybrid-v3:hybrid-v3-gate-v1:neural-grid-v1:A:")


CALIBRATION = BUNDLE.parents[1] / "hybrid-v3-calibration" / "calibration.json"


@pytest.mark.skipif(not CALIBRATION.exists(), reason="TASK-0803 calibration output absent")
def test_hybrid_v3_recorded_thresholds_match_the_calibration():
    from game_predictor_worker.vision_lab.hybrid_v3_engine import RUN1_DEVELOPMENT_THRESHOLDS

    recorded = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    assert recorded["threshold_grid"] == {k: list(v) for k, v in calibration.THRESHOLD_GRID.items()}
    assert recorded["selection_rule"] == calibration.SELECTION_RULE
    assert recorded["identity"]["role"] == "development"
    assert recorded["selected"]["thresholds"] == RUN1_DEVELOPMENT_THRESHOLDS.as_dict()
