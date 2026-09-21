from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import cv2
import game_predictor_worker.images.page_geometry_preflight as preflight_module
import numpy as np
import pytest
from game_predictor_api.domain.global_geometry_library import (
    GlobalGeometryTopology,
    global_geometry_profile_descriptor_checksum,
)
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.page_geometry_incremental import (
    PageGeometryCheckpointStore,
)
from game_predictor_worker.images.page_geometry_preflight import PageGeometryPreflightHandler
from game_predictor_worker.images.page_geometry_registration import (
    PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    PAGE_REGISTRATION_VERSION,
    PageRegistrationEvaluation,
    RegisteredPageGeometry,
)
from game_predictor_worker.images.shape_geometry_v2.preflight import (
    SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION,
)
from game_predictor_worker.images.source_ingestion import ManagedOriginalStore
from game_predictor_worker.jobs.runtime import JobHandlerError
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


def _shape_geometry_v2_profile_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": "shape-geometry-v2-preflight-profile-v1",
        "profileId": str(uuid4()),
        "profileNumber": 1,
        "profileChecksumSha256": "a" * 64,
        "geometryFamily": "framed_full_page_v2",
        "topology": {
            "pageBoardRows": 3,
            "pageBoardColumns": 3,
            "boardCellRows": 3,
            "boardCellColumns": 5,
        },
        "normalizedTemplate": {
            "schemaVersion": "shape-geometry-normalized-template-v1",
            "topology": {
                "pageBoardRows": 3,
                "pageBoardColumns": 3,
                "boardCellRows": 3,
                "boardCellColumns": 5,
            },
            "frameQuad": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            "aspectRatioRange": {"minimum": 0.5, "maximum": 2.0},
        },
        "frameAppearance": {
            "schemaVersion": "shape-geometry-frame-appearance-v1",
            "sides": {
                "top": {
                    "clusters": [{"lab": [44.0, 12.0, -8.0], "hsv": [23.0, 0.5, 0.7]}],
                    "contrast": {"minimum": 0.2, "median": 0.4, "maximum": 0.8},
                    "continuity": 0.9,
                }
            },
        },
        "localVerification": {
            "schemaVersion": "shape-geometry-v2-local-policy-v1",
            "colorCompatibility": "structural_only",
        },
    }
    topology = GlobalGeometryTopology(3, 3, 3, 5)
    payload["profileDescriptorChecksumSha256"] = global_geometry_profile_descriptor_checksum(
        geometry_family=payload["geometryFamily"],
        topology=topology,
        normalized_template=payload["normalizedTemplate"],  # type: ignore[arg-type]
        frame_appearance=payload["frameAppearance"],  # type: ignore[arg-type]
    )
    return payload


def test_preflight_preserves_qualified_slots_in_pinned_input(tmp_path: Path) -> None:
    from game_predictor_api.domain.geometry_qualification import GeometryQualification

    initial, checksums = _cold_start_job(tmp_path, image_count=1)
    job = create_job(
        JobType.VALIDATE,
        game_id=initial.game_id,
        input_payload={
            **initial.input_payload,
            "page_geometry_overrides": {
                checksums[0]: {"slotQualifications": [GeometryQualification().to_dict()] * 9}
            },
        },
    )
    normalized = preflight_module._input(job)
    assert normalized["pageGeometryOverrides"] == job.input_payload["page_geometry_overrides"]


def test_masked_preflight_policy_is_pinned_and_unknown_policy_fails_closed(
    tmp_path: Path,
) -> None:
    base, _checksums = _cold_start_job(tmp_path, image_count=1)
    masked = create_job(
        JobType.VALIDATE,
        game_id=base.game_id,
        input_payload={
            **base.input_payload,
            "preflight_policy_version": "page-geometry-preflight-v3-board-area-mask",
            "page_registration_profile": {
                "schemaVersion": 1,
                "policy": PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
                "anchors": [],
            },
        },
    )

    normalized = preflight_module._input(masked)

    assert normalized["preflightPolicyVersion"] == "page-geometry-preflight-v3-board-area-mask"
    with pytest.raises(JobHandlerError) as captured:
        preflight_module._input(
            create_job(
                JobType.VALIDATE,
                game_id=base.game_id,
                input_payload={
                    **base.input_payload,
                    "preflight_policy_version": "page-geometry-preflight-v999",
                },
            )
        )
    assert captured.value.code == "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD"


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
    final_board_count: int = 9,
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
                "relativePath": (
                    f"seq_{index * 9 + 1}-"
                    f"{index * 9 + (final_board_count if index == image_count - 1 else 9)}.jpg"
                ),
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


def test_shape_geometry_profile_is_pinned_to_manifest_and_never_registers_directly(
    tmp_path: Path,
) -> None:
    initial, checksums = _cold_start_job(tmp_path, image_count=1)
    profile = _shape_geometry_v2_profile_payload()
    job = create_job(
        JobType.VALIDATE,
        game_id=initial.game_id,
        input_payload={
            **initial.input_payload,
            "preflight_policy_version": SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION,
            "shape_geometry_v2_profile": profile,
        },
    )
    context = _Context()

    PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(context, job)  # type: ignore[arg-type]

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = tmp_path / "artifacts" / Path(
        *checkpoint["geometry_manifest_relative_path"].split("/")
    )
    manifest = json.loads(output.read_text(encoding="utf-8"))
    entry = manifest["entries"][checksums[0]]
    assert manifest["schemaVersion"] == 3
    assert manifest["shapeGeometryV2Profile"] == profile
    assert entry["status"] == "review_required"
    assert "quads" not in entry
    assert entry["shapeGeometryV2Verification"]["schemaVersion"] == (
        "shape-geometry-v2-local-verification-v1"
    )


def test_shape_geometry_profile_ignores_an_unavailable_legacy_anchor(tmp_path: Path) -> None:
    _image, quads = _page()
    initial, checksums = _cold_start_job(tmp_path, image_count=1)
    job = create_job(
        JobType.VALIDATE,
        game_id=initial.game_id,
        input_payload={
            **initial.input_payload,
            "preflight_policy_version": SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION,
            "shape_geometry_v2_profile": _shape_geometry_v2_profile_payload(),
            "page_registration_profile": {
                "schemaVersion": 1,
                "policy": PAGE_REGISTRATION_VERSION,
                "anchors": [
                    {
                        "sourceChecksumSha256": "a" * 64,
                        "imageWidth": 680,
                        "imageHeight": 480,
                        "quads": quads,
                    }
                ],
            },
        },
    )
    context = _Context()

    PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(context, job)  # type: ignore[arg-type]

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = tmp_path / "artifacts" / Path(
        *checkpoint["geometry_manifest_relative_path"].split("/")
    )
    entry = json.loads(output.read_text(encoding="utf-8"))["entries"][checksums[0]]
    assert entry["status"] == "review_required"
    assert "SHAPE_GEOMETRY_V2" in entry["reasonCode"]


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

        def evaluate(self, rgb):
            return PageRegistrationEvaluation(self.register(rgb))

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


def test_manual_override_anchor_loads_from_current_staging_before_managed_original(
    tmp_path: Path,
) -> None:
    _image, quads = _page()
    initial_job, checksums = _cold_start_job(tmp_path, image_count=2)
    override = {
        checksums[0]: {
            "decisionChecksumSha256": "f" * 64,
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
    artifact_root = tmp_path / "artifacts"
    managed_anchor = (
        artifact_root / "data" / "originals" / checksums[0][:2] / (f"{checksums[0]}.jpg")
    )
    context = _Context()

    PageGeometryPreflightHandler(artifact_root=artifact_root)(  # type: ignore[arg-type]
        context,
        job,
    )

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = artifact_root / Path(*checkpoint["geometry_manifest_relative_path"].split("/"))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert managed_anchor.exists() is False
    assert payload["entries"][checksums[0]]["status"] == "registered"
    assert payload["entries"][checksums[0]]["registrationVersion"] == (
        "manual-page-geometry-override-v1"
    )
    assert payload["entries"][checksums[1]]["anchorSourceChecksumSha256"] == checksums[0]


def test_missing_current_staging_override_anchor_reports_source_unavailable(
    tmp_path: Path,
) -> None:
    _image, quads = _page()
    initial_job, checksums = _cold_start_job(tmp_path, image_count=1)
    override = {
        checksums[0]: {
            "decisionChecksumSha256": "e" * 64,
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
    source_directory = Path(str(job.input_payload["source_directory"]))
    (source_directory / "00000000.jpg").unlink()

    with pytest.raises(
        preflight_module.JobHandlerError,
        match="A staged image cannot be decoded for geometry preflight",
    ) as error:
        PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(
            _Context(),
            job,
        )  # type: ignore[arg-type]

    assert error.value.code == "IMAGE_PAGE_GEOMETRY_SOURCE_UNAVAILABLE"


def test_missing_historical_profile_anchor_remains_fail_closed(tmp_path: Path) -> None:
    _image, quads = _page()
    initial_job, _checksums = _cold_start_job(tmp_path, image_count=1)
    historical_checksum = "a" * 64
    job = create_job(
        JobType.VALIDATE,
        game_id=initial_job.game_id,
        input_payload={
            **initial_job.input_payload,
            "page_registration_profile": {
                "schemaVersion": 1,
                "policy": PAGE_REGISTRATION_VERSION,
                "anchors": [
                    {
                        "sourceChecksumSha256": historical_checksum,
                        "imageWidth": 680,
                        "imageHeight": 480,
                        "quads": quads,
                    }
                ],
            },
        },
    )

    with pytest.raises(
        preflight_module.JobHandlerError,
        match="A reviewed geometry anchor image is unavailable",
    ) as error:
        PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(
            _Context(),
            job,
        )  # type: ignore[arg-type]

    assert error.value.code == "IMAGE_PAGE_GEOMETRY_ANCHOR_UNAVAILABLE"


def test_missing_optional_historical_override_anchor_is_skipped(tmp_path: Path) -> None:
    _image, quads = _page()
    initial_job, checksums = _cold_start_job(tmp_path, image_count=1)
    historical_checksum = "b" * 64
    job = create_job(
        JobType.VALIDATE,
        game_id=initial_job.game_id,
        input_payload={
            **initial_job.input_payload,
            "page_geometry_overrides": {
                historical_checksum: {
                    "decisionChecksumSha256": "c" * 64,
                    "imageHeight": 480,
                    "imageWidth": 680,
                    "overrideId": str(uuid4()),
                    "quads": quads,
                    "revision": 1,
                }
            },
        },
    )
    context = _Context()

    PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(
        context,
        job,
    )  # type: ignore[arg-type]

    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = (tmp_path / "artifacts") / Path(
        *checkpoint["geometry_manifest_relative_path"].split("/")
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["registeredSourceCount"] == 0
    assert payload["reviewRequiredSourceCount"] == 1
    assert payload["entries"][checksums[0]]["reasonCode"] == (
        "PAGE_GEOMETRY_BOOTSTRAP_ANCHOR_REQUIRED"
    )


def test_manual_override_registers_attested_five_board_final_page(tmp_path: Path) -> None:
    _image, quads = _page()
    initial_job, checksums = _cold_start_job(
        tmp_path,
        image_count=1,
        final_board_count=5,
    )
    override = {
        checksums[0]: {
            "decisionChecksumSha256": "e" * 64,
            "expectedBoardCount": 5,
            "imageHeight": 480,
            "imageWidth": 680,
            "overrideId": str(uuid4()),
            "quads": quads[:5],
            "revision": 1,
        }
    }
    job = create_job(
        JobType.VALIDATE,
        game_id=initial_job.game_id,
        input_payload={**initial_job.input_payload, "page_geometry_overrides": override},
    )
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
    entry = payload["entries"][checksums[0]]
    assert payload["registeredSourceCount"] == 1
    assert payload["reviewRequiredSourceCount"] == 0
    assert len(entry["quads"]) == 5
    assert len(entry["boardRedEdgeCoverages"]) == 5


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
        tmp_path / "artifacts" / Path(*checkpoint["geometry_manifest_relative_path"].split("/"))
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["registeredSourceCount"] == 3
    assert payload["reviewRequiredSourceCount"] == 0
    assert {
        checksum: payload["entries"][checksum]["manualOverrideDecisionChecksumSha256"]
        for checksum in checksums
    } == {checksum: overrides[checksum]["decisionChecksumSha256"] for checksum in checksums}


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
    intensities = (30, *range(150, 177))
    for index, intensity in enumerate(intensities):
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

        def evaluate(self, rgb):
            result = self.register(rgb)
            return PageRegistrationEvaluation(result)

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
    assert payload["registeredSourceCount"] == len(intensities)
    assert payload["reviewRequiredSourceCount"] == 0
    assert payload["automaticAnchorPasses"][0]["resolvedSourceCount"] == len(intensities) - 1
    retry_checkpoints = [
        checkpoint
        for checkpoint in context.checkpoints
        if checkpoint["checkpoint_payload"].get("progress_phase") == "auto_anchor_retry"
        and checkpoint["checkpoint_payload"].get("auto_anchor_pass") == 1
    ]
    phase_positions = [
        checkpoint["checkpoint_payload"]["phase_current"] for checkpoint in retry_checkpoints
    ]
    assert phase_positions == [
        0,
        25,
        27,
    ]
    assert all(
        checkpoint["checkpoint_payload"]["phase_total"] == 27 for checkpoint in retry_checkpoints
    )
    assert context.checkpoints[-2]["stage"] == "page_geometry_manifest_writing"
    assert context.checkpoints[-1]["stage"] == "page_geometry_manifest_ready"
    assert all(checkpoint["review_count"] == 0 for checkpoint in context.checkpoints)


def test_auto_anchor_retry_resume_stops_after_a_durable_zero_resolution_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checksum = "a" * 64
    entries: dict[str, object] = {checksum: {"status": "registered"}}
    reports = [
        {"pass": 1, "promotedAnchorChecksums": ["b" * 64], "resolvedSourceCount": 0}
    ]
    store = PageGeometryCheckpointStore(
        tmp_path,
        job_id=str(uuid4()),
        input_fingerprint_sha256="c" * 64,
        source_inventory_checksum_sha256="d" * 64,
    )
    state = store.initialize(
        entries,
        metadata={
            "phase": "auto_anchor_retry",
            "autoAnchorPasses": reports,
            "activeAutoAnchorPass": None,
        },
    )
    monkeypatch.setattr(preflight_module, "_strong_auto_anchor", lambda _entry: True)

    def unexpected_registrar(*_args: object, **_kwargs: object) -> None:
        pytest.fail("A completed zero-resolution pass must not create another registrar")

    monkeypatch.setattr(preflight_module, "VerifiedPageRegistrar", unexpected_registrar)
    result_entries, result_reports, result_state = (
        PageGeometryPreflightHandler(artifact_root=tmp_path)
        ._retry_with_verified_auto_anchors(  # noqa: SLF001
            entries,
            (),
            context=_Context(),  # type: ignore[arg-type]
            source_directory=tmp_path,
            payload={},
            base_profile={"anchors": []},
            checkpoint_store=store,
            checkpoint_state=state,
            reused_source_count=0,
            recomputed_source_count=0,
        )
    )
    assert result_entries == entries
    assert result_reports == reports
    assert result_state == state


def test_geometry_preflight_resumes_from_artifact_ahead_of_database_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, _checksums = _cold_start_job(tmp_path, image_count=30)
    calls = 0
    original_evaluate = PageGeometryPreflightHandler._evaluate_source

    def counted_evaluate(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original_evaluate(self, *args, **kwargs)

    monkeypatch.setattr(PageGeometryPreflightHandler, "_evaluate_source", counted_evaluate)

    class _InterruptedContext:
        def checkpoint(self, **_kwargs: object) -> None:
            raise RuntimeError("database response lost after durable state")

    artifact_root = tmp_path / "artifacts"
    with pytest.raises(RuntimeError, match="database response lost"):
        PageGeometryPreflightHandler(artifact_root=artifact_root)(
            _InterruptedContext(), job  # type: ignore[arg-type]
        )
    assert calls == 25

    calls = 0
    context = _Context()
    PageGeometryPreflightHandler(artifact_root=artifact_root)(
        context,
        replace(job, checkpoint_payload=None),  # type: ignore[arg-type]
    )

    assert calls == 5
    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    output = artifact_root / Path(
        *checkpoint["geometry_manifest_relative_path"].split("/")
    )
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["sourceCount"] == 30
    assert manifest["reuseProvenance"]["reusedSourceCount"] == 0
    assert manifest["reuseProvenance"]["recomputedSourceCount"] == 30


def test_parallel_registration_writes_same_manifest_as_serial_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, _checksums = _cold_start_job(tmp_path, image_count=30)
    _image, raw_quads = _page()
    quads = tuple(
        tuple(Point(point["x"], point["y"]) for point in raw_quad)
        for raw_quad in raw_quads
    )

    class _DeterministicRegistrar:
        available = True

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def prepare(self) -> None:
            pass

        def evaluate(self, rgb: np.ndarray) -> PageRegistrationEvaluation:
            delay = hashlib.sha256(rgb.tobytes()).digest()[0] % 5
            time.sleep(delay / 1000)
            return PageRegistrationEvaluation(
                RegisteredPageGeometry(
                    anchor_source_checksum_sha256="a" * 64,
                    quads=quads,
                    board_red_edge_coverages=(0.9,) * 9,
                    inlier_count=80,
                    inlier_ratio=0.5,
                    p95_reprojection_error=1.0,
                    mean_red_edge_coverage=0.9,
                    feature_count=1000,
                )
            )

    monkeypatch.setattr(preflight_module, "VerifiedPageRegistrar", _DeterministicRegistrar)

    manifests: list[bytes] = []
    for worker_count in (1, 7):
        artifact_root = tmp_path / f"artifacts-{worker_count}"
        context = _Context()
        PageGeometryPreflightHandler(
            artifact_root=artifact_root,
            registration_workers=worker_count,
        )(context, job)  # type: ignore[arg-type]
        checkpoint = context.checkpoints[-1]["checkpoint_payload"]
        output = artifact_root / Path(
            *checkpoint["geometry_manifest_relative_path"].split("/")
        )
        manifests.append(output.read_bytes())

    assert manifests[0] == manifests[1]
