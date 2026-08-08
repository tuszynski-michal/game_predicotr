import hashlib
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
from game_predictor_worker.images.pipeline_execution import ImageStageContext
from game_predictor_worker.images.production_workflow import (
    ProductionImageStageAdapterSuite,
    _symbol_model_snapshot,
)
from game_predictor_worker.images.symbol_onnx import OnnxInference
from game_predictor_worker.jobs.runtime import JobHandlerError
from PIL import Image


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
    assert (artifact_root / "data" / first["boardRelativePath"]).is_file()


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


def test_symbol_projection_records_the_pinned_iteration_and_manifest(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    cell_path = artifact_root / "data" / "cells" / "cell.png"
    cell_path.parent.mkdir(parents=True)
    Image.new("RGB", (20, 20), (255, 255, 0)).save(cell_path, format="PNG")
    snapshot = _candidate_snapshot()
    suite = ProductionImageStageAdapterSuite(
        artifact_root,
        repository_root=Path.cwd(),
        symbol_model=snapshot,
    )
    suite._symbol_model = _FakeSymbolAdapter()  # type: ignore[assignment]
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
