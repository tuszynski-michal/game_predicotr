"""Actual file renderer and cold CLI, with tiny real rasters and no NN/DB calls."""

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest
from game_predictor_api.domain.grid_cell_content import ContentRevision
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_worker.geometry_core.input_diagnostics import _stage, array_sha256
from game_predictor_worker.images import comparison_production_crop_report as module
from game_predictor_worker.images.normalization import (
    CanonicalSourceLoader,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.production_cell_evaluation import render_cells
from game_predictor_worker.images.production_crop_artifacts import save_raster, sealed
from game_predictor_worker.training_core.grid_correction_metrics import evaluate_photo
from PIL import Image
from test_production_cell_observations import fixture as render_fixture

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "scripts/render_grid_correction_comparison.py"


def save_documents(root, capture, photo):
    capture = sealed({k: v for k, v in capture.items() if k != "sha256"})
    report = sealed(
        {
            "schemaVersion": "production-crop-comparison-v1",
            "captureSha256": capture["sha256"],
            "diagnosticOnly": True,
            "qualificationAllowed": False,
            "variantNames": {"base": "legacy08", "candidate": "legacy00"},
            "accessScope": "internal-diagnostic-metadata",
            "visualExportRule": "TRAIN-and-visualExportAllowed-only",
            "photos": photo,
            "state": "not_evaluable",
        }
    )
    (root / "capture.json").write_text(json.dumps(capture), encoding="utf-8")
    (root / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return capture, report


@pytest.fixture
def package(tmp_path):
    artifacts, root = tmp_path / "store", tmp_path / "report"
    artifacts.mkdir()
    root.mkdir()
    rgb = np.indices((120, 200)).sum(axis=0).astype(np.uint8)
    rgb = np.stack([rgb, rgb // 2, rgb // 3], axis=2)
    original = artifacts / "original.jpg"
    Image.fromarray(rgb).save(original)
    sha = hashlib.sha256(original.read_bytes()).hexdigest()
    frame = CanonicalSourceLoader().load(original, expected_source_checksum_sha256=sha)
    rgb = frame.rgb
    _, source, target, nodes, context = render_fixture(state="unknown")
    identity = {
        **source["sourceIdentity"],
        "id": source["sourceId"],
        "game_id": str(UUID(int=6)),
        "checksum_sha256": sha,
        "normalized_pixel_checksum_sha256": frame.pixel_checksum_sha256,
    }
    source.update(
        sourceIdentity=identity,
        role="TRAIN",
        used=True,
        original={"path": "original.jpg", "sha256": sha, "bytes": original.stat().st_size},
    )
    target = {
        k: v
        for k, v in target.items()
        if k not in ("contentAnnotation", "contentReferenceSha256", "contentReferenceRevision")
    }
    target["nodes"] = [{"x": float(x), "y": float(y)} for x, y in nodes]
    pair = {
        "state": "available",
        "gate": {"state": "not_evaluable", "reasonCodes": ["CONTENT_REFERENCE_INSUFFICIENT"]},
        "configurations": {},
        "classification": [],
        "rasters": [],
        "observation": {
            "sourceId": source["sourceId"],
            "models": {},
            "boards": [
                {
                    "positionIndex": 0,
                    "cells": [{"cellIndex": i, "contentState": "unknown"} for i in range(15)],
                }
            ],
        },
    }
    for variant, padding in (("base", 0.08), ("candidate", 0.0)):
        configuration = {**context["renderConfiguration"], "paddingFraction": padding}
        retained = []
        render_cells(
            frame,
            nodes,
            target,
            {**context, "renderConfiguration": configuration},
            raster_sink=retained.append,
        )
        pair["configurations"][variant] = configuration
        pair["observation"]["models"][variant] = {"detections": [{"nodes": nodes.tolist()}]}
        pair["observation"]["boards"][0][variant] = {
            "matchedPrediction": 0,
            "matchAmbiguous": False,
        }
        for raster in retained:
            pin = save_raster(root, f"rasters/{variant}-{raster.cell_index}.png", raster)
            pair["rasters"].append(
                {**pin, "variant": variant, "predictionIndex": 0, "cellIndex": raster.cell_index}
            )
    # Original found index2 differs from usable index0 used by crop matching.
    model_pair = deepcopy(pair)
    for variant in ("base", "candidate"):
        model_pair["observation"]["models"][variant]["detections"] = [
            {"nodes": None},
            {"nodes": None},
            {"nodes": nodes.tolist()},
        ]
    input_path = root / "input.png"
    Image.fromarray(rgb).save(input_path)
    entry = {
        "stage": "board",
        "predictionIndex": 2,
        "path": "input.png",
        "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "bytes": input_path.stat().st_size,
        "pixelSha256": rgb_pixel_checksum_sha256(rgb),
        "input": _stage(rgb, np.eye(3), screen=False).model_dump(mode="json"),
        "observedSampleTensorSha256": array_sha256(rgb.transpose(2, 0, 1).astype("<f4")),
    }
    neural = sealed(
        {
            "schemaVersion": "production-crop-input-witness-v1",
            "state": "partial",
            "sourceId": source["sourceId"],
            "sourcePixelSha256": frame.pixel_checksum_sha256,
            "context": {},
            "contextSha256": digest({}),
            "entries": [entry],
            "unavailablePredictionIndices": [],
            "unavailableScreenStages": ["base"],
            "reason": "CROP_ACTUAL_SCREEN_INPUT_NOT_BOUND",
        }
    )
    photo = {
        "sourceId": source["sourceId"],
        "role": "TRAIN",
        "state": "available",
        "visualExportAllowed": True,
        "geometry": {"human": pair, "model": model_pair},
        "neuralInput": neural,
    }
    capture = {
        "schemaVersion": "production-crop-capture-v1",
        "gameId": str(UUID(int=6)),
        "diagnosticOnly": True,
        "qualificationAllowed": False,
        "photos": [
            {
                "sourceId": source["sourceId"],
                "role": "TRAIN",
                "state": "available",
                "frozenSource": source,
                "targets": [target],
            }
        ],
    }
    save_documents(root, capture, [photo])
    return root, artifacts, capture, photo


def test_actual_files_unknown_gt_and_separate_index_spaces(package, tmp_path):
    root, artifacts, _, _ = package
    output = tmp_path / "html"
    result = module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    public = json.loads((output / "crop-comparison-data.json").read_bytes())
    photo = public["photos"][0]
    assert photo["original"]["state"] == "available"
    assert photo["neuralInput"]["entries"][0]["originalPredictionIndex"] == 2
    assert photo["neuralInput"]["entries"][0]["state"] == "available"
    board = photo["boards"][0]
    assert board["content"]["state"] == "unavailable"
    for kind in ("human", "model"):
        assert len(board["geometry"][kind]["cells"]) == 15
        for cell in board["geometry"][kind]["cells"]:
            for variant in ("base", "candidate"):
                assert cell[variant]["state"] == "available"
                assert cell[variant]["usablePredictionIndex"] == 0
                assert cell[variant]["assessment"] is None
    assert len(list((output / "cells").glob("*.png"))) == 60
    assert "Diagnoza marginesów" in result.read_text(encoding="utf-8")


def test_control_and_false_flag_are_removed_before_assets_and_public_data(
    package, tmp_path, monkeypatch
):
    root, artifacts, capture, photo = package
    forbidden = []
    for i, (role, allowed) in enumerate(
        (("A", True), ("B", True), ("REGRESSION", True), ("TRAIN", False), ("TRAIN", None)), 200
    ):
        item = deepcopy(photo)
        item.update(
            sourceId=str(UUID(int=i)),
            role=role,
            visualExportAllowed=allowed,
            secret="FORBIDDEN_CONTROL_HINT",
            neuralInput={"path": "never-open-control.png"},
        )
        forbidden.append(item)
    forbidden.append(
        {
            "role": "TRAIN",
            "visualExportAllowed": True,
            "state": "unavailable",
            "secret": "FORBIDDEN_CONTROL_HINT",
        }
    )
    save_documents(root, capture, [*forbidden, photo])
    original = module._asset_bytes
    calls = []

    def guarded(directory, pin):
        calls.append(pin["path"])
        assert "never-open" not in pin["path"]
        return original(directory, pin)

    monkeypatch.setattr(module, "_asset_bytes", guarded)
    output = tmp_path / "html"
    module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    assert calls
    for path in (output / "crop-comparison-data.json", output / "index.html"):
        assert "FORBIDDEN_CONTROL_HINT" not in path.read_text(encoding="utf-8")
        assert "never-open-control" not in path.read_text(encoding="utf-8")
    public = json.loads((output / "crop-comparison-data.json").read_bytes())
    assert len(public["photos"]) == 1
    assert public["omittedTrainSources"] == 3


@pytest.mark.parametrize("problem", ["png", "spec", "quad", "ambiguous", "duplicate", "path"])
def test_bad_cell_is_missing_without_losing_other_slots(package, tmp_path, problem):
    root, artifacts, capture, photo = package
    pair = photo["geometry"]["human"]
    pin = pair["rasters"][0]
    if problem == "png":
        (root / pin["path"]).write_bytes(b"tampered")
    elif problem == "spec":
        pin["renderSpecSha256"] = "e" * 64
    elif problem == "quad":
        pin["renderSpec"]["paddedSourceQuad"][0] = ['" onload="alert(1)', 0]
        pin["renderSpecSha256"] = digest(pin["renderSpec"])
    elif problem == "ambiguous":
        pair["observation"]["boards"][0]["base"]["matchAmbiguous"] = True
    elif problem == "duplicate":
        pair["rasters"].append(deepcopy(pin))
    else:
        pin["path"] = "../outside.png"
    save_documents(root, capture, [photo])
    output = tmp_path / "html"
    module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    cells = json.loads((output / "crop-comparison-data.json").read_bytes())["photos"][0]["boards"][
        0
    ]["geometry"]["human"]["cells"]
    assert len(cells) == 15 and cells[0]["base"]["state"] == "unavailable"
    assert all(c["candidate"]["state"] == "available" for c in cells)
    if problem not in ("ambiguous",):
        assert cells[1]["base"]["state"] == "available"


def test_input_witness_tamper_and_no_target_nodes_are_explicit(package, tmp_path):
    root, artifacts, capture, photo = package
    capture["photos"][0]["targets"][0]["nodes"] = None
    proof = photo["neuralInput"]
    proof["entries"][0]["observedSampleTensorSha256"] = "e" * 64
    photo["neuralInput"] = sealed({k: v for k, v in proof.items() if k != "sha256"})
    save_documents(root, capture, [photo])
    output = tmp_path / "html"
    module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    p = json.loads((output / "crop-comparison-data.json").read_bytes())["photos"][0]
    assert p["boards"][0]["nodes"] is None
    assert p["neuralInput"]["entries"][0]["state"] == "unavailable"
    assert not list((output / "inputs").glob("*.png"))


def test_actual_cli_cold_replay_preserves_inputs_and_outputs(package, tmp_path):
    root, artifacts, _, _ = package
    output = tmp_path / "html"
    env = {**os.environ, "PYTHONUTF8": "1"}
    env.pop("PYTHONPATH", None)
    command = [
        sys.executable,
        str(CLI),
        "--crop-report",
        str(root / "report.json"),
        "--artifact-root",
        str(artifacts),
        "--output-directory",
        str(output),
    ]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    subprocess.run(command, check=True, timeout=30, env=env, capture_output=True)
    written = {
        p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in output.rglob("*")
        if p.is_file()
    }
    subprocess.run(command, check=True, timeout=30, env=env, capture_output=True)
    assert written == {
        p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in output.rglob("*")
        if p.is_file()
    }
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}


def test_approved_outline_classes_and_actual_template_interactions(package, tmp_path):
    root, artifacts, capture, photo = package
    _, _, labeled, _, _ = render_fixture(state="visible")
    identity = capture["photos"][0]["frozenSource"]["sourceIdentity"]
    raw = labeled["contentAnnotation"]
    raw["source"].update(
        sourceSha256=identity["checksum_sha256"],
        sourceRepresentativeSha256=identity["normalized_pixel_checksum_sha256"],
    )
    raw["reference"]["sourceRepresentativeSha256"] = identity["normalized_pixel_checksum_sha256"]
    for index, state in ((1, "occluded"), (2, "out_of_frame"), (3, "unknown")):
        raw["reference"]["cells"][index]["state"] = state
    annotation = ContentRevision.model_validate(raw)
    target = capture["photos"][0]["targets"][0]
    target.update(
        contentAnnotation=annotation.model_dump(mode="json"),
        contentReferenceSha256=annotation.sha256,
    )
    truth = {
        "state": "available",
        "code": "J",
        "renderedPixelSha256": "a" * 64,
        "event": {"id": "human-proof"},
    }
    second_truth = {**truth, "code": "10"}
    target["classes"] = [truth, second_truth] + [{"state": "unavailable"} for _ in range(13)]
    for geometry in photo["geometry"].values():
        geometry["classification"] = [
            {
                "positionIndex": 0,
                "sequenceNumber": 1,
                "cellIndex": 0,
                "state": "available",
                "classReference": truth,
                "base": {"code": "J"},
                "candidate": {"code": "10"},
                "baseCorrect": True,
                "candidateCorrect": False,
                "baseFalseAccept": False,
                "candidateFalseAccept": None,
            },
            {
                "positionIndex": 0,
                "sequenceNumber": 1,
                "cellIndex": 1,
                "state": "unavailable",
                "classReference": second_truth,
                "reason": "CLASS_MODEL_UNAVAILABLE",
                "base": None,
                "candidate": None,
            },
        ]
        observed_cells = geometry["observation"]["boards"][0]["cells"]
        for index, cell in enumerate(observed_cells):
            cell["contentState"] = raw["reference"]["cells"][index]["state"]
        observed_cells[0]["base"] = {
            "finalContentState": "preserved",
            "wrongCell": False,
            "tie": False,
            "foreignFullSymbol": False,
        }
        observed_cells[0]["candidate"] = {
            "finalContentState": "clipped",
            "wrongCell": True,
            "tie": True,
            "foreignFullSymbol": True,
        }
    save_documents(root, capture, [photo])
    output = tmp_path / "html"
    page = module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    data = json.loads((output / "crop-comparison-data.json").read_bytes())
    board = data["photos"][0]["boards"][0]
    assert board["content"]["state"] == "available" and len(board["content"]["cells"]) == 15
    assert board["geometry"]["human"]["cells"][0]["classification"]["candidateCorrect"] is False
    subprocess.run(
        [
            "node",
            str(ROOT / "scripts/tests/verify_production_crop_report.mjs"),
            str(page),
            "--expect-approved",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )


def test_public_json_script_escape_and_output_conflicts(package, tmp_path):
    root, artifacts, capture, photo = package
    photo["geometry"]["human"]["gate"]["reasonCodes"] = [
        "</script><script>globalThis.BAD=1</script>"
    ]
    save_documents(root, capture, [photo])
    output = tmp_path / "html"
    page = module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    text = page.read_text(encoding="utf-8")
    assert "</script><script>globalThis.BAD=1" not in text
    assert "\\u003c/script>" in text
    subprocess.run(
        ["node", str(ROOT / "scripts/tests/verify_production_crop_report.mjs"), str(page)],
        check=True,
        capture_output=True,
        timeout=20,
    )
    image = next((output / "cells").glob("*.png"))
    image.write_bytes(b"foreign-output")
    with pytest.raises(RuntimeError, match="OUTPUT_CONFLICT"):
        module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    assert image.read_bytes() == b"foreign-output"


def test_ambiguous_model_geometry_is_labeled_without_guessing_nodes(package, tmp_path):
    root, artifacts, capture, photo = package
    for variant in ("base", "candidate"):
        photo["geometry"]["model"]["observation"]["boards"][0][variant]["matchAmbiguous"] = True
    save_documents(root, capture, [photo])
    page = module.render_crop_report(
        root / "report.json", output=tmp_path / "html", artifact_root=artifacts
    )
    subprocess.run(
        [
            "node",
            str(ROOT / "scripts/tests/verify_production_crop_report.mjs"),
            str(page),
            "--expect-no-model-nodes",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )


@pytest.mark.parametrize("full", [False, True])
def test_real_geometry_metrics_and_label_ordinal_are_visible_in_dom(package, tmp_path, full):
    root, artifacts, capture, photo = package
    member = capture["photos"][0]
    first = member["targets"][0]
    label = np.asarray([[p["x"], p["y"]] for p in first["nodes"]])
    if full:
        targets = []
        for i in range(9):
            item = deepcopy(first)
            item.update(positionIndex=i, sequenceNumber=i + 1)
            item["nodes"] = (label + [300 * (i % 3), 200 * (i // 3)]).tolist()
            targets.append(item)
        member["targets"] = targets
    else:
        first["positionIndex"] = 7  # Sole label has ordinal0, not physical position7.
        first["sequenceNumber"] = 8
        reference = first["productionContentReference"]
        reference["sourceContext"]["sequenceRangeEnd"] = 9
        reference["sourceContextSha256"] = digest(reference["sourceContext"])
        reference["sha256"] = digest({k: v for k, v in reference.items() if k != "sha256"})
    labels = [
        np.asarray(t["nodes"]) if isinstance(t["nodes"][0], list) else label
        for t in member["targets"]
    ]
    predicted = label + [0, 8]
    extra = label + [2000, 2000]
    measured = evaluate_photo(
        photo["sourceId"],
        photo["sourceId"],
        labels,
        [(predicted, True), (extra, True)],
        full_geometry=full,
    ).as_dict()
    assert measured["matches"][0]["label"] == 0
    assert measured["matches"][0]["correct"] is False
    assert measured["false_boards"] == (1 if full else None)
    pair = photo["geometry"]["model"]
    pair["geometryMetrics"] = measured
    original_board = pair["observation"]["boards"][0]
    pair["observation"]["boards"] = []
    for i, target in enumerate(member["targets"]):
        board = deepcopy(original_board)
        board["positionIndex"] = target["positionIndex"]
        for variant in ("base", "candidate"):
            board[variant]["matchedPrediction"] = 0 if i == 0 else None
        pair["observation"]["boards"].append(board)
    frame = CanonicalSourceLoader().load(
        artifacts / "original.jpg",
        expected_source_checksum_sha256=member["frozenSource"]["original"]["sha256"],
    )
    for variant in ("base", "candidate"):
        pair["observation"]["models"][variant]["detections"] = [
            {"nodes": None},
            {"nodes": None},
            {"nodes": predicted.tolist()},
            {"nodes": extra.tolist()},
        ]
        retained = []
        target = member["targets"][0]
        context = {
            **target["productionContentReference"]["sourceContext"],
            "renderConfiguration": pair["configurations"][variant],
        }
        render_cells(frame, predicted, target, context, raster_sink=retained.append)
        pair["rasters"] = [r for r in pair["rasters"] if r["variant"] != variant]
        for raster in retained:
            pin = save_raster(root, f"shifted/{variant}-{raster.cell_index}.png", raster)
            pair["rasters"].append(
                {**pin, "variant": variant, "predictionIndex": 0, "cellIndex": raster.cell_index}
            )
    save_documents(root, capture, [photo])
    output = tmp_path / "html"
    page = module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    board = json.loads((output / "crop-comparison-data.json").read_bytes())["photos"][0]["boards"][
        0
    ]
    assert board["geometry"]["model"]["boardMatches"]["base"]["correct"] is False
    assert all(c["base"]["state"] == "available" for c in board["geometry"]["model"]["cells"])
    subprocess.run(
        [
            "node",
            str(ROOT / "scripts/tests/verify_production_crop_report.mjs"),
            str(page),
            "--expect-incorrect-geometry",
            "--expect-full-geometry" if full else "--expect-partial-geometry",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )


def test_unexpected_margin_is_unavailable_instead_of_mislabeled(package, tmp_path):
    root, artifacts, capture, photo = package
    pair = photo["geometry"]["human"]
    pair["configurations"]["base"]["paddingFraction"] = 0.04
    for raster in pair["rasters"]:
        if raster["variant"] == "base":
            raster["renderSpec"]["configuration"]["paddingFraction"] = 0.04
            raster["renderSpecSha256"] = digest(raster["renderSpec"])
    save_documents(root, capture, [photo])
    output = tmp_path / "html"
    module.render_crop_report(root / "report.json", output=output, artifact_root=artifacts)
    cells = json.loads((output / "crop-comparison-data.json").read_bytes())["photos"][0]["boards"][
        0
    ]["geometry"]["human"]["cells"]
    assert all(c["base"]["state"] == "unavailable" for c in cells)
    assert all(c["candidate"]["state"] == "available" for c in cells)
