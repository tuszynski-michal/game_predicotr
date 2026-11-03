from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import numpy as np
import pytest
from game_predictor_worker.geometry_core.input_diagnostics import (
    array_sha256,
    decode_record,
    digest,
)
from game_predictor_worker.geometry_core.preprocessing import grid_from_quad
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from PIL import Image
from test_full_board_input_diagnostics import sample  # noqa: F401

from scripts import diagnose_full_board_input as cli
from scripts.diagnose_full_board_input import associate_saved, capture, frozen, read_json, replay


@pytest.fixture
def files(request, tmp_path):
    rgb, record = request.getfixturevalue("sample")
    image = tmp_path / "source.jpg"
    Image.fromarray(rgb).save(image)
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    frame = CanonicalSourceLoader().load(image, expected_source_checksum_sha256=sha)
    source = {
        "id": "source",
        "relative_path": image.name,
        "checksum_sha256": sha,
        "normalized_pixel_checksum_sha256": frame.source.normalized_pixel_checksum_sha256,
        "oriented_width": 153,
        "oriented_height": 97,
        "exif_orientation": None,
        "normalization_adapter_version": frame.source.normalization_adapter_version,
        "coordinate_space": frame.source.coordinate_space,
    }
    quad = [[10.0, 15.0], [130.0, 10.0], [140.0, 87.0], [5.0, 78.0]]
    nodes = grid_from_quad(np.asarray(quad, np.float32)).tolist()
    binding = {
        "gameId": "game",
        "sourceChecksumSha256": sha,
        "sourceWidth": 153,
        "sourceHeight": 97,
        "confirmedRange": {"sequenceRangeStart": 101, "sequenceRangeEnd": 101},
        "assignments": [{"detectionId": "archived-base", "positionIndex": 0}],
        "missingPositionIndexes": [],
    }
    board = {
        "source_image_id": "source",
        "sequence_number": 101,
        "position_index": 0,
        "board_geometry": {
            "latticeNodes": [{"x": x, "y": y} for x, y in nodes],
            "neuralProposalBinding": binding,
            "detectionId": "archived-base",
            "attestedRangeStart": 101,
            "attestedRangeEnd": 101,
            "structuredDisposition": "automatic",
        },
    }
    inputs = {"photos": [source], "boards": [board], "gameId": "game"}
    preset = {
        "screen": record.screen_preset.model_dump(),
        "board": record.board_preset.model_dump(),
        "preprocessing_version": "neural-grid-screen768-board320x192-v1",
    }
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    bundle = bundle_dir / "bundle.json"
    bundle.write_text(json.dumps({"preset": preset}))
    observations = {}
    for kind in ("base", "candidate"):
        (tmp_path / kind).mkdir()
        observation = {
            "status": "ok",
            "sourceId": "source",
            "sourceChecksum": sha,
            "versionId": kind,
            "bundleSha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
            "width": 153,
            "height": 97,
            "detections": [
                {
                    "nodes": nodes,
                    "screenQuad": quad,
                    "structurallyValid": True,
                    "reasons": [] if kind == "base" else ["NEURAL_GRID_FIT_OUTLIERS"],
                }
            ],
        }
        (tmp_path / kind / "source.json").write_text(json.dumps(observation))
        observations[kind] = observation
    (tmp_path / "inputs.json").write_text(json.dumps(inputs))
    return (
        argparse.Namespace(
            comparison=tmp_path,
            data_root=tmp_path,
            base_bundle=bundle_dir,
            candidate_bundle=bundle_dir,
            source="source",
            sequence=101,
            position=0,
            output=tmp_path / "result",
        ),
        inputs,
        observations,
    )


def test_capture_and_replay_preserve_unknowns_and_separate_tensors(files):
    args, _, _ = files
    capture(args)
    report = read_json(args.output / "report.json")
    assert len(report["diagnosticUse"]) == 1
    assert report["diagnosticUse"][0]["future_control_exclusion_required"]
    assert {entry["recordSha256"] for entry in report["diagnosticUse"][0]["records"]} == set(
        report["records"].values()
    )
    for kind in ("base", "candidate"):
        record = decode_record(read_json(args.output / f"{kind}.json"))
        replay(
            argparse.Namespace(
                record=args.output / f"{kind}.json", original=args.data_root / "source.jpg"
            )
        )
        assert record.raw_nodes.nodes is None and record.human_reference == "unavailable"
        assert record.fraction_of_gt_outside_input is None
        for name in ("screen", "board"):
            stage = getattr(record, name)
            pixels = np.asarray(Image.open(args.output / f"{kind}-{name}.png"))
            tensor = np.load(args.output / f"{kind}-{name}.npy", allow_pickle=False)
            assert array_sha256(pixels) == stage.rgb_sha256
            assert array_sha256(tensor) == stage.tensor_sha256
            assert tensor.dtype == np.float32
            assert tensor.max() > 1  # No undocumented division by255.
    candidate = decode_record(read_json(args.output / "candidate.json"))
    assert "NEURAL_GRID_FIT_OUTLIERS" in candidate.current_policy_blockers
    assert (
        candidate.current_policy_verdict == "blocked" and candidate.historical_disposition is None
    )
    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        capture(args)


def test_matching_never_uses_detection_order_or_guesses_sequence(files):
    _, inputs, observations = files
    base, candidate = deepcopy(observations["base"]), deepcopy(observations["candidate"])
    unrelated = {"nodes": [[0, 0]] * 24, "screenQuad": [[0, 0]] * 4}
    base["detections"].insert(0, unrelated)
    candidate["detections"].append(unrelated)
    _, _, first, second = associate_saved(inputs, base, candidate, "source", 101, 0)
    assert first["screenQuad"] == second["screenQuad"]
    with pytest.raises(ValueError, match="SEQUENCE_AMBIGUOUS"):
        associate_saved(inputs, base, candidate, "source", 102, 0)
    candidate["detections"].append(deepcopy(second))
    with pytest.raises(ValueError, match="CORRESPONDENCE_UNAVAILABLE"):
        associate_saved(inputs, base, candidate, "source", 101, 0)


def test_model_source_and_attestation_drift_fail_before_publication(files):
    args, inputs, observations = files
    wrong = deepcopy(inputs)
    wrong["boards"][0]["board_geometry"]["attestedRangeStart"] = 100
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        associate_saved(wrong, observations["base"], observations["candidate"], "source", 101, 0)
    (args.base_bundle / "bundle.json").write_text('{"preset":{}}')
    with pytest.raises(ValueError, match="BUNDLE_MISMATCH"):
        capture(args)
    assert not args.output.exists()


def test_replay_rejects_changed_decoder_metadata(files):
    args, _, _ = files
    capture(args)
    record_path = args.output / "base.json"
    document = read_json(record_path)
    document["payload"]["source"]["decoder_version"] = "other-decoder"
    document["sha256"] = digest(document["payload"])
    record_path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="CANONICAL_SOURCE_MISMATCH"):
        replay(argparse.Namespace(record=record_path, original=args.data_root / "source.jpg"))


def test_frozen_counts_preserve_roles_and_explicit_budget(monkeypatch, tmp_path):
    from game_predictor_worker.images import grid_cohort_dataset

    sources = [
        {"role": "REGRESSION", "used": True, "targets": [1] * 9, "screenEligible": True},
        {"role": "TRAIN", "used": True, "targets": [1], "screenEligible": False},
        {"role": "TRAIN", "used": False},
        {"role": None, "used": False, "targets": [1] * 9, "screenEligible": True},
    ]
    fake = argparse.Namespace(
        sources=lambda: iter(sources),
        manifest={
            "gameId": "g",
            "cohortId": "c",
            "counts": {
                "TRAIN": {"boards": 1, "photos": 1, "fullPhotos": 0},
                "VALIDATION": {"boards": 0, "photos": 0, "fullPhotos": 0},
                "REGRESSION": {"boards": 9, "photos": 1, "fullPhotos": 1},
            },
        },
    )
    monkeypatch.setattr(grid_cohort_dataset, "GridCohortSnapshot", lambda *args: fake)
    args = argparse.Namespace(
        artifact_root=tmp_path,
        manifest="pinned.json",
        manifest_sha="a" * 64,
        max_sources=1,
        output=tmp_path / "frozen.json",
    )
    frozen(args)
    report = read_json(args.output)
    assert report["status"] == "partial" and not report["populationComplete"]
    assert report["roles"]["REGRESSION"]["humanLabels"] == 9
    assert report["roles"]["REGRESSION"]["screenEligiblePhotos"] == 1
    assert report["liveEligibility"] is None and report["independentGroups"] is None
    assert report["diagnosticUse"] == [] and not report["ledgerModified"]
    args.max_sources = 4
    args.output = tmp_path / "frozen-complete.json"
    frozen(args)
    complete = read_json(args.output)
    assert complete["populationComplete"]
    assert complete["roles"] == {
        "TRAIN": {"photos": 2, "usedPhotos": 1, "humanLabels": 1, "screenEligiblePhotos": 0},
        "REGRESSION": {"photos": 1, "usedPhotos": 1, "humanLabels": 9, "screenEligiblePhotos": 1},
        "UNASSIGNED": {"photos": 1, "usedPhotos": 0, "humanLabels": 0, "screenEligiblePhotos": 0},
    }
    fake.manifest["counts"]["TRAIN"]["boards"] = 2
    args.output = tmp_path / "inconsistent.json"
    with pytest.raises(ValueError, match="FROZEN_COUNTS_MISMATCH"):
        frozen(args)
    assert not args.output.exists()


def test_historical_automatic_cannot_override_current_blocker_in_same_record(files):
    args, _, observations = files
    observations["base"]["detections"][0]["reasons"] = ["NEURAL_GRID_FIT_OUTLIERS"]
    (args.comparison / "base/source.json").write_text(json.dumps(observations["base"]))
    capture(args)
    record = decode_record(read_json(args.output / "base.json"))
    assert record.historical_disposition == "automatic"
    assert record.current_policy_verdict == "blocked"
    assert "NEURAL_GRID_FIT_OUTLIERS" in record.current_policy_blockers


def test_atomic_json_two_writers_do_not_overwrite_or_publish_partial_content(tmp_path):
    barrier = Barrier(2)
    output = tmp_path / "report.json"

    def write(value):
        barrier.wait(timeout=5)
        try:
            cli.write_json(output, {"value": value, "payload": "complete" * 1000})
            return value
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (1, 2)))
    assert results.count(None) == 1
    assert read_json(output) == {
        "value": next(v for v in results if v),
        "payload": "complete" * 1000,
    }
    assert list(tmp_path.iterdir()) == [output]


def test_atomic_json_failed_flush_leaves_no_final_output(monkeypatch, tmp_path):
    def failed_flush(fd):
        raise OSError("flush failed")

    monkeypatch.setattr(cli.os, "fsync", failed_flush)
    with pytest.raises(OSError, match="flush failed"):
        cli.write_json(tmp_path / "report.json", {"complete": True})
    assert list(tmp_path.iterdir()) == []


def test_capture_flushes_all_files_before_exclusive_directory_publication(monkeypatch, tmp_path):
    staging, output = tmp_path / "stage", tmp_path / "result"
    staging.mkdir()
    for name in ("a.json", "b.npy", "c.png"):
        (staging / name).write_bytes(b"complete")
    original_fsync, original_rename = os.fsync, os.rename
    flushed = []

    def flush(fd):
        original_fsync(fd)
        flushed.append(fd)

    def publish(source, destination):
        assert len(flushed) == 3
        original_rename(source, destination)

    monkeypatch.setattr(cli.os, "fsync", flush)
    monkeypatch.setattr(cli.os, "rename", publish)
    cli.publish_capture(staging, output)
    assert not staging.exists() and len(list(output.iterdir())) == 3


def test_capture_racing_existing_empty_directory_is_not_replaced(files, monkeypatch):
    args, _, _ = files
    original_publish = cli.publish_capture

    def race(staging, output):
        output.mkdir()
        original_publish(staging, output)

    monkeypatch.setattr(cli, "publish_capture", race)
    with pytest.raises(FileExistsError):
        capture(args)
    assert args.output.is_dir() and list(args.output.iterdir()) == []
    assert len(list(args.output.parent.glob(".input-diagnostic-*/report.json"))) == 1
