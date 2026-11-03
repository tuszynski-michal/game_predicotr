"""Small contract fixtures; no operator pilot or synthetic overlap training."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from game_predictor_worker.images.symbol_classifier import load_image_tensor
from game_predictor_worker.images.symbol_model_benchmark import SpatialSymbolCnn
from game_predictor_worker.images.symbol_onnx import preprocess_rgb_batch
from game_predictor_worker.symbols import readability_detector as detector
from game_predictor_worker.symbols.readability_cohort import (
    CohortSplit,
    QualitySample,
    assign_families,
    pilot_issues,
)
from game_predictor_worker.symbols.readability_features import (
    FEATURE_COUNT,
    PREPROCESSING,
    FrozenBase,
    ReadabilityError,
    extract_features,
    fingerprint,
    native_features,
    preflight_base,
)
from PIL import Image


def sample(index: int, **changes: Any) -> QualitySample:
    result = QualitySample(
        str(index),
        index + 1,
        f"source{index}",
        f"sha{index}",
        f"rgb{index}",
        "geometry-v1",
        f"import{index % 3}",
        f"class{index % 2}",
        index % 2 == 0,
        False,
        False,
    )
    return replace(result, **changes)


def base() -> FrozenBase:
    return FrozenBase("a" * 64, "b" * 64, "c" * 64, ("A", "B"), ())


def valid_cohort(*, audit: bool = False) -> CohortSplit:
    samples: list[QualitySample] = []
    splits = []
    for split in ("train", "validation", "test"):
        for kind, count in (("overlap", 40), ("readable", 40), ("other", 20)):
            for _i in range(count):
                samples.append(
                    sample(
                        len(samples),
                        overlap=kind == "overlap",
                        unreadable=kind != "readable",
                        sharp=kind == "overlap",
                        similar_readable=kind == "readable",
                        top1=0.99,
                    )
                )
                splits.append(split)
    if audit:
        for i in range(200):
            samples.append(
                sample(
                    len(samples),
                    overlap=i % 3 == 0,
                    unreadable=i % 2 == 0,
                    previously_unlabelled=True,
                )
            )
            splits.append("audit")
    return assign_families(samples, base(), assignments=splits)


def artifact(cohort: CohortSplit) -> detector.QualityArtifact:
    # A fixed fixture detector, never an empirical model claim.
    head = detector.LinearHead((0.0,) * FEATURE_COUNT, 1.0, 10.0, 0.5, 1.0, 1.0)
    return detector.QualityArtifact(
        base().binding(),
        fingerprint(cohort.binding()),
        (0.0,) * FEATURE_COUNT,
        (1.0,) * FEATURE_COUNT,
        head,
        head,
    )


def test_native_features_and_frozen_weights_bn_and_logits_independence() -> None:
    torch.set_num_threads(1)
    model = SpatialSymbolCnn(2)
    state = {name: value.clone() for name, value in model.state_dict().items()}
    rgb = np.arange(80 * 90 * 3, dtype=np.uint8).reshape(80, 90, 3)
    actual = extract_features(model, [rgb])
    assert actual.shape == (1, FEATURE_COUNT)
    np.testing.assert_array_equal(actual[0, -8:], native_features(rgb))
    model.classifier[-1].bias.data.fill_(100)
    np.testing.assert_array_equal(actual, extract_features(model, [rgb]))
    for name, value in model.state_dict().items():
        if name != "classifier.4.bias":
            assert torch.equal(value, state[name])
    assert not model.training
    assert all(not parameter.requires_grad for parameter in model.parameters())
    assert not np.array_equal(native_features(rgb), native_features(rgb[::2, ::2]))


def test_production_preprocessing_and_64px_training_parity(tmp_path: Path) -> None:
    rgb = np.arange(64 * 64 * 3, dtype=np.uint8).reshape(64, 64, 3)
    path = tmp_path / "crop.png"
    Image.fromarray(rgb).save(path)
    production = preprocess_rgb_batch([rgb], input_size=64)
    np.testing.assert_allclose(production[0], load_image_tensor(path, 64).numpy(), atol=2e-7)
    model = SpatialSymbolCnn(2).eval()
    with torch.inference_mode():
        expected = model.features(torch.from_numpy(production)).flatten(1).numpy()
    np.testing.assert_allclose(extract_features(model, [rgb])[0, :1024], expected[0])


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("valid", None),
        ("legacy_checksum_default", None),
        ("split_summary", "READABILITY_DATASET_INVALID"),
        ("dataset_sha", "READABILITY_INPUT_DRIFT"),
        ("checkpoint_sha", "READABILITY_INPUT_DRIFT"),
        ("missing_dataset", "READABILITY_INPUT_MISSING"),
        ("missing_checkpoint", "READABILITY_INPUT_MISSING"),
        ("missing_asset", "READABILITY_INPUT_MISSING"),
        ("corrupt_asset", "READABILITY_INPUT_MISSING"),
        ("changed_rgb", "READABILITY_INPUT_DRIFT"),
        ("assignments", "READABILITY_DATASET_INVALID"),
        ("family_cross_split", "READABILITY_DATASET_INVALID"),
        ("rgb_cross_split", "READABILITY_BASE_LEAKAGE"),
        ("class_catalogue", "READABILITY_CHECKPOINT_INVALID"),
        ("corrupt_checkpoint", "READABILITY_CHECKPOINT_INVALID"),
        ("native_size", "READABILITY_PREPROCESSING_DRIFT"),
        ("malformed_json", "READABILITY_DATASET_INVALID"),
        ("missing_key", "READABILITY_DATASET_INVALID"),
    ],
)
def test_preflight_complete_manifest_and_drift(
    tmp_path: Path, failure: str, expected_code: str | None
) -> None:
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "status": "ready",
        "sampleCount": 4,
        "catalog": [{"symbolCode": "A"}, {"symbolCode": "B"}],
        "artifactBaseRelativePath": "dataset",
        "samples": [],
        "configuration": {"sourceAssignments": {}},
        "splits": [],
    }
    for i, split in enumerate(("train", "validation", "test", "regression")):
        rgb = np.full((64, 64, 3), 20 + i * 30, dtype=np.uint8)
        path = tmp_path / "dataset" / f"{i}.png"
        path.parent.mkdir(exist_ok=True)
        Image.fromarray(rgb).save(path)
        document["samples"].append(
            {
                "cropSampleId": str(i),
                "sourceFamily": str(i),
                "sourceImageId": str(i),
                "sourceImageChecksumSha256": str(i),
                "split": split,
                "symbolCode": "A",
                "assetRelativePath": path.name,
                "cropChecksumSha256": rgb_pixel_checksum_sha256(rgb),
                "assetChecksumKind": "rgb-pixel-v1",
            }
        )
        document["configuration"]["sourceAssignments"][str(i)] = split
        document["splits"].append(
            {"name": split, "sampleCount": 1, "sourceFamilies": [str(i)], "sourceFamilyCount": 1}
        )
    dataset = tmp_path / "manifest.json"
    checkpoint = tmp_path / "checkpoint.pt"
    torch.save(
        {"classCodes": ("A", "B"), "bestState": SpatialSymbolCnn(2).state_dict()}, checkpoint
    )
    initial_checkpoint_sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()

    def run() -> tuple[FrozenBase, SpatialSymbolCnn]:
        dataset.write_text(json.dumps(document))
        if failure == "malformed_json":
            dataset.write_text("{not-json")
        checkpoint_sha = (
            hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            if checkpoint.exists()
            else initial_checkpoint_sha
        )
        return preflight_base(
            checkpoint,
            tmp_path / "absent.json" if failure == "missing_dataset" else dataset,
            tmp_path,
            checkpoint_sha256="0" * 64 if failure == "checkpoint_sha" else checkpoint_sha,
            dataset_sha256=(
                "0" * 64
                if failure == "dataset_sha"
                else hashlib.sha256(dataset.read_bytes()).hexdigest()
            ),
            preprocessing=PREPROCESSING,
        )

    # Each mutation reaches its own fail-closed branch with all earlier gates valid.
    asset = tmp_path / "dataset/0.png"
    if failure == "split_summary":
        document["splits"][0]["sampleCount"] = 2
    elif failure == "missing_checkpoint":
        checkpoint.unlink()
    elif failure == "missing_asset":
        asset.unlink()
    elif failure == "corrupt_asset":
        asset.write_bytes(b"changed")
    elif failure == "changed_rgb":
        Image.fromarray(np.full((64, 64, 3), 251, dtype=np.uint8)).save(asset)
    elif failure == "assignments":
        document["configuration"]["sourceAssignments"]["0"] = "validation"
    elif failure == "family_cross_split":
        document["samples"][1]["sourceFamily"] = "0"
    elif failure == "rgb_cross_split":
        document["samples"][1]["assetRelativePath"] = "0.png"
        document["samples"][1]["cropChecksumSha256"] = document["samples"][0]["cropChecksumSha256"]
    elif failure == "class_catalogue":
        torch.save(
            {"classCodes": ("A", "OTHER"), "bestState": SpatialSymbolCnn(2).state_dict()},
            checkpoint,
        )
    elif failure == "corrupt_checkpoint":
        checkpoint.write_bytes(b"not-a-checkpoint")
    elif failure == "native_size":
        Image.fromarray(np.full((32, 64, 3), 20, dtype=np.uint8)).save(asset)
    elif failure == "missing_key":
        del document["configuration"]
    elif failure == "legacy_checksum_default":
        del document["samples"][0]["assetChecksumKind"]
        document["samples"][0]["cropChecksumSha256"] = hashlib.sha256(
            asset.read_bytes()
        ).hexdigest()
    if expected_code is None:
        frozen, model = run()
        assert len(frozen.members) == 4 and not model.training
        return
    with pytest.raises(ReadabilityError) as error:
        run()
    assert error.value.code == expected_code


def test_preflight_rejects_preprocessing_before_missing_files(tmp_path: Path) -> None:
    with pytest.raises(ReadabilityError) as error:
        preflight_base(
            tmp_path / "absent.pt",
            tmp_path / "absent.json",
            tmp_path,
            checkpoint_sha256="a" * 64,
            dataset_sha256="b" * 64,
            preprocessing={"resize": "bilinear"},
        )
    assert error.value.code == "READABILITY_PREPROCESSING_DRIFT"


@pytest.mark.parametrize("content", ["{not-json", "[]", "null", '{"score":NaN}', None])
def test_artifact_malformed_input_has_stable_error(tmp_path: Path, content: str | None) -> None:
    path = tmp_path / "untrusted.json"
    if content is not None:
        path.write_text(content)
    with pytest.raises(ReadabilityError) as error:
        detector.load_artifact(path, expected_fingerprint="a" * 64, base=base())
    assert error.value.code == "READABILITY_ARTIFACT_INVALID"


def test_default_split_protects_base_exposure_and_proposes_sixty_twenty_twenty() -> None:
    samples = [sample(i) for i in range(10)]
    frozen = replace(
        base(),
        members=tuple(
            {
                "sourceId": samples[i].source_id,
                "sourceSha256": samples[i].source_sha256,
                "rgbSha256": samples[i].rgb_sha256,
                "family": str(i),
                "split": split,
            }
            for i, split in enumerate(("train", "test", "regression"))
        ),
    )
    cohort = assign_families(samples, frozen)
    assert cohort.assignments[0] in ("train", "validation")
    assert cohort.assignments[1:3] == ("test", "test")
    assert {
        split: cohort.assignments.count(split) for split in ("train", "validation", "test")
    } == {
        "train": 6,
        "validation": 2,
        "test": 2,
    }


def test_pilot_and_natural_audit_combined_limit() -> None:
    with pytest.raises(ReadabilityError) as error:
        assign_families([sample(i) for i in range(801)], base())
    assert error.value.code == "READABILITY_COHORT_LIMIT"


def test_family_aliases_transitive_and_protected_base() -> None:
    first, second, third = (
        sample(0),
        sample(1, source_sha256="sha0", recording_id="film"),
        sample(2, recording_id="film"),
    )
    cohort = assign_families([first, second, third], base(), assignments=["train"] * 3)
    assert len(set(cohort.families)) == 1
    with pytest.raises(ReadabilityError) as error:
        assign_families([first, second, third], base(), assignments=["train", "train", "test"])
    assert error.value.code == "READABILITY_SPLIT_LEAKAGE"
    frozen = replace(
        base(),
        members=(
            {
                "sourceId": "old",
                "sourceSha256": "oldsha",
                "rgbSha256": "rgb0",
                "family": "old",
                "split": "train",
            },
        ),
    )
    with pytest.raises(ReadabilityError, match="base exposure"):
        assign_families([first], frozen, assignments=["test"])
    with pytest.raises(ReadabilityError):
        assign_families([sample(4, geometry_identity="")], base())


def test_pilot_minima_sharp_and_confident_missing_never_pass() -> None:
    cohort = valid_cohort()
    assert pilot_issues(cohort) == ()
    changed = replace(cohort, samples=tuple(replace(s, top1=0.5) for s in cohort.samples))
    assert "test_confident_overlap_insufficient" in pilot_issues(changed)
    changed = replace(cohort, samples=tuple(replace(s, sharp=False) for s in cohort.samples))
    assert "test_sharp_overlap_insufficient" in pilot_issues(changed)


def test_solver_deterministic_l2_bias_and_threshold_selection() -> None:
    x = np.array([[-2.0], [-1.0], [1.0], [2.0]], dtype=np.float64)
    head = detector.select_head(x, [False, False, True, True], x, [False, False, True, True])
    assert head.regularization == 10  # Equal perfect precision chooses stronger L2.
    repeated = detector.select_head(x, [False, False, True, True], x, [False, False, True, True])
    assert head == repeated
    assert head.validation_recall == 1 and head.validation_precision == 1
    assert head.weights[0] > 0 and abs(head.bias) < 1e-6
    threshold, _, recall = detector.select_threshold(
        np.array([0.1, 0.2, 0.8, 0.9]), [False, True, True, True]
    )
    assert threshold < 0.2 and np.nextafter(threshold, np.inf) == 0.2 and recall == 1


def test_scaler_and_fits_ignore_test_and_null_per_head(monkeypatch: pytest.MonkeyPatch) -> None:
    cohort = valid_cohort()
    samples = list(cohort.samples)
    samples[0] = replace(samples[0], overlap=None)
    cohort = replace(cohort, samples=tuple(samples))
    # 39 overlap train families still exceeds the required 10.
    assert not pilot_issues(cohort)
    features = np.zeros((len(samples), FEATURE_COUNT))
    features[:100, 0] = np.arange(100)
    calls: list[tuple[np.ndarray, list[bool], np.ndarray, list[bool]]] = []

    def capture(
        train: np.ndarray, labels: list[bool], val: np.ndarray, val_labels: list[bool]
    ) -> detector.LinearHead:
        calls.append((train.copy(), labels, val.copy(), val_labels))
        return detector.LinearHead((0.0,) * FEATURE_COUNT, 0.0, 1.0, 0.5, 1.0, 1.0)

    monkeypatch.setattr(detector, "select_head", capture)
    original = detector.train_detector(cohort, features, base())
    assert len(calls[0][1]) == 99 and len(calls[1][1]) == 100
    assert original.mean[0] == 49.5 and original.scale[1] == 1
    features[200:] = 10000
    changed = detector.train_detector(cohort, features, base())
    assert changed == original
    for before, after in zip(calls[:2], calls[2:], strict=True):
        np.testing.assert_array_equal(before[0], after[0])
        np.testing.assert_array_equal(before[2], after[2])


def test_artifact_reload_drift_ranking_and_wilson(tmp_path: Path) -> None:
    cohort = valid_cohort()
    model = artifact(cohort)
    values = np.zeros((3, FEATURE_COUNT))
    samples = [sample(3), sample(1), sample(2)]
    ranked = detector.rank_candidates(model, samples, values)
    assert [item["cellId"] for item in ranked] == ["1", "2", "3"]
    path = tmp_path / "model.json"
    document = model.document()
    path.write_text(json.dumps(document))
    loaded = detector.load_artifact(path, expected_fingerprint=document["fingerprint"], base=base())
    assert detector.rank_candidates(loaded, samples, values) == ranked
    document["overlap"]["bias"] = 0
    path.write_text(json.dumps(document))
    with pytest.raises(ReadabilityError):
        detector.load_artifact(
            path, expected_fingerprint=model.document()["fingerprint"], base=base()
        )
    assert detector.rate_metric(0, 0, 0)["rate"] is None
    metric = detector.rate_metric(40, 40, 10)
    assert metric["rate"] == 1 and 0.91 < metric["wilson95"][0] < 0.92


def test_natural_audit_and_operator_gate() -> None:
    cohort = valid_cohort(audit=True)
    model = artifact(cohort)
    values = np.zeros((len(cohort.samples), FEATURE_COUNT))
    report = detector.evaluate_pilot(model, cohort, values)
    assert report["status"] == "STOP" and not report["fullScanAllowed"]
    identities = [
        s.identity()
        for s, split in zip(cohort.samples, cohort.assignments, strict=True)
        if split == "audit"
    ]
    receipt = {
        "selection": "uniform-random-before-labels",
        "seed": "frozen-fixture",
        "identitiesSha256": fingerprint(sorted(identities)),
    }
    report = detector.evaluate_pilot(model, cohort, values, natural_audit_receipt=receipt)
    assert report["status"] == "PASS" and not report["fullScanAllowed"]
    assert report["test"]["confident_overlap"]["count"] == 40
    assert report["test"]["similar_readable_fpr"]["rate"] == 1
    report = detector.evaluate_pilot(
        model, cohort, values, natural_audit_receipt=receipt, operator_accepted=True
    )
    assert report["fullScanAllowed"]


def test_test_recall_below_ninety_blocks_even_with_operator_acceptance() -> None:
    cohort = valid_cohort(audit=True)
    model = artifact(cohort)
    negative_head = replace(model.overlap, bias=-1)
    model = replace(model, overlap=negative_head, unreadable=negative_head)
    receipt = {
        "selection": "uniform-random-before-labels",
        "seed": "frozen-fixture",
        "identitiesSha256": fingerprint(
            sorted(
                item.identity()
                for item, split in zip(cohort.samples, cohort.assignments, strict=True)
                if split == "audit"
            )
        ),
    }
    report = detector.evaluate_pilot(
        model,
        cohort,
        np.zeros((len(cohort.samples), FEATURE_COUNT)),
        natural_audit_receipt=receipt,
        operator_accepted=True,
    )
    assert report["status"] == "STOP" and not report["fullScanAllowed"]
    assert report["issues"] == [
        "overlap_unreadable_recall_below_90",
        "all_unreadable_recall_below_90",
    ]


def test_full_fit_and_reload_in_new_process(tmp_path: Path) -> None:
    cohort = valid_cohort()
    features = np.zeros((len(cohort.samples), FEATURE_COUNT))
    for i, item in enumerate(cohort.samples):
        features[i, 0] = 1 if item.overlap else -1
        features[i, 1] = 1 if item.unreadable else -1
    fitted = detector.train_detector(cohort, features, base())
    assert fitted.overlap.weights != fitted.unreadable.weights
    report = detector.evaluate_pilot(fitted, cohort, features)
    assert report["test"]["overlap_unreadable"]["rate"] == 1
    assert report["test"]["similar_readable_fpr"]["rate"] == 0
    document = fitted.document()
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(document))
    source = Path(__file__).resolve().parents[1] / "src"
    api_source = source.parents[1] / "api/src"
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(source), str(api_source)))}
    code = """
import sys
from pathlib import Path
from game_predictor_worker.symbols.readability_features import FrozenBase
from game_predictor_worker.symbols.readability_detector import load_artifact
b=FrozenBase('a'*64,'b'*64,'c'*64,('A','B'),())
a=load_artifact(Path(sys.argv[1]),expected_fingerprint=sys.argv[2],base=b)
assert a.document()['fingerprint']==sys.argv[2]
print('fresh-process-artifact-ok')
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(path), document["fingerprint"]],
        env=environment,
        timeout=30,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "fresh-process-artifact-ok" in completed.stdout


def test_nonconvergence_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.optim.LBFGS, "step", lambda *args, **kwargs: None)
    with pytest.raises(ReadabilityError) as error:
        detector.fit_linear(np.array([[-1.0], [1.0]]), [False, True], 1.0)
    assert error.value.code == "READABILITY_NONCONVERGENCE"
