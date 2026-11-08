"""Small real files exercise the actual export, install and consumption guards."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from game_predictor_api.domain import grid_content_bundle as contract
from game_predictor_api.storage.grid_content_bundle import (
    read_content_bundle,
    read_content_bundle_bytes,
)
from game_predictor_api.storage.grid_model_registry import GridModelArtifactInspector
from game_predictor_worker.geometry_core.rescue import GridRescueVariantV2
from game_predictor_worker.images.grid_rescue_assessment import (
    assessment_engine,
    load_assessment_engine,
)
from game_predictor_worker.images.grid_rescue_runtime import run_with_rescue
from game_predictor_worker.images.grid_training_child import EXPORT_PREFIX, _export
from game_predictor_worker.images.grid_training_handler import GridTrainingJobHandler
from game_predictor_worker.jobs.runtime import JobHandlerError


def test_stream_bound_checks_growth_after_stat_before_json(tmp_path, monkeypatch):
    path = tmp_path / "bundle.json"
    path.write_bytes(b"x" * 65)  # Invalid JSON: size must fail first.
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 64)
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda self, **kwargs: SimpleNamespace(st_size=1)
        if self == path
        else original_stat(self, **kwargs),
    )
    with pytest.raises(contract.ContentBundleTooLarge) as caught:
        read_content_bundle(path)
    assert (caught.value.actual_bytes, caught.value.limit_bytes) == (65, 64)


def test_qualified_runtime_evidence_bounds_growth_before_json_and_retains_hash_guard(
    tmp_path, monkeypatch
):
    from game_predictor_worker.images.full_board_runtime_evidence import runtime_evidence

    path = tmp_path / "bundle.json"
    payload = b"x" * 65  # Invalid JSON makes a skipped size/hash guard observable.
    path.write_bytes(payload)
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda self, **kwargs: SimpleNamespace(st_size=1)
        if self == path
        else original_stat(self, **kwargs),
    )
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 64)
    args = dict(
        found=[],
        detections=[],
        observation={},
        pin={
            "contractVersion": "neural-grid-operation-pin-v3",
            "automaticQualification": {"state": "qualified", "profile": {}},
        },
        bundle=tmp_path,
        bundle_sha=hashlib.sha256(payload).hexdigest(),
        source_sha="a" * 64,
        width=10,
        height=10,
        available_source_box=[0, 0, 10, 10],
    )
    with pytest.raises(ValueError, match="^COMPLETENESS_PRESET_SIZE$") as caught:
        runtime_evidence(**args)
    assert isinstance(caught.value.__cause__, contract.ContentBundleTooLarge)
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 128)
    args["bundle_sha"] = "b" * 64
    with pytest.raises(ValueError, match="^COMPLETENESS_PRESET_CHANGED$"):
        runtime_evidence(**args)


def test_assessment_passes_bounded_bytes_to_onnx_without_a_second_file_read(tmp_path, monkeypatch):
    from game_predictor_worker.geometry_core import inference

    path = tmp_path / "bundle.json"
    payload = b"{"  # The bounded original must reach the real parser.
    path.write_bytes(payload)
    real_engine = inference.onnx_engine

    def changed_before_engine(*args, **kwargs):
        assert kwargs["bundle_bytes"] == payload
        path.write_bytes(b"x" * 65)
        return real_engine(*args, **kwargs)

    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 64)
    monkeypatch.setattr(inference, "onnx_engine", changed_before_engine)
    with pytest.raises(json.JSONDecodeError):
        load_assessment_engine(tmp_path, hashlib.sha256(payload).hexdigest(), 1)


def test_runtime_process_uses_bounded_original_and_rejects_oversize_before_spawn(
    tmp_path, monkeypatch
):
    from game_predictor_worker.geometry_core.inference import onnx_engine
    from game_predictor_worker.geometry_core.proposal_runtime import CPUGridProposalRunner, _serve

    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 64)
    path = tmp_path / "bundle.json"
    path.write_bytes(b"{")
    payload = read_content_bundle_bytes(path)
    path.write_bytes(b"x" * 65)
    sent = []
    connection = SimpleNamespace(send=sent.append, close=lambda: None)
    _serve(
        connection,
        tmp_path,
        hashlib.sha256(payload).hexdigest(),
        1,
        onnx_engine,
        payload,
    )
    assert sent[0][0] == "error" and "JSONDecodeError" in sent[0][1]
    runner = CPUGridProposalRunner(threads=1)
    with pytest.raises(contract.ContentBundleTooLarge):
        runner.run(
            tmp_path,
            "a" * 64,
            None,
            heartbeat=lambda: None,
            max_seconds=1,
            bundle_bytes=b"x" * 65,
        )
    assert runner._process is None


def test_exact_byte_boundary_and_predictable_inputs_bank(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 256)
    path = tmp_path / "bundle.json"
    path.write_bytes(b" " * 254 + b"{}")
    assert read_content_bundle(path) == {}
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(contract.ContentBundleTooLarge):
        read_content_bundle_bytes(path)
    contract.require_content_bundle_inputs({}, {})
    for plan, inputs, bank in (({}, {"sources": "x" * 256}, None), ({}, {}, {"x": "y" * 256})):
        with pytest.raises(contract.ContentBundleTooLarge):
            contract.require_content_bundle_inputs(plan, inputs, bank)
    document = {"unicode": "ą" * 25}
    size = len(json.dumps(document, indent=2, sort_keys=True).encode("utf-8"))
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", size)
    contract.require_content_bundle_size(document)
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", size - 1)
    with pytest.raises(contract.ContentBundleTooLarge):
        contract.require_content_bundle_size(document)


def test_export_rejects_known_oversize_before_graphs_or_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 128)
    with pytest.raises(contract.ContentBundleTooLarge):
        _export(
            {},
            tmp_path,
            None,
            None,
            {},
            b"",
            None,
            (None, None),
            content_experiment={"bank": "x" * 128},
        )
    assert list(tmp_path.iterdir()) == []


def test_export_recovery_is_bounded_before_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 128)
    checkpoint = "a" * 64
    destination = tmp_path / f"{EXPORT_PREFIX}{checkpoint[:16]}"
    destination.mkdir()
    (destination / "bundle.json").write_bytes(b"x" * 129)
    with pytest.raises(contract.ContentBundleTooLarge):
        _export(
            {},
            tmp_path,
            None,
            None,
            {},
            b"",
            SimpleNamespace(checkpoint_sha256=checkpoint),
            (None, None),
            content_experiment={},
        )


def test_install_blocks_before_copy_or_destination_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 64)
    run = tmp_path / "run"
    source = run / "export"
    source.mkdir(parents=True)
    (source / "bundle.json").write_bytes(b"x" * 65)
    handler = GridTrainingJobHandler(
        None, artifact_root=tmp_path, python=None, pythonpath="", repository_root=tmp_path
    )
    with pytest.raises(JobHandlerError) as caught:
        handler._install(
            run,
            {"directory": "export"},
            {"modelVersion": "neural-grid-v2", "managedDirectory": "models/new"},
        )
    assert caught.value.code == "CONTENT_EXPERIMENT_BUNDLE_TOO_LARGE"
    assert not (tmp_path / "models").exists()


def test_inspector_new_v2_limit_does_not_change_legacy_availability(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "api" / "tests"))
    from test_grid_model_registry import candidate

    payload = candidate(tmp_path)
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 8)
    inspector = GridModelArtifactInspector(tmp_path)
    assert inspector.inspect(payload) == (True, "GRID_MODEL_ARTIFACT_AVAILABLE")
    payload["modelVersion"] = "neural-grid-v2"
    assert inspector.inspect(payload) == (False, "CONTENT_EXPERIMENT_BUNDLE_TOO_LARGE")


@pytest.mark.parametrize("surface", ["assessment", "assessment_factory", "runtime"])
def test_consumers_reject_between_16_and_32_mib_before_inference(tmp_path, monkeypatch, surface):
    assert contract.CONTENT_BUNDLE_MAX_BYTES == 16 * 1024 * 1024
    path = tmp_path / "bundle.json"
    path.write_bytes(b"{}")
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda self, **kwargs: SimpleNamespace(st_size=17 * 1024 * 1024)
        if self == path
        else original_stat(self, **kwargs),
    )
    checksum = hashlib.sha256(b"{}").hexdigest()
    with pytest.raises(contract.ContentBundleTooLarge) as caught:
        if surface == "assessment":
            assessment_engine(None, tmp_path, checksum)
        elif surface == "assessment_factory":
            load_assessment_engine(tmp_path, checksum, 1)
        else:
            variant = GridRescueVariantV2()
            pin = {
                "policyVersion": "grid-content-rescue-policy-v1",
                "variantId": variant.sha256,
                "variant": variant.model_dump(mode="json"),
                "selectedPath": "combined",
                "bundleSha256": checksum,
                "proofSha256": "b" * 64,
                "publicationEvidenceSha256": "c" * 64,
            }
            run_with_rescue(
                runner=None,
                bundle=tmp_path,
                bundle_sha=checksum,
                rgb=None,
                heartbeat=lambda: None,
                max_seconds=1,
                directory=tmp_path / "attempt",
                source_sha="d" * 64,
                pin=pin,
                expected_positions={0},
            )
    assert caught.value.actual_bytes == 17 * 1024 * 1024
    assert not (tmp_path / "attempt").exists()
