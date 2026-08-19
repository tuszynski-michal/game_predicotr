from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.page_geometry_preflight import PageGeometryPreflightHandler
from game_predictor_worker.images.page_geometry_registration import PAGE_REGISTRATION_VERSION
from game_predictor_worker.images.source_ingestion import ManagedOriginalStore
from PIL import Image


class _Context:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []

    def checkpoint(self, **kwargs: object) -> None:
        self.checkpoints.append(kwargs)


def _page() -> tuple[np.ndarray, list[list[dict[str, int]]]]:
    image = np.full((480, 680, 3), (20, 30, 80), dtype=np.uint8)
    quads: list[list[dict[str, int]]] = []
    for row in range(3):
        for column in range(3):
            left = 50 + column * 200
            top = 50 + row * 130
            cv2.rectangle(image, (left, top), (left + 140, top + 80), (235, 25, 20), 7)
            cv2.putText(
                image,
                str(row * 3 + column + 1),
                (left + 60, top + 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )
            quads.append(
                [
                    Point(left, top).to_dict(),
                    Point(left + 140, top).to_dict(),
                    Point(left + 140, top + 80).to_dict(),
                    Point(left, top + 80).to_dict(),
                ]
            )
    return image, quads


def test_geometry_preflight_writes_a_content_addressed_manifest(tmp_path: Path) -> None:
    image, quads = _page()
    selection_id = uuid4()
    staged = tmp_path / str(selection_id)
    staged.mkdir()
    source = staged / "00000000.jpg"
    Image.fromarray(image, mode="RGB").save(source, format="JPEG")
    content = source.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    manifest_payload = {
        "schemaVersion": 1,
        "purpose": "layout_import",
        "gameId": None,
        "orderingPolicy": "natural_relative_path_v1",
        "files": [
            {
                "orderIndex": 0,
                "relativePath": "seq_10-18.jpg",
                "storedFileName": "00000000.jpg",
                "sizeBytes": len(content),
                "checksumSha256": checksum,
            }
        ],
    }
    browser_manifest = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode()
    (staged / "_browser_manifest.json").write_bytes(browser_manifest)
    artifact_root = tmp_path / "artifacts"
    anchor = artifact_root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    anchor.parent.mkdir(parents=True)
    anchor.write_bytes(content)
    profile = {
        "policy": PAGE_REGISTRATION_VERSION,
        "anchors": [
            {
                "sourceChecksumSha256": checksum,
                "imageWidth": 680,
                "imageHeight": 480,
                "quads": quads,
            }
        ],
    }
    job = create_job(
        JobType.VALIDATE,
        game_id=uuid4(),
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "source_selection_id": str(selection_id),
            "source_directory": str(staged),
            "source_manifest_sha256": "0" * 64,
            "page_registration_profile": profile,
            "page_geometry_overrides": {},
            "canonical_sequence_numbers": [],
        },
    )
    source_manifest = ManagedOriginalStore(artifact_root).load_or_create_manifest(
        job,
        source_directory=staged,
    )
    job = replace(
        job,
        input_payload={
            **job.input_payload,
            "source_manifest_sha256": source_manifest.checksum_sha256,
        },
    )
    context = _Context()
    handler = PageGeometryPreflightHandler(artifact_root=artifact_root)

    handler(context, job)  # type: ignore[arg-type]

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    assert isinstance(checkpoint, dict)
    assert checkpoint["complete"] is True
    relative = checkpoint["geometry_manifest_relative_path"]
    assert isinstance(relative, str)
    output = artifact_root / Path(*relative.split("/"))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["registeredSourceCount"] == 1
    assert payload["reviewRequiredSourceCount"] == 0
    assert payload["entries"][checksum]["status"] == "registered"
