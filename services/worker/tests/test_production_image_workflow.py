import hashlib
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from game_predictor_worker.images.pipeline_execution import ImageStageContext
from game_predictor_worker.images.production_workflow import (
    ProductionImageStageAdapterSuite,
)
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
