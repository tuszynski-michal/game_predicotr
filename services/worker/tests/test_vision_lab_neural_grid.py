"""TASK-0802 neural_grid: decoding, grid fit, metrics, role guard, presets, budget, engine."""

import hashlib
import itertools
import json
import subprocess
import sys

import numpy as np
import pytest
from game_predictor_worker.vision_lab import neural_grid_protocol as protocol
from game_predictor_worker.vision_lab.contracts import Board, GeometryResult, Point, Topology
from game_predictor_worker.vision_lab.neural_grid_data import (
    LATTICE,
    board_rectifier,
    grid_from_quad,
    load_samples,
    screen_targets,
    transform_points,
)
from game_predictor_worker.vision_lab.neural_grid_inference import (
    DecodeSettings,
    NeuralGridEngine,
    decode_screen,
    fit_grid,
)
from game_predictor_worker.vision_lab.neural_grid_metrics import (
    evaluate_photo,
    hungarian,
    summarize,
)
from game_predictor_worker.vision_lab.run_contracts import RunMutation
from game_predictor_worker.vision_lab.runs import RunManager


def preset(name="A"):
    return protocol.load_preset(name)[0]


def board_quads(count, origin=(40.0, 30.0), size=(88.0, 50.0), gap=(30.0, 40.0), columns=3):
    quads = []
    for index in range(count):
        row, column = divmod(index, columns)
        x = origin[0] + column * (size[0] + gap[0])
        y = origin[1] + row * (size[1] + gap[1])
        quads.append(
            np.array(
                [
                    [x, y],
                    [x + size[0], y + 2],
                    [x + size[0] - 1, y + size[1]],
                    [x + 1, y + size[1] - 1],
                ],
                dtype=np.float32,
            )
        )
    return quads


# --- presets, role guard and budget ----------------------------------------------------------


def test_neural_grid_presets_frozen_and_drift_refused(tmp_path, monkeypatch):
    fingerprints = set()
    for name in protocol.PRESET_NAMES:
        loaded, fingerprint = protocol.load_preset(name)
        assert loaded.name == name and fingerprint == protocol.FROZEN_PRESET_FINGERPRINTS[name]
        assert loaded.metrics == protocol.METRIC_DEFINITION
        assert loaded.schedule.max_run_seconds == protocol.MAX_RUN_SECONDS == 14400
        fingerprints.add(fingerprint)
    assert len(fingerprints) == 3
    payload = json.loads(protocol.preset_path("A").read_text(encoding="utf-8"))
    payload["optimization"]["learning_rate"] = 0.002
    (tmp_path / "A.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(protocol, "PRESET_DIRECTORY", tmp_path)
    with pytest.raises(ValueError, match="FINGERPRINT_MISMATCH"):
        protocol.load_preset("A")


@pytest.mark.parametrize("role", ["gold", "final_test", "unseen_game", "validation"])
def test_neural_grid_role_guard_refuses_gold_and_holdouts(tmp_path, role):
    with pytest.raises(protocol.RoleForbiddenError, match="ROLE_FORBIDDEN"):
        protocol.require_roles((role,))
    # The guard runs before the snapshot is opened: a missing snapshot is not reached.
    with pytest.raises(protocol.RoleForbiddenError):
        load_samples(tmp_path / "missing", ("training", role))


def _mini_snapshot(tmp_path):
    nodes = grid_from_quad(board_quads(1)[0]).tolist()
    lines = []
    selection = []
    for image_id, role in (
        ("img-train", "training"),
        ("img-dev", "development"),
        ("img-gold", "gold"),
    ):
        checksum = hashlib.sha256(image_id.encode()).hexdigest()
        selection.append([image_id, role, checksum, ".jpg"])
        if role == "gold":
            # Not valid JSON after the id: decoding a gold line would fail the test.
            lines.append(f'{{"imageId":"{image_id}", GOLD-NOT-DECODED'.encode() + b"\n")
            continue
        row = {
            "imageId": image_id,
            "role": role,
            "imageLevel": "S",
            "coordinateSpace": "exif-normalized-rgb-pixels-v1",
            "imagePath": f"images/{checksum[:2]}/{checksum}.jpg",
            "sourceChecksumSha256": checksum,
            "orientedWidth": 400,
            "orientedHeight": 300,
            "familyId": "family",
            "boards": [{"nodes": nodes, "unavailableCellIndices": [], "level": "S"}],
        }
        lines.append(json.dumps(row).encode() + b"\n")
    samples = b"".join(lines)
    split = json.dumps(
        {
            "selectionColumns": ["imageId", "role", "sourceChecksumSha256", "suffix"],
            "selection": selection,
        }
    ).encode()
    files = {
        "samples.jsonl": hashlib.sha256(samples).hexdigest(),
        "split.json": hashlib.sha256(split).hexdigest(),
    }
    root = tmp_path / ("a" * 64)
    root.mkdir()
    (root / "samples.jsonl").write_bytes(samples)
    (root / "split.json").write_bytes(split)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "format": "production-geometry-snapshot-v1",
                "snapshotId": "a" * 64,
                "policy": {"policyVersion": "production-geometry-split-v2"},
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return root


def test_neural_grid_loader_never_decodes_gold_lines(tmp_path):
    root = _mini_snapshot(tmp_path)
    loaded = load_samples(root, ("training", "development"))
    assert [s.role for s in loaded] == ["development", "training"]
    assert all(s.image_id != "img-gold" for s in loaded)
    assert loaded[0].boards[0].nodes.shape == (24, 2)
    (root / "samples.jsonl").write_bytes((root / "samples.jsonl").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="CHECKSUM"):
        load_samples(root, ("training",))


def _manager(tmp_path, launcher=None):
    return RunManager(
        tmp_path,
        validate=protocol.validate_request,
        models=(protocol.MODEL_VERSION,),
        launcher=launcher or (lambda run: None),
        state_type=protocol.NeuralGridRunState,
        admit=protocol.admit_run,
        identity=lambda pid: None,
    )


def _request(name, purpose="train", request_id=None):
    return protocol.build_request(
        request_id=request_id or f"neural-{name}-{purpose}",
        preset_name=name,
        purpose=purpose,
        snapshot_id="b" * 64,
    )


def test_neural_grid_durable_budget_three_runs_one_per_preset(tmp_path):
    manager = _manager(tmp_path)
    smoke = manager.create_or_get_run(_request("A", "smoke"))
    manager.cancel_run(smoke.id, RunMutation(request_id="cancel-smoke", expected_attempt=1))
    started = []
    for name in ("A", "B", "C"):
        if name == "B":
            # Same preset again is refused even while budget remains.
            with pytest.raises(ValueError, match="PRESET_ALREADY_RUN"):
                manager.create_or_get_run(_request("A", request_id="neural-A-again"))
        run = manager.create_or_get_run(_request(name))
        assert run.request.configuration.max_seconds == 14400
        # Interrupted (cancelled) runs keep consuming the budget.
        manager.cancel_run(run.id, RunMutation(request_id=f"cancel-{name}", expected_attempt=1))
        started.append(run.id)
    fresh = _manager(tmp_path)  # durable: a new process sees the same state.json
    with pytest.raises(ValueError, match="BUDGET_EXHAUSTED"):
        fresh.create_or_get_run(_request("A", request_id="neural-fourth"))
    # Resume is a new attempt of the same run, not a new run.
    resumed = fresh.retry_run(started[0], RunMutation(request_id="resume-A", expected_attempt=1))
    assert resumed.id == started[0] and resumed.attempt == 2
    # A replayed start request returns the recorded run instead of spending budget.
    assert fresh.create_or_get_run(_request("B")).id == started[1]


def test_neural_grid_contract_limits_four_hours_and_smoke_steps():
    request = _request("A")
    payload = request.model_dump()
    payload["configuration"]["max_seconds"] = 14401
    with pytest.raises(ValueError):
        protocol.NeuralGridRunRequest.model_validate(payload)
    smoke = _request("A", "smoke").model_dump()
    smoke["configuration"]["max_steps"] = 51
    with pytest.raises(ValueError, match="SMOKE_STEP_LIMIT"):
        protocol.NeuralGridRunRequest.model_validate(smoke)
    shortened = request.model_copy(
        update={"configuration": request.configuration.model_copy(update={"max_seconds": 600.0})}
    )
    with pytest.raises(ValueError, match="PRESET_REQUEST_MISMATCH"):
        protocol.validate_request(shortened)


# --- decoding, fit, metrics -------------------------------------------------------------------


@pytest.mark.parametrize("count", [5, 9])
def test_neural_grid_decode_synthetic_heatmaps_any_board_count(count):
    settings = preset()
    quads = board_quads(count)
    heat, offsets, _ = screen_targets(quads, (480, 352), settings.screen)
    found = decode_screen(heat[0], offsets, settings.screen)
    assert len(found) == count
    for quad in quads:
        assert min(np.abs(d.quad - quad).max() for d in found) < 1e-3


def test_neural_grid_fit_noise_and_three_outliers():
    rng = np.random.default_rng(5)
    truth = grid_from_quad(np.array([[100, 80], [400, 90], [395, 260], [96, 250]], np.float32))
    noisy = truth + rng.normal(0, 0.4, truth.shape).astype(np.float32)
    for index in (3, 11, 20):
        noisy[index] += np.array([25.0, -18.0], np.float32)
    scale = float(np.linalg.norm(truth[23] - truth[0]))
    fitted = fit_grid(noisy, scale, preset().fit)
    assert fitted.ok and int(fitted.inliers.sum()) == 21
    assert not fitted.inliers[[3, 11, 20]].any()
    assert np.abs(fitted.nodes - truth).max() < 1.0
    assert fitted.residual < 0.005


def _labels(count=9):
    return [grid_from_quad(q * 3) for q in board_quads(count)]


def test_neural_grid_metrics_photo_needs_every_board_and_no_false_board():
    labels = _labels(9)
    perfect = evaluate_photo("p", "S", labels, [(n, True) for n in labels])
    assert perfect.complete_correct and perfect.macro_cost == 0
    eight = evaluate_photo("p", "S", labels, [(n, True) for n in labels[:8]])
    assert not eight.complete_correct and eight.correct == 8
    assert eight.macro_cost == pytest.approx(1 / 9)
    shifted = [n.copy() for n in labels]
    shifted[4] = shifted[4] + np.float32(20.0)  # matched (IoU >= 0.5) but not correct
    wrong = evaluate_photo("p", "S", labels, [(n, True) for n in shifted])
    assert wrong.matched == 9 and wrong.correct == 8 and not wrong.complete_correct
    far = grid_from_quad(
        np.array([[2000, 2000], [2100, 2000], [2100, 2060], [2000, 2060]], np.float32)
    )
    extra = evaluate_photo("p", "S", labels, [(n, True) for n in [*labels, far]])
    assert extra.false_boards == 1 and not extra.complete_correct
    assert extra.macro_cost == 0  # T05 image-macro has no false-board cost
    summary = summarize([perfect, eight, wrong, extra])
    assert summary["photo_complete_correct"] == 1
    assert summary["photo_complete_correct_rate"] == 0.25
    assert summary["false_boards"] == 1 and summary["boards_expected"] == 36


def test_neural_grid_metrics_hungarian_assignment_ignores_order():
    labels = _labels(5)
    predictions = [(n, True) for n in reversed(labels)]
    result = evaluate_photo("p", "B", labels, predictions)
    assert {(m.prediction, m.label) for m in result.matches} == {(4 - i, i) for i in range(5)}
    rng = np.random.default_rng(1)
    for rows, columns in ((4, 4), (3, 5), (5, 3)):
        cost = rng.random((rows, columns))
        pairs = hungarian(cost)
        assert len(pairs) == min(rows, columns)
        assert len({i for i, _ in pairs}) == len({j for _, j in pairs}) == len(pairs)
        small, large = sorted((rows, columns))
        brute = min(
            sum(cost[i, j] if rows <= columns else cost[j, i] for i, j in enumerate(choice))
            for choice in itertools.permutations(range(large), small)
        )
        assert sum(cost[i, j] for i, j in pairs) == pytest.approx(brute)


# --- engine contract ---------------------------------------------------------------------------


def _fake_engine(source_quads, settings):
    """Runners that emit exact targets: tests decoding, crops, fit and the contract only."""

    def screen(pixels):
        height, width = pixels.shape[2:]
        scale = 768 / max(400, 300)
        quads = [q * np.float32(scale) for q in source_quads]
        heat, offsets, _ = screen_targets(quads, (width, height), settings.screen)
        return heat[None], offsets[None]

    reference = board_rectifier(source_quads[0], settings.board)
    canonical = transform_points(grid_from_quad(source_quads[0]), reference)

    def board(crops):
        count = len(crops)
        return (
            np.repeat(canonical[None], count, axis=0),
            np.ones((count, 24), np.float32),
            np.ones((count, 15), np.float32),
        )

    return NeuralGridEngine(screen, board, DecodeSettings.of(settings))


@pytest.mark.parametrize("count", [5, 9])
def test_neural_grid_engine_board_count_follows_detection(count):
    settings = preset()
    quads = board_quads(count, origin=(20.0, 20.0), size=(100.0, 60.0), gap=(25.0, 30.0))
    engine = _fake_engine(quads, settings)
    rgb = np.zeros((300, 400, 3), np.uint8)
    result = engine.detect("source", rgb, Topology())
    assert result.status == "detected" and len(result.boards) == count
    assert [b.position_index for b in result.boards] == list(range(count))
    for board_result in result.boards:
        nodes = np.array([(p.x, p.y) for p in board_result.nodes], np.float32)
        error = min(np.abs(nodes - grid_from_quad(q)).max() for q in quads)
        assert error < 0.5
        assert board_result.status == "needs_review"
        assert "NEURAL_GRID_GATE_UNCALIBRATED" in board_result.reasons
    unsupported = engine.detect("source", rgb, Topology(columns=3))
    assert unsupported.status == "unsupported" and not unsupported.boards


def test_neural_grid_engine_swap_without_changing_the_consumer(tmp_path):
    from game_predictor_worker.vision_lab.catalog import Catalog
    from game_predictor_worker.vision_lab.contracts import Source
    from PIL import Image

    rng = np.random.default_rng(2)
    image = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)
    path = tmp_path / "source.png"
    Image.fromarray(image).save(path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    catalog = Catalog(None)
    catalog.sources["source"] = Source(
        id="source",
        game_id="777",
        game_name="777",
        filename="source.png",
        sha256=checksum,
        asset_id="asset",
        source_kind="folder",
        family_candidate="family",
        role="data",
    )
    catalog.paths["asset"] = path
    quads = board_quads(2, origin=(20.0, 20.0), size=(100.0, 60.0), gap=(25.0, 30.0))

    class FixedEngine:
        def detect(self, source_id, rgb, topology):
            return GeometryResult(
                source_id=source_id,
                topology=topology,
                model_version="fixed",
                status="detected",
                width=rgb.shape[1],
                height=rgb.shape[0],
                boards=[
                    Board(
                        position_index=i,
                        status="needs_review",
                        nodes=[Point(x=float(x), y=float(y)) for x, y in grid_from_quad(q)],
                    )
                    for i, q in enumerate(quads)
                ],
            )

    for engine in (FixedEngine(), _fake_engine(quads, preset())):
        result = catalog.detect("source", Topology(), engine=engine)
        assert len(result.boards) == 2
        assert all(len(b.cells) == 15 for b in result.boards)
        assert all(c.status == "available" for b in result.boards for c in b.cells)


def test_neural_grid_torch_free_modules():
    code = (
        "import sys\n"
        "import game_predictor_worker.vision_lab.neural_grid_protocol\n"
        "import game_predictor_worker.vision_lab.neural_grid_data\n"
        "import game_predictor_worker.vision_lab.neural_grid_metrics\n"
        "import game_predictor_worker.vision_lab.neural_grid_inference\n"
        "import game_predictor_worker.vision_lab.neural_grid_runs\n"
        "assert 'torch' not in sys.modules, 'torch imported'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


# --- torch (CPU) -------------------------------------------------------------------------------


def test_neural_grid_network_shapes_losses_and_checkpoint_round_trip(tmp_path):
    torch = pytest.importorskip("torch")
    from game_predictor_worker.training_core.checkpoint import (
        checkpoint_bytes,
        load_checkpoint,
        make_checkpoint,
    )
    from game_predictor_worker.vision_lab.neural_grid_model import NeuralGridNetwork
    from game_predictor_worker.vision_lab.neural_grid_training import (
        compute_losses,
        learning_rate,
    )

    torch.manual_seed(0)
    torch.set_num_threads(2)
    settings = preset()
    network = NeuralGridNetwork()
    heat, offsets = network.screen(torch.zeros(1, 3, 128, 160))
    assert heat.shape == (1, 1, 32, 40) and offsets.shape == (1, 8, 32, 40)
    logits, nodes, visibility = network.board(torch.zeros(2, 3, 192, 320))
    assert logits.shape == (2, 24, 48, 80) and nodes.shape == (2, 24, 2)
    assert visibility.shape == (2, 15)
    assert float(nodes[..., 0].min()) >= 0 and float(nodes[..., 0].max()) <= 320
    quads = board_quads(2)
    heat_t, offsets_t, weight_t = screen_targets(quads, (160, 128), settings.screen)
    batch = {
        "image": torch.zeros(1, 3, 128, 160, dtype=torch.uint8),
        "heat": torch.from_numpy(heat_t)[None],
        "offsets": torch.from_numpy(offsets_t)[None],
        "offset_weight": torch.from_numpy(weight_t)[None],
        "crops": torch.zeros(1, 2, 3, 192, 320, dtype=torch.uint8),
        "nodes": torch.from_numpy(np.repeat(LATTICE[None] * 40 + 40, 2, axis=0))[None],
        "visible": torch.ones(1, 2, 15),
    }
    losses = compute_losses(network, batch, settings, "cpu")
    assert all(torch.isfinite(v) for v in losses.values())
    losses["total"].backward()
    assert learning_rate(settings, 0.0) < learning_rate(settings, 0.03)
    assert learning_rate(settings, 1.0) == pytest.approx(
        settings.optimization.learning_rate * settings.optimization.final_learning_rate_fraction
    )
    optimizer = torch.optim.AdamW(network.parameters())
    content = checkpoint_bytes(
        make_checkpoint(
            network,
            optimizer,
            None,
            torch.Generator(),
            binding={"x": 1},
            epoch=1,
            global_step=3,
            history=[],
            best_state={"round": 1},
        )
    )
    path = tmp_path / "checkpoint.pt"
    path.write_bytes(content)
    value = load_checkpoint(path, hashlib.sha256(content).hexdigest(), expected_binding={"x": 1})
    assert value["epoch"] == 1 and value["bestState"] == {"round": 1}
