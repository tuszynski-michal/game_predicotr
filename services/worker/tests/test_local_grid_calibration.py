from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images.cell_grid_golden import (
    BoardCandidate,
    CellGridGolden,
    GridReviewEntry,
)
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.local_grid_calibration import (
    BASIS_VERSION,
    MISSING_PROFILE_REASON,
    PROFILE_SET_VERSION,
    LocalGridCalibrationError,
    LocalImageGridCalibrationProfiles,
    build_local_profile_document,
    local_bounding_frame,
    local_profile_document_bytes,
)
from game_predictor_worker.images.local_grid_review import LocalGridCalibrationReview
from game_predictor_worker.images.rectification import BoardGeometry, PageGeometry


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _fixture(
    tmp_path: Path,
) -> tuple[
    LocalImageGridCalibrationProfiles,
    dict[str, object],
    Path,
    Path,
    str,
    str,
]:
    source_a = _sha("source-a")
    source_b = _sha("source-b")
    manifest = {
        "corpusId": "local-calibration-test",
        "images": [
            {
                "expectedBoardCount": 2,
                "expectedSequenceStart": 1,
                "sha256": source_a,
                "sourceGroup": "group-a",
            },
            {
                "expectedBoardCount": 2,
                "expectedSequenceStart": 3,
                "sha256": source_b,
                "sourceGroup": "group-a",
            },
        ],
        "schemaVersion": 1,
        "status": "accepted",
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_bytes = _json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    detected_quad = (
        (105.0, 110.0),
        (295.0, 100.0),
        (300.0, 220.0),
        (100.0, 225.0),
    )
    accepted_quad = (
        (95.0, 105.0),
        (310.0, 100.0),
        (315.0, 230.0),
        (90.0, 235.0),
    )
    candidate = BoardCandidate(
        observation_id=_sha("observation-a"),
        image_id="image-a",
        source_image_checksum_sha256=source_a,
        source_image_relative_path="a.jpg",
        source_image_width=1000,
        source_image_height=800,
        source_group="group-a",
        condition_tags=("test",),
        sequence_number=1,
        board_position=0,
        board_relative_path="old/board.png",
        board_checksum_sha256=_sha("board-a"),
        detected_source_quad=detected_quad,
    )
    entry = GridReviewEntry(
        selection_index=0,
        candidate=candidate,
        source_quad=accepted_quad,
        v1_cut_cell_indexes=(0,),
        v1_impact_reviewed=True,
        review_status="accepted",
        reviewed_by="owner",
        decision_revision=1,
        line_source="human-adjusted",
    )
    golden = CellGridGolden(
        corpus_id="local-calibration-test",
        corpus_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        golden_annotations_sha256=_sha("annotations"),
        crop_report_sha256=_sha("crops"),
        source_groups=("group-a",),
        review_revision=1,
        entries=(entry,),
    )
    detection = {
        "detections": [
            {
                "result": {
                    "boards": [
                        {
                            "boundingBox": {
                                "height": 140,
                                "width": 220,
                                "x": 90,
                                "y": 95,
                            },
                            "positionIndex": 0,
                        },
                        {
                            "boundingBox": {
                                "height": 120,
                                "width": 200,
                                "x": 350,
                                "y": 100,
                            },
                            "positionIndex": 1,
                        },
                    ]
                },
                "sourceChecksumSha256": source_a,
            },
            {
                "result": {"boards": []},
                "sourceChecksumSha256": source_b,
            },
        ],
        "detectorVersion": "page-board-detector-v2",
    }
    document = build_local_profile_document(
        golden,
        golden_sha256=_sha("golden"),
        detector_report_sha256=_sha("detection"),
        detection_report=detection,
        corpus_manifest=manifest,
    )
    profile_path = tmp_path / "profiles.json"
    profile_path.write_bytes(local_profile_document_bytes(document))
    return (
        LocalImageGridCalibrationProfiles.from_files(profile_path, manifest_path),
        document,
        profile_path,
        manifest_path,
        source_a,
        source_b,
    )


def test_local_profile_document_is_exact_source_and_lists_missing_images(
    tmp_path: Path,
) -> None:
    _, document, _, _, source_a, source_b = _fixture(tmp_path)

    assert document["profileSetVersion"] == PROFILE_SET_VERSION
    assert document["basisVersion"] == BASIS_VERSION
    assert document["coveredSourceImageCount"] == 1
    assert document["sourceImageCount"] == 2
    assert document["missingSourceImageChecksums"] == [source_b]
    assert document["status"] == "partial_review_required"
    assert document["trainingAllowed"] is False
    profile = document["profiles"][0]
    assert profile["sourceImageChecksumSha256"] == source_a
    assert profile["anchor"]["localBaseQuad"] == [
        {"x": 90.0, "y": 95.0},
        {"x": 309.0, "y": 95.0},
        {"x": 309.0, "y": 234.0},
        {"x": 90.0, "y": 234.0},
    ]


def test_calibrator_uses_each_board_local_frame_without_cross_source_fallback(
    tmp_path: Path,
) -> None:
    profiles, _, _, _, source_a, source_b = _fixture(tmp_path)
    geometry = PageGeometry(
        status="detected",
        image_width=1000,
        image_height=800,
        boards=(
            BoardGeometry(
                position_index=0,
                quad=tuple(
                    Point(int(x), int(y)) for x, y in local_bounding_frame((90, 95, 220, 140))
                ),
                bounding_box=(90, 95, 220, 140),
            ),
            BoardGeometry(
                position_index=1,
                quad=tuple(
                    Point(int(x), int(y)) for x, y in local_bounding_frame((350, 100, 200, 120))
                ),
                bounding_box=(350, 100, 200, 120),
            ),
        ),
    )

    calibrated = profiles.calibrate(source_a, geometry)
    missing = profiles.calibrate(source_b, geometry)

    assert calibrated.status == "detected"
    assert len(calibrated.boards) == 2
    assert calibrated.boards[0].quad == (
        Point(95, 105),
        Point(310, 100),
        Point(315, 230),
        Point(90, 235),
    )
    assert calibrated.boards[1].quad != calibrated.boards[0].quad
    assert calibrated.boards[1].source_quad_source == "local-image-calibration-profile"
    assert calibrated.boards[1].calibration_anchor_sequence_numbers == (1,)
    assert missing.status == "needs_review"
    assert missing.boards == ()
    assert missing.review_reasons == (MISSING_PROFILE_REASON,)


def test_missing_bounding_frame_and_profile_drift_fail_explicitly(
    tmp_path: Path,
) -> None:
    profiles, document, profile_path, manifest_path, source_a, _ = _fixture(tmp_path)
    geometry = PageGeometry(
        status="detected",
        image_width=1000,
        image_height=800,
        boards=(
            BoardGeometry(position_index=0, quad=(Point(1, 1),) * 4),
            BoardGeometry(position_index=1, quad=(Point(2, 2),) * 4),
        ),
    )
    with pytest.raises(LocalGridCalibrationError) as missing:
        profiles.calibrate(source_a, geometry)
    assert missing.value.code == "LOCAL_GRID_CALIBRATION_BOUNDING_BOX_MISSING"

    changed = json.loads(json.dumps(document))
    changed["profiles"][0]["anchor"]["localCornerOffsets"][0]["u"] += 0.01
    profile_path.write_bytes(_json_bytes(changed))
    with pytest.raises(LocalGridCalibrationError) as drift:
        LocalImageGridCalibrationProfiles.from_files(profile_path, manifest_path)
    assert drift.value.code == "LOCAL_GRID_CALIBRATION_PROFILE_INVALID"


def test_real_corrective_review_has_missing_anchors_and_disjoint_heldout(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[3]
    output = tmp_path / "local-review.json"
    arguments = {
        "repository_root": root,
        "manifest_path": root / "ai_docs/quality/m5-corpus-manifest.json",
        "annotations_path": root / "ai_docs/quality/m5-golden-annotations.json",
        "crop_report_path": root / "ai_docs/quality/m5-board-cell-crops-report.json",
        "crop_root": root / "artifacts/m5-board-crops",
        "profiles_path": (root / "ai_docs/quality/m5-local-grid-calibration-profiles.json"),
        "detection_report_path": (root / "ai_docs/quality/m5-page-board-detection-report.json"),
        "output_path": output,
    }
    review = LocalGridCalibrationReview(**arguments)
    state = review.state(status="all", limit=100)
    samples = state["samples"]
    assert isinstance(samples, list)
    missing = [sample for sample in samples if sample["purpose"] == "missing_anchor"]
    heldout = [sample for sample in samples if sample["purpose"] == "heldout"]
    profiles = json.loads(arguments["profiles_path"].read_bytes())
    anchor_position_by_source = {
        profile["sourceImageChecksumSha256"]: profile["anchor"]["boardPosition"]
        for profile in profiles["profiles"]
    }

    assert len(missing) == 16
    assert len(heldout) == 9
    assert {sample["boardPosition"] for sample in heldout} == set(range(9))
    assert len({sample["sourceImageChecksumSha256"] for sample in heldout}) == 9
    assert all(
        anchor_position_by_source[sample["sourceImageChecksumSha256"]] != sample["boardPosition"]
        for sample in heldout
    )
    assert all(sample["v1CutCellIndexes"] == [] for sample in samples)
    assert output.exists()

    stale_pristine = json.loads(output.read_bytes())
    for entry in stale_pristine["entries"]:
        entry["v1CutCellIndexes"] = list(range(15))
    output.write_bytes(_json_bytes(stale_pristine))

    reloaded = LocalGridCalibrationReview(**arguments)
    assert all(
        sample["v1CutCellIndexes"] == []
        for sample in reloaded.state(status="all", limit=100)["samples"]
    )
    assert reloaded.progress() == {
        "accepted": 0,
        "pending": 25,
        "total": 25,
    }
