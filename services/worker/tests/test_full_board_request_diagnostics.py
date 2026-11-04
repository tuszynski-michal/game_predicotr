"""Exact request replay; controlled CPU arrays and receipts, no network models."""

from copy import deepcopy

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.canonical_source import rgb_pixel_checksum_sha256
from game_predictor_api.domain.grid_rescue_policy import POLICY
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.geometry_core.input_diagnostics import (
    array_sha256,
    digest,
    encode_record,
)
from game_predictor_worker.geometry_core.input_diagnostics_v2 import (
    capture_request_input,
    decode_input_record,
    replay_request_input,
)
from game_predictor_worker.geometry_core.preprocessing import (
    board_rectifier,
    crop_board,
    screen_input,
)
from game_predictor_worker.geometry_core.rescue import GridRescueVariantV1
from game_predictor_worker.geometry_core.rescue_serialization import detection_document
from test_full_board_input_diagnostics import sample as _sample_fixture


@pytest.fixture
def sample():
    return _sample_fixture.__wrapped__()


def inputs(sample, kind="board", *, managed=False):
    rgb, old = sample
    if managed:
        rgb = rgb.copy()
        rgb[:12] = 114
    source = old.source.model_copy(update={"rgb_bytes_sha256": array_sha256(rgb)})
    variant = GridRescueVariantV1(
        screen={"longSide": 1024, "trainCanvas": [1024, 768]}, board={"margin": 0.25}
    )
    pin = {
        "policyVersion": POLICY,
        "variantId": variant.sha256,
        "variant": variant.model_dump(mode="json"),
        "selectedPath": "combined",
        "bundleSha256": old.model.bundle_sha256,
        "proofSha256": "d" * 64,
        "publicationEvidenceSha256": "e" * 64,
    }
    request = {
        "kind": kind,
        "geometry": (variant.board if kind == "board" else variant.screen).model_dump(mode="json"),
        "opencvVersion": cv2.__version__,
        "preprocessingContract": "neural-grid-rescue-preprocessing-v1",
    }
    if kind == "board":
        request["detection"] = detection_document(
            BoardDetection(0.9, np.asarray(old.screen_quad, np.float32))
        )
    execution = {
        "contractVersion": "grid-rescue-execution-v1",
        "preprocessingContract": "neural-grid-rescue-preprocessing-v1",
        "identity": {
            "sourceSha256": source.source_sha256,
            "pin": pin,
            "baselinePresetSha256": old.model.preset_sha256,
            "opencvVersion": cv2.__version__,
            "preprocessingContract": "neural-grid-rescue-preprocessing-v1",
            "positions": [0],
            "width": source.width,
            "height": source.height,
            "inputRaster": {
                "pixelSha256": rgb_pixel_checksum_sha256(rgb),
                "validBox": [0, 12 if managed else 0, source.width, source.height],
                "coordinateSpace": "exif-normalized-rgb-pixels-v1",
            },
        },
        "attempts": [
            {
                "attempt": "crop-0" if kind == "board" else "redetect",
                "request": request,
                "reservationSha256": digest({"state": "reserved", "request": request}),
                "resultSha256": "f" * 64,
                "state": "completed",
            }
        ],
        "reasonCodes": [],
    }
    execution["sha256"] = digest(execution)
    return (
        rgb,
        dict(
            source=source,
            model=old.model,
            archived_preset=old.archived_preset,
            execution=execution,
            expected_positions=[0],
            attempt=execution["attempts"][0]["attempt"],
            rgb=rgb,
        ),
        variant,
    )


@pytest.mark.parametrize("kind", ["board", "screen"])
def test_completed_request_replays_exact_production_override_and_float_tensor(sample, kind):
    rgb, args, variant = inputs(sample, kind)
    record = capture_request_input(**args)
    document = {
        "payload": record.model_dump(mode="json"),
        "sha256": digest(record.model_dump(mode="json")),
    }
    replayed = replay_request_input(decode_input_record(document), rgb)
    old = sample[1]
    expected = (
        crop_board(
            rgb,
            board_rectifier(
                np.asarray(old.screen_quad, np.float32), old.board_preset, geometry=variant.board
            ),
            old.board_preset,
        )
        if kind == "board"
        else screen_input(rgb, old.screen_preset, geometry=variant.screen)[0]
    )
    np.testing.assert_array_equal(replayed, expected)
    tensor = expected.transpose(2, 0, 1).astype("<f4")
    if kind == "screen":
        tensor = tensor[None]
    assert record.stage.tensor_sha256 == array_sha256(tensor)
    assert old.archived_preset["board"]["margin"] == 0.15  # baseline remains unchanged


@pytest.mark.parametrize(
    "failure",
    [
        "reserved",
        "alias",
        "positions",
        "preset",
        "model",
        "opencv",
        "request",
        "missing_raster",
        "raster",
        "support",
    ],
)
def test_invalid_or_unexecuted_request_never_becomes_an_actual_input(sample, failure):
    rgb, args, _ = inputs(sample)
    args = deepcopy(args)
    e = args["execution"]
    if failure == "reserved":
        e["attempts"][0].update(state="consumed_without_result", resultSha256=None)
    if failure == "alias":
        e["reasonCodes"] = ["GRID_RESCUE_SLOT_BINDING_REQUIRED"]
    if failure == "positions":
        args["expected_positions"] = [1]
    if failure == "preset":
        args["archived_preset"]["board"]["margin"] = 0.3
    if failure == "model":
        args["model"] = args["model"].model_copy(update={"bundle_sha256": "0" * 64})
    if failure == "opencv":
        e["identity"]["opencvVersion"] = "unsupported"
    if failure == "request":
        e["attempts"][0]["request"]["geometry"]["margin"] = 0.45
    if failure == "missing_raster":
        del e["identity"]["inputRaster"]
    if failure == "raster":
        e["identity"]["inputRaster"]["pixelSha256"] = "0" * 64
    if failure == "support":
        e["identity"]["inputRaster"]["validBox"] = [0, 0, 999, 999]
    e["sha256"] = digest({k: v for k, v in e.items() if k != "sha256"})
    with pytest.raises(ValueError):
        capture_request_input(**args)


def test_managed_canvas_cannot_be_replaced_by_former_original(sample):
    rgb, args, _ = inputs(sample, managed=True)
    record = capture_request_input(**args)
    replay_request_input(record, rgb)
    with pytest.raises(ValueError, match="SOURCE_PIXELS_MISMATCH"):
        replay_request_input(record, sample[0])


def test_decoder_preserves_v1_payload(sample):
    document = encode_record(sample[1])
    assert encode_record(decode_input_record(document)) == document


def test_request_record_replays_in_a_fresh_process(sample, tmp_path):
    import json
    import os
    import subprocess
    import sys

    rgb, args, _ = inputs(sample, managed=True)
    record = capture_request_input(**args)
    payload = record.model_dump(mode="json")
    (tmp_path / "record.json").write_text(
        json.dumps({"payload": payload, "sha256": digest(payload)}), encoding="utf-8"
    )
    np.save(tmp_path / "actual.npy", rgb)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,numpy as np;from pathlib import Path;"
            "from game_predictor_worker.geometry_core.input_diagnostics_v2 import "
            "decode_input_record,replay_request_input;"
            "r=decode_input_record(json.loads(Path('record.json').read_text()));"
            "replay_request_input(r,np.load('actual.npy',allow_pickle=False))",
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        timeout=20,
    )
    assert child.returncode == 0, child.stderr.decode(errors="replace")


def test_html_uses_only_the_completed_crop_of_the_exact_physical_slot(sample, tmp_path):
    import json

    from game_predictor_worker.images.comparison_input_diagnostics import diagnostic_inputs

    rgb, args, _ = inputs(sample, managed=True)
    args["expected_positions"] = [0, 1]
    args["execution"]["identity"]["positions"] = [0, 1]
    args["execution"]["sha256"] = digest(
        {k: v for k, v in args["execution"].items() if k != "sha256"}
    )
    record = capture_request_input(**args)
    folder = tmp_path / "diagnostics"
    folder.mkdir()
    payload = record.model_dump(mode="json")
    (folder / "record.json").write_text(json.dumps({"payload": payload, "sha256": digest(payload)}))
    np.save(folder / "raster.npy", rgb)
    entry = {
        "sourceId": record.source.source_id,
        "positionIndex": 1,
        "sequenceNumber": 102,
        "modelVersionId": record.model.version_id,
        "record": "diagnostics/record.json",
        "actualRaster": "diagnostics/raster.npy",
    }
    (folder / "index.json").write_text(json.dumps([entry]))
    source = {"id": record.source.source_id, "checksum_sha256": record.source.source_sha256}
    result = diagnostic_inputs(
        tmp_path,
        source,
        {"position_index": 1, "sequence_number": 102},
        {"base": record.model.version_id},
    )
    assert result["base"]["state"] == "unavailable"  # crop-0 cannot be presented as slot1
    entry["positionIndex"] = 0
    entry["sequenceNumber"] = 101
    (folder / "index.json").write_text(json.dumps([entry]))
    result = diagnostic_inputs(
        tmp_path,
        source,
        {"position_index": 0, "sequence_number": 101},
        {"base": record.model.version_id},
    )
    assert result["base"]["state"] == "available"


@pytest.mark.parametrize("kind", ["board", "screen"])
@pytest.mark.parametrize("binding", ["exact", "missing", "changed_board_sequence"])
def test_html_v2_requires_archived_sequence_and_labels_the_actual_stage(
    sample, tmp_path, kind, binding
):
    import json

    from game_predictor_worker.images.comparison_input_diagnostics import diagnostic_inputs

    rgb, args, _ = inputs(sample, kind)
    record = capture_request_input(**args)
    folder = tmp_path / "diagnostics"
    folder.mkdir()
    payload = record.model_dump(mode="json")
    (folder / "record.json").write_text(json.dumps({"payload": payload, "sha256": digest(payload)}))
    np.save(folder / "raster.npy", rgb)
    entry = {
        "sourceId": record.source.source_id,
        "positionIndex": 0,
        # Saved when the record is indexed, not derived from the current board.
        "sequenceNumber": 101,
        "modelVersionId": record.model.version_id,
        "record": "diagnostics/record.json",
        "actualRaster": "diagnostics/raster.npy",
    }
    if binding == "missing":
        del entry["sequenceNumber"]
    (folder / "index.json").write_text(json.dumps([entry]))
    result = diagnostic_inputs(
        tmp_path,
        {"id": record.source.source_id, "checksum_sha256": record.source.source_sha256},
        {
            "position_index": 0,
            "sequence_number": 102 if binding == "changed_board_sequence" else 101,
        },
        {"base": record.model.version_id},
    )["base"]
    if binding != "exact":
        assert result == {"state": "unavailable", "reason": "DIAGNOSTIC_TARGET_SEQUENCE_MISMATCH"}
        assert not (tmp_path / "diagnostic-inputs").exists()
    else:
        assert result["state"] == "available"
        assert result["stageLabel"] == ("wejście ekranu" if kind == "screen" else "wejście planszy")
        assert result["margin"] is None if kind == "screen" else result["margin"] == 0.25
