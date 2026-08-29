from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, cast

import numpy as np
import pytest
import torch
from game_predictor_api.domain.image_geometry_v2 import SourcePoint, SourceQuad
from game_predictor_worker.images.keypoint_geometry import (
    DEFAULT_KEYPOINT_MODEL_CONFIGURATION,
    ApprovedKeypointGeometrySample,
    KeypointCpuTiming,
    KeypointGeometryDatasetError,
    KeypointGeometryReleaseError,
    KeypointOnnxArtifact,
    KeypointOnnxParityReport,
    KeypointTrainingConfiguration,
    build_keypoint_geometry_release_manifest,
    encode_keypoint_training_sample,
    freeze_keypoint_geometry_dataset,
    load_approved_keypoint_source,
    train_keypoint_geometry_model,
)
from PIL import Image


def _quad(offset: float = 0.0) -> SourceQuad:
    return SourceQuad(
        corners=(
            SourcePoint(10 + offset, 10),
            SourcePoint(90 + offset, 10),
            SourcePoint(90 + offset, 70),
            SourcePoint(10 + offset, 70),
        )
    )


def _sample(
    index: int,
    family: str,
    *,
    approval: str = "manual_approved",
) -> ApprovedKeypointGeometrySample:
    return ApprovedKeypointGeometrySample(
        sample_id=f"sample-{index}",
        source_family_id=family,
        source_checksum_sha256=f"{index + 1:064x}",
        source_relative_path=f"originals/{index}.jpg",
        canonical_width=120,
        canonical_height=80,
        active_board_slots=(0,),
        approved_quads=(_quad(),),
        approval_kind=cast("Literal['manual_approved']", approval),
    )


def test_manifest_is_deterministic_and_source_family_disjoint() -> None:
    samples = (
        _sample(0, "family-a"),
        _sample(1, "family-a"),
        _sample(2, "family-b"),
        _sample(3, "family-c"),
        _sample(4, "family-d"),
    )

    first = freeze_keypoint_geometry_dataset(samples)
    second = freeze_keypoint_geometry_dataset(tuple(reversed(samples)))

    assert first.manifest_checksum_sha256 == second.manifest_checksum_sha256
    assignments: dict[str, set[str]] = {}
    for sample, split in first.samples:
        assignments.setdefault(sample.source_family_id, set()).add(split)
    assert all(len(values) == 1 for values in assignments.values())
    assert {split for _sample_value, split in first.samples} == {
        "train",
        "validation",
        "test",
    }


def test_non_manual_quad_is_rejected_before_freeze() -> None:
    with pytest.raises(KeypointGeometryDatasetError) as error:
        freeze_keypoint_geometry_dataset(
            (
                _sample(0, "family-a", approval="model_prediction"),
                _sample(1, "family-b"),
                _sample(2, "family-c"),
            )
        )

    assert error.value.code == "KEYPOINT_GEOMETRY_APPROVAL_REQUIRED"


def test_at_least_three_source_families_are_required() -> None:
    with pytest.raises(KeypointGeometryDatasetError) as error:
        freeze_keypoint_geometry_dataset((_sample(0, "family-a"), _sample(1, "family-b")))

    assert error.value.code == "KEYPOINT_GEOMETRY_SOURCE_FAMILIES_INSUFFICIENT"


def test_heatmap_target_preserves_slot_and_corner_order() -> None:
    sample = _sample(0, "family-a")
    rgb = np.zeros((80, 120, 3), dtype=np.uint8)

    encoded = encode_keypoint_training_sample(sample, rgb)

    assert encoded.image.shape == (3, 128, 128)
    assert encoded.heatmaps.shape == (9, 4, 32, 32)
    assert encoded.slot_presence.tolist() == [1.0] + [0.0] * 8
    assert encoded.active_corner_mask[0].tolist() == [1.0] * 4
    peaks = [
        np.unravel_index(int(encoded.heatmaps[0, corner].argmax()), (32, 32)) for corner in range(4)
    ]
    assert peaks == [(4, 3), (4, 23), (27, 23), (27, 3)]


def test_bounded_cpu_training_returns_expected_model_outputs() -> None:
    sample = _sample(0, "family-a")
    rgb = np.zeros((80, 120, 3), dtype=np.uint8)

    samples = (
        sample,
        _sample(1, "family-b"),
        _sample(2, "family-c"),
    )
    frozen = freeze_keypoint_geometry_dataset(samples)
    result = train_keypoint_geometry_model(
        frozen,
        load_rgb=lambda _sample_value: rgb,
        training_configuration=KeypointTrainingConfiguration(
            epochs=1,
            batch_size=1,
            seed=319,
        ),
    )
    heatmaps, presence = result.model(torch.zeros((1, 3, 128, 128), dtype=torch.float32))

    assert result.training_sample_count == 1
    assert len(result.losses) == 1
    assert np.isfinite(result.losses[0])
    assert tuple(heatmaps.shape) == (1, 9, 4, 32, 32)
    assert tuple(presence.shape) == (1, 9)
    artifact_content = b"keypoint-onnx-fixture"
    release = build_keypoint_geometry_release_manifest(
        dataset=frozen,
        model_configuration=DEFAULT_KEYPOINT_MODEL_CONFIGURATION,
        training_configuration=KeypointTrainingConfiguration(
            epochs=1,
            batch_size=1,
            seed=319,
        ),
        training_result=result,
        onnx_artifact=KeypointOnnxArtifact(
            content=artifact_content,
            checksum_sha256=hashlib.sha256(artifact_content).hexdigest(),
            model_version=result.model_version,
            adapter_version="keypoint-geometry-onnx-cpu-v1",
            input_size=128,
            heatmap_size=32,
        ),
        parity=KeypointOnnxParityReport(
            maximum_absolute_error=1e-6,
            heatmap_argmax_equal=True,
            presence_mask_equal=True,
        ),
        cpu_timing=KeypointCpuTiming(
            warmup_count=1,
            measurement_count=3,
            median_milliseconds=2.0,
            p95_milliseconds=2.5,
        ),
    )
    assert release.shadow_only is True
    assert release.payload["activationAllowed"] is False

    with pytest.raises(KeypointGeometryReleaseError) as error:
        build_keypoint_geometry_release_manifest(
            dataset=frozen,
            model_configuration=DEFAULT_KEYPOINT_MODEL_CONFIGURATION,
            training_configuration=KeypointTrainingConfiguration(
                epochs=1,
                batch_size=1,
                seed=319,
            ),
            training_result=result,
            onnx_artifact=KeypointOnnxArtifact(
                content=artifact_content,
                checksum_sha256=hashlib.sha256(artifact_content).hexdigest(),
                model_version=result.model_version,
                adapter_version="wrong-adapter",
                input_size=128,
                heatmap_size=32,
            ),
            parity=KeypointOnnxParityReport(
                maximum_absolute_error=1e-6,
                heatmap_argmax_equal=True,
                presence_mask_equal=True,
            ),
            cpu_timing=KeypointCpuTiming(
                warmup_count=1,
                measurement_count=3,
                median_milliseconds=2.0,
                p95_milliseconds=2.5,
            ),
        )
    assert error.value.code == "KEYPOINT_ONNX_RELEASE_CONTRACT_MISMATCH"


def test_managed_source_loader_verifies_jpeg_checksum(tmp_path: Path) -> None:
    source = tmp_path / "originals" / "source.jpg"
    source.parent.mkdir()
    Image.fromarray(np.zeros((80, 120, 3), dtype=np.uint8), mode="RGB").save(
        source,
        format="JPEG",
    )
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    sample = ApprovedKeypointGeometrySample(
        sample_id="managed-source",
        source_family_id="family-a",
        source_checksum_sha256=checksum,
        source_relative_path="originals/source.jpg",
        canonical_width=120,
        canonical_height=80,
        active_board_slots=(0,),
        approved_quads=(_quad(),),
        approval_kind="manual_approved",
    )

    rgb = load_approved_keypoint_source(tmp_path, sample)

    assert rgb.shape == (80, 120, 3)
    source.write_bytes(b"changed")
    with pytest.raises(KeypointGeometryDatasetError) as error:
        load_approved_keypoint_source(tmp_path, sample)
    assert error.value.code == "KEYPOINT_GEOMETRY_SOURCE_CHECKSUM_MISMATCH"
