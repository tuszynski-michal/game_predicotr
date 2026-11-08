"""Contract/gradient tests; synthetic fixtures never qualify a real model."""

import numpy as np
import pytest
import torch
from game_predictor_api.domain.grid_visibility_contract import (
    BoardContentReference,
    CellContentReference,
    GridOutputContract,
    visibility_supervision,
)
from game_predictor_worker.geometry_core.inference import (
    BoardDetection,
    DecodeSettings,
    NeuralGridEngine,
)
from game_predictor_worker.geometry_core.preprocessing import grid_from_quad
from game_predictor_worker.images.full_board_completeness import features, input_edge_clearance
from game_predictor_worker.training_core.grid_training import (
    _supervised_losses,
    weighted_node_losses,
)
from game_predictor_worker.training_core.grid_visibility_targets import (
    content_targets,
    node_support_weights,
    supervised_board_crop,
)
from game_predictor_worker.training_core.neural_grid_network import BoardExport, BoardNetwork
from game_predictor_worker.vision_lab.neural_grid_protocol import load_preset


def reference(source=0, negative=6):
    cells = [CellContentReference(state="occluded") for _ in range(negative)]
    cells += [
        CellContentReference(state="visible", quad=((4, 4), (8, 4), (8, 8), (4, 8)))
        for _ in range(15 - negative)
    ]
    return BoardContentReference(
        gameId="10000000-0000-0000-0000-000000000001",
        sourceRepresentativeSha256=f"{source:064x}",
        positionIndex=0,
        revision=1,
        humanApproved=True,
        cells=tuple(cells),
    )


def qualified():
    return visibility_supervision([reference(i) for i in range(5)])


def board_settings():
    return load_preset("A")[0].board


def test_real_label_minima_aliases_unknown_and_unapproved():
    refs = [reference(i) for i in range(5)]
    assert qualified().qualified
    assert not visibility_supervision(refs[:4] * 10).qualified
    assert visibility_supervision(refs * 3) == qualified()
    assert not visibility_supervision(
        [x.model_copy(update={"humanApproved": False}) for x in refs]
    ).qualified
    assert not visibility_supervision([reference(i, 5) for i in range(5)]).qualified
    with pytest.raises(ValueError, match="ALIAS_CONFLICT"):
        visibility_supervision([refs[0], refs[0].model_copy(update={"revision": 2})])
    from uuid import UUID

    second = [reference(i + 5).model_copy(update={"gameId": UUID(int=2)}) for i in range(4)]
    assert not visibility_supervision(refs + second).qualified
    assert not visibility_supervision(refs, game_ids=[str(UUID(int=2))]).qualified


def test_supervised_batches_keep_unknown_masked_and_zero_weight_padding():
    from game_predictor_worker.images.grid_training_data import GridOnlyBatches, ScreenGridBatches

    preset = load_preset("A")[0]

    class Photos:
        def __len__(self):
            return 1

        def rgb(self, index):
            return np.full((100, 100, 3), 200, np.uint8)

        def targets(self, index):
            quad = np.array([[10, 10], [80, 10], [80, 80], [10, 80]], np.float32)
            return [(grid_from_quad(quad), 1)]

    contract = GridOutputContract(supervision=visibility_supervision([]))
    for cls in (GridOnlyBatches, ScreenGridBatches):
        source = cls(Photos(), preset, 1, 11, 1, output_contract=contract)
        try:
            item = source._build(0)
            assert item["visibility_mask"].sum() == 0
            assert item["node_weights"].shape[-1] == 24
            assert item["visibility_targets"].shape[-1] == 15
            assert item["node_weights"][item["weights"] == 0].sum() == 0
        finally:
            source.close()


def test_visibility_optimizer_exposure_survives_restart_and_is_frozen_at_best(tmp_path):
    from dataclasses import replace

    from game_predictor_worker.training_core.grid_training import TrainingInterrupted, train
    from test_durable_v3_grid_training import PRESET, Control, Tiny, batches, losses, plan

    execution = plan()
    execution = replace(
        execution, binding={**execution.binding, "gridOutputContract": {"test": True}}
    )

    def supervised(network, batch):
        return {
            **losses(network, batch),
            "valid_visibility": torch.tensor(2.0),
            "positive_visibility": torch.tensor(1.0),
            "negative_visibility": torch.tensor(1.0),
        }

    # Equal scores choose the first checkpoint; later steps must not inflate its proof.
    kwargs = dict(
        preset=PRESET,
        plan=execution,
        batches=batches,
        losses=supervised,
        evaluate=lambda _: 1.0,
        checkpoint_directory=tmp_path,
    )
    control = Control(stop_at=2)
    with pytest.raises(TrainingInterrupted):
        train(network=Tiny(), control=control, **kwargs)
    path, sha, _ = control.published[-1]
    result = train(network=Tiny(), control=Control(), resume=(path, sha), **kwargs)
    assert result.best_step == 3
    assert result.steps == 9 and result.stop_reason == "early_stopping"
    assert result.visibility_exposure == {
        "positiveTargets": 3,
        "negativeTargets": 3,
        "optimizerSteps": 3,
    }


def test_scaler_skipped_step_never_increases_visibility_exposure(tmp_path, monkeypatch):
    from dataclasses import replace

    from game_predictor_worker.training_core.grid_training import train
    from test_durable_v3_grid_training import PRESET, Control, Tiny, batches, losses, plan

    class BackoffScaler:
        def __init__(self, *args, **kwargs):
            self.value = 1024.0

        def scale(self, value):
            return value

        def unscale_(self, optimizer):
            pass

        def get_scale(self):
            return self.value

        def step(self, optimizer):
            pass  # A non-finite gradient skips optimizer.step().

        def update(self):
            self.value /= 2

        def state_dict(self):
            return {"scale": self.value}

    monkeypatch.setattr("torch.amp.grad_scaler.GradScaler", BackoffScaler)
    execution = plan()
    execution = replace(execution, binding={**execution.binding, "gridOutputContract": {}})
    network = Tiny()
    initial = {key: value.detach().clone() for key, value in network.named_parameters()}

    def supervised(model, batch):
        return {
            **losses(model, batch),
            "valid_visibility": torch.tensor(2.0),
            "positive_visibility": torch.tensor(1.0),
            "negative_visibility": torch.tensor(1.0),
        }

    result = train(
        network=network,
        preset=PRESET,
        plan=execution,
        batches=batches,
        losses=supervised,
        evaluate=lambda _: 1.0,
        control=Control(),
        checkpoint_directory=tmp_path,
    )
    assert result.visibility_exposure == {
        "positiveTargets": 0,
        "negativeTargets": 0,
        "optimizerSteps": 0,
    }
    assert all(torch.equal(value, initial[key]) for key, value in network.named_parameters())


def test_parallel_photo_input_keeps_pixels_and_support_together_once_per_photo(
    tmp_path, monkeypatch
):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    from game_predictor_worker.images import grid_cohort_dataset as module
    from game_predictor_worker.images.grid_training_data import (
        CohortPhotos,
        photo_pixels_and_support,
    )
    from test_grid_cohort_dataset import SnapshotFixture

    fixture = SnapshotFixture(tmp_path)
    sources = [fixture.source() for _ in range(6)]
    snapshot = fixture.publish()
    photos = CohortPhotos(snapshot, "TRAIN", full_only=False)
    positions = {source["original"]["sha256"]: index for index, source in enumerate(sources)}
    original = module.decode_canonical_source_bytes
    active = maximum = reads = 0
    guard = threading.Lock()
    original_read = snapshot._read

    def read(*args, **kwargs):
        nonlocal reads
        with guard:
            reads += 1
        return original_read(*args, **kwargs)

    def decode(*args, **kwargs):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.01)  # Allow six prefetch workers to overlap if the cache is unguarded.
            frame = original(*args, **kwargs)
            top = positions[kwargs["expected_source_checksum_sha256"]] + 1
            return SimpleNamespace(
                rgb=frame.rgb,
                source=frame.source,
                crop=SimpleNamespace(
                    valid_box=SimpleNamespace(left=0, top=top, right=64, bottom=48)
                ),
            )
        finally:
            with guard:
                active -= 1

    monkeypatch.setattr(snapshot, "_read", read)
    monkeypatch.setattr(module, "decode_canonical_source_bytes", decode)
    with ThreadPoolExecutor(max_workers=6) as pool:
        inputs = list(pool.map(lambda index: photo_pixels_and_support(photos, index), range(6)))
    assert reads == 6 and maximum == 1
    for (rgb, support), (source, _) in zip(inputs, photos.rows, strict=True):
        index = positions[source["original"]["sha256"]]
        expected = original(
            original_read(source["original"], 64 * 1024 * 1024),
            expected_source_checksum_sha256=source["original"]["sha256"],
        )
        np.testing.assert_array_equal(rgb, expected.rgb)
        assert not support[: index + 1].any()
        assert support[index + 1 :].all()


def test_all_masked_board_step_does_not_apply_adam_weight_decay(tmp_path):
    from game_predictor_worker.training_core.grid_training import train
    from test_durable_v3_grid_training import PRESET, Control, Tiny, batches, plan

    network = Tiny()
    initial = {key: value.detach().clone() for key, value in network.named_parameters()}

    def masked(model, batch):
        return {
            "total": model.board(batch["x"]).sum() * 0,
            "valid_nodes": torch.tensor(0.0),
            "valid_visibility": torch.tensor(0.0),
        }

    train(
        network=network,
        preset=PRESET,
        plan=plan(),
        batches=batches,
        losses=masked,
        evaluate=lambda _: 1.0,
        control=Control(),
        checkpoint_directory=tmp_path,
    )
    assert all(torch.equal(value, initial[key]) for key, value in network.named_parameters())


def test_content_after_crop_occlusion_unknown_and_missing_reference():
    support = np.ones((16, 16), np.float32)
    ref = reference()
    targets, mask = content_targets(ref, np.eye(3), support, qualified())
    assert targets.tolist() == [0] * 6 + [1] * 9
    assert mask.sum() == 15
    support[5:7, 5:7] = 0
    targets, mask = content_targets(ref, np.eye(3), support, qualified())
    assert targets.sum() == 0 and mask.sum() == 15
    shifted = np.eye(3)
    shifted[1, 2] = -6
    assert content_targets(ref, shifted, np.ones_like(support), qualified())[0].sum() == 0
    for absent in (None, ref.model_copy(update={"humanApproved": False})):
        assert content_targets(absent, np.eye(3), support, qualified())[1].sum() == 0
    assert content_targets(ref, np.eye(3), support, visibility_supervision([]))[1].sum() == 0
    unknown = ref.model_copy(update={"cells": (CellContentReference(state="unknown"),) * 15})
    assert content_targets(unknown, np.eye(3), support, qualified())[1].sum() == 0


def test_softargmax_stride_band_and_padded_node_support():
    support = np.ones((32, 64), np.float32)
    nodes = np.tile([16, 16], (24, 1)).astype(np.float32)
    nodes[:6] = [[-1, 16], [1.99, 16], [2, 16], [62, 16], [62.01, 16], [16, 30.01]]
    support[15:18, 15:18] = 0
    assert node_support_weights(nodes, support, 4).tolist() == [0, 0, 1, 1, 0, 0] + [0] * 18


@pytest.mark.parametrize("all_masked", [False, True])
def test_masked_gradients_unknown_nan_targets_and_explicit_counts(all_masked):
    logits = torch.randn(2, 24, 4, 4, requires_grad=True)
    predicted = torch.randn(2, 24, 2, requires_grad=True)
    visibility = torch.randn(2, 15, requires_grad=True)
    weights = torch.tensor([1.0, 0.0])
    node_weights = torch.ones(2, 24)
    node_weights[:, :3] = 0
    mask = torch.ones(2, 15)
    mask[:, 0] = 0
    if all_masked:
        node_weights.zero_()
        mask.zero_()
    targets = torch.ones(2, 15)
    targets[mask == 0] = float("nan")
    nodes = torch.ones(2, 24, 2)
    nodes[node_weights == 0] = float("nan")
    batch = {"node_weights": node_weights, "visibility_targets": targets, "visibility_mask": mask}
    loss = _supervised_losses(
        logits, predicted, visibility, nodes, weights, batch, board_settings(), "cpu"
    )
    assert torch.isfinite(loss["total"])
    assert loss["valid_nodes"] == (0 if all_masked else 21)
    assert loss["valid_visibility"] == (0 if all_masked else 14)
    loss["total"].backward()
    assert torch.count_nonzero(logits.grad[:, :3]) == 0
    assert torch.count_nonzero(predicted.grad[1]) == 0
    assert torch.count_nonzero(visibility.grad[1]) == 0
    assert torch.count_nonzero(visibility.grad[:, 0]) == 0
    if all_masked:
        assert loss["total"] == 0
        assert torch.count_nonzero(visibility.grad) == 0


def test_legacy_loss_and_builder_remain_explicitly_untrained():
    logits, nodes = torch.randn(1, 24, 4, 4), torch.ones(1, 24, 2)
    result = weighted_node_losses(logits, nodes, nodes, torch.ones(1), board_settings())
    assert set(result) == {"nodes", "node_heatmap"}
    quad = np.array([[10, 10], [60, 10], [60, 40], [10, 40]], np.float32)
    detection = BoardDetection(
        1, quad, grid_from_quad(quad), grid_from_quad(quad), np.ones(24), np.ones(15), 0, 0, 24
    )
    kwargs = dict(
        width=100,
        height=100,
        real_input_support=quad,
        game_log_aspect_reference=None,
        neighbor_deviation=None,
        neighbor_applicable=False,
    )
    legacy = features(detection, **kwargs)
    assert legacy.values["visibility"] is None  # v1 semantics, never reinterpreted.
    contract = GridOutputContract(supervision=qualified())
    fresh = features(detection, **kwargs, output_contract=contract, board=board_settings())
    assert "COMPLETENESS_VISIBILITY_SUPERVISION_REQUIRED" in fresh.hardReasons
    trained = contract.model_copy(update={"trainedVisibility": True})
    measured = features(detection, **kwargs, output_contract=trained, board=board_settings())
    assert measured.values["visibility"] == 1
    detection.visibility[4] = 0.1
    assert features(detection, **kwargs, output_contract=trained, board=board_settings()).values[
        "visibility"
    ] == pytest.approx(0.1)


def test_real_input_edge_uses_raw_nodes_and_available_pixels():
    quad = np.array([[20, 20], [120, 20], [120, 80], [20, 80]], np.float32)
    nodes = grid_from_quad(quad)
    detection = BoardDetection(1, quad, nodes.copy(), nodes.copy())
    base = input_edge_clearance(detection, board_settings(), 160, 100)
    assert base > 0
    available = np.array([[0, 30], [160, 30], [160, 100], [0, 100]], np.float32)
    assert input_edge_clearance(detection, board_settings(), 160, 100, available) < 0
    detection.nodes[:6, 1] = 50  # fitting cannot conceal the raw top row.
    assert input_edge_clearance(detection, board_settings(), 160, 100, available) < 0


def test_export_cannot_claim_visibility_training_from_labels_or_later_steps(tmp_path):
    from copy import deepcopy

    from game_predictor_api.domain.grid_visibility_contract import require_output_contract

    incoming = GridOutputContract(supervision=qualified()).model_dump(mode="json")
    bundle = {
        "format": "neural-grid-bundle-v2",
        "model_version": "neural-grid-v2",
        "gridOutputContract": incoming,
        "provenance": {
            "bestStep": 3,
            "visibilityExposure": {"positiveTargets": 0, "negativeTargets": 0, "optimizerSteps": 0},
        },
    }
    assert require_output_contract(bundle, incoming).trainedVisibility is False
    import json

    from game_predictor_worker.images.grid_training_child import canonical, sha256_bytes
    from game_predictor_worker.images.grid_training_handler import GridTrainingJobHandler

    legacy_spec = {"preset": {"id": "grid-corrections-v1"}}
    (tmp_path / "spec.json").write_text(
        json.dumps(
            {
                "payload": legacy_spec,
                "sha256": sha256_bytes(canonical(legacy_spec)),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="INPUT_CONTRACT_REQUIRED"):
        GridTrainingJobHandler._verify_screen_export(tmp_path, bundle)
    assert require_output_contract(bundle) is not None  # Runtime has no training spec.
    claimed = deepcopy(bundle)
    claimed["gridOutputContract"]["trainedVisibility"] = True
    with pytest.raises(ValueError, match="EVIDENCE_INVALID"):
        require_output_contract(claimed, incoming)
    claimed["provenance"]["visibilityExposure"] = {
        "positiveTargets": 6,
        "negativeTargets": 6,
        "optimizerSteps": 6,
    }
    with pytest.raises(ValueError, match="EVIDENCE_INVALID"):
        require_output_contract(claimed, incoming)
    claimed["provenance"]["visibilityExposure"]["optimizerSteps"] = 3
    assert require_output_contract(claimed, incoming).trainedVisibility is True
    assert require_output_contract({"format": "neural-grid-bundle-v1"}) is None


def test_invalid_jitter_skips_without_gt_fallback(monkeypatch):
    from game_predictor_worker.training_core import grid_visibility_targets as module

    calls = []
    monkeypatch.setattr(
        module, "perturb_quad", lambda *args: calls.append(1) or np.zeros((4, 2), np.float32)
    )
    preset = load_preset("A")[0]
    image = np.zeros((100, 100, 3), np.uint8)
    nodes = grid_from_quad(np.array([[10, 10], [80, 10], [80, 80], [10, 80]], np.float32))
    item = supervised_board_crop(
        image,
        nodes,
        preset.board,
        preset.augmentation,
        np.random.default_rng(0),
        reference=reference(),
        supervision=qualified(),
        source_support=np.ones((100, 100), np.float32),
    )
    assert len(calls) == 3
    assert item["node_weights"].sum() == item["visibility_mask"].sum() == 0


def test_real_board_export_onnx_preserves_24_15_and_cannot_recover_missing_row(tmp_path):
    import onnxruntime as ort

    torch.set_num_threads(2)
    torch.manual_seed(14)
    graph = BoardExport(BoardNetwork()).eval()
    # A real raster whose original top row has been cut off. Missing GT y<0 is unreachable.
    original = np.tile(np.arange(256, dtype=np.uint8)[None, :, None], (256, 1, 3))
    import cv2

    cropped = cv2.resize(original[64:], (320, 192))
    tensor = torch.from_numpy(cropped.transpose(2, 0, 1)[None].astype(np.float32))
    path = tmp_path / "board.onnx"
    torch.onnx.export(
        graph,
        tensor,
        path,
        input_names=["crops"],
        output_names=["nodes", "peak", "visibility"],
        dynamic_axes={
            "crops": {0: "batch"},
            "nodes": {0: "batch"},
            "peak": {0: "batch"},
            "visibility": {0: "batch"},
        },
        opset_version=18,
        dynamo=False,
    )
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
    actual = session.run(None, {"crops": tensor.numpy()})
    with torch.no_grad():
        expected = graph(tensor)
    assert [a.shape for a in actual] == [(1, 24, 2), (1, 24), (1, 15)]
    for left, right in zip(expected, actual, strict=True):
        assert np.max(np.abs(left.numpy() - right) / np.maximum(1, np.abs(left.numpy()))) < 1e-4
    assert np.all(actual[0] >= 2)
    assert np.all(actual[0][:, :, 0] <= 318) and np.all(actual[0][:, :, 1] <= 190)
    preset = load_preset("A")[0]
    engine = NeuralGridEngine(
        lambda _: None,
        lambda crops: tuple(session.run(None, {"crops": crops})),
        DecodeSettings.of(preset),
        output_contract=GridOutputContract(supervision=visibility_supervision([])),
    )
    found = BoardDetection(1, np.array([[0, 0], [319, 0], [319, 191], [0, 191]], np.float32))
    engine._decode_boards(cropped, [found])
    assert found.node_peak.shape == (24,) and found.visibility.shape == (15,)
