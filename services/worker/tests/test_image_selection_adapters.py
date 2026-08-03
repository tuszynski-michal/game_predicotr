from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from game_predictor_api.domain.image_selections import IMAGE_SELECTION_SELECTOR_FINGERPRINT
from game_predictor_worker.cli import main
from game_predictor_worker.images.geometry import BoardDetection, Point
from game_predictor_worker.images.selection.adapters import (
    AnchoredSequenceRangeRecognizer,
    ComposedCheapImageAnalyzer,
    OpenCvImageQualityAnalyzer,
    PillowThumbnailLoader,
    build_default_adapters,
)
from game_predictor_worker.images.selection.contracts import (
    ImageQualityMetrics,
    ImageSelectionSource,
)
from game_predictor_worker.images.selection.manifest import DEFAULT_SELECTOR_MANIFEST
from game_predictor_worker.images.selection.ports import LatticeFingerprint, ThumbnailFrame
from game_predictor_worker.images.sequence_ocr import Recognition
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]


def _write_jpeg(path: Path, *, width: int = 320, height: int = 480) -> str:
    image = Image.new("RGB", (width, height), (20, 30, 40))
    image.save(path, format="JPEG", quality=92)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(checksum: str) -> ImageSelectionSource:
    return ImageSelectionSource(
        order_index=0,
        relative_path="camera/photo1.jpg",
        stored_relative_path="00000001.jpg",
        checksum_sha256=checksum,
        size_bytes=1024,
    )


def test_selector_manifest_fingerprint_is_the_api_run_identity() -> None:
    manifest = DEFAULT_SELECTOR_MANIFEST

    assert manifest.to_dict()["algorithmVersion"] == "fast-image-selector-v1"
    assert len(manifest.fingerprint) == 64
    assert manifest.fingerprint == IMAGE_SELECTION_SELECTOR_FINGERPRINT
    assert manifest.canonical_bytes() == DEFAULT_SELECTOR_MANIFEST.canonical_bytes()


def test_pillow_thumbnail_loader_verifies_checksum_and_applies_exif(tmp_path: Path) -> None:
    path = tmp_path / "00000001.jpg"
    image = Image.new("RGB", (80, 40), (10, 20, 30))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, format="JPEG", exif=exif)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()

    frame = PillowThumbnailLoader(tmp_path, max_edge=50).load(_source(checksum))

    assert (frame.source_width, frame.source_height) == (40, 80)
    assert max(frame.rgb.shape[:2]) == 50


class _FixedLatticeAnalyzer:
    version = "fake-lattice-v1"

    def analyze(self, frame: ThumbnailFrame) -> LatticeFingerprint:
        del frame
        return LatticeFingerprint(
            fingerprint_hex="a" * 64,
            geometry_signature=(0.2, 0.3, 0.4, 0.1),
            board_count=9,
            geometry_confidence=0.95,
            boards=(),
            reason_codes=(),
        )


class _FixedQualityAnalyzer:
    version = "fake-quality-v1"

    def measure(
        self,
        frame: ThumbnailFrame,
        lattice: LatticeFingerprint,
    ) -> ImageQualityMetrics:
        del frame, lattice
        return ImageQualityMetrics(0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 1.0, 0.92)


def test_composed_scan_uses_explicit_ports_and_returns_bounded_observation(
    tmp_path: Path,
) -> None:
    checksum = _write_jpeg(tmp_path / "00000001.jpg")
    analyzer = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(tmp_path, max_edge=320),
        _FixedLatticeAnalyzer(),
        _FixedQualityAnalyzer(),
    )

    observation = analyzer.analyze(_source(checksum))

    assert observation.fingerprint_hex == "a" * 64
    assert observation.board_count == 9
    assert observation.quality.overall_score == 0.92


def test_opencv_quality_scores_sharp_pattern_above_blurred_pattern() -> None:
    checker = np.indices((240, 320)).sum(axis=0) % 2
    sharp = np.repeat((checker * 255).astype(np.uint8)[:, :, None], 3, axis=2)
    blurred = np.full_like(sharp, 127)
    lattice = LatticeFingerprint(
        fingerprint_hex="f" * 64,
        geometry_signature=(),
        board_count=None,
        geometry_confidence=0.8,
        boards=(),
        reason_codes=(),
    )
    analyzer = OpenCvImageQualityAnalyzer(DEFAULT_SELECTOR_MANIFEST.quality_weights)

    sharp_quality = analyzer.measure(ThumbnailFrame(sharp, 320, 240), lattice)
    blurred_quality = analyzer.measure(ThumbnailFrame(blurred, 320, 240), lattice)

    assert sharp_quality.sharpness > blurred_quality.sharpness


class _AnchorRecognizer:
    version = "fake-ocr-v1"
    model_name = "fake"
    model_fingerprint = "0" * 64
    model_files: dict[str, str] = {}
    runtime_name = "fake"
    runtime_version = "1"

    def recognize(self, rgb_image: np.ndarray) -> Recognition:
        del rgb_image
        raise AssertionError("The batched anchor method should be used.")

    def recognize_many(self, rgb_images: tuple[np.ndarray, ...]) -> tuple[Recognition, ...]:
        assert len(rgb_images) == 3
        return (
            Recognition("400", 0.99),
            Recognition("404", 0.98),
            Recognition("408", 0.97),
        )


def test_range_adapter_reads_only_first_middle_last_anchor() -> None:
    boards = tuple(
        BoardDetection(
            position_index=index,
            quad=(
                Point(20 + (index % 3) * 100, 20 + (index // 3) * 100),
                Point(100 + (index % 3) * 100, 20 + (index // 3) * 100),
                Point(100 + (index % 3) * 100, 80 + (index // 3) * 100),
                Point(20 + (index % 3) * 100, 80 + (index // 3) * 100),
            ),
            bounding_box=(20 + (index % 3) * 100, 20 + (index // 3) * 100, 80, 60),
            red_border_score=0.9,
            refined_from_grid=False,
        )
        for index in range(9)
    )
    image = np.zeros((420, 340, 3), dtype=np.uint8)

    recognized, reasons = AnchoredSequenceRangeRecognizer(_AnchorRecognizer()).recognize(
        image,
        boards,
    )

    assert reasons == ()
    assert recognized is not None
    assert (recognized.start, recognized.end, recognized.confidence) == (400, 408, 0.97)


def test_standalone_cli_writes_manual_report_without_loading_ocr_model(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "staging"
    source_root.mkdir()
    image_path = source_root / "00000001.jpg"
    checksum = _write_jpeg(image_path)
    size = image_path.stat().st_size
    manifest = {
        "files": [
            {
                "checksumSha256": checksum,
                "orderIndex": 0,
                "relativePath": "camera/photo1.jpg",
                "sizeBytes": size,
                "storedFileName": image_path.name,
            }
        ],
        "gameId": "00000000-0000-0000-0000-000000000001",
        "orderingPolicy": "natural_relative_path_v1",
        "purpose": "photo_selection",
        "schemaVersion": 1,
    }
    manifest_path = source_root / "_browser_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    output_root = tmp_path / "output"

    exit_code = main(
        (
            "--image-selection-manifest",
            str(manifest_path),
            "--image-selection-output",
            str(output_root),
        )
    )

    report = json.loads((output_root / "selection-report.json").read_text("utf-8"))
    assert exit_code == 0
    assert report["selectorVersion"] == "fast-image-selector-v1"
    assert report["groups"][0]["status"] == "manual_required"
    assert (output_root / "candidates.jsonl").is_file()
    assert (output_root / "groups.jsonl").is_file()
    assert (output_root / "checkpoint.json").is_file()


def test_private_real_corpus_cheap_scan_matches_pinned_observations() -> None:
    source_root = ROOT / "examples" / "imgs"
    golden_path = ROOT / "ai_docs" / "quality" / "fast-image-selector-v1-real-observations.json"
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    values = payload["observations"]
    if any(not (source_root / value["relativePath"]).is_file() for value in values):
        pytest.skip("The private user-provided image corpus is not present.")
    analyzer, _ = build_default_adapters(source_root)
    first_pass = []
    second_pass = []
    for index, value in enumerate(values):
        source = ImageSelectionSource(
            order_index=index,
            relative_path=value["relativePath"],
            stored_relative_path=value["relativePath"],
            checksum_sha256=value["sha256"],
            size_bytes=value["sizeBytes"],
        )
        first_pass.append(analyzer.analyze(source))
        second_pass.append(analyzer.analyze(source))

    assert [observation.board_count for observation in first_pass] == [
        value["expectedBoardCount"] for value in values
    ]
    assert [list(observation.reason_codes) for observation in first_pass] == [
        value["expectedReasonCodes"] for value in values
    ]
    assert [
        (
            observation.fingerprint_hex,
            observation.geometry_signature,
            observation.quality.to_dict(),
        )
        for observation in first_pass
    ] == [
        (
            observation.fingerprint_hex,
            observation.geometry_signature,
            observation.quality.to_dict(),
        )
        for observation in second_pass
    ]
