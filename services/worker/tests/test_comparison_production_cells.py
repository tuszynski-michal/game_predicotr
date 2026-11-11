"""Real renderer/file CLI checks on tiny synthetic photos, without NN or DB access."""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.domain.canonical_source import rgb_pixel_checksum_sha256
from game_predictor_api.domain.grid_cell_content import ContentRevision
from game_predictor_api.domain.grid_training_cohorts import digest, exact_lattice
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_worker.filesystem import long_path_aware
from game_predictor_worker.images.comparison_production_bundle import build_production_package
from game_predictor_worker.images.comparison_production_cells import (
    INDEX_VERSION,
    ComparisonProductionCells,
)
from game_predictor_worker.images.grid_cohort_dataset import GridBoardDataset, GridCohortSnapshot
from game_predictor_worker.images.production_cell_evaluation import render_cells
from game_predictor_worker.images.production_cell_run import ProductionContentRun
from game_predictor_worker.images.virtual_cell_extraction import VirtualCellExtractionError
from game_predictor_worker.training_core.grid_correction_metrics import (
    CorrectionControlPhoto,
    evaluate_photo,
)
from game_predictor_worker.training_core.grid_evaluation import predictions
from PIL import Image
from test_production_cell_frozen_pipeline import Engine, frozen_fixture
from test_production_cell_observations import fixture

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/render_grid_correction_comparison.py"


def write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, allow_nan=False).encode()
    path.write_bytes(raw)
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}


def _nine_targets(_fixture, sources, split):
    source = sources[0]
    template = deepcopy(source["targets"][0])
    source["targets"] = []
    source["screenEligible"] = True
    for position in range(9):
        target = deepcopy(template)
        offset = np.asarray([0.5 + (position % 3) * 18, 0.5 + (position // 3) * 14])
        nodes = np.asarray([[p["x"], p["y"]] for p in target["nodes"]]) * 0.2 + offset
        target.update(
            positionIndex=position,
            sequenceNumber=17 + position,
            nodes=[{"x": float(x), "y": float(y)} for x, y in nodes],
        )
        annotation = target["contentAnnotation"]
        annotation["sequenceNumber"] = 17 + position
        annotation["reference"]["positionIndex"] = position
        annotation["measuredNodes"] = nodes.tolist()
        for cell in annotation["reference"]["cells"]:
            cell["quad"] = (np.asarray(cell["quad"]) * 0.2 + offset).tolist()
        parsed = ContentRevision.model_validate(annotation)
        target.update(
            contentAnnotation=parsed.model_dump(mode="json"), contentReferenceSha256=parsed.sha256
        )
        target["blindGeometry"].update(
            contentReferenceSha256=parsed.sha256, nodesSha256=digest(target["nodes"])
        )
        _, target["render"]["cellQuads"] = exact_lattice({"latticeNodes": target["nodes"]}, 64, 48)
        pin = target["productionContentReference"]
        pin["sourceContext"]["sequenceRangeEnd"] = 25
        pin["sourceContextSha256"] = digest(pin["sourceContext"])
        pin["sha256"] = digest({k: v for k, v in pin.items() if k != "sha256"})
        source["targets"].append(target)
    split["purposeCounts"]["VALIDATION-A"].update(boards=9, fullPhotos=1)
    next(p for p in split["sources"] if p["sourceId"] == source["sourceId"])["eligibleBoards"] = 9


def _publish_actual_root(root, fixture, snapshot):
    store = GridCohortArtifactStore(root)
    game, cohort = UUID(fixture.game), UUID(fixture.cohort)
    pages = []
    for page in fixture.pages:
        published = store.publish_json(game, cohort, store.read_json(page["path"], page["sha256"]))
        pages.append(
            {**published, "boardCount": page["boardCount"], "screenCount": page["screenCount"]}
        )
    document = snapshot.manifest
    document["pageIndex"] = store.publish_index(game, cohort, pages)
    pin = store.publish_json(game, cohort, document)
    # Remove this test's old fake location: the CLI must consume the real publisher path.
    (root / fixture.manifest_pin["path"]).unlink()
    fixture.manifest_pin = pin
    assert pin["path"] == f"{fixture.directory}/pages/{pin['sha256']}.json"
    assert not (root / fixture.directory / "manifest.json").exists()
    assert store.read_json(pin["path"], pin["sha256"]) == document
    return GridCohortSnapshot(root, pin["path"], pin["sha256"])


def _comparison_files(tmp_path, *, nine=False):
    frozen, snapshot, sources = frozen_fixture(tmp_path, configure=_nine_targets if nine else None)
    snapshot = _publish_actual_root(tmp_path, frozen, snapshot)
    source = sources[0]
    target = source["targets"][0]
    frame = snapshot.frame(source, "VALIDATION")
    frozen_labels = next(
        labels
        for s, labels in GridBoardDataset(snapshot, "VALIDATION").indexed()
        if s["sourceId"] == source["sourceId"]
    )
    labels = tuple(nodes for nodes, _weight in frozen_labels)
    nodes = labels[0]
    engines = {name: Engine(nodes.copy()) for name in ("base", "candidate")}
    photo = CorrectionControlPhoto(
        source["sourceId"],
        str(uuid4()),
        source["original"]["sha256"],
        labels,
        lambda: frame.rgb,
        full_geometry=nine,
    )
    observed = {}
    rows = {}
    detections = {}
    for name, engine in engines.items():
        predicted_nodes = [n.copy() for n in labels]
        if nine and name == "candidate":
            predicted_nodes[0][:, 0] -= 0.8  # Negative corner, still an unambiguous T3 match.
        found = [Engine(n).analyse(frame.rgb)[0] for n in predicted_nodes]
        detections[name] = [{"nodes": d.nodes.tolist()} for d in found]
        result = evaluate_photo(
            photo.source_id,
            photo.group_id,
            list(photo.labels),
            predictions(found),
            full_geometry=nine,
        )
        rows[name] = result.as_dict()
        observed[name] = found, result, engine
    observation = ProductionContentRun(snapshot).observer("VALIDATION")(photo, frame.rgb, observed)
    job = str(uuid4())
    document = {
        "schemaVersion": "grid-model-evaluation-detail-v1",
        "jobId": job,
        "gameId": frozen.game,
        "cohortId": frozen.cohort,
        "role": "VALIDATION",
        "photos": [
            {
                "sourceId": source["sourceId"],
                "groupId": photo.group_id,
                "contentEvaluation": observation,
                **rows,
            }
        ],
    }
    detail = write(tmp_path, "grid-model-evaluations/detail.json", document)
    metrics = {"boards_correct": 1, "boards_expected": 1, "normalized_error": 0.01}
    role = {"photos": 1, "base": metrics, "candidate": metrics, "detail": detail}
    evaluation = {
        "evaluationId": job,
        "versionId": "new",
        "baseVersionId": frozen.base["versionId"],
        "trainingGameId": frozen.game,
        "status": "completed",
        "report": {
            "schemaVersion": "grid-model-evaluation-read-v6",
            "versionId": "new",
            "baseVersionId": frozen.base["versionId"],
            "verdict": "NOT_EVALUABLE",
            "rawQuality": {"verdict": "PASS"},
            "cohorts": [
                {
                    "gameId": frozen.game,
                    "cohortId": frozen.cohort,
                    "manifestSha256": frozen.manifest_pin["sha256"],
                }
            ],
            "games": [
                {
                    "gameId": frozen.game,
                    "reasons": ["fixture_only"],
                    "roles": {"VALIDATION": role, "REGRESSION": role},
                }
            ],
        },
    }
    evaluation["report"]["rawQuality"] = {
        **{k: v for k, v in evaluation["report"].items() if k != "rawQuality"},
        "schemaVersion": "grid-model-evaluation-read-v5",
        "verdict": "PASS",
    }
    entry = {
        "sourceId": source["sourceId"],
        "gameId": frozen.game,
        "role": "VALIDATION",
        "manifest": {k: frozen.manifest_pin[k] for k in ("path", "sha256")},
        "detail": detail,
    }
    index = {"schemaVersion": INDEX_VERSION, "entries": [entry]}
    write(tmp_path, "production-cells/index.json", index)
    selected_source = {
        "id": source["sourceId"],
        "checksum_sha256": source["sourceIdentity"]["checksum_sha256"],
        "oriented_width": 64,
        "oriented_height": 48,
    }
    board = {
        "id": "fixture-board",
        "source_image_id": source["sourceId"],
        "position_index": 0,
        "sequence_number": target["sequenceNumber"],
        "grid_rows": 3,
        "grid_columns": 5,
        "board_geometry": {"latticeNodes": nodes.tolist()},
    }
    inference = {}
    for name in ("base", "candidate"):
        inference[name] = {
            "versionId": frozen.base["versionId"] if name == "base" else "new",
            "sourceChecksum": selected_source["checksum_sha256"],
            "status": "ok",
            "detections": detections[name],
        }
        write(tmp_path, f"{name}/{source['sourceId']}.json", inference[name])
    boards = [
        {
            **board,
            "id": f"fixture-board-{t['positionIndex']}",
            "position_index": t["positionIndex"],
            "sequence_number": t["sequenceNumber"],
            "board_geometry": {"latticeNodes": t["nodes"]},
        }
        for t in source["targets"]
    ]
    write(
        tmp_path, "inputs.json", {"photos": [selected_source], "boards": boards, "membership": []}
    )
    write(tmp_path, "learning-final.json", {"candidateVersionId": "new", "gameId": frozen.game})
    write(tmp_path, "evaluation-final.json", evaluation)
    preview = tmp_path / f"photos/{source['sourceId']}.jpg"
    preview.parent.mkdir()
    preview.write_bytes((tmp_path / source["original"]["path"]).read_bytes())
    return tmp_path, selected_source, board, inference, evaluation, index, document


@pytest.fixture
def files(tmp_path):
    return _comparison_files(tmp_path)


@pytest.fixture
def nine_files(tmp_path):
    return _comparison_files(tmp_path, nine=True)


def test_sink_exact_default_metadata_regression_and_pixel_contract():
    frame, _, target, nodes, context = fixture()
    before = render_cells(frame, nodes, target, context)
    rasters = []
    after = render_cells(frame, nodes, target, context, raster_sink=rasters.append)
    assert before == after and len(rasters) == 15
    assert [r.cell_index for r in rasters] == list(range(15))
    assert len({r.rendered_pixel_checksum_sha256 for r in rasters}) > 1
    for witness, raster in zip(before, rasters, strict=True):
        assert raster.rgb.dtype == np.uint8 and raster.rgb.shape == (64, 64, 3)
        assert not raster.rgb.flags.writeable
        assert witness["renderedPixelSha256"] == rgb_pixel_checksum_sha256(raster.rgb)
        assert witness["renderSpecSha256"] == raster.render_spec_checksum_sha256


def test_sink_failure_is_not_silently_classified_as_missing_crop():
    frame, _, target, nodes, context = fixture()

    def failure(_raster):
        raise VirtualCellExtractionError("FILE_CONSUMER_FAILED", "Synthetic sink failure")

    with pytest.raises(VirtualCellExtractionError, match="Synthetic sink failure"):
        render_cells(frame, nodes, target, context, raster_sink=failure)


@pytest.mark.parametrize("variation", ["perspective", "source_edge"])
def test_sink_preserves_real_warp_and_source_bounds_contract(variation):
    frame, _, target, nodes, context = fixture()
    nodes = nodes.astype(np.float64)
    if variation == "perspective":
        nodes[:, 0] += nodes[:, 1] * 0.1
    else:
        nodes[:, 0] -= 15
        rasters = []
        with pytest.raises(ValueError, match="inside the source"):
            render_cells(frame, nodes, target, context)
        with pytest.raises(ValueError, match="inside the source"):
            render_cells(frame, nodes, target, context, raster_sink=rasters.append)
        assert rasters == []
        return
    expected = render_cells(frame, nodes, target, context)
    rasters = []
    actual = render_cells(frame, nodes, target, context, raster_sink=rasters.append)
    assert actual == expected and len(actual) == 15
    assert {r.cell_index for r in rasters} == {
        i for i, c in enumerate(actual) if c["reason"] is None
    }
    assert len(rasters) == 15
    assert all(r.rgb.shape == (64, 64, 3) for r in rasters)


def test_real_fifteen_lossless_pngs_match_t3_with_separate_file_hashes(files):
    root, source, board, inference, evaluation, _, document = files
    before = deepcopy(document)
    result = ComparisonProductionCells(root, evaluation).for_board(source, board, inference)
    assert result["state"] == "available", result
    assert result["contentReferenceRevision"] == 1
    for name in ("base", "candidate"):
        model = result["models"][name]
        assert model["state"] == "available" and model["matchedPrediction"] == 0
        assert [c["cellIndex"] for c in model["cells"]] == list(range(15))
        for cell, witness in zip(
            model["cells"],
            before["photos"][0]["contentEvaluation"]["models"][name]["crops"],
            strict=True,
        ):
            raw = (root / cell["image"]).read_bytes()
            assert raw.startswith(b"\x89PNG\r\n\x1a\n")
            assert cell["pngFileSha256"] == hashlib.sha256(raw).hexdigest()
            with Image.open(root / cell["image"]) as image:
                assert image.mode == "RGB"
                assert (
                    rgb_pixel_checksum_sha256(np.asarray(image)) == witness["renderedPixelSha256"]
                )
            assert cell["renderedPixelSha256"] != cell["pngFileSha256"]
            assert cell["renderSpec"]["sourceChecksumSha256"] == source["checksum_sha256"]
    assert document == before


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "duplicate",
        "version",
        "escape",
        "manifest",
        "detail_sha",
        "report_pin",
        "source",
        "sequence",
        "slot",
        "game",
        "nodes",
        "pixel_lie",
        "matching_lie",
        "support_lie",
        "classifier_lie",
        "input_sha_lie",
        "raw_pin",
        "role",
        "job",
        "cohort",
    ],
)
def test_missing_foreign_ambiguous_or_tampered_proof_is_unavailable(files, failure):
    root, source, board, inference, evaluation, index, document = files
    entry = index["entries"][0]
    recorded = document["photos"][0]["contentEvaluation"]
    if failure == "missing":
        long_path_aware(root / entry["manifest"]["path"]).unlink()
    elif failure == "duplicate":
        index["entries"] *= 2
    elif failure == "version":
        index["schemaVersion"] = "invented"
    elif failure == "escape":
        entry["manifest"]["path"] = "../elsewhere.json"
    elif failure == "manifest":
        entry["manifest"]["sha256"] = "0" * 64
    elif failure == "detail_sha":
        (root / entry["detail"]["path"]).write_text("{}")
    elif failure == "report_pin":
        evaluation["report"]["games"][0]["roles"]["VALIDATION"] = {
            "detail": {"path": "other", "sha256": "f" * 64}
        }
    elif failure == "source":
        source["checksum_sha256"] = "f" * 64
    elif failure == "raw_pin":
        raw = deepcopy(evaluation["report"]["rawQuality"])
        raw["games"][0]["roles"]["VALIDATION"]["detail"]["sha256"] = "f" * 64
        evaluation["report"]["rawQuality"] = raw
    elif failure == "sequence":
        board["sequence_number"] += 1
    elif failure == "slot":
        board["position_index"] = 8
    elif failure == "game":
        board["game_id"] = str(uuid4())
    elif failure == "nodes":
        inference["candidate"]["detections"][0]["nodes"][0][0] += 1
    elif failure in (
        "pixel_lie",
        "support_lie",
        "matching_lie",
        "job",
        "cohort",
        "classifier_lie",
        "input_sha_lie",
    ):
        if failure == "pixel_lie":
            recorded["models"]["candidate"]["crops"][0]["renderedPixelSha256"] = "f" * 64
        if failure == "support_lie":
            recorded["models"]["candidate"]["crops"][0]["support"][0][0] += 1
        if failure == "matching_lie":
            recorded["boards"][0]["candidate"]["matchAmbiguous"] = True
        if failure == "job":
            document["jobId"] = str(uuid4())
        if failure == "cohort":
            document["cohortId"] = str(uuid4())
        if failure == "classifier_lie":
            recorded["referenceSha256"] = "f" * 64
        if failure == "input_sha_lie":
            proof = recorded["boards"][0]["candidate"]["inputEvidence"]
            proof["inputRasterSha256"] = "f" * 64
            proof["sha256"] = digest({k: v for k, v in proof.items() if k != "sha256"})
        pin = write(root, entry["detail"]["path"], document)
        entry["detail"].update(pin)
    elif failure == "role":
        entry["role"] = "TRAIN"
    write(root, "production-cells/index.json", index)
    result = ComparisonProductionCells(root, evaluation).for_board(source, board, inference)
    assert result["state"] == "unavailable" and result["reason"], result
    assert "models" not in result


def test_existing_cli_cold_process_uses_sink_and_preserves_files_and_verdict(files):
    artifacts, _, _, _, evaluation, index, _ = files
    manifest = index["entries"][0]["manifest"]
    cohort = evaluation["report"]["cohorts"][0]
    assert manifest["path"] == (
        f"data/grid-training-cohorts/{cohort['gameId']}/{cohort['cohortId']}/pages/"
        f"{cohort['manifestSha256']}.json"
    )
    assert not (artifacts / manifest["path"]).parent.parent.joinpath("manifest.json").exists()
    pinned_files = {
        p: hashlib.sha256(long_path_aware(p).read_bytes()).hexdigest()
        for p in artifacts.rglob("*")
        if long_path_aware(p).is_file()
    }
    root = artifacts / "portable-report"
    root.mkdir()
    for name in ("inputs.json", "learning-final.json", "evaluation-final.json"):
        shutil.copyfile(artifacts / name, root / name)
    for name in ("base", "candidate", "photos"):
        shutil.copytree(artifacts / name, root / name)
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [
                str(ROOT / "services/api/src"),
                str(ROOT / "services/worker/src"),
                str(ROOT),
            ]
        ),
    }
    command = [
        sys.executable,
        str(SCRIPT),
        "--directory",
        str(root),
        "--artifact-root",
        str(artifacts),
    ]
    for _ in range(2):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
        assert result.returncode == 0, result.stderr
        cards = json.loads((root / "comparison-data.json").read_bytes())
        assert cards[0]["paired"] is True  # One detection is enough only with genuine T3 proof.
        assert cards[0]["productionCells"]["state"] == "available"
        assert len(cards[0]["reference"]) == 24
        assert cards[0]["humanReference"]["state"] == "available"
        assert len(cards[0]["humanReference"]["cells"]) == 15
        assert cards[0]["contentChange"]["state"] in {
            "improved",
            "unchanged",
            "degraded",
            "unresolved",
        }
        diagnostic = cards[0]["diagnostics"]["candidate"]
        assert diagnostic["state"] == "available"
        assert diagnostic["schemaVersion"] == "frozen-a-neural-input-content-v1"
        assert diagnostic["tensorSha256"] is None and diagnostic["tensorShape"] is None
        with Image.open(root / diagnostic["image"]) as image:
            assert rgb_pixel_checksum_sha256(np.asarray(image)) == diagnostic["rgbSha256"]
        assert len(list(root.glob("production-cell-images/*/0/*/*.png"))) == 30
        check = subprocess.run(
            [
                "node",
                str(ROOT / "scripts/tests/verify_grid_correction_comparison.mjs"),
                str(root / "comparison.html"),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert check.returncode == 0, check.stderr
    html = (root / "comparison.html").read_text(encoding="utf-8")
    assert "NOT_EVALUABLE" in html
    assert "Wszystkie porównania wykonano na CPU" not in html
    assert "przy dziewięciu detekcjach" not in html
    assert all(
        hashlib.sha256(long_path_aware(p).read_bytes()).hexdigest() == sha
        for p, sha in pinned_files.items()
    )
    assert evaluation["report"]["verdict"] == "NOT_EVALUABLE"


def test_expected_invalid_render_is_local_to_one_of_nine_boards_and_one_model(nine_files):
    root, source, _, inference, evaluation, index, document = nine_files
    boards = json.loads((root / "inputs.json").read_bytes())["boards"]
    recorded = document["photos"][0]["contentEvaluation"]
    assert len(boards) == len(recorded["boards"]) == 9
    assert (
        recorded["models"]["candidate"]["crops"][:15]
        == [{"support": None, "reason": "CONTENT_PREDICTION_INVALID"}] * 15
    )
    consumer = ComparisonProductionCells(root, evaluation)
    results = [consumer.for_board(source, board, inference) for board in boards]
    assert all(r["state"] == "available" for r in results), results
    assert all(r["models"]["base"]["state"] == "available" for r in results)
    assert results[0]["models"]["candidate"]["state"] == "unavailable"
    assert results[0]["models"]["candidate"]["reason"] == "CONTENT_PREDICTION_INVALID"
    assert "cells" not in results[0]["models"]["candidate"]
    assert all(r["models"]["candidate"]["state"] == "available" for r in results[1:])
    assert all(len(r["models"]["candidate"]["cells"]) == 15 for r in results[1:])
    spec = importlib.util.spec_from_file_location("comparison_renderer_nine", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.render(root)
    cards = json.loads((root / "comparison-data.json").read_bytes())
    assert len(cards) == 9 and sum(c["paired"] for c in cards) == 8
    assert all(c["productionCells"]["models"]["base"]["state"] == "available" for c in cards)
    # Rehashing a false saved failure is still rejected by strict replay, not localized away.
    recorded["models"]["candidate"]["crops"][0]["reason"] = "FABRICATED_FAILURE"
    entry = index["entries"][0]
    entry["detail"].update(write(root, entry["detail"]["path"], document))
    write(root, "production-cells/index.json", index)
    rejected = ComparisonProductionCells(root, evaluation).for_board(source, boards[0], inference)
    assert rejected["state"] == "unavailable"
    assert "T3_REPLAY_CHANGED" in rejected["reason"]


@pytest.mark.parametrize("suffix", ["0/base/0.png", "source.png", "0/candidate-input.png"])
def test_foreign_differing_png_is_preserved_and_fails_closed(files, suffix):
    root, source, board, inference, evaluation, _, _ = files
    path = root / "production-cell-images" / source["id"] / suffix
    path.parent.mkdir(parents=True, exist_ok=True)
    foreign = b"foreign content: must not overwrite"
    path.write_bytes(foreign)
    result = ComparisonProductionCells(root, evaluation).for_board(source, board, inference)
    assert result["state"] == "unavailable"
    assert result["reason"] == "CONTENT_COMPARISON_OUTPUT_CONFLICT"
    assert path.read_bytes() == foreign


def test_foreign_differing_index_is_preserved_and_fails_closed(files):
    root, source, _, _, evaluation, _, _ = files
    output = root / "foreign-index"
    path = output / "production-cells/index.json"
    path.parent.mkdir(parents=True)
    foreign = b'{"foreign":"must remain"}'
    path.write_bytes(foreign)
    with pytest.raises(ValueError, match="^CONTENT_COMPARISON_OUTPUT_CONFLICT$"):
        build_production_package(output, root, evaluation, {source["id"]})
    assert path.read_bytes() == foreign


def test_identical_png_and_index_replays_do_not_rewrite_existing_files(files):
    root, source, board, inference, evaluation, _, _ = files
    output = root / "idempotent"
    assert build_production_package(output, root, evaluation, {source["id"]}) == {}
    assert (
        ComparisonProductionCells(output, evaluation).for_board(source, board, inference)["state"]
        == "available"
    )
    files = [
        *output.glob("production-cell-images/**/*.png"),
        output / "production-cells/index.json",
    ]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    assert len(files) == 34  # 30 final cells + 2 NN rasters + source + index.
    assert build_production_package(output, root, evaluation, {source["id"]}) == {}
    assert (
        ComparisonProductionCells(output, evaluation).for_board(source, board, inference)["state"]
        == "available"
    )
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == state for p, state in before.items())


def test_nine_detections_without_t3_proof_never_fall_back_to_index(files):
    root, _, _, inference, evaluation, _, _ = files
    (root / "production-cells/index.json").unlink()
    for name in ("base", "candidate"):
        inference[name]["detections"] *= 9
        source_id = json.loads((root / "inputs.json").read_bytes())["photos"][0]["id"]
        write(root, f"{name}/{source_id}.json", inference[name])
    spec = importlib.util.spec_from_file_location("comparison_renderer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.render(root)
    cards = json.loads((root / "comparison-data.json").read_bytes())
    assert not cards[0]["paired"]
    assert cards[0]["base"] is None and cards[0]["candidate"] is None
    assert len(cards[0]["candidateAll"]) == 9
    assert cards[0]["productionCells"]["state"] == "unavailable"


@pytest.mark.parametrize("failure", ["tie", "missing"])
def test_real_t3_tie_or_missing_match_never_maps_the_candidate(files, failure):
    root, source, board, inference, evaluation, index, document = files
    manifest = index["entries"][0]["manifest"]
    snapshot = GridCohortSnapshot(root, manifest["path"], manifest["sha256"])
    frozen, labels = next(
        (s, labels)
        for s, labels in GridBoardDataset(snapshot, "VALIDATION").indexed()
        if s["sourceId"] == source["id"]
    )
    frame = snapshot.frame(frozen, "VALIDATION")
    nodes = labels[0][0]
    engine = Engine(nodes)
    observed = {}
    row = document["photos"][0]
    photo = CorrectionControlPhoto(
        source["id"],
        row["groupId"],
        source["checksum_sha256"],
        (nodes,),
        lambda: frame.rgb,
        full_geometry=False,
    )
    for name in ("base", "candidate"):
        detections = engine.analyse(frame.rgb)
        if name == "candidate":
            detections = detections * 2 if failure == "tie" else []
        measured = evaluate_photo(
            photo.source_id, photo.group_id, [nodes], predictions(detections), full_geometry=False
        )
        row[name] = measured.as_dict()
        observed[name] = detections, measured, engine
        inference[name]["detections"] = [{"nodes": d.nodes.tolist()} for d in detections]
    row["contentEvaluation"] = ProductionContentRun(snapshot).observer("VALIDATION")(
        photo, frame.rgb, observed
    )
    entry = index["entries"][0]
    entry["detail"].update(write(root, entry["detail"]["path"], document))
    write(root, "production-cells/index.json", index)
    result = ComparisonProductionCells(root, evaluation).for_board(source, board, inference)
    assert result["state"] == "available", result
    assert result["models"]["base"]["state"] == "available"
    assert result["models"]["candidate"]["state"] == "unavailable"
    assert "cells" not in result["models"]["candidate"]


def test_bundle_preserves_conflicting_existing_files_and_missing_artifact_is_explicit(files):
    root, source, _, _, evaluation, index, _ = files
    output = root / "conflicting-report"
    pin = index["entries"][0]["manifest"]
    conflict = long_path_aware(output / pin["path"])
    conflict.parent.mkdir(parents=True)
    conflict.write_bytes(b"must not overwrite a foreign artifact")
    errors = build_production_package(output, root, evaluation, {source["id"]})
    assert "CONFLICT" in errors[source["id"]]
    assert conflict.read_bytes() == b"must not overwrite a foreign artifact"
    assert json.loads((output / "production-cells/index.json").read_bytes())["entries"] == []


def test_missing_unrelated_game_artifacts_do_not_hide_a_verified_source(files):
    root, source, _, _, evaluation, _, _ = files
    evaluation["report"]["cohorts"].append(
        {"gameId": str(uuid4()), "cohortId": str(uuid4()), "manifestSha256": "f" * 64}
    )
    output = root / "multi-game-report"
    errors = build_production_package(output, root, evaluation, {source["id"]})
    assert errors == {}
    entries = json.loads((output / "production-cells/index.json").read_bytes())["entries"]
    assert len(entries) == 1 and entries[0]["sourceId"] == source["id"]


def test_v1_v2_diagnostics_take_precedence_over_available_t3(files, monkeypatch):
    root, _, _, _, _, _, _ = files
    spec = importlib.util.spec_from_file_location("comparison_renderer_priority", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archived = {"state": "available", "image": "archived.png", "schemaVersion": "v2"}
    monkeypatch.setattr(
        module, "diagnostic_inputs", lambda *_a: {"base": archived, "candidate": archived}
    )
    module.render(root)
    cards = json.loads((root / "comparison-data.json").read_bytes())
    assert cards[0]["diagnostics"]["base"] == archived
    assert cards[0]["diagnostics"]["candidate"] == archived
