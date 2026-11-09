"""Bounded real-renderer/CPU diagnostic tests, never operator quality evidence."""

import hashlib
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_api.storage.production_crop_capture import role_reason
from game_predictor_worker.images.production_cell_evaluation import render_cells
from game_predictor_worker.images.production_crop_artifacts import sealed
from game_predictor_worker.images.production_crop_classification import (
    PinnedClassifier,
    acceptance_policy,
    current_runtime_pin,
    human_class,
)
from game_predictor_worker.images.production_crop_comparison import paired_gate, run_comparison
from game_predictor_worker.images.symbol_onnx import (
    ONNX_INPUT_NAME,
    ONNX_OPSET_VERSION,
    ONNX_OUTPUT_NAME,
)
from onnx import TensorProto, helper, numpy_helper
from test_production_cell_observations import fixture


def model(tmp_path, *, lab=False):
    from game_predictor_api.domain.symbol_model_snapshots import LAB_RGB_SYMBOL_MODEL_VERSION

    graph = helper.make_graph(
        [
            helper.make_node("GlobalAveragePool", [ONNX_INPUT_NAME], ["average"]),
            helper.make_node("Flatten", ["average"], ["flat"], axis=1),
            helper.make_node("MatMul", ["flat", "weights"], ["zero"]),
            helper.make_node("Add", ["zero", "bias"], [ONNX_OUTPUT_NAME]),
        ],
        "bounded-cpu-test",
        [helper.make_tensor_value_info(ONNX_INPUT_NAME, TensorProto.FLOAT, ["batch", 3, 64, 64])],
        [helper.make_tensor_value_info(ONNX_OUTPUT_NAME, TensorProto.FLOAT, ["batch", 3])],
        [
            numpy_helper.from_array(np.zeros((3, 3), np.float32), "weights"),
            numpy_helper.from_array(np.asarray([3, 1, 0], np.float32), "bias"),
        ],
    )
    artifact = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 17 if lab else ONNX_OPSET_VERSION)],
        ir_version=10,
    )
    raw = artifact.SerializeToString()
    path = "lab.onnx" if lab else "model.onnx"
    (tmp_path / path).write_bytes(raw)
    return SymbolModelJobSnapshot(
        iteration_id=None,
        model_version=LAB_RGB_SYMBOL_MODEL_VERSION if lab else "bootstrap-symbol-cnn-onnx-v1",
        manifest_checksum_sha256="a" * 64,
        onnx_checksum_sha256=hashlib.sha256(raw).hexdigest(),
        onnx_relative_path=path,
        storage_root=SymbolModelStorageRoot.REPOSITORY,
        class_codes=("a", "b", "c"),
        input_size=64,
        crop_size=96 if lab else None,
        temperature=1.0,
    )


def setup(tmp_path, *, role="TRAIN", state="visible"):
    from game_predictor_api.domain.grid_training_cohorts import digest

    frame, source, target, nodes, context = fixture(content_inset=1, inset=0.08, state=state)
    pinned = model(tmp_path)
    context["classifier"] = pinned.to_payload()
    pin = target["productionContentReference"]
    pin["sourceContextSha256"] = digest(context)
    pin["sha256"] = digest({k: v for k, v in pin.items() if k != "sha256"})
    target["nodes"] = [{"x": float(x), "y": float(y)} for x, y in nodes]
    class_rasters = render_cells(frame, nodes, target, context)
    target["classes"] = [
        {
            "state": "available",
            "code": "a",
            "event": {"id": str(j)},
            "renderedPixelSha256": class_rasters[j]["renderedPixelSha256"],
        }
        for j in range(15)
    ]
    target["classificationPolicy"] = {
        "runtime": current_runtime_pin(pinned),
        "runtimeAutoAccept": False,
        "report": {
            "schemaVersion": 1,
            "calibrationVersion": "symbol-temperature-calibration-v2-safe-floor-v1",
            "classes": ["a", "b", "c"],
            "temperature": 1.0,
            "inputs": {
                "onnxArtifactSha256": pinned.onnx_checksum_sha256,
                "modelVersion": pinned.model_version,
            },
            "policy": {
                "policyVersion": "symbol-confidence-policy-v1",
                "autoAccept": {"enabled": True, "threshold": 0.8},
            },
        },
    }
    source.update(role="VALIDATION" if role == "A" else "TRAIN", used=True)
    game = str(UUID(int=6))
    snapshot = SimpleNamespace(
        manifest={"gameId": game}, manifest_sha256="b" * 64, frame=lambda *_a, **_k: frame
    )
    capture = sealed(
        {
            "schemaVersion": "production-crop-capture-v1",
            "gameId": game,
            "manifestSha256": snapshot.manifest_sha256,
            "gridModel": None,
            "labModel": None,
            "measurement": {"games": {game: {"u": 0.0}}},
            "photos": [
                {
                    "sourceId": source["sourceId"],
                    "role": role,
                    "state": "available",
                    "reasonCodes": [],
                    "frozenSource": source,
                    "targets": [target],
                    "instanceCount": 15,
                }
            ],
        }
    )
    engine = SimpleNamespace(
        analyse=lambda _rgb: [SimpleNamespace(nodes=nodes, screen_quad=nodes[[0, 5, 23, 18]])]
    )
    return snapshot, capture, engine, frame, target, nodes, context


def test_real_renderer_cpu_classification_and_exact_replay(tmp_path):
    snapshot, capture, engine, *_ = setup(tmp_path)
    report = run_comparison(
        snapshot,
        capture,
        root=tmp_path / "out",
        repository_root=tmp_path,
        artifact_root=tmp_path,
        engine=engine,
    )
    assert report["state"] == "candidate"
    human = report["photos"][0]["geometry"]["human"]
    assert human["summary"]["base"]["clipped"] > human["summary"]["candidate"]["clipped"]
    assert len(human["rasters"]) == 30
    assert all(c["baseCorrect"] and c["candidateCorrect"] for c in human["classification"])
    engine.analyse = lambda _rgb: pytest.fail("Replay must not rerun inference")
    assert (
        run_comparison(
            snapshot,
            capture,
            root=tmp_path / "out",
            repository_root=tmp_path,
            artifact_root=tmp_path,
            engine=engine,
        )
        == report
    )
    raster = tmp_path / "out" / human["rasters"][0]["path"]
    raster.write_bytes(b"changed")
    with pytest.raises(ValueError, match="CROP_RASTER_CHANGED"):
        run_comparison(
            snapshot,
            capture,
            root=tmp_path / "out",
            repository_root=tmp_path,
            artifact_root=tmp_path,
            engine=engine,
        )


def test_missing_gt_keeps_denominator_and_actual_diagnostic_rasters(tmp_path):
    snapshot, capture, engine, *_ = setup(tmp_path, state="unknown")
    report = run_comparison(
        snapshot,
        capture,
        root=tmp_path / "out",
        repository_root=tmp_path,
        artifact_root=tmp_path,
        engine=engine,
    )
    assert report["state"] == "not_evaluable"
    assert report["games"][0]["selectedInstances"] == 15
    assert report["games"][0]["summary"]["unknown"] == 15
    assert len(report["photos"][0]["geometry"]["human"]["rasters"]) == 30


def test_a_never_exports_png_or_render_hints(tmp_path):
    snapshot, capture, engine, *_ = setup(tmp_path, role="A")
    report = run_comparison(
        snapshot,
        capture,
        root=tmp_path / "out",
        repository_root=tmp_path,
        artifact_root=tmp_path,
        engine=engine,
    )
    assert not list((tmp_path / "out").rglob("*.png"))
    assert all("path" not in r for r in report["photos"][0]["geometry"]["human"]["rasters"])


def test_irregular_internal_nodes_preserve_existing_margin_semantics(tmp_path):
    _, _, _, frame, target, nodes, context = setup(tmp_path)
    irregular = nodes.copy()
    irregular[7] += [2, 1]
    zero = {
        **context,
        "renderConfiguration": {**context["renderConfiguration"], "paddingFraction": 0.0},
    }
    original = render_cells(frame, nodes, target, context)
    changed = render_cells(frame, irregular, target, context)
    full = render_cells(frame, irregular, target, zero)
    assert original[0]["float32Footprint"] == changed[0]["float32Footprint"]
    assert full[0]["float32Footprint"][2] == irregular[7].tolist()
    assert full[0]["float32Footprint"] != changed[0]["float32Footprint"]


def test_improved_crops_cannot_compensate_class_error_or_missing_policy(tmp_path):
    snapshot, captured, engine, *_ = setup(tmp_path)
    report = run_comparison(
        snapshot,
        captured,
        root=tmp_path / "out",
        repository_root=tmp_path,
        artifact_root=tmp_path,
        engine=engine,
    )
    row = report["photos"][0]["geometry"]["human"]
    classes = deepcopy(row["classification"])
    classes[0]["candidateCorrect"] = False
    assert paired_gate(row["summary"], classes)["state"] == "regression"
    classes = deepcopy(row["classification"])
    classes[0]["acceptanceState"] = "unavailable"
    gate = paired_gate(row["summary"], classes)
    assert gate["state"] == "not_evaluable" and gate["newFalseAccepts"] is None
    classes = deepcopy(row["classification"])
    classes[0].update(baseFalseAccept=False, candidateFalseAccept=True)
    assert paired_gate(row["summary"], classes)["state"] == "regression"


def test_lab_uses_separate_real_weights_and_rgb96_transform(tmp_path):
    pinned = model(tmp_path, lab=True)
    classifier = PinnedClassifier(
        pinned.to_payload(), repository_root=tmp_path, artifact_root=tmp_path
    )
    assert (
        classifier.predict([SimpleNamespace(rgb=np.zeros((96, 96, 3), np.uint8))])[0]["code"] == "a"
    )
    with pytest.raises(ValueError, match="RGB|SYMBOL|LAB"):
        classifier.predict([SimpleNamespace(rgb=np.zeros((64, 64, 3), np.uint8))])
    assert acceptance_policy(pinned, None)["state"] == "unavailable"
    snapshot, captured, engine, *_ = setup(tmp_path)
    captured["labModel"] = pinned.to_payload()
    captured = sealed({k: v for k, v in captured.items() if k != "sha256"})
    report = run_comparison(
        snapshot,
        captured,
        root=tmp_path / "out",
        repository_root=tmp_path,
        artifact_root=tmp_path,
        engine=engine,
    )
    lab = report["photos"][0]["geometry"]["human"]["labRgb"]
    assert lab["comparisonKind"] == "lab-rgb-reference"
    assert lab["configurations"]["base"]["outputWidth"] == 96
    assert lab["classifier"]["modelVersion"] == pinned.model_version
    assert len(lab["rasters"]) == 30
    assert "gate" not in lab and lab["reference"]["purpose"] == "absolute-reference"
    assert all(g["reference"]["purpose"] == "absolute-reference" for g in report["labGames"])
    assert all(g["evaluatedInstances"] == 15 for g in report["labGames"])


def test_blind_protection_joins_current_alias_components_without_images(monkeypatch):
    from game_predictor_api.storage import production_crop_capture as module

    own, other = str(UUID(int=21)), str(UUID(int=22))
    rows = [{"source_id": other, "phase": "pass1"}]
    repo = SimpleNamespace(
        session=SimpleNamespace(execute=lambda *_a: SimpleNamespace(mappings=lambda: rows))
    )
    monkeypatch.setattr(
        module,
        "contexts",
        lambda *_a, **_k: {other: {"proofSha256": "a" * 64, "aliasComponentIds": ["shared"]}},
    )
    assert module._blind_aliases(repo, UUID(int=6), {own: {"aliasComponentIds": ["shared"]}}) == {
        own: ["pass1"]
    }


@pytest.mark.parametrize("change", ["buffer", "role", "alias"])
def test_role_closure_fail_closed(change):
    source = {"sourceId": "s", "role": "TRAIN", "used": True}
    closure = {
        "sourceId": "s",
        "proofSha256": "a" * 64,
        "allowedRoles": ["TRAIN"],
        "priorRoles": ["TRAIN"],
        "aliasComponentIds": [],
    }
    split = {}
    if change == "buffer":
        split["buffer"] = True
    if change == "role":
        closure["priorRoles"] = ["REGRESSION"]
    if change == "alias":
        closure["validationPurposes"] = ["B"]
    assert role_reason(source, closure, split) is not None


def human_cell_fixture():
    cell = {
        "id": "c",
        "assigned_symbol_id": "a",
        "review_state": "approved",
        "quality_issue": None,
        "source_available": True,
        "source_visibility": "full",
        "geometry_revision": 1,
        "sequence_number": 7,
        "asset_mode": "virtual_source",
        "revision": 2,
        "crop_sample_id": "c",
        "crop_checksum_sha256": "x",
        "source_geometry_revision_id": "r",
        "render_spec_checksum_sha256": "s",
        "rendered_pixel_checksum_sha256": "p",
    }
    for key in (
        "crop_sample_id",
        "crop_checksum_sha256",
        "geometry_revision",
        "asset_mode",
        "source_geometry_revision_id",
        "render_spec_checksum_sha256",
        "rendered_pixel_checksum_sha256",
    ):
        cell["approved_" + key] = cell[key]
    board = {
        k: cell[k] for k in ("geometry_revision", "source_geometry_revision_id", "sequence_number")
    }
    event = {
        **cell,
        "cell_review_id": "c",
        "cell_revision": 2,
        "action": "approve",
        "actor": "local-admin",
    }
    return cell, board, event


def test_human_gt_requires_exact_current_event_not_status_or_actor():
    cell, board, event = human_cell_fixture()
    assert human_class(cell, [], board, {"a": "J"})["state"] == "unavailable"
    assert human_class(cell, [event], board, {"a": "J"})["code"] == "J"
    event["rendered_pixel_checksum_sha256"] = "different"
    assert human_class(cell, [event], board, {"a": "J"})["state"] == "unavailable"


@pytest.mark.parametrize("reason", ["blind", "alias", "source", "blank-a"])
def test_capture_protects_before_geometry_or_pixels(tmp_path, monkeypatch, reason):
    from game_predictor_api.domain.grid_cell_content import content_source_identity
    from game_predictor_api.storage import production_crop_capture as capture_module

    _, source, _, _, _ = fixture()
    source["sourceIdentity"]["id"] = source["sourceId"]
    source.update(used=True, role="TRAIN")
    if reason == "blank-a":
        source.update(role="VALIDATION", validationPurpose="A")
    snapshot = SimpleNamespace(
        sources=lambda: [source],
        manifest={"photoSplit": {"sources": [source]}},
        frame=lambda *_a, **_k: pytest.fail("Protected pixels must not be read"),
    )
    identity = content_source_identity(source["sourceIdentity"])
    repo = SimpleNamespace(
        bind=lambda *_a: None,
        snapshot=lambda *_a: snapshot,
        current_source=lambda *_a: None if reason == "source" else identity,
    )
    monkeypatch.setattr(capture_module, "SqlAlchemyGridCellContentRepository", lambda *_a: repo)
    monkeypatch.setattr(capture_module, "contexts", lambda *_a, **_k: {source["sourceId"]: {}})
    monkeypatch.setattr(capture_module, "_blind_aliases", lambda *_a: {source["sourceId"]: []})
    monkeypatch.setattr(
        capture_module,
        "role_reason",
        lambda *_a: "CROP_VALIDATION_ALIAS_PROTECTED" if reason == "alias" else None,
    )
    monkeypatch.setattr(capture_module, "protected_source", lambda *_a: reason == "blind")
    monkeypatch.setattr(capture_module, "_measurement", lambda *_a: None)
    monkeypatch.setattr(capture_module, "content_pin", lambda *_a, **_k: None)
    monkeypatch.setattr(
        capture_module,
        "GridCohortEvidenceReader",
        lambda *_a: SimpleNamespace(
            capture=lambda *_a: pytest.fail("Protected geometry must not be read")
        ),
    )
    session = SimpleNamespace(scalar=lambda query: "on" if str(query).startswith("SHOW") else None)
    _, captured = capture_module.capture(
        session,
        artifact_root=tmp_path,
        repository_root=tmp_path,
        game=UUID(int=6),
        cohort=UUID(int=7),
        manifest_sha256="b" * 64,
        source_ids=[UUID(source["sourceId"])],
    )
    photo = captured["photos"][0]
    assert photo["state"] == "unavailable" and photo["frozenSource"] is None
    assert photo["targets"] == [] and photo["instanceCount"] == 15


def test_changed_approved_pixels_never_become_class_gt(tmp_path):
    snapshot, captured, engine, *_ = setup(tmp_path)
    captured["photos"][0]["targets"][0]["classes"][0]["renderedPixelSha256"] = "0" * 64
    captured = sealed({k: v for k, v in captured.items() if k != "sha256"})
    report = run_comparison(
        snapshot,
        captured,
        root=tmp_path / "out",
        repository_root=tmp_path,
        artifact_root=tmp_path,
        engine=engine,
    )
    assert report["state"] == "not_evaluable"
    for kind in ("human", "model"):
        first = report["photos"][0]["geometry"][kind]["classification"][0]
        assert first["state"] == "unavailable"
        assert first["reason"] == "CLASS_APPROVED_RASTER_CHANGED"


def test_current_frozen_a_ref_selects_measurement_despite_old_blank_session(tmp_path, monkeypatch):
    from game_predictor_api.domain.grid_cell_content import content_source_identity
    from game_predictor_api.storage import production_crop_capture as module

    snapshot, captured, _, _, target, _, _ = setup(tmp_path, role="A")
    source = captured["photos"][0]["frozenSource"]
    source["sourceIdentity"]["id"] = source["sourceId"]
    source["validationPurpose"] = "A"
    snapshot.sources = lambda: [source]
    snapshot.manifest["photoSplit"] = {"sources": [source]}
    frozen_session = str(UUID(int=14))
    target["contentAnnotation"]["sessionId"] = frozen_session
    pin = {
        k: target[k]
        for k in ("contentAnnotation", "contentReferenceSha256", "contentReferenceRevision")
    }
    session = SimpleNamespace(scalar=lambda query: "on")
    repo = SimpleNamespace(
        session=session,
        bind=lambda *_a: None,
        snapshot=lambda *_a: snapshot,
        current_source=lambda *_a: content_source_identity(source["sourceIdentity"]),
    )
    monkeypatch.setattr(module, "SqlAlchemyGridCellContentRepository", lambda *_a: repo)
    monkeypatch.setattr(module, "contexts", lambda *_a, **_k: {source["sourceId"]: {}})
    monkeypatch.setattr(
        module, "_blind_aliases", lambda *_a: {source["sourceId"]: ["pass1", "frozen"]}
    )
    monkeypatch.setattr(module, "role_reason", lambda *_a: None)
    measurement = {"sha256": "f" * 64, "games": {str(UUID(int=6)): {"u": 0.0, "delta": 0.0}}}
    seen = []

    def measured(_session, _game, ids=None):
        seen.append(ids)
        return measurement if ids == {frozen_session} else None

    monkeypatch.setattr(module, "_measurement", measured)
    monkeypatch.setattr(module, "content_pin", lambda *_a, **_k: pin)
    monkeypatch.setattr(
        module,
        "GridCohortEvidenceReader",
        lambda *_a: SimpleNamespace(
            capture=lambda *_a: {
                "source": source["sourceIdentity"],
                "positions": [{"positionIndex": 0, "label": target, "reason": None}],
            }
        ),
    )
    monkeypatch.setattr(module, "current_targets", lambda *_a: {0: {"board": {}}})
    monkeypatch.setattr(module, "_classes", lambda *_a: target["classes"])
    monkeypatch.setattr(module, "_policy", lambda *_a: None)
    monkeypatch.setattr(module, "apply_blind_a_geometry", lambda value: value)
    monkeypatch.setattr(
        module, "capture_production_reference", lambda *_a: target["productionContentReference"]
    )
    _, result = module.capture(
        session,
        artifact_root=tmp_path,
        repository_root=tmp_path,
        game=UUID(int=6),
        cohort=UUID(int=7),
        manifest_sha256="b" * 64,
        source_ids=[UUID(source["sourceId"])],
    )
    assert result["photos"][0]["state"] == "available"
    assert result["photos"][0]["measurement"] == measurement
    assert seen == [None, {frozen_session}]


@pytest.mark.parametrize("wide", [False, True])
@pytest.mark.parametrize("screen_drift", [False, True])
def test_actual_nn_input_witness_without_content_gt(tmp_path, monkeypatch, wide, screen_drift):
    from game_predictor_worker.geometry_core.preprocessing import board_rectifier, crop_board
    from game_predictor_worker.geometry_core.rescue import GridRescueVariantV2
    from game_predictor_worker.geometry_core.settings import ScreenPreset
    from game_predictor_worker.images import production_crop_inputs as inputs
    from test_production_cell_observations import board_preset

    frame, source, _, nodes, _ = fixture(state="unknown")
    screen = ScreenPreset(
        heat_sigma_fraction=0.1,
        min_heat_sigma=1,
        offset_scale=1,
        positive_radius=0.1,
        offset_loss_weight=1,
        decode_threshold=0.5,
        nms_iou=0.5,
        top_k=9,
    )
    core = SimpleNamespace(
        settings=SimpleNamespace(board=board_preset(), screen=screen),
        board_runner=lambda batch: None,
        screen_runner=lambda batch: None,
    )
    detection = SimpleNamespace(nodes=nodes, raw_nodes=nodes, screen_quad=nodes[[0, 5, 23, 18]])
    variant = GridRescueVariantV2() if wide else None
    geometry = variant.board if wide else None

    def analyse(rgb):
        screen_pixels, _, _ = inputs.screen_input(rgb, core.settings.screen)
        if screen_drift and not wide:
            screen_pixels = np.zeros_like(screen_pixels)
        core.screen_runner(screen_pixels.transpose(2, 0, 1)[None].astype(np.float32))
        if wide:
            screen_pixels, _, _ = inputs.screen_input(
                rgb, core.settings.screen, geometry=variant.screen
            )
            if screen_drift:
                screen_pixels = np.zeros_like(screen_pixels)
            core.screen_runner(screen_pixels.transpose(2, 0, 1)[None].astype(np.float32))
        matrix = board_rectifier(detection.screen_quad, core.settings.board, geometry=geometry)
        rgb_input = crop_board(rgb, matrix, core.settings.board, geometry=geometry)
        core.board_runner(rgb_input.transpose(2, 0, 1)[None].astype(np.float32))
        return [detection]

    core.analyse = analyse
    engine = (
        SimpleNamespace(
            engine=core,
            analyse=analyse,
            variant=variant,
            path="combined",
            routing={},
            last_baseline=[object()],
            last_result=SimpleNamespace(crop_calls={0}, redetect_calls=1),
        )
        if wide
        else core
    )
    monkeypatch.setattr(inputs, "slots", lambda _found: {0: 0})
    before = core.board_runner
    found, proof = inputs.analyse_with_inputs(
        engine,
        frame,
        {"sourceId": source["sourceId"], "role": "TRAIN"},
        {"versionId": "pinned-test-version"},
        tmp_path,
    )
    assert found == [detection] and proof["state"] == ("partial" if screen_drift else "available")
    if screen_drift:
        assert proof["reason"] == "CROP_ACTUAL_SCREEN_INPUT_NOT_BOUND"
    assert core.board_runner is before
    entry = next(e for e in proof["entries"] if e["stage"] == "board")
    assert entry["geometry"] == (variant.board.model_dump(mode="json") if wide else None)
    assert entry["observedSampleTensorSha256"] == entry["input"]["tensor_sha256"]
    assert (tmp_path / entry["path"]).exists()
    assert proof["contentReferenceRequired"] is False


def test_concurrent_artifact_writers_never_replace_existing_pin(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from game_predictor_worker.images import production_crop_artifacts as artifacts

    operation = "rename" if artifacts.os.name == "nt" else "link"
    barrier, link = Barrier(2), getattr(artifacts.os, operation)

    def publish(source, target):
        barrier.wait(timeout=5)
        return link(source, target)

    monkeypatch.setattr(artifacts.os, operation, publish)

    def write(raw):
        try:
            artifacts.write_bytes(tmp_path, "capture.json", raw)
            return "written"
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [b"one", b"two"]))
    assert sorted(results) == ["CROP_COMPARISON_REPLAY_CONFLICT", "written"]
    assert (tmp_path / "capture.json").read_bytes() in (b"one", b"two")
    assert list(tmp_path.glob("*.pending")) == []


def test_calibration_needs_runtime_pin_and_exact_model_scope(tmp_path):
    _, captured, _, *_ = setup(tmp_path)
    target = captured["photos"][0]["targets"][0]
    pinned = SymbolModelJobSnapshot.from_payload(
        target["productionContentReference"]["sourceContext"]["classifier"]
    )
    evidence = deepcopy(target["classificationPolicy"])
    assert acceptance_policy(pinned, evidence)["state"] == "disabled"
    evidence.pop("runtimeAutoAccept")
    assert acceptance_policy(pinned, evidence)["state"] == "unavailable"
    evidence["runtimeAutoAccept"] = False
    assert acceptance_policy(pinned, evidence)["state"] == "disabled"
    disabled_classes = [
        {
            "state": "available",
            "acceptanceState": "disabled",
            "baseCorrect": True,
            "candidateCorrect": True,
            "baseFalseAccept": False,
            "candidateFalseAccept": False,
        }
    ]
    summary = {
        "reasonCodes": [],
        "visible": 1,
        "unknown": 0,
        "slots": 1,
        "base": {"clipped": 1},
        "candidate": {"clipped": 0},
        **{
            k: 0
            for k in (
                "degradedInstances",
                "newWrongCells",
                "newTies",
                "newForeignSymbols",
                "newMatchAmbiguities",
            )
        },
    }
    gate = paired_gate(summary, disabled_classes)
    assert gate["automaticAcceptance"] == "disabled"
    assert gate["newFalseAccepts"] == 0 and gate["state"] == "candidate"
    evidence["runtimeAutoAccept"] = True
    evidence["report"]["inputs"]["modelVersion"] = "lab-rgb-symbol-onnx-v1"
    assert acceptance_policy(pinned, evidence)["state"] == "unavailable"


def test_classes_use_current_review_owner_not_old_same_board_cell(monkeypatch):
    from game_predictor_api.storage import production_crop_capture as module
    from game_predictor_worker.images import production_crop_classification as classification

    target = {
        "board": {"id": "board", "source_image_id": "source"},
        "review": {"id": "current", "status": "accepted"},
        "owner": {
            "recognized_board_id": "board",
            "source_image_id": "source",
            "review_item_id": "current",
        },
    }
    rows = [
        {
            "cell": {"cell_index": 0, "review_item_id": "current", "assigned_symbol_id": "j"},
            "code": "J",
        },
        {
            "cell": {"cell_index": 0, "review_item_id": "old", "assigned_symbol_id": "ten"},
            "code": "10",
        },
    ]
    queries = []

    def execute(query, parameters):
        queries.append(str(query))
        assert parameters["r"] == "current"
        assert "c.review_item_id=CAST(:r AS uuid)" in str(query)
        return SimpleNamespace(mappings=lambda: rows, scalars=lambda: [])

    monkeypatch.setattr(
        classification,
        "human_class",
        lambda cell, _events, _board, codes: {
            "state": "available",
            "code": codes[cell["assigned_symbol_id"]],
        },
    )
    result = module._classes(SimpleNamespace(execute=execute), UUID(int=6), target)
    assert result[0] == {"state": "available", "code": "J"}
    assert "source_replacement_current_v1" in queries[0]
    target["owner"]["review_item_id"] = "foreign"
    assert all(
        c["reason"] == "CLASS_CURRENT_OWNER_UNAVAILABLE"
        for c in module._classes(SimpleNamespace(), UUID(int=6), target)
    )


def ready_gate_summary():
    return {
        "reasonCodes": [],
        "visible": 15,
        "unknown": 0,
        "slots": 15,
        "base": {"clipped": 2, "missing": 0},
        "candidate": {"clipped": 1, "missing": 0},
        **{
            key: 0
            for key in (
                "degradedInstances",
                "newWrongCells",
                "newTies",
                "newForeignSymbols",
                "newMatchAmbiguities",
            )
        },
    }


@pytest.mark.parametrize(
    "counter",
    ["degradedInstances", "newWrongCells", "newTies", "newForeignSymbols", "newMatchAmbiguities"],
)
def test_each_content_damage_blocks_even_fewer_clipped(counter):
    summary = ready_gate_summary()
    classes = [{"state": "available", "acceptanceState": "disabled"}]
    assert paired_gate(summary, classes)["state"] == "candidate"
    summary[counter] = 1
    gate = paired_gate(summary, classes)
    assert gate["fewerClipped"] and gate["state"] == "regression"


def test_clipped_to_missing_is_never_an_improvement():
    summary = ready_gate_summary()
    summary["candidate"]["missing"] = 1
    gate = paired_gate(summary, [{"state": "available", "acceptanceState": "disabled"}])
    assert not gate["fewerClipped"] and gate["newMissing"] == 1
    assert gate["state"] == "regression"


def test_actual_zero_margin_takes_neighbor_despite_fewer_clips(tmp_path):
    from game_predictor_api.domain.grid_cell_content import ContentRevision

    snapshot, captured, engine, _, target, *_ = setup(tmp_path)
    # Physical cell0 ends at x30. The neighbor's true glyph is in its final
    # strip, outside the 8% crop but fully contained by the zero-margin crop.
    target["contentAnnotation"]["reference"]["cells"][1]["quad"] = [
        [28.8, 15],
        [29.8, 15],
        [29.8, 25],
        [28.8, 25],
    ]
    target["contentReferenceSha256"] = ContentRevision.model_validate(
        target["contentAnnotation"]
    ).sha256
    captured = sealed({k: v for k, v in captured.items() if k != "sha256"})
    report = run_comparison(
        snapshot,
        captured,
        root=tmp_path / "neighbor",
        repository_root=tmp_path,
        artifact_root=tmp_path,
        engine=engine,
    )
    row = report["photos"][0]["geometry"]["human"]
    assert row["summary"]["candidate"]["clipped"] < row["summary"]["base"]["clipped"]
    assert row["summary"]["newForeignSymbols"] > 0
    assert row["gate"]["state"] == report["state"] == "regression"


@pytest.mark.parametrize("mutation", [None, "system", "reopened", "old", "unverified-actor"])
def test_board_synchronized_requires_current_verified_human_decision(mutation):
    cell, board, event = human_cell_fixture()
    cell["assignment_source"] = "board_decision"
    event.update(action="board_synchronized", human_board_decision=True)
    if mutation == "system":
        event["actor"] = "system:write-through"
    elif mutation == "reopened":
        cell["review_state"] = "pending"
    elif mutation == "old":
        event["cell_revision"] -= 1
    elif mutation == "unverified-actor":
        event["human_board_decision"] = False
    result = human_class(cell, [event], board, {"a": "J"})
    assert result["state"] == ("available" if mutation is None else "unavailable")


def test_real_legacy_calibration_producer_and_current_runtime():
    from pathlib import Path

    from game_predictor_api.domain.symbol_model_snapshots import bootstrap_symbol_model_snapshot
    from game_predictor_api.storage.production_crop_capture import _policy

    root = Path(__file__).resolve().parents[3]
    pinned = bootstrap_symbol_model_snapshot()
    evidence = _policy(None, pinned.to_payload(), root / "artifacts", root)
    assert evidence["report"]["calibrationVersion"] == "symbol-temperature-calibration-v1"
    assert evidence["runtime"]["scope"] == "current-diagnostic-runtime"
    assert acceptance_policy(pinned, evidence)["state"] == "disabled"
    wrong_model = deepcopy(evidence)
    wrong_model["report"]["inputs"]["modelVersion"] = "other-model"
    assert acceptance_policy(pinned, wrong_model)["state"] == "unavailable"
    missing_runtime = {k: v for k, v in evidence.items() if k != "runtime"}
    assert acceptance_policy(pinned, missing_runtime)["state"] == "unavailable"


def test_missing_recovery_cannot_compensate_new_missing_instance():
    from game_predictor_worker.images.production_crop_comparison import comparison_summary

    def cell(base, candidate):
        def result(state):
            return {
                "finalContentState": state,
                "wrongCell": False,
                "tie": False,
                "foreignFullSymbol": False,
            }

        return {"contentState": "visible", "base": result(base), "candidate": result(candidate)}

    photo = {
        "reasonCodes": [],
        "fullGeometry": True,
        "referenceSha256": "f" * 64,
        "boards": [
            {
                "base": {"usable": True, "matchAmbiguous": False},
                "candidate": {"usable": True, "matchAmbiguous": False},
                "cells": [cell("missing", "preserved"), cell("clipped", "missing")],
            }
        ],
    }
    summary = comparison_summary([photo])
    gate = paired_gate(summary, [{"state": "available", "acceptanceState": "disabled"}])
    assert gate["fewerClipped"] and gate["newMissing"] == 1
    assert gate["state"] == "regression"


def test_real_candidate_author_policy_producer_reaches_candidate(tmp_path):
    import json

    from game_predictor_api.domain.grid_training_cohorts import digest
    from game_predictor_api.storage.production_crop_capture import _policy
    from game_predictor_worker.symbols.candidate_gate import (
        SymbolCandidateGateConfiguration,
        build_symbol_candidate,
    )
    from test_symbol_candidate_gate import _fixture

    checkpoint, checksum, data, config = _fixture(tmp_path)
    built = build_symbol_candidate(
        artifact_root=tmp_path,
        candidate_root=tmp_path / "authored",
        checkpoint_path=checkpoint,
        checkpoint_checksum=checksum,
        data=data,
        training_config=config,
        configuration=SymbolCandidateGateConfiguration(
            minimum_accuracy=0, minimum_macro_recall=0, performance_repetitions=1
        ),
    )
    manifest = json.loads((tmp_path / built.manifest_relative_path).read_text())
    calibration = json.loads(
        (tmp_path / manifest["artifacts"]["calibration"]["relativePath"]).read_text()
    )
    pinned = SymbolModelJobSnapshot(
        iteration_id=UUID(int=77),
        model_version="spatial-symbol-cnn-onnx-v1",
        manifest_checksum_sha256=built.manifest_checksum_sha256,
        onnx_checksum_sha256=built.onnx_checksum_sha256,
        onnx_relative_path=built.onnx_relative_path,
        storage_root=SymbolModelStorageRoot.ARTIFACT,
        class_codes=data.class_codes,
        input_size=config.input_size,
        temperature=calibration["temperature"],
    )
    iteration = SimpleNamespace(
        candidate_manifest_checksum_sha256=built.manifest_checksum_sha256,
        candidate_manifest_relative_path=built.manifest_relative_path,
        configuration_payload={"inputSize": config.input_size},
    )
    policy = _policy(
        SimpleNamespace(get=lambda *_a: iteration), pinned.to_payload(), tmp_path, tmp_path
    )
    assert policy["report"]["version"] == "symbol-temperature-calibration-v2-safe-floor-v1"
    assert acceptance_policy(pinned, policy)["state"] == "disabled"
    missing = {k: v for k, v in policy.items() if k != "runtime"}
    assert acceptance_policy(pinned, missing)["state"] == "unavailable"
    snapshot, captured, engine, frame, target, nodes, context = setup(tmp_path)
    context["classifier"] = pinned.to_payload()
    context["renderConfiguration"].update(outputWidth=16, outputHeight=16)
    pin = target["productionContentReference"]
    pin["sourceContextSha256"] = digest(context)
    pin["sha256"] = digest({k: v for k, v in pin.items() if k != "sha256"})
    rendered = render_cells(frame, nodes, target, context)
    for truth, raster in zip(target["classes"], rendered, strict=True):
        truth.update(code="A", renderedPixelSha256=raster["renderedPixelSha256"])
    target["classificationPolicy"] = policy
    captured = sealed({k: v for k, v in captured.items() if k != "sha256"})
    report = run_comparison(
        snapshot,
        captured,
        root=tmp_path / "result",
        repository_root=tmp_path,
        artifact_root=tmp_path,
        engine=engine,
    )
    assert report["state"] == "candidate"
    assert all(g["gate"]["automaticAcceptance"] == "disabled" for g in report["games"])
    damaged = deepcopy(report["games"][0]["summary"])
    damaged["candidate"]["missing"] += 1
    assert (
        paired_gate(damaged, report["photos"][0]["geometry"]["human"]["classification"])["state"]
        == "regression"
    )
