from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from game_predictor_worker.images.cell_grid_golden import (
    BoardCandidate,
    CellGridGolden,
    GridReviewEntry,
)
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.grid_calibration import (
    INTERPOLATION_VERSION,
    PROFILE_SET_VERSION,
    GridCalibrationError,
    GridCalibrationProfiles,
    build_profile_document,
    profile_document_bytes,
)
from game_predictor_worker.images.rectification import BoardGeometry, PageGeometry

DETECTION_SHA = "d" * 64
GOLDEN_SHA = "g" * 64


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _quad(shift_x: float = 0.0, shift_y: float = 0.0) -> tuple[tuple[float, float], ...]:
    return (
        (100.0 + shift_x, 100.0 + shift_y),
        (300.0 + shift_x, 95.0 + shift_y),
        (310.0 + shift_x, 220.0 + shift_y),
        (95.0 + shift_x, 225.0 + shift_y),
    )


def _entry(
    *,
    source_group: str,
    position: int,
    sequence_number: int,
    accepted_shift: tuple[float, float],
    suffix: str,
) -> GridReviewEntry:
    detected = _quad(position * 2.0, position * 1.0)
    accepted = tuple(
        (point[0] + accepted_shift[0], point[1] + accepted_shift[1])
        for point in detected
    )
    source_checksum = _sha(f"{source_group}-source")
    candidate = BoardCandidate(
        observation_id=_sha(f"{source_group}-{position}-{suffix}"),
        image_id=f"{source_group}-{suffix}",
        source_image_checksum_sha256=source_checksum,
        source_image_relative_path=f"{source_group}.jpg",
        source_image_width=1000,
        source_image_height=800,
        source_group=source_group,
        condition_tags=("test",),
        sequence_number=sequence_number,
        board_position=position,
        board_relative_path=f"boards/{source_group}-{position}.png",
        board_checksum_sha256=_sha(f"board-{source_group}-{position}-{suffix}"),
        detected_source_quad=detected,
    )
    return GridReviewEntry(
        selection_index=0,
        candidate=candidate,
        source_quad=accepted,
        v1_cut_cell_indexes=(0,),
        v1_impact_reviewed=True,
        review_status="accepted",
        reviewed_by="owner",
        decision_revision=1,
        line_source="human-adjusted",
    )


def _fixture(tmp_path: Path) -> tuple[GridCalibrationProfiles, dict[str, object], Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_groups = ("group-a", "group-b")
    manifest = {
        "corpusId": "calibration-test-corpus",
        "images": [
            {
                "expectedBoardCount": 9,
                "expectedSequenceStart": 5,
                "sha256": _sha("group-a-source"),
                "sourceGroup": "group-a",
            },
            {
                "expectedBoardCount": 9,
                "expectedSequenceStart": 1,
                "sha256": _sha("group-b-source"),
                "sourceGroup": "group-b",
            },
        ],
        "schemaVersion": 1,
        "status": "accepted",
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_bytes = _json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)

    entries: list[GridReviewEntry] = []
    for group_index, source_group in enumerate(source_groups):
        for position in range(9):
            entries.append(
                _entry(
                    source_group=source_group,
                    position=position,
                    sequence_number=position + 1,
                    accepted_shift=(2.0 + group_index, 3.0 + position / 10),
                    suffix="first",
                )
            )
    entries.append(
        _entry(
            source_group="group-a",
            position=0,
            sequence_number=10,
            accepted_shift=(12.0, 8.0),
            suffix="second",
        )
    )
    entries = [
        GridReviewEntry(
            selection_index=index,
            candidate=entry.candidate,
            source_quad=entry.source_quad,
            v1_cut_cell_indexes=entry.v1_cut_cell_indexes,
            v1_impact_reviewed=entry.v1_impact_reviewed,
            review_status=entry.review_status,
            reviewed_by=entry.reviewed_by,
            decision_revision=entry.decision_revision,
            line_source=entry.line_source,
        )
        for index, entry in enumerate(entries)
    ]
    golden = CellGridGolden(
        corpus_id="calibration-test-corpus",
        corpus_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        golden_annotations_sha256="a" * 64,
        crop_report_sha256="c" * 64,
        source_groups=source_groups,
        review_revision=1,
        entries=tuple(entries),
    )
    document = build_profile_document(
        golden,
        golden_sha256=GOLDEN_SHA,
        detector_report_sha256=DETECTION_SHA,
    )
    profile_path = tmp_path / "profiles.json"
    profile_path.write_bytes(profile_document_bytes(document))
    return (
        GridCalibrationProfiles.from_files(profile_path, manifest_path),
        document,
        profile_path,
        manifest_path,
    )


def test_profile_document_covers_every_scope_and_anchor(tmp_path: Path) -> None:
    profiles, document, _, _ = _fixture(tmp_path)

    assert document["profileSetVersion"] == PROFILE_SET_VERSION
    assert document["interpolation"] == INTERPOLATION_VERSION
    assert document["profileCount"] == 18
    assert document["anchorCount"] == 19
    profile_items = document["profiles"]
    assert isinstance(profile_items, list)
    assert all(isinstance(item, dict) for item in profile_items)
    typed_profiles = cast(list[dict[str, object]], profile_items)
    assert len({item["profileId"] for item in typed_profiles}) == 18
    assert profiles.profile_set_version == PROFILE_SET_VERSION


def test_sequence_interpolation_and_clamping_are_deterministic(tmp_path: Path) -> None:
    profiles, _, _, _ = _fixture(tmp_path)
    detected = _quad()

    first = profiles.apply(
        source_group="group-a",
        board_position=0,
        sequence_number=1,
        detected_quad=detected,
    )
    middle = profiles.apply(
        source_group="group-a",
        board_position=0,
        sequence_number=5,
        detected_quad=detected,
    )
    last = profiles.apply(
        source_group="group-a",
        board_position=0,
        sequence_number=10,
        detected_quad=detected,
    )
    before = profiles.apply(
        source_group="group-a",
        board_position=0,
        sequence_number=0,
        detected_quad=detected,
    )
    after = profiles.apply(
        source_group="group-a",
        board_position=0,
        sequence_number=99,
        detected_quad=detected,
    )

    assert first.calibrated_quad == (
        Point(102, 103),
        Point(302, 98),
        Point(312, 223),
        Point(97, 228),
    )
    assert last.calibrated_quad == (
        Point(112, 108),
        Point(312, 103),
        Point(322, 228),
        Point(107, 233),
    )
    assert middle.anchor_sequence_numbers == (1, 10)
    assert middle.interpolation_weight == pytest.approx(4 / 9)
    assert first.anchor_sequence_numbers == (1,)
    assert before == first
    assert after == last
    assert middle == profiles.apply(
        source_group="group-a",
        board_position=0,
        sequence_number=5,
        detected_quad=detected,
    )


def test_calibrator_applies_scope_and_records_provenance(tmp_path: Path) -> None:
    profiles, _, _, _ = _fixture(tmp_path)
    detected = tuple(Point(int(x), int(y)) for x, y in _quad())
    geometry = PageGeometry(
        status="detected",
        image_width=1000,
        image_height=800,
        boards=tuple(
            BoardGeometry(position_index=position, quad=detected)
            for position in range(9)
        ),
    )

    calibrated = profiles.calibrate(_sha("group-a-source"), geometry)

    assert calibrated is not geometry
    assert len(calibrated.boards) == 9
    assert calibrated.boards[0].source_quad_source == "calibration-profile"
    assert calibrated.boards[0].calibration_profile_version == 1
    assert calibrated.boards[0].calibration_anchor_sequence_numbers == (1, 10)
    assert calibrated.boards[0].calibration_interpolation_weight == pytest.approx(4 / 9)
    assert calibrated.boards[1].calibration_anchor_sequence_numbers == (2,)


def test_profile_scope_and_contract_drift_fail_explicitly(tmp_path: Path) -> None:
    profiles, document, profile_path, manifest_path = _fixture(tmp_path)
    with pytest.raises(GridCalibrationError) as missing:
        profiles.apply(
            source_group="unknown",
            board_position=0,
            sequence_number=1,
            detected_quad=_quad(),
        )
    assert missing.value.code == "GRID_CALIBRATION_SCOPE_MISSING"

    changed = json.loads(json.dumps(document))
    changed["profiles"][0]["anchors"][0]["localCornerOffsets"][0]["u"] += 0.1
    profile_path.write_bytes(_json_bytes(changed))
    with pytest.raises(GridCalibrationError) as drift:
        GridCalibrationProfiles.from_files(profile_path, manifest_path)
    assert drift.value.code == "GRID_CALIBRATION_ANCHOR_DRIFT"


def test_incomplete_profile_and_manifest_drift_fail_explicitly(tmp_path: Path) -> None:
    _, document, profile_path, manifest_path = _fixture(tmp_path)
    incomplete = json.loads(json.dumps(document))
    incomplete["profiles"].pop()
    incomplete["profileCount"] -= 1
    profile_path.write_bytes(_json_bytes(incomplete))
    with pytest.raises(GridCalibrationError) as scope:
        GridCalibrationProfiles.from_files(profile_path, manifest_path)
    assert scope.value.code == "GRID_CALIBRATION_SCOPE_INCOMPLETE"

    _, document, profile_path, manifest_path = _fixture(tmp_path / "second")
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    profile_path.write_bytes(_json_bytes(document))
    with pytest.raises(GridCalibrationError) as manifest:
        GridCalibrationProfiles.from_files(profile_path, manifest_path)
    assert manifest.value.code == "GRID_CALIBRATION_PROFILE_SET_INVALID"
