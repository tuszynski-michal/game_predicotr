from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

import pytest
from game_predictor_worker.images.cell_grid_golden import (
    CellGridGoldenError,
    CellGridGoldenReview,
    GridReviewEntry,
    baseline_report_bytes,
    build_v1_baseline_report,
)
from game_predictor_worker.images.cell_grid_v2_quality import (
    CellGridV2QualityError,
    build_calibrated_quality_report,
    build_v2_quality_report,
    v2_quality_report_bytes,
)
from game_predictor_worker.images.grid_calibration import (
    GridCalibrationProfiles,
    build_profile_document,
    profile_document_bytes,
)
from game_predictor_worker.images.rectification import (
    CALIBRATED_CROPPER_VERSION,
    V2_CROPPER_VERSION,
    V2_GRID_CONTRACT,
)
from PIL import Image


def _json_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> dict[str, Path]:
    repository = tmp_path / "repository"
    sources = repository / "examples" / "imgs"
    crop_root = tmp_path / "board-crops"
    sources.mkdir(parents=True)
    crop_root.mkdir()
    manifest_images: list[dict[str, object]] = []
    annotation_images: list[dict[str, object]] = []
    crop_images: list[dict[str, object]] = []
    sequence = 1

    for image_index in range(4):
        image_id = f"source-{image_index}"
        source_group = "session-a" if image_index < 2 else "session-b"
        source_path = sources / f"{image_id}.jpg"
        Image.new(
            "RGB",
            (960, 1280),
            (20 + image_index * 30, 40, 60),
        ).save(source_path)
        source_checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()
        sequence_start = sequence
        manifest_images.append(
            {
                "conditionTags": [
                    ["sharp", "blur", "glare", "perspective"][image_index],
                ],
                "id": image_id,
                "expectedBoardCount": 9,
                "expectedSequenceStart": sequence_start,
                "height": 1280,
                "relativePath": source_path.name,
                "sha256": source_checksum,
                "sourceGroup": source_group,
                "width": 960,
            }
        )
        annotation_boards: list[dict[str, int]] = []
        crop_boards: list[dict[str, object]] = []
        for position in range(9):
            board_relative = f"{image_id}/board-{position:02d}/board.png"
            board_path = crop_root / Path(*board_relative.split("/"))
            board_path.parent.mkdir(parents=True)
            Image.new(
                "RGB",
                (500, 300),
                (
                    20 + image_index * 30,
                    10 + position * 20,
                    (image_index * 40 + position * 7) % 255,
                ),
            ).save(board_path)
            board_checksum = hashlib.sha256(board_path.read_bytes()).hexdigest()
            annotation_boards.append({"positionIndex": position, "sequenceNumber": sequence})
            crop_boards.append(
                {
                    "boardChecksumSha256": board_checksum,
                    "boardRelativePath": board_relative,
                    "positionIndex": position,
                    "sourceQuad": [
                        {"x": 100, "y": 100},
                        {"x": 599, "y": 100},
                        {"x": 599, "y": 399},
                        {"x": 100, "y": 399},
                    ],
                }
            )
            sequence += 1
        annotation_images.append(
            {
                "boards": annotation_boards,
                "imageId": image_id,
                "status": "complete",
            }
        )
        crop_images.append(
            {
                "boards": crop_boards,
                "sourceChecksumSha256": source_checksum,
                "status": "cropped",
            }
        )

    quality = repository / "ai_docs" / "quality"
    manifest = quality / "manifest.json"
    annotations = quality / "annotations.json"
    crop_report = quality / "crop-report.json"
    golden = quality / "cell-grid-golden.json"
    _json_write(
        manifest,
        {
            "corpusId": "test-corpus",
            "imageCount": len(manifest_images),
            "images": manifest_images,
            "rootPath": "examples/imgs",
            "schemaVersion": 1,
            "status": "accepted",
        },
    )
    _json_write(
        annotations,
        {
            "coordinateSystem": "source-image-pixels-before-normalization",
            "corpusId": "test-corpus",
            "images": annotation_images,
        },
    )
    _json_write(
        crop_report,
        {
            "boardCount": 36,
            "cropperVersion": "board-cell-crops-v1",
            "images": crop_images,
            "status": "cropped",
        },
    )
    return {
        "annotations_path": annotations,
        "crop_report_path": crop_report,
        "crop_root": crop_root,
        "manifest_path": manifest,
        "output_path": golden,
        "repository_root": repository,
    }


def _review(paths: dict[str, Path]) -> CellGridGoldenReview:
    return CellGridGoldenReview(**paths)


def _accept_all(
    review: CellGridGoldenReview,
    *,
    source_quad: list[dict[str, float]] | None = None,
    cut_cells: list[int] | None = None,
) -> None:
    for entry in review.golden.entries:
        accepted_quad = source_quad or [
            {"x": point[0], "y": point[1]} for point in entry.candidate.detected_source_quad
        ]
        review.accept(
            observation_id=entry.candidate.observation_id,
            source_quad=accepted_quad,
            v1_cut_cell_indexes=cut_cells if cut_cells is not None else [0, 14],
            v1_impact_reviewed=True,
            reviewed_by="owner",
        )


def _png(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v2_crop_report(
    review: CellGridGoldenReview,
    paths: dict[str, Path],
    *,
    quad_source: str = "detector",
    cropper_version: str = V2_CROPPER_VERSION,
    profiles: GridCalibrationProfiles | None = None,
) -> Path:
    by_source: dict[str, list[GridReviewEntry]] = defaultdict(list)
    for entry in review.golden.entries:
        by_source[entry.candidate.source_image_checksum_sha256].append(entry)
    images: list[dict[str, object]] = []
    board_count = 0
    cell_count = 0
    for source_checksum in sorted(by_source):
        boards: list[dict[str, object]] = []
        for entry_value in sorted(
            by_source[source_checksum],
            key=lambda item: item.candidate.board_position,
        ):
            entry = entry_value
            candidate = entry.candidate
            board_root = Path(
                cropper_version,
                source_checksum[:2],
                source_checksum,
                f"board-{candidate.board_position:02d}",
            )
            board_relative = (board_root / "board.png").as_posix()
            overlay_relative = (board_root / "grid-overlay.png").as_posix()
            board_checksum = _png(
                paths["crop_root"] / board_root / "board.png",
                (500, 300),
                (30, 40, 50),
            )
            overlay_checksum = _png(
                paths["crop_root"] / board_root / "grid-overlay.png",
                (500, 300),
                (20, 80, 90),
            )
            cells: list[dict[str, object]] = []
            for row in range(3):
                for column in range(5):
                    relative = (board_root / "cells" / f"r{row:02d}-c{column:02d}.png").as_posix()
                    checksum = _png(
                        paths["crop_root"] / Path(*PurePosixPath(relative).parts),
                        (90, 90),
                        (20 + row * 20, 30 + column * 20, 40),
                    )
                    cells.append(
                        {
                            "checksumSha256": checksum,
                            "columnIndex": column,
                            "height": 90,
                            "relativePath": relative,
                            "rowIndex": row,
                            "width": 90,
                        }
                    )
            board: dict[str, object] = {
                "boardChecksumSha256": board_checksum,
                "boardHeight": 300,
                "boardRelativePath": board_relative,
                "boardWidth": 500,
                "cells": cells,
                "grid": V2_GRID_CONTRACT.to_dict(),
                "overlayChecksumSha256": overlay_checksum,
                "overlayRelativePath": overlay_relative,
                "positionIndex": candidate.board_position,
                "sourceQuad": [],
                "sourceQuadSource": quad_source,
                "transformMatrix": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
            }
            if profiles is None:
                board["sourceQuad"] = [
                    {"x": point[0], "y": point[1]} for point in candidate.detected_source_quad
                ]
            else:
                application = profiles.apply(
                    source_group=candidate.source_group,
                    board_position=candidate.board_position,
                    sequence_number=candidate.sequence_number,
                    detected_quad=candidate.detected_source_quad,
                )
                board["sourceQuad"] = [
                    {"x": point.x, "y": point.y} for point in application.calibrated_quad
                ]
                board["calibrationProfile"] = {
                    "anchorSequenceNumbers": list(application.anchor_sequence_numbers),
                    "interpolationWeight": application.interpolation_weight,
                    "profileId": application.profile_id,
                    "profileVersion": 1,
                }
            boards.append(board)
            board_count += 1
            cell_count += 15
        images.append(
            {
                "boards": boards,
                "normalizedRelativePath": f"normalized/{source_checksum}.png",
                "reviewReasons": [],
                "sourceChecksumSha256": source_checksum,
                "status": "cropped",
            }
        )
    output = paths["repository_root"] / "ai_docs" / "quality" / "v2-report.json"
    report: dict[str, object] = {
        "boardCount": board_count,
        "cellCount": cell_count,
        "croppedImageCount": len(images),
        "cropperVersion": cropper_version,
        "detectionReportSha256": "d" * 64,
        "imageCount": len(images),
        "images": images,
        "needsReviewCount": 0,
        "normalizationReportSha256": "n" * 64,
        "numpyVersion": "test",
        "opencvVersion": "test",
        "schemaVersion": 1,
        "status": "cropped",
    }
    if profiles is not None:
        report.update(
            {
                "calibrationProfileSetSha256": profiles.profile_set_sha256,
                "calibrationProfileSetVersion": profiles.profile_set_version,
                "corpusManifestSha256": profiles.corpus_manifest_sha256,
            }
        )
    _json_write(output, report)
    return output


def _calibration_profiles(
    review: CellGridGoldenReview,
    paths: dict[str, Path],
) -> GridCalibrationProfiles:
    profile_path = (
        paths["repository_root"] / "ai_docs" / "quality" / "grid-calibration-profiles.json"
    )
    profile_path.write_bytes(
        profile_document_bytes(
            build_profile_document(
                review.golden,
                golden_sha256=hashlib.sha256(paths["output_path"].read_bytes()).hexdigest(),
                detector_report_sha256="d" * 64,
            )
        )
    )
    return GridCalibrationProfiles.from_files(
        profile_path,
        paths["manifest_path"],
    )


def test_selection_is_deterministic_stratified_and_pending(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    review = _review(paths)
    first_bytes = paths["output_path"].read_bytes()
    second = _review(paths)

    assert second.golden.to_json_bytes() == first_bytes
    assert review.progress() == {"accepted": 0, "pending": 27, "total": 27}
    assert len(review.golden.entries) == 27
    assert Counter(entry.candidate.board_position for entry in review.golden.entries) == Counter(
        {position: 3 for position in range(9)}
    )
    groups_by_position: dict[int, set[str]] = defaultdict(set)
    for entry in review.golden.entries:
        groups_by_position[entry.candidate.board_position].add(entry.candidate.source_group)
        assert entry.review_status == "pending"
        assert entry.reviewed_by is None
        assert not entry.v1_impact_reviewed
    assert all(groups == {"session-a", "session-b"} for groups in groups_by_position.values())


def test_pristine_legacy_axis_golden_migrates_without_human_decisions(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    _review(paths)
    legacy = json.loads(paths["output_path"].read_text(encoding="utf-8"))
    legacy["coordinateSystem"] = "rectified-board-pixels-500x300"
    legacy.pop("geometryVersion")
    for entry in legacy["entries"]:
        entry["lineSource"] = "equal-grid-suggestion"
        entry["verticalLines"] = [100, 200, 300, 400]
        entry["horizontalLines"] = [100, 200]
        entry.pop("sourceQuad")
        entry.pop("suggestionVersion")
    _json_write(paths["output_path"], legacy)

    migrated = _review(paths)

    assert migrated.progress() == {"accepted": 0, "pending": 27, "total": 27}
    persisted = json.loads(paths["output_path"].read_text(encoding="utf-8"))
    assert persisted["geometryVersion"] == "source-quad-perspective-grid-v1"
    assert persisted["coordinateSystem"] == "source-image-pixels"
    assert persisted["reviewRevision"] == 0
    assert all(entry["decisionRevision"] == 0 for entry in persisted["entries"])
    assert all(entry["sourceQuad"] == entry["detectedSourceQuad"] for entry in persisted["entries"])


def test_source_checksum_drift_fails_explicitly(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _review(paths)
    source = paths["repository_root"] / "examples" / "imgs" / "source-0.jpg"
    source.write_bytes(b"changed")

    with pytest.raises(CellGridGoldenError) as error:
        _review(paths)

    assert error.value.code == "CELL_GRID_ARTIFACT_DRIFT"


def test_grid_validation_and_acceptance_are_explicit(tmp_path: Path) -> None:
    review = _review(_fixture(tmp_path))
    observation_id = review.golden.entries[0].candidate.observation_id

    with pytest.raises(CellGridGoldenError) as lines_error:
        review.save_draft(
            observation_id=observation_id,
            source_quad=[
                {"x": 100, "y": 100},
                {"x": 599, "y": 399},
                {"x": 599, "y": 100},
                {"x": 100, "y": 399},
            ],
            v1_cut_cell_indexes=[],
            v1_impact_reviewed=False,
        )
    assert lines_error.value.code == "CELL_GRID_QUAD_INVALID"

    with pytest.raises(CellGridGoldenError) as impact_error:
        review.accept(
            observation_id=observation_id,
            source_quad=[
                {"x": 100, "y": 100},
                {"x": 599, "y": 100},
                {"x": 599, "y": 399},
                {"x": 100, "y": 399},
            ],
            v1_cut_cell_indexes=[0],
            v1_impact_reviewed=False,
            reviewed_by="owner",
        )
    assert impact_error.value.code == "CELL_GRID_V1_IMPACT_NOT_REVIEWED"


def test_draft_accept_resume_reopen_and_idempotency(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    review = _review(paths)
    observation_id = review.golden.entries[0].candidate.observation_id
    arguments = {
        "observation_id": observation_id,
        "source_quad": [
            {"x": 98, "y": 101},
            {"x": 601, "y": 99},
            {"x": 600, "y": 401},
            {"x": 99, "y": 400},
        ],
        "v1_cut_cell_indexes": [0, 2, 14],
        "v1_impact_reviewed": True,
    }

    assert review.save_draft(**arguments)
    assert not review.save_draft(**arguments)
    assert review.accept(**arguments, reviewed_by="owner")
    assert not review.accept(**arguments, reviewed_by="owner")
    resumed = _review(paths)
    accepted = resumed.state(status="accepted")["samples"]
    assert len(accepted) == 1
    assert accepted[0]["sourceQuad"] == arguments["source_quad"]
    assert resumed.reopen(observation_id)
    assert not resumed.reopen(observation_id)
    again = _review(paths)
    assert again.progress() == {"accepted": 0, "pending": 27, "total": 27}


def test_baseline_requires_complete_review_and_calculates_metrics(
    tmp_path: Path,
) -> None:
    review = _review(_fixture(tmp_path))
    with pytest.raises(CellGridGoldenError) as incomplete:
        build_v1_baseline_report(review)
    assert incomplete.value.code == "CELL_GRID_BASELINE_REVIEW_INCOMPLETE"

    _accept_all(review)
    report = build_v1_baseline_report(review)

    assert report["status"] == "historical_cropper_rejected"
    assert report["trainingAllowed"] is False
    assert report["goldenAcceptedEntryCount"] == 27
    assert report["affectedBoardCount"] == 27
    assert report["affectedCellObservationCount"] == 54
    assert len(report["lineErrors"]) == 162
    assert len(report["quadErrors"]) == 108
    assert report["summary"]["overall"] == {
        "lineCount": 162,
        "maxAbsoluteErrorPx": 15,
        "p50AbsoluteErrorPx": 5.0,
        "p95AbsoluteErrorPx": 15.0,
    }
    assert report["summary"]["quadCornersOverall"] == {
        "lineCount": 108,
        "maxAbsoluteErrorPx": 0.0,
        "p50AbsoluteErrorPx": 0.0,
        "p95AbsoluteErrorPx": 0.0,
    }
    assert baseline_report_bytes(review) == baseline_report_bytes(review)


def test_v2_quality_passes_exact_detector_quad_and_is_deterministic(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    review = _review(paths)
    _accept_all(review)
    crop_report = _v2_crop_report(review, paths)

    report = build_v2_quality_report(
        review,
        crop_report_path=crop_report,
        crop_root=paths["crop_root"],
    )

    assert report["status"] == "passed"
    assert report["trainingAllowed"] is True
    assert report["nextTask"] is None
    assert report["artifactVerification"] == {
        "verifiedBoardCount": 27,
        "verifiedCellCount": 405,
    }
    assert report["summary"]["overall"]["p95AbsoluteErrorPx"] == 0.0
    assert v2_quality_report_bytes(
        review,
        crop_report_path=crop_report,
        crop_root=paths["crop_root"],
    ) == v2_quality_report_bytes(
        review,
        crop_report_path=crop_report,
        crop_root=paths["crop_root"],
    )


def test_calibrated_quality_requires_published_profile_provenance(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    review = _review(paths)
    _accept_all(
        review,
        source_quad=[
            {"x": 90, "y": 95},
            {"x": 590, "y": 95},
            {"x": 590, "y": 405},
            {"x": 90, "y": 405},
        ],
    )
    profiles = _calibration_profiles(review, paths)
    crop_report = _v2_crop_report(
        review,
        paths,
        quad_source="calibration-profile",
        cropper_version=CALIBRATED_CROPPER_VERSION,
        profiles=profiles,
    )

    report = build_calibrated_quality_report(
        review,
        crop_report_path=crop_report,
        crop_root=paths["crop_root"],
        profiles=profiles,
    )

    assert report["status"] == "passed"
    assert report["trainingAllowed"] is True
    assert report["nextTask"] == "TASK-0097"
    assert report["calibrationProfileSetSha256"] == profiles.profile_set_sha256
    assert report["summary"]["overall"]["p95AbsoluteErrorPx"] <= 5
    assert report["artifactVerification"] == {
        "verifiedBoardCount": 27,
        "verifiedCellCount": 405,
    }

    value = json.loads(crop_report.read_text(encoding="utf-8"))
    value["images"][0]["boards"][0]["calibrationProfile"]["profileId"] = "f" * 64
    _json_write(crop_report, value)
    with pytest.raises(CellGridV2QualityError) as provenance:
        build_calibrated_quality_report(
            review,
            crop_report_path=crop_report,
            crop_root=paths["crop_root"],
            profiles=profiles,
        )
    assert provenance.value.code == "CELL_GRID_V2_CALIBRATION_PROVENANCE_DRIFT"


def test_v2_quality_quarantines_detector_error_without_using_golden_override(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    review = _review(paths)
    _accept_all(
        review,
        source_quad=[
            {"x": 90, "y": 95},
            {"x": 590, "y": 95},
            {"x": 590, "y": 405},
            {"x": 90, "y": 405},
        ],
    )
    crop_report = _v2_crop_report(review, paths)

    report = build_v2_quality_report(
        review,
        crop_report_path=crop_report,
        crop_root=paths["crop_root"],
    )

    assert report["status"] == "quarantined_calibration_required"
    assert report["trainingAllowed"] is False
    assert report["nextTask"] == "TASK-0096"
    assert report["summary"]["overall"]["p95AbsoluteErrorPx"] > 5

    value = json.loads(crop_report.read_text(encoding="utf-8"))
    value["images"][0]["boards"][0]["sourceQuadSource"] = "golden"
    _json_write(crop_report, value)
    with pytest.raises(CellGridV2QualityError) as circular:
        build_v2_quality_report(
            review,
            crop_report_path=crop_report,
            crop_root=paths["crop_root"],
        )
    assert circular.value.code == "CELL_GRID_V2_EVALUATION_CIRCULAR"


def test_resolve_board_revalidates_the_artifact(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    review = _review(paths)
    entry = review.golden.entries[0]
    path, checksum = review.resolve_board(entry.candidate.observation_id)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum

    Image.new("RGB", (500, 300), (255, 255, 255)).save(path)
    with pytest.raises(CellGridGoldenError) as error:
        review.resolve_board(entry.candidate.observation_id)
    assert error.value.code == "CELL_GRID_ARTIFACT_DRIFT"
