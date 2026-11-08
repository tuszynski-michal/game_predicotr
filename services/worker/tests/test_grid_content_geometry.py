"""The larger content crop changes actual pixels and inverse geometry together."""

import numpy as np
import pytest
from game_predictor_worker.geometry_core.preprocessing import (
    board_rectifier,
    crop_board,
    transform_points,
)
from game_predictor_worker.geometry_core.rescue import (
    BoardCropGeometryV1,
    BoardCropGeometryV2,
    GridRescueVariantV2,
)
from game_predictor_worker.geometry_core.settings import BoardPreset
from pydantic import ValidationError


def test_content_geometry_json_roundtrip_and_closed_pairs():
    variant = GridRescueVariantV2()
    assert GridRescueVariantV2.model_validate_json(variant.model_dump_json()) == variant
    assert variant.paths == ("combined",)
    with pytest.raises(ValidationError):
        BoardCropGeometryV2(margin=0.15, canvas=(480, 288))


def test_content_geometry_uses_actual_large_canvas_without_changing_legacy():
    import json

    from game_predictor_worker.images.grid_training_child import RECIPE_FILE

    board = BoardPreset.model_validate(json.loads(RECIPE_FILE.read_bytes())["board"])
    rgb = np.full((400, 600, 3), 200, dtype=np.uint8)
    quad = np.asarray([[100, 100], [400, 100], [400, 280], [100, 280]], np.float64)
    large = BoardCropGeometryV2(margin=0.30, canvas=(480, 288))
    matrix = board_rectifier(quad, board, geometry=large)
    assert crop_board(rgb, matrix, board, geometry=large).shape == (288, 480, 3)
    assert np.allclose(transform_points(quad, matrix)[0], [90, 54])
    legacy = BoardCropGeometryV1(margin=0.30)
    old = board_rectifier(quad, board, geometry=legacy)
    assert crop_board(rgb, old, board).shape == (192, 320, 3)
    assert np.allclose(transform_points(quad, old)[0], [60, 36])


def test_v2_actual_input_witness_replays_larger_raster_and_rejects_substitution(tmp_path):
    from copy import deepcopy
    from types import SimpleNamespace
    from uuid import UUID

    from game_predictor_api.domain.grid_training_cohorts import digest
    from game_predictor_worker.images.production_cell_input import observe_input, verify_input
    from test_production_cell_frozen_pipeline import Engine, frozen_fixture

    fixture, snapshot, rows = frozen_fixture(tmp_path)
    source, target = rows[0], rows[0]["targets"][0]
    nodes = np.asarray([[p["x"], p["y"]] for p in target["nodes"]], np.float32)
    core = Engine(nodes)
    frame = snapshot.frame(source, "VALIDATION")
    primary = core.analyse(frame.rgb)
    detection = deepcopy(primary[0])
    engine = SimpleNamespace(
        engine=core,
        variant=GridRescueVariantV2(),
        path="combined",
        routing=None,
        last_baseline=primary,
        last_result=SimpleNamespace(crop_calls={0: 1}),
    )
    proof = observe_input(frame, source, target, detection, engine, UUID(fixture.game))
    assert proof["geometry"]["canvas"] == [480, 288]
    assert verify_input(frame, source, target, proof, UUID(fixture.game)) == proof
    changed = deepcopy(proof)
    changed["geometry"] = {"margin": 0.30}  # V1 nominal canvas must not verify V2 raster proof.
    changed["sha256"] = digest({k: v for k, v in changed.items() if k != "sha256"})
    with pytest.raises(ValueError, match="INPUT_CONTENT_EVIDENCE_CHANGED"):
        verify_input(frame, source, target, changed, UUID(fixture.game))
