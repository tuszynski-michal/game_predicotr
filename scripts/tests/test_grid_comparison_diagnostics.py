"""Strict archived pixels on exact targets; missing diagnostics never invent an input."""

import importlib.util
import json
from pathlib import Path

import pytest
from game_predictor_worker.geometry_core.input_diagnostics import digest, encode_record
from game_predictor_worker.images.comparison_input_diagnostics import diagnostic_inputs
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def archived(tmp_path):
    path = ROOT / "services/worker/tests/test_full_board_input_diagnostics.py"
    spec = importlib.util.spec_from_file_location("saved_diagnostic_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rgb, record = module.sample.__wrapped__()
    folder = tmp_path / "diagnostics"
    folder.mkdir()
    document = encode_record(record)
    (folder / "record.json").write_text(json.dumps(document), encoding="utf-8")
    from game_predictor_worker.geometry_core.input_diagnostics import reconstruct_input

    _, pixels = reconstruct_input(record, rgb)
    Image.fromarray(pixels).save(folder / "input.png")
    entry = {
        "sourceId": record.source.source_id,
        "positionIndex": record.position_index,
        "modelVersionId": record.model.version_id,
        "record": "diagnostics/record.json",
        "inputRgb": "diagnostics/input.png",
    }
    (folder / "index.json").write_text(json.dumps([entry]), encoding="utf-8")
    source = {"id": record.source.source_id, "checksum_sha256": record.source.source_sha256}
    board = {"position_index": record.position_index, "sequence_number": record.sequence_number}
    return tmp_path, source, board, {"base": record.model.version_id}, document


def test_archived_input_has_exact_separate_rgb_and_tensor_identity(archived):
    root, source, board, versions, _ = archived
    result = diagnostic_inputs(root, source, board, versions)["base"]
    assert result["state"] == "available"
    assert result["rgbSha256"] != result["tensorSha256"]
    assert result["humanReference"] == "unavailable"
    assert (root / result["image"]).exists()


@pytest.mark.parametrize(
    "failure", ["preset", "missing_preset", "source", "sequence", "model", "pixels", "duplicate"]
)
def test_missing_mismatched_or_ambiguous_archive_is_explicitly_unavailable(archived, failure):
    root, source, board, versions, document = archived
    if failure == "preset":
        document["payload"]["archived_preset"]["board"]["margin"] = 0.4
    if failure == "missing_preset":
        del document["payload"]["archived_preset"]
    if failure == "source":
        source["checksum_sha256"] = "0" * 64
    if failure == "sequence":
        board["sequence_number"] += 1
    if failure == "model":
        versions["base"] = "other-model"
    if failure == "pixels":
        Image.new("RGB", (320, 192)).save(root / "diagnostics/input.png")
    if failure == "duplicate":
        p = root / "diagnostics/index.json"
        rows = json.loads(p.read_text())
        p.write_text(json.dumps(rows * 2))
    document["sha256"] = digest(document["payload"])
    (root / "diagnostics/record.json").write_text(json.dumps(document), encoding="utf-8")
    result = diagnostic_inputs(root, source, board, versions)["base"]
    assert result["state"] == "unavailable" and result["reason"]
    assert "image" not in result
