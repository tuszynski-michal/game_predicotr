from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.page_geometry_registration import PAGE_REGISTRATION_VERSION
from game_predictor_worker.images.shape_geometry_v2.corpus import (
    ShapeGeometryCorpusError,
    ShapeGeometryCorpusManifest,
    ShapeGeometryManualAnnotations,
    canonical_json_bytes,
    require_matching_baseline,
    run_v11_baseline,
    select_v2_anchors,
    verify_split_boundary,
)
from PIL import Image


def _games(*, v11_profile: dict[str, object] | None = None) -> list[dict[str, object]]:
    return [
        {
            "gameId": game_id,
            "pageBoardRows": 3,
            "pageBoardColumns": 3,
            "cellRows": 3,
            "cellColumns": 5,
            "activeBoardSlots": list(range(9)),
            "v11Profile": v11_profile if game_id == "777" else None,
        }
        for game_id in ("777", "blazing", "gang", "reels", "mummies")
    ]


def _source(
    *,
    source_id: str,
    checksum: str,
    relative_path: str,
    split: str = "development",
    role: str = "measurement",
    family: str = "capture_a",
    ordinal: int = 1,
    game_id: str = "777",
) -> dict[str, object]:
    return {
        "sourceId": source_id,
        "gameId": game_id,
        "relativePath": relative_path,
        "sourceChecksumSha256": checksum,
        "split": split,
        "corpusRole": role,
        "captureFamilyId": family,
        "sourceOrdinal": ordinal,
        "scenarios": ["clear_frame"],
    }


def _manifest(
    root: Path,
    *,
    visibility: str = "executor",
    sources: list[dict[str, object]] | None = None,
    v11_profile: dict[str, object] | None = None,
) -> ShapeGeometryCorpusManifest:
    return ShapeGeometryCorpusManifest.from_mapping(
        {
            "schemaVersion": 1,
            "visibility": visibility,
            "corpusRoot": str(root),
            "games": _games(v11_profile=v11_profile),
            "sources": [] if sources is None else sources,
        }
    )


def _write(root: Path, relative_path: str, content: bytes) -> str:
    path = root / Path(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_manifest_enforces_visibility_topology_and_excluded_reels_data(tmp_path: Path) -> None:
    with pytest.raises(ShapeGeometryCorpusError) as acceptance_error:
        _manifest(
            tmp_path,
            sources=[
                _source(
                    source_id="acceptance_frame",
                    checksum="a" * 64,
                    relative_path="777/frame.jpg",
                    split="acceptance",
                )
            ],
        )
    assert acceptance_error.value.code == "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN"

    with pytest.raises(ShapeGeometryCorpusError) as topology_error:
        ShapeGeometryCorpusManifest.from_mapping(
            {
                "schemaVersion": 1,
                "visibility": "executor",
                "corpusRoot": str(tmp_path),
                "games": [
                    {
                        **game,
                        "cellColumns": 4 if game["gameId"] == "777" else game["cellColumns"],
                    }
                    for game in _games()
                ],
                "sources": [],
            }
        )
    assert topology_error.value.code == "SHAPE_GEOMETRY_V2_TOPOLOGY_UNSUPPORTED"

    with pytest.raises(ShapeGeometryCorpusError) as excluded_error:
        _manifest(
            tmp_path,
            sources=[
                _source(
                    source_id="reels_reserved",
                    checksum="b" * 64,
                    relative_path="reels/frame.jpg",
                    family="reels_test",
                )
            ],
        )
    assert excluded_error.value.code == "SHAPE_GEOMETRY_V2_CORPUS_EXCLUDED_DATASET"

    with pytest.raises(ShapeGeometryCorpusError) as excluded_path_error:
        _manifest(
            tmp_path,
            sources=[
                _source(
                    source_id="reels_path_reserved",
                    checksum="c" * 64,
                    relative_path="reels_test/frame.jpg",
                    family="ordinary_capture",
                )
            ],
        )
    assert excluded_path_error.value.code == "SHAPE_GEOMETRY_V2_CORPUS_EXCLUDED_DATASET"


def test_inventory_detects_byte_drift_and_reports_intra_split_duplicates(tmp_path: Path) -> None:
    first_checksum = _write(tmp_path, "777/one.jpg", b"same-jpeg")
    second_checksum = _write(tmp_path, "777/two.jpg", b"same-jpeg")
    manifest = _manifest(
        tmp_path,
        sources=[
            _source(
                source_id="first",
                checksum=first_checksum,
                relative_path="777/one.jpg",
                family="capture_a",
            ),
            _source(
                source_id="second",
                checksum=second_checksum,
                relative_path="777/two.jpg",
                family="capture_b",
            ),
        ],
    )

    report = manifest.freeze_inventory().as_dict()

    assert report["duplicates"] == [
        {
            "gameIds": ["777"],
            "occurrenceCount": 2,
            "sourceChecksumSha256": first_checksum,
            "sourceIds": ["first", "second"],
        }
    ]
    _write(tmp_path, "777/two.jpg", b"changed")
    with pytest.raises(ShapeGeometryCorpusError) as drift_error:
        manifest.freeze_inventory()
    assert drift_error.value.code == "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_DRIFT"


def test_manifest_blocks_byte_identical_anchor_measurement_and_split_leakage(
    tmp_path: Path,
) -> None:
    checksum = "a" * 64
    with pytest.raises(ShapeGeometryCorpusError) as role_error:
        _manifest(
            tmp_path,
            sources=[
                _source(
                    source_id="anchor",
                    checksum=checksum,
                    relative_path="777/anchor.jpg",
                    role="anchor_pool",
                    family="anchor_capture",
                ),
                _source(
                    source_id="measurement",
                    checksum=checksum,
                    relative_path="777/measurement.jpg",
                    family="measurement_capture",
                ),
            ],
        )
    assert role_error.value.code == "SHAPE_GEOMETRY_V2_ANCHOR_MEASUREMENT_DUPLICATE"

    with pytest.raises(ShapeGeometryCorpusError) as split_error:
        _manifest(
            tmp_path,
            sources=[
                _source(
                    source_id="development",
                    checksum=checksum,
                    relative_path="777/development.jpg",
                    family="development_capture",
                ),
                _source(
                    source_id="calibration",
                    checksum=checksum,
                    relative_path="777/calibration.jpg",
                    split="calibration",
                    family="calibration_capture",
                ),
            ],
        )
    assert split_error.value.code == "SHAPE_GEOMETRY_V2_CHECKSUM_SPLIT_LEAKAGE"


def test_capture_family_and_checksum_cannot_cross_executor_acceptance_boundary(
    tmp_path: Path,
) -> None:
    executor_root = tmp_path / "executor"
    acceptance_root = tmp_path / "acceptance"
    checksum = _write(executor_root, "777/frame.jpg", b"same")
    _write(acceptance_root, "777/frame.jpg", b"same")
    executor = _manifest(
        executor_root,
        sources=[
            _source(
                source_id="executor_frame",
                checksum=checksum,
                relative_path="777/frame.jpg",
                family="shared_family",
            )
        ],
    )
    acceptance = _manifest(
        acceptance_root,
        visibility="acceptance",
        sources=[
            _source(
                source_id="acceptance_frame",
                checksum=checksum,
                relative_path="777/frame.jpg",
                split="acceptance",
                family="other_family",
            )
        ],
    )

    with pytest.raises(ShapeGeometryCorpusError) as checksum_error:
        verify_split_boundary(executor, acceptance)
    assert checksum_error.value.code == "SHAPE_GEOMETRY_V2_CHECKSUM_SPLIT_LEAKAGE"

    changed_checksum = _write(acceptance_root, "777/frame.jpg", b"different")
    family_leakage = _manifest(
        acceptance_root,
        visibility="acceptance",
        sources=[
            _source(
                source_id="acceptance_frame",
                checksum=changed_checksum,
                relative_path="777/frame.jpg",
                split="acceptance",
                family="shared_family",
            )
        ],
    )
    with pytest.raises(ShapeGeometryCorpusError) as family_error:
        verify_split_boundary(executor, family_leakage)
    assert family_error.value.code == "SHAPE_GEOMETRY_V2_CAPTURE_FAMILY_SPLIT_LEAKAGE"


def test_anchor_selection_is_deterministic_and_rejects_incomplete_candidates(
    tmp_path: Path,
) -> None:
    manifest = _manifest(
        tmp_path,
        sources=[
            _source(
                source_id="vertical",
                checksum="a" * 64,
                relative_path="777/vertical.jpg",
                role="anchor_pool",
                family="a_capture",
            ),
            _source(
                source_id="complete",
                checksum="b" * 64,
                relative_path="777/complete.jpg",
                role="anchor_pool",
                family="b_capture",
            ),
        ],
    )
    annotations = ShapeGeometryManualAnnotations.from_mapping(
        {
            "schemaVersion": 1,
            "corpusManifestFingerprint": manifest.fingerprint(),
            "annotations": [
                {
                    "sourceId": "complete",
                    "sourceChecksumSha256": "b" * 64,
                    "pageState": "complete",
                    "topologyConfirmed": True,
                    "visibleGrid": True,
                    "anchorCandidate": True,
                    "activeOperatorSeconds": 19,
                },
                {
                    "sourceId": "vertical",
                    "sourceChecksumSha256": "a" * 64,
                    "pageState": "vertical_crop",
                    "topologyConfirmed": True,
                    "visibleGrid": True,
                    "anchorCandidate": True,
                    "activeOperatorSeconds": 11,
                },
            ],
        }
    )

    selection = select_v2_anchors(manifest, annotations)
    game = next(value for value in selection["games"] if value["gameId"] == "777")

    assert game["anchor"] == {
        "sourceId": "complete",
        "sourceChecksumSha256": "b" * 64,
    }
    assert game["candidates"][0]["reasons"] == ["PAGE_NOT_COMPLETE"]
    assert game["candidates"][1]["reasons"] == ["SELECTED"]


def _synthetic_page() -> tuple[np.ndarray, tuple[tuple[Point, Point, Point, Point], ...]]:
    rng = np.random.default_rng(20260921)
    image = rng.integers(0, 60, size=(620, 760, 3), dtype=np.uint8)
    quads = []
    for row in range(3):
        for column in range(3):
            left = 85 + column * 210
            top = 70 + row * 165
            right, bottom = left + 155, top + 100
            cv2.rectangle(image, (left, top), (right, bottom), (235, 25, 20), 7)
            cv2.putText(
                image,
                f"{row * 3 + column + 1}",
                (left + 65, top + 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 255),
                2,
            )
            quads.append(
                (
                    Point(left, top),
                    Point(right, top),
                    Point(right, bottom),
                    Point(left, bottom),
                )
            )
    return image, tuple(quads)


def test_v11_baseline_is_bounded_read_only_and_replayable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image, quads = _synthetic_page()
    anchor_path = tmp_path / "777" / "anchor.jpg"
    target_path = tmp_path / "777" / "target.jpg"
    anchor_path.parent.mkdir(parents=True)
    Image.fromarray(image).save(anchor_path)
    transform = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [759, 0], [759, 619], [0, 619]]),
        np.float32([[17, 11], [747, 22], [754, 608], [6, 600]]),
    )
    target = cv2.warpPerspective(image, transform, (760, 620))
    Image.fromarray(target).save(target_path)
    anchor_checksum = hashlib.sha256(anchor_path.read_bytes()).hexdigest()
    target_checksum = hashlib.sha256(target_path.read_bytes()).hexdigest()
    profile = {
        "policy": PAGE_REGISTRATION_VERSION,
        "anchors": [
            {
                "sourceChecksumSha256": anchor_checksum,
                "imageWidth": 760,
                "imageHeight": 620,
                "quads": [[point.to_dict() for point in quad] for quad in quads],
            }
        ],
    }
    manifest = _manifest(
        tmp_path,
        v11_profile=profile,
        sources=[
            _source(
                source_id="anchor",
                checksum=anchor_checksum,
                relative_path="777/anchor.jpg",
                role="anchor_pool",
                family="anchor_capture",
            ),
            _source(
                source_id="target",
                checksum=target_checksum,
                relative_path="777/target.jpg",
                family="measurement_capture",
            ),
        ],
    )
    inventory = manifest.freeze_inventory()

    first = run_v11_baseline(manifest, inventory)
    second = run_v11_baseline(manifest, inventory)
    game = next(value for value in first["games"] if value["gameId"] == "777")

    assert game["status"] == "measured"
    assert game["selectedSourceCount"] == 1
    assert game["results"][0]["status"] == "registered"
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    require_matching_baseline(first, second)
    with pytest.raises(ShapeGeometryCorpusError) as limit_error:
        run_v11_baseline(manifest, inventory, max_sources_per_game=11)
    assert limit_error.value.code == "SHAPE_GEOMETRY_V2_BASELINE_LIMIT_INVALID"

    original_freeze_inventory = ShapeGeometryCorpusManifest.freeze_inventory

    def freeze_then_change_target(self: ShapeGeometryCorpusManifest):
        frozen = original_freeze_inventory(self)
        if self is manifest:
            target_path.write_bytes(b"changed-after-inventory-freeze")
        return frozen

    monkeypatch.setattr(
        ShapeGeometryCorpusManifest,
        "freeze_inventory",
        freeze_then_change_target,
    )
    with pytest.raises(ShapeGeometryCorpusError) as drift_error:
        run_v11_baseline(manifest, inventory)
    assert drift_error.value.code == "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_DRIFT"


def test_baseline_never_reads_acceptance_or_treats_missing_data_as_success(tmp_path: Path) -> None:
    acceptance = _manifest(tmp_path, visibility="acceptance")
    with pytest.raises(ShapeGeometryCorpusError) as visibility_error:
        run_v11_baseline(acceptance, acceptance.freeze_inventory())
    assert visibility_error.value.code == "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN"

    executor = _manifest(tmp_path)
    report = run_v11_baseline(executor, executor.freeze_inventory())
    assert {game["status"] for game in report["games"]} == {"not_evaluable"}

    checksum = _write(tmp_path, "777/unconfigured.jpg", b"not-a-decoded-page")
    unconfigured = _manifest(
        tmp_path,
        sources=[
            _source(
                source_id="unconfigured",
                checksum=checksum,
                relative_path="777/unconfigured.jpg",
            )
        ],
    )
    unconfigured_report = run_v11_baseline(unconfigured, unconfigured.freeze_inventory())
    game = next(value for value in unconfigured_report["games"] if value["gameId"] == "777")
    assert game["status"] == "not_configured"
    assert game["results"][0]["status"] == "not_configured"


def test_baseline_rejects_missing_or_cross_game_profile_anchors_before_evaluation(
    tmp_path: Path,
) -> None:
    target_checksum = _write(tmp_path, "777/target.jpg", b"target")
    missing_profile = {
        "policy": PAGE_REGISTRATION_VERSION,
        "anchors": [{"sourceChecksumSha256": "a" * 64}],
    }
    missing_anchor = _manifest(
        tmp_path,
        v11_profile=missing_profile,
        sources=[
            _source(
                source_id="target",
                checksum=target_checksum,
                relative_path="777/target.jpg",
                family="target_capture",
            )
        ],
    )
    with pytest.raises(ShapeGeometryCorpusError) as missing_error:
        run_v11_baseline(missing_anchor, missing_anchor.freeze_inventory())
    assert missing_error.value.code == "SHAPE_GEOMETRY_V2_V11_PROFILE_ANCHOR_MISSING"

    blazing_checksum = _write(tmp_path, "blazing/anchor.jpg", b"blazing-anchor")
    cross_game_profile = {
        "policy": PAGE_REGISTRATION_VERSION,
        "anchors": [{"sourceChecksumSha256": blazing_checksum}],
    }
    cross_game = _manifest(
        tmp_path,
        v11_profile=cross_game_profile,
        sources=[
            _source(
                source_id="777-target",
                checksum=target_checksum,
                relative_path="777/target.jpg",
                family="target_capture",
            ),
            _source(
                source_id="blazing-anchor",
                checksum=blazing_checksum,
                relative_path="blazing/anchor.jpg",
                game_id="blazing",
                role="anchor_pool",
                family="blazing_capture",
            ),
        ],
    )
    with pytest.raises(ShapeGeometryCorpusError) as cross_game_error:
        run_v11_baseline(cross_game, cross_game.freeze_inventory())
    assert cross_game_error.value.code == "SHAPE_GEOMETRY_V2_V11_PROFILE_ANCHOR_MISSING"


def test_freeze_and_baseline_commands_support_write_then_check(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    manifest_path = tmp_path / "executor-manifest.json"
    inventory_path = tmp_path / "executor-inventory.json"
    baseline_path = tmp_path / "v11-baseline.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "visibility": "executor",
                "corpusRoot": str(tmp_path),
                "games": _games(),
                "sources": [],
            }
        ),
        encoding="utf-8",
    )
    freeze = repository_root / "scripts" / "freeze_shape_geometry_v2_corpus.py"
    baseline = repository_root / "scripts" / "run_shape_geometry_v2_v11_baseline.py"

    for command in (
        [
            sys.executable,
            str(freeze),
            "--manifest",
            str(manifest_path),
            "--output",
            str(inventory_path),
        ],
        [
            sys.executable,
            str(baseline),
            "--manifest",
            str(manifest_path),
            "--inventory",
            str(inventory_path),
            "--output",
            str(baseline_path),
        ],
        [
            sys.executable,
            str(freeze),
            "--manifest",
            str(manifest_path),
            "--output",
            str(inventory_path),
            "--check",
        ],
        [
            sys.executable,
            str(baseline),
            "--manifest",
            str(manifest_path),
            "--inventory",
            str(inventory_path),
            "--output",
            str(baseline_path),
            "--check",
        ],
    ):
        completed = subprocess.run(
            command,
            cwd=repository_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr

    baseline_report = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert {game["status"] for game in baseline_report["games"]} == {"not_evaluable"}

    acceptance_manifest_path = tmp_path / "acceptance-manifest.json"
    acceptance_manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "visibility": "acceptance",
                "corpusRoot": str(tmp_path / "unavailable-acceptance-corpus"),
                "games": _games(),
                "sources": [],
            }
        ),
        encoding="utf-8",
    )
    acceptance = subprocess.run(
        [
            sys.executable,
            str(baseline),
            "--manifest",
            str(acceptance_manifest_path),
            "--inventory",
            str(tmp_path / "unread-inventory.json"),
            "--output",
            str(tmp_path / "unwritten-baseline.json"),
        ],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert acceptance.returncode == 2
    assert "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN" in acceptance.stderr
