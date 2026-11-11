"""Two frozen games, real content/crop evaluation; graph execution is a small explicit fixture."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from game_predictor_worker.images import grid_content_consistency as consistency
from game_predictor_worker.images import grid_content_experiment_data as data
from game_predictor_worker.training_core.grid_content_experiment import selection_record
from test_grid_content_experiment import game
from test_production_cell_frozen_pipeline import Engine, frozen_fixture


@pytest.mark.parametrize("failure", [None, "raw_second", "decision_second"])
def test_all_frozen_a_and_production_cells_include_second_game(tmp_path, monkeypatch, failure):
    import onnxruntime

    snapshots, nodes = [], None
    for name in ("first", "second"):
        _, snapshot, rows = frozen_fixture(tmp_path / name)
        snapshots.append(snapshot)
        nodes = np.asarray([[p["x"], p["y"]] for p in rows[0]["targets"][0]["nodes"]], np.float32)
    screen_calls = []

    def outputs(stage):
        if stage == "screen":
            return [np.zeros((1, 1, 2, 2), np.float32), np.zeros((1, 8, 2, 2), np.float32)]
        return [
            np.zeros((1, 24, 2), np.float32),
            np.ones((1, 24), np.float32),
            np.ones((1, 15), np.float32),
        ]

    class ExecutedEngine(Engine):
        def __init__(self, screen=None, board=None, settings=None):
            super().__init__(nodes)
            self.screen_runner = screen or (lambda pixels: outputs("screen"))
            self.board_runner = board or (lambda pixels: outputs("board"))
            if settings is not None:
                self.settings = settings

        def analyse(self, rgb):
            heat = self.screen_runner(np.zeros((1, 3, 64, 64), np.float32))[0]
            self.board_runner(np.zeros((1, 3, 192, 320), np.float32))
            found = super().analyse(rgb)
            # A tiny raw change crosses a discrete decode boundary on the second
            # source. The real renderer/matcher must reject it despite raw PASS.
            if heat.max() > 0:
                found[0].nodes += 100
            return found

    class Session:
        def __init__(self, path, providers):
            self.stage = Path(path).stem

        def run(self, names, feeds):
            result = outputs(self.stage)
            if self.stage == "screen":
                screen_calls.append(feeds)
                if len(screen_calls) == 2 and failure:
                    result[0][0, 0, 0, 0] = 1.0 if failure == "raw_second" else 1e-5
            return result

    monkeypatch.setattr(onnxruntime, "InferenceSession", Session)
    monkeypatch.setattr(consistency, "NeuralGridEngine", ExecutedEngine)
    monkeypatch.setattr(data, "torch_engine", lambda *args: ExecutedEngine())
    evaluator = data.ContentSelectionEvaluator(
        snapshots, Engine(nodes), SimpleNamespace(), "cpu", "R0", lambda: 200, lambda: None
    )
    selected = evaluator.measure(ExecutedEngine())["selection"]
    kwargs = dict(roster_sha256="a" * 64, selected=selected, history=[], arm_selections=[])
    if failure:
        with pytest.raises(consistency.ContentConsistencyError) as error:
            consistency.verify_content_export(evaluator, torch.nn.Identity(), tmp_path, **kwargs)
        proof = error.value.proof
        assert "CONTENT_MATCHING_OR_CELL_VERDICT_DIFFERENCE" in proof["reasonCodes"]
        assert ("CONTENT_RAW_OUTPUT_DIFFERENCE" in proof["reasonCodes"]) == (
            failure == "raw_second"
        )
    else:
        proof = consistency.verify_content_export(
            evaluator, torch.nn.Identity(), tmp_path, **kwargs
        )
        assert proof["passed"] and proof["reasonCodes"] == []
        assert proof["reference"] == proof["onnx"]
    assert len(screen_calls) == 2
    assert len(proof["onnx"]["photos"]) == 2
    assert {row["gameId"] for row in proof["onnx"]["photos"]} == {
        snapshot.manifest["gameId"] for snapshot in snapshots
    }
    assert len(proof["inputs"]) == 4


def test_small_nme_drift_cannot_reverse_checkpoint_or_arm_preference():
    original_game = game()
    original = selection_record([original_game], "R0", 200)
    other_game = deepcopy(original_game)
    other_game["quality"]["candidate"]["normalized_error"] += 1e-7
    other = selection_record([other_game], "R1", 400)
    replay_game = deepcopy(original_game)
    replay_game["quality"]["candidate"]["normalized_error"] += 2e-7
    replay = selection_record([replay_game], "R0", 200)
    assert consistency.selection_preserved(original, replay, [])
    assert not consistency.selection_preserved(original, replay, [other])


def test_preflight_export_cost_includes_legacy_eight_crop_check_and_both_variants(
    tmp_path, monkeypatch
):
    from game_predictor_worker.images import grid_content_experiment_export as export
    from game_predictor_worker.vision_lab.neural_grid_protocol import load_preset

    calls = []
    monkeypatch.setattr(
        export,
        "raw_parity",
        lambda network, directory, board, screen, **kwargs: calls.append(
            (board.shape, screen.shape)
        )
        or {"passed": True},
    )
    for name in ("screen.onnx", "board.onnx"):
        (tmp_path / name).write_bytes(b"explicit graph fixture")
    nodes = np.array(
        [[10 + col * 6, 10 + row * 8] for row in range(4) for col in range(6)], np.float32
    )

    class Photos:
        def __len__(self):
            return 2

        def rgb(self, index):
            return np.zeros((48, 64, 3), np.uint8)

        def targets(self, index):
            return [(nodes, 1)] * 9

    export.content_parity(None, tmp_path, Photos(), load_preset("A")[0], "R2", True)
    assert [shape[0][0] for shape in calls] == [8, 1, 1]
    assert calls[-1][0][-2:] == (288, 480)
