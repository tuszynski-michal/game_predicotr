from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import cv2
import game_predictor_worker.images.page_geometry_preflight as preflight_module
import numpy as np
import pytest
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.page_geometry_preflight import PageGeometryPreflightHandler
from game_predictor_worker.images.page_geometry_registration import (
    PAGE_REGISTRATION_VERSION,
    RegisteredPageGeometry,
)
from game_predictor_worker.images.source_ingestion import ManagedOriginalStore
from PIL import Image


class _Context:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []

    def checkpoint(self, **kwargs: object) -> None:
        if self.checkpoints:
            previous = self.checkpoints[-1]
            for key in ("current", "success_count", "failure_count", "review_count"):
                assert int(kwargs[key]) >= int(previous[key]), f"{key} regressed"
        self.checkpoints.append(kwargs)


def test_geometry_preflight_validates_registration_worker_budget(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="registration_workers must be between 1 and 64"):
        PageGeometryPreflightHandler(artifact_root=tmp_path, registration_workers=0)

    handler = PageGeometryPreflightHandler(artifact_root=tmp_path, registration_workers=7)

    assert handler._registration_workers == 7  # noqa: SLF001


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


def _cold_start_job(
    tmp_path: Path,
    *,
    image_count: int,
    overrides: dict[str, object] | None = None,
) -> tuple[Job, list[str]]:
    selection_id = uuid4()
    staged = tmp_path / str(selection_id)
    staged.mkdir()
    files: list[dict[str, object]] = []
    checksums: list[str] = []
    for index in range(image_count):
        source = staged / f"{index:08d}.jpg"
        image, _quads = _page()
        image = np.roll(image, index * 3, axis=1)
        Image.fromarray(image, mode="RGB").save(source, format="JPEG")
        content = source.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        checksums.append(checksum)
        files.append(
            {
                "orderIndex": index,
                "relativePath": f"seq_{index * 9 + 1}-{index * 9 + 9}.jpg",
                "storedFileName": source.name,
                "sizeBytes": len(content),
                "checksumSha256": checksum,
            }
        )
    browser_manifest = json.dumps(
        {
            "schemaVersion": 1,
            "purpose": "layout_import",
            "gameId": None,
            "orderingPolicy": "natural_relative_path_v1",
            "files": files,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (staged / "_browser_manifest.json").write_bytes(browser_manifest)
    return (
        create_job(
            JobType.VALIDATE,
            game_id=uuid4(),
            input_payload={
                "schema_version": 2,
                "validation_kind": "page_geometry_preflight",
                "preflight_policy_version": "page-geometry-preflight-v2-auto-anchor",
                "source_selection_id": str(selection_id),
                "source_directory": str(staged),
                "source_manifest_sha256": hashlib.sha256(browser_manifest).hexdigest(),
                "page_registration_profile": {
                    "schemaVersion": 1,
                    "policy": PAGE_REGISTRATION_VERSION,
                    "anchors": [],
                },
                "page_geometry_overrides": overrides or {},
                "canonical_sequence_numbers": [],
            },
        ),
        checksums,
    )


def test_geometry_preflight_without_anchor_creates_review_queue(tmp_path: Path) -> None:
    job, checksums = _cold_start_job(tmp_path, image_count=2)
    context = _Context()

    PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(  # type: ignore[arg-type]
        context,
        job,
    )

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = (
        tmp_path / "artifacts" / Path(*checkpoint["geometry_manifest_relative_path"].split("/"))
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["registeredSourceCount"] == 0
    assert payload["reviewRequiredSourceCount"] == 2
    assert {payload["entries"][checksum]["reasonCode"] for checksum in checksums} == {
        "PAGE_GEOMETRY_BOOTSTRAP_ANCHOR_REQUIRED"
    }


def test_manual_override_bootstraps_registration_for_remaining_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _image, quads = _page()
    initial_job, checksums = _cold_start_job(tmp_path, image_count=2)
    override = {
        checksums[0]: {
            "decisionChecksumSha256": "d" * 64,
            "imageHeight": 480,
            "imageWidth": 680,
            "overrideId": str(uuid4()),
            "quads": quads,
            "revision": 1,
        }
    }
    job = create_job(
        JobType.VALIDATE,
        game_id=initial_job.game_id,
        input_payload={**initial_job.input_payload, "page_geometry_overrides": override},
    )

    class _Registrar:
        def __init__(self, profile, **_kwargs) -> None:
            self.available = bool(profile["anchors"])
            assert profile["anchors"][0]["sourceChecksumSha256"] == checksums[0]

        def register(self, _rgb):
            return RegisteredPageGeometry(
                anchor_source_checksum_sha256=checksums[0],
                quads=tuple(
                    tuple(Point(point["x"], point["y"]) for point in quad) for quad in quads
                ),
                board_red_edge_coverages=(0.9,) * 9,
                inlier_count=80,
                inlier_ratio=0.5,
                p95_reprojection_error=1.0,
                mean_red_edge_coverage=0.9,
                feature_count=1000,
            )

    monkeypatch.setattr(preflight_module, "VerifiedPageRegistrar", _Registrar)
    context = _Context()
    PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(  # type: ignore[arg-type]
        context,
        job,
    )

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = (
        tmp_path / "artifacts" / Path(*checkpoint["geometry_manifest_relative_path"].split("/"))
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["registeredSourceCount"] == 2
    assert payload["reviewRequiredSourceCount"] == 0
    assert payload["entries"][checksums[0]]["registrationVersion"] == (
        "manual-page-geometry-override-v1"
    )
    assert payload["entries"][checksums[1]]["anchorSourceChecksumSha256"] == checksums[0]


def test_geometry_preflight_applies_every_manual_override_from_one_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _image, quads = _page()
    initial_job, checksums = _cold_start_job(tmp_path, image_count=3)
    overrides = {
        checksum: {
            "decisionChecksumSha256": f"{index + 1:x}" * 64,
            "imageHeight": 480,
            "imageWidth": 680,
            "overrideId": str(uuid4()),
            "quads": quads,
            "revision": 1,
        }
        for index, checksum in enumerate(checksums)
    }
    job = create_job(
        JobType.VALIDATE,
        game_id=initial_job.game_id,
        input_payload={**initial_job.input_payload, "page_geometry_overrides": overrides},
    )
    context = _Context()

    class _OverrideOnlyRegistrar:
        available = True

        def __init__(self, _profile, **_kwargs) -> None:
            pass

        def register(self, _rgb):
            raise AssertionError("Every source should use its direct override.")

    monkeypatch.setattr(
        preflight_module,
        "VerifiedPageRegistrar",
        _OverrideOnlyRegistrar,
    )

    PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(  # type: ignore[arg-type]
        context,
        job,
    )

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = (
        tmp_path
        / "artifacts"
        / Path(*checkpoint["geometry_manifest_relative_path"].split("/"))
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["registeredSourceCount"] == 3
    assert payload["reviewRequiredSourceCount"] == 0
    assert {
        checksum: payload["entries"][checksum]["manualOverrideDecisionChecksumSha256"]
        for checksum in checksums
    } == {
        checksum: overrides[checksum]["decisionChecksumSha256"] for checksum in checksums
    }


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
            "source_display_name": "10-18",
            "source_manifest_sha256": hashlib.sha256(browser_manifest).hexdigest(),
            "page_registration_profile": profile,
            "page_geometry_overrides": {},
            "canonical_sequence_numbers": [],
        },
    )
    ManagedOriginalStore(artifact_root).load_or_create_manifest(job, source_directory=staged)
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


def test_geometry_preflight_retries_unresolved_page_with_strict_auto_anchor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    selection_id = uuid4()
    staged = tmp_path / str(selection_id)
    staged.mkdir()
    files = []
    for index, intensity in enumerate((30, 220)):
        source = staged / f"{index:08d}.jpg"
        Image.fromarray(np.full((120, 180, 3), intensity, dtype=np.uint8), mode="RGB").save(
            source,
            format="JPEG",
        )
        content = source.read_bytes()
        files.append(
            {
                "orderIndex": index,
                "relativePath": f"seq_{index * 9 + 1}-{index * 9 + 9}.jpg",
                "storedFileName": source.name,
                "sizeBytes": len(content),
                "checksumSha256": hashlib.sha256(content).hexdigest(),
            }
        )
    browser_manifest = json.dumps(
        {
            "schemaVersion": 1,
            "purpose": "layout_import",
            "gameId": None,
            "orderingPolicy": "natural_relative_path_v1",
            "files": files,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (staged / "_browser_manifest.json").write_bytes(browser_manifest)
    quads = tuple(
        tuple(Point(column * 10 + x, row * 10 + y) for x, y in ((0, 0), (8, 0), (8, 8), (0, 8)))
        for row in range(3)
        for column in range(3)
    )

    class _Registrar:
        instances = 0

        def __init__(self, *_args, **_kwargs) -> None:
            type(self).instances += 1
            self.instance = type(self).instances
            self.available = True

        def register(self, rgb):
            if self.instance == 1 and float(rgb.mean()) > 100:
                return None
            return RegisteredPageGeometry(
                anchor_source_checksum_sha256="a" * 64,
                quads=quads,
                board_red_edge_coverages=(0.9,) * 9,
                inlier_count=80,
                inlier_ratio=0.5,
                p95_reprojection_error=1.0,
                mean_red_edge_coverage=0.9,
                feature_count=1000,
            )

    monkeypatch.setattr(preflight_module, "VerifiedPageRegistrar", _Registrar)
    job = create_job(
        JobType.VALIDATE,
        game_id=uuid4(),
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "preflight_policy_version": "page-geometry-preflight-v2-auto-anchor",
            "source_selection_id": str(selection_id),
            "source_directory": str(staged),
            "source_manifest_sha256": hashlib.sha256(browser_manifest).hexdigest(),
            "page_registration_profile": {
                "policy": PAGE_REGISTRATION_VERSION,
                "anchors": [{"sourceChecksumSha256": "c" * 64}],
            },
            "page_geometry_overrides": {},
            "canonical_sequence_numbers": [],
        },
    )
    context = _Context()

    PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(context, job)  # type: ignore[arg-type]

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = (
        tmp_path / "artifacts" / Path(*checkpoint["geometry_manifest_relative_path"].split("/"))
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["version"] == "page-geometry-preflight-v2-auto-anchor"
    assert payload["registeredSourceCount"] == 2
    assert payload["reviewRequiredSourceCount"] == 0
    assert payload["automaticAnchorPasses"][0]["resolvedSourceCount"] == 1
    assert [checkpoint["review_count"] for checkpoint in context.checkpoints] == [0, 0, 0]
