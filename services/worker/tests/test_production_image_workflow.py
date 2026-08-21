import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_worker.images.geometry import (
    ClassicalPageBoardDetector,
    DetectionResult,
    Point,
)
from game_predictor_worker.images.page_geometry_registration import (
    PAGE_REGISTRATION_VERSION,
)
from game_predictor_worker.images.pipeline_execution import (
    ImagePipelineExecutionError,
    ImageStageContext,
)
from game_predictor_worker.images.production_workflow import (
    ProductionImageStageAdapterSuite,
    _attested_sequence_payload,
    _calibrated_quad,
    _resolve_page_sequence_numbers,
    _symbol_model_snapshot,
)
from game_predictor_worker.images.symbol_onnx import OnnxInference
from game_predictor_worker.jobs.runtime import JobHandlerError
from PIL import Image


def test_grid_profile_uses_run_scope_and_falls_back_without_mutating_detector_quad() -> None:
    detector_quad = (
        Point(10, 10),
        Point(90, 10),
        Point(90, 90),
        Point(10, 90),
    )
    profile = {
        "scopes": [
            {
                "imageSelectionRunId": "run-1",
                "positionIndex": 0,
                "normalizedCornerOffsets": [
                    {"x": 0.1, "y": 0.05},
                    {"x": 0.1, "y": 0.05},
                    {"x": 0.1, "y": 0.05},
                    {"x": 0.1, "y": 0.05},
                ],
            }
        ],
        "positionFallbacks": [],
    }

    calibrated = _calibrated_quad(
        detector_quad,
        profile=profile,
        image_selection_run_id="run-1",
        position_index=0,
        image_width=100,
        image_height=100,
    )

    assert calibrated[0] == Point(20, 15)
    assert detector_quad[0] == Point(10, 10)


def test_grid_profile_uses_position_fallback_for_direct_import() -> None:
    detector_quad = (
        Point(10, 10),
        Point(90, 10),
        Point(90, 90),
        Point(10, 90),
    )
    profile = {
        "scopes": [],
        "positionFallbacks": [
            {
                "positionIndex": 0,
                "normalizedCornerOffsets": [
                    {"x": 0.05, "y": 0.1},
                    {"x": 0.05, "y": 0.1},
                    {"x": 0.05, "y": 0.1},
                    {"x": 0.05, "y": 0.1},
                ],
            }
        ],
    }

    calibrated = _calibrated_quad(
        detector_quad,
        profile=profile,
        image_selection_run_id=None,
        position_index=0,
        image_width=100,
        image_height=100,
    )

    assert calibrated[0] == Point(15, 20)


def test_page_sequence_continuity_repairs_missing_and_isolated_bad_ocr() -> None:
    resolved, base = _resolve_page_sequence_numbers(
        (None, 2, 9, 4, 5, 6, 7, 8, 9),
        tuple(range(9)),
    )

    assert base == 1
    assert resolved == tuple(range(1, 10))


def test_page_sequence_continuity_rejects_competing_bases() -> None:
    observed = (1, 2, None, None, 11, 12, None, None, None)

    resolved, base = _resolve_page_sequence_numbers(observed, tuple(range(9)))

    assert base is None
    assert resolved == observed


def test_attested_sequence_range_assigns_row_major_numbers_without_ocr() -> None:
    detections = tuple({"positionIndex": index} for index in range(9))

    payload = _attested_sequence_payload(detections, (10, 18))

    boards = payload["boards"]
    assert isinstance(boards, list)
    assert [board["normalizedNumber"] for board in boards] == list(range(10, 19))
    assert all(board["sequenceSource"] == "filename" for board in boards)
    assert payload["rangeSource"] == "filename"


def test_attested_sequence_range_keeps_partial_geometry_in_review() -> None:
    detections = tuple({"positionIndex": index} for index in range(8))

    payload = _attested_sequence_payload(detections, (1, 9))

    boards = payload["boards"]
    assert isinstance(boards, list)
    assert all(board["normalizedNumber"] is None for board in boards)
    assert all(
        "SEQUENCE_ATTESTED_RANGE_GEOMETRY_REVIEW_REQUIRED" in board["reviewReasons"]
        for board in boards
    )


def _grid_image() -> np.ndarray:
    image = np.full((640, 680, 3), (20, 30, 180), dtype=np.uint8)
    for row in range(3):
        for column in range(3):
            left = 60 + column * 200
            top = 60 + row * 150
            cv2.rectangle(
                image,
                (left, top),
                (left + 140, top + 80),
                (235, 25, 20),
                10,
            )
    return image


def _grid_quads() -> list[list[dict[str, int]]]:
    return [
        [
            Point(60 + column * 200, 60 + row * 150).to_dict(),
            Point(200 + column * 200, 60 + row * 150).to_dict(),
            Point(200 + column * 200, 140 + row * 150).to_dict(),
            Point(60 + column * 200, 140 + row * 150).to_dict(),
        ]
        for row in range(3)
        for column in range(3)
    ]


def test_page_registration_anchor_loads_from_managed_data_root(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source_content_path = tmp_path / "anchor.jpg"
    Image.fromarray(_grid_image(), mode="RGB").save(source_content_path, format="JPEG")
    content = source_content_path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    anchor_path = artifact_root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    anchor_path.parent.mkdir(parents=True)
    anchor_path.write_bytes(content)

    suite = ProductionImageStageAdapterSuite(
        artifact_root,
        repository_root=Path.cwd(),
        symbol_model=_candidate_snapshot(),
        page_registration_profile={
            "policy": PAGE_REGISTRATION_VERSION,
            "anchors": [
                {
                    "sourceChecksumSha256": checksum,
                    "imageWidth": 680,
                    "imageHeight": 640,
                    "quads": _grid_quads(),
                }
            ],
        },
    )

    assert suite._page_registrar.available is True


class _AmbiguousDetector:
    version = "ambiguous-detector-test-v1"

    def __init__(self, result: DetectionResult) -> None:
        self._result = replace(
            result,
            layout_hypotheses=(result.boards, result.boards),
        )

    def detect(self, *_args: object, **_kwargs: object) -> DetectionResult:
        return self._result


class _UnexpectedDetector:
    def detect(self, *_args: object, **_kwargs: object) -> DetectionResult:
        raise AssertionError("a pinned verified page manifest must bypass the legacy detector")


def test_production_detection_rejects_multiple_partial_grid_hypotheses(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    normalized_relative = "working/test/normalized.png"
    normalized_path = artifact_root / "data" / normalized_relative
    normalized_path.parent.mkdir(parents=True)
    Image.fromarray(_grid_image(), mode="RGB").save(normalized_path, format="PNG")
    detection = ClassicalPageBoardDetector().detect(_grid_image())
    assert detection.status == "detected"
    suite = ProductionImageStageAdapterSuite(
        artifact_root,
        repository_root=Path.cwd(),
        symbol_model=_candidate_snapshot(),
    )
    suite._detector = _AmbiguousDetector(detection)  # type: ignore[assignment]
    context = ImageStageContext(
        job_id=uuid4(),
        file_execution_key="f" * 64,
        source_checksum_sha256="c" * 64,
        source_relative_path="unused.jpg",
        pipeline_fingerprint="d" * 64,
        previous_results={
            "normalization": {"normalizedRelativePath": normalized_relative},
        },
    )

    with pytest.raises(ImagePipelineExecutionError) as error:
        suite.board_detection(context)

    assert error.value.code == "IMAGE_PAGE_GEOMETRY_REQUIRES_REVIEW"


def test_pinned_complete_page_geometry_bypasses_the_legacy_detector(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    normalized_relative = "working/test/normalized.png"
    normalized_path = artifact_root / "data" / normalized_relative
    normalized_path.parent.mkdir(parents=True)
    Image.fromarray(_grid_image(), mode="RGB").save(normalized_path, format="PNG")
    checksum = "c" * 64
    quads = []
    for row in range(3):
        for column in range(3):
            left = 60 + column * 200
            top = 60 + row * 150
            quads.append(
                [
                    Point(left, top).to_dict(),
                    Point(left + 140, top).to_dict(),
                    Point(left + 140, top + 80).to_dict(),
                    Point(left, top + 80).to_dict(),
                ]
            )
    suite = ProductionImageStageAdapterSuite(
        artifact_root,
        repository_root=Path.cwd(),
        symbol_model=_candidate_snapshot(),
        page_registration_profile={
            "policy": PAGE_REGISTRATION_VERSION,
            "anchors": [
                {
                    "sourceChecksumSha256": "a" * 64,
                    "imageWidth": 680,
                    "imageHeight": 640,
                    "quads": _grid_quads(),
                }
            ],
        },
        page_geometry_manifest={
            checksum: {
                "status": "registered",
                "quads": quads,
                "boardRedEdgeCoverages": [0.9] * 9,
                "featureCount": 1000,
                "featuresVersion": "orb-1000-1500-3000-fallback-v1",
                "registrationVersion": "verified-page-registration-v1",
                "thresholdsVersion": "verified-page-registration-thresholds-v1",
            }
        },
    )
    suite._detector = _UnexpectedDetector()  # type: ignore[assignment]
    assert suite._page_registrar.available is False
    context = ImageStageContext(
        job_id=uuid4(),
        file_execution_key="f" * 64,
        source_checksum_sha256=checksum,
        source_relative_path="unused.jpg",
        pipeline_fingerprint="d" * 64,
        previous_results={
            "normalization": {"normalizedRelativePath": normalized_relative},
        },
    )

    detection = suite.board_detection(context)

    assert detection["geometryValidity"] == "verified"
    assert detection["recoveryMode"] == "pinned_verified_page_registration"
    assert detection["registration"]["featureCount"] == 1000
    assert detection["registration"]["featuresVersion"] == "orb-1000-1500-3000-fallback-v1"
    assert len(detection["boards"]) == 9


def test_production_stages_create_review_ready_board_and_cell_artifacts(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    source_content_path = tmp_path / "source.jpg"
    Image.fromarray(_grid_image(), mode="RGB").save(source_content_path, format="JPEG")
    content = source_content_path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    source_relative = f"originals/{checksum[:2]}/{checksum}.jpg"
    source_path = artifact_root / "data" / Path(*source_relative.split("/"))
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(content)

    suite = ProductionImageStageAdapterSuite(
        artifact_root,
        repository_root=Path.cwd(),
        symbol_model=_candidate_snapshot(),
    )
    results: dict[str, dict[str, object]] = {}
    adapters = suite.adapters()[:4]
    for adapter in adapters:
        context = ImageStageContext(
            job_id=uuid4(),
            file_execution_key="f" * 64,
            source_checksum_sha256=checksum,
            source_relative_path=source_relative,
            pipeline_fingerprint="a" * 64,
            previous_results=results,
        )
        results[adapter.stage] = dict(adapter.execute(context))

    detections = results["board_detection"]["boards"]
    crops = results["board_crops"]["boards"]
    assert isinstance(detections, list) and len(detections) == 9
    assert isinstance(crops, list) and len(crops) == 9
    first = crops[0]
    assert isinstance(first, dict)
    assert len(first["cells"]) == 15
    assert first["cellOutputSize"] == 32
    assert first["displayAssetKind"] == "source_context"
    assert f"/{'f' * 64}/" in first["boardRelativePath"]
    context_path = artifact_root / "data" / first["boardRelativePath"]
    assert context_path.is_file()
    context_rgb = np.asarray(Image.open(context_path).convert("RGB"), dtype=np.uint8)
    assert context_rgb.shape[:2] != (300, 500)
    bounds = first["sourceContextBounds"]
    assert isinstance(bounds, dict)
    normalized_path = artifact_root / "data" / results["normalization"]["normalizedRelativePath"]
    normalized_rgb = np.asarray(Image.open(normalized_path).convert("RGB"), dtype=np.uint8)
    expected_context = normalized_rgb[
        bounds["y"] : bounds["y"] + bounds["height"],
        bounds["x"] : bounds["x"] + bounds["width"],
    ]
    assert np.array_equal(context_rgb, expected_context)
    first_cell = first["cells"][0]
    assert isinstance(first_cell, dict)
    cell_rgb = np.asarray(
        Image.open(artifact_root / "data" / first_cell["cropRelativePath"]).convert("RGB"),
        dtype=np.uint8,
    )
    assert cell_rgb.shape == (32, 32, 3)


def _candidate_snapshot() -> SymbolModelJobSnapshot:
    return SymbolModelJobSnapshot(
        iteration_id=uuid4(),
        model_version="candidate-symbol-model-v1",
        manifest_checksum_sha256="a" * 64,
        onnx_checksum_sha256="b" * 64,
        onnx_relative_path="models/candidate/model.onnx",
        storage_root=SymbolModelStorageRoot.ARTIFACT,
        class_codes=("lemon", "seven"),
        input_size=32,
        temperature=1.25,
    )


def test_image_import_job_uses_the_exact_pinned_symbol_model_snapshot() -> None:
    snapshot = _candidate_snapshot()
    job = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 2,
            "import_kind": "image_directory",
            "symbol_model": snapshot.to_payload(),
        },
    )

    assert _symbol_model_snapshot(job) == snapshot


def test_image_import_rejects_a_modified_pinned_model_snapshot() -> None:
    snapshot = _candidate_snapshot()
    payload = snapshot.to_payload()
    payload["temperature"] = 9.0
    job = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 2,
            "import_kind": "image_directory",
            "symbol_model": payload,
        },
    )

    with pytest.raises(JobHandlerError) as error:
        _symbol_model_snapshot(job)

    assert error.value.code == "IMAGE_SYMBOL_MODEL_SNAPSHOT_DRIFT"


def test_missing_pinned_model_artifact_fails_without_bootstrap_fallback(tmp_path: Path) -> None:
    suite = ProductionImageStageAdapterSuite(
        tmp_path / "artifacts",
        repository_root=Path.cwd(),
        symbol_model=_candidate_snapshot(),
    )

    with pytest.raises(JobHandlerError) as error:
        suite._symbol_adapter()

    assert error.value.code == "IMAGE_SYMBOL_ONNX_ARTIFACT_MISSING"


class _FakeSymbolAdapter:
    def infer(self, tensors: np.ndarray) -> OnnxInference:
        assert tensors.shape == (1, 3, 32, 32)
        return OnnxInference(
            logits=np.asarray([[3.0, 1.0]], dtype=np.float32),
            probabilities=np.asarray([[0.88, 0.12]], dtype=np.float32),
            class_indexes=np.asarray([0], dtype=np.int64),
        )


def test_symbol_projection_uses_exact_size_crop_without_second_resize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "artifacts"
    cell_path = artifact_root / "data" / "cells" / "cell.png"
    cell_path.parent.mkdir(parents=True)
    Image.new("RGB", (32, 32), (255, 255, 0)).save(cell_path, format="PNG")
    snapshot = _candidate_snapshot()
    suite = ProductionImageStageAdapterSuite(
        artifact_root,
        repository_root=Path.cwd(),
        symbol_model=snapshot,
    )
    suite._symbol_model = _FakeSymbolAdapter()  # type: ignore[assignment]

    def unexpected_resize(*_args: object, **_kwargs: object) -> np.ndarray:
        raise AssertionError("source-direct model crops must not be resized again")

    monkeypatch.setattr(cv2, "resize", unexpected_resize)
    context = ImageStageContext(
        job_id=uuid4(),
        file_execution_key="f" * 64,
        source_checksum_sha256="c" * 64,
        source_relative_path="unused.jpg",
        pipeline_fingerprint="d" * 64,
        previous_results={
            "board_crops": {
                "boards": [
                    {
                        "positionIndex": 0,
                        "cells": [
                            {
                                "columnIndex": 0,
                                "rowIndex": 0,
                                "cropRelativePath": "cells/cell.png",
                            }
                        ],
                    }
                ]
            }
        },
    )

    result = suite.symbol_inference(context)

    assert result["modelIterationId"] == str(snapshot.iteration_id)
    assert result["modelManifestChecksumSha256"] == snapshot.manifest_checksum_sha256
    assert result["modelVersion"] == snapshot.model_version
