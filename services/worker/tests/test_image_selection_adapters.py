from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import StatisticsError

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.image_selections import IMAGE_SELECTION_SELECTOR_FINGERPRINT
from game_predictor_worker.cli import main
from game_predictor_worker.images.geometry import BoardDetection, DetectionResult, Point
from game_predictor_worker.images.selection.adapters import (
    AdaptiveVisibleSequenceLabelRangeRecognizer,
    AnchoredSequenceRangeRecognizer,
    BestEffortVisibleSequenceLabelRangeRecognizer,
    ComposedCheapImageAnalyzer,
    FullCandidateVerifier,
    NoRangeRecognizer,
    OpenCvAppearanceFingerprintAnalyzer,
    OpenCvAppearanceQualityAnalyzer,
    OpenCvImageQualityAnalyzer,
    PillowThumbnailLoader,
    VisibleSequenceLabelRangeRecognizer,
    build_default_adapters,
    configure_opencv_thread_budget,
)
from game_predictor_worker.images.selection.contracts import (
    ImageQualityMetrics,
    ImageSelectionSource,
)
from game_predictor_worker.images.selection.engine import appearance_distance
from game_predictor_worker.images.selection.manifest import (
    APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
    DEFAULT_SELECTOR_MANIFEST,
    FIRST_USABLE_SELECTOR_MANIFEST_V8,
    REDUCED_JPEG_THUMBNAIL_ADAPTER_VERSION,
    SelectorManifest,
    selector_manifest_for_fingerprint,
)
from game_predictor_worker.images.selection.ports import LatticeFingerprint, ThumbnailFrame
from game_predictor_worker.images.selection.telemetry import StageTimingCollector
from game_predictor_worker.images.sequence_ocr import Recognition
from PIL import Image, ImageOps, JpegImagePlugin

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

    assert manifest.to_dict()["algorithmVersion"] == "fast-image-selector-v8"
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


def test_reduced_jpeg_loader_calls_draft_before_decode_and_preserves_source_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "00000001.jpg"
    image = Image.new("RGB", (1600, 1200), (10, 20, 30))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, format="JPEG", exif=exif)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    events: list[tuple[str, tuple[int, int]]] = []
    original_draft = JpegImagePlugin.JpegImageFile.draft
    original_load = JpegImagePlugin.JpegImageFile.load

    def draft_spy(
        source: JpegImagePlugin.JpegImageFile,
        mode: str,
        size: tuple[int, int],
    ) -> tuple[str, tuple[int, int, int, int]] | None:
        events.append(("draft", source.size))
        return original_draft(source, mode, size)

    def load_spy(source: JpegImagePlugin.JpegImageFile) -> object:
        events.append(("load", source.size))
        return original_load(source)

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", draft_spy)
    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "load", load_spy)

    frame = PillowThumbnailLoader(
        tmp_path,
        max_edge=480,
        adapter_version=REDUCED_JPEG_THUMBNAIL_ADAPTER_VERSION,
    ).load(_source(checksum))

    assert events[0] == ("draft", (1600, 1200))
    first_load_size = next(size for event, size in events if event == "load")
    assert max(first_load_size) < 1600
    assert (frame.source_width, frame.source_height) == (1200, 1600)
    assert max(frame.rgb.shape[:2]) == 480


def test_reduced_manifest_preserves_historical_v8_resume_identity() -> None:
    assert DEFAULT_SELECTOR_MANIFEST.thumbnail_max_edge == 960
    assert (
        DEFAULT_SELECTOR_MANIFEST.thumbnail_adapter_version
        == REDUCED_JPEG_THUMBNAIL_ADAPTER_VERSION
    )
    assert FIRST_USABLE_SELECTOR_MANIFEST_V8.fingerprint == (
        "9dc754cca7e7e7afe23e8a25c8574e0ef4ed5f7fd5829a24984c25f4c256f42d"
    )
    assert (
        selector_manifest_for_fingerprint(FIRST_USABLE_SELECTOR_MANIFEST_V8.fingerprint)
        is FIRST_USABLE_SELECTOR_MANIFEST_V8
    )


def test_opencv_thread_budget_disables_nested_parallel_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured: list[int] = []
    monkeypatch.setattr("cv2.setNumThreads", configured.append)
    monkeypatch.setattr("cv2.getNumThreads", lambda: configured[-1])

    assert configure_opencv_thread_budget() == 1
    assert configured == [1]

    with pytest.raises(ValueError, match="exactly one"):
        configure_opencv_thread_budget(2)


def test_pillow_thumbnail_loader_reports_measured_decode_and_checksum(tmp_path: Path) -> None:
    path = tmp_path / "00000001.jpg"
    checksum = _write_jpeg(path)
    telemetry = StageTimingCollector()

    PillowThumbnailLoader(
        tmp_path,
        max_edge=50,
        telemetry=telemetry,
    ).load(_source(checksum))

    snapshot = telemetry.snapshot()
    assert snapshot["counters"] == {"checksumReads": 1, "decoderCalls": 1}
    stages = snapshot["stages"]
    assert isinstance(stages, dict)
    assert stages["checksum"]["count"] == 1
    assert stages["decode"]["count"] == 1


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


class _StatisticsLatticeAnalyzer:
    version = "statistics-lattice-v1"

    def analyze(self, frame: ThumbnailFrame) -> LatticeFingerprint:
        del frame
        raise StatisticsError("no median for this image")


class _StatisticsDetector:
    version = "statistics-detector-v1"

    def detect(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise StatisticsError("no median for this image")


class _RecoveryProbeDetector:
    version = "recovery-probe-v1"

    def __init__(self) -> None:
        self.recovery_flags: list[bool] = []

    def detect(
        self,
        rgb_image: np.ndarray,
        *,
        expected_board_count: int = 9,
        allow_grid_recovery: bool = False,
        allow_occluded_grid_recovery: bool = False,
    ) -> DetectionResult:
        del expected_board_count, allow_occluded_grid_recovery
        self.recovery_flags.append(allow_grid_recovery)
        return DetectionResult(
            status="needs_review",
            image_width=rgb_image.shape[1],
            image_height=rgb_image.shape[0],
            candidate_count=8,
            page_quad=None,
            boards=(),
            confidence=0.8,
            confidence_components={"candidateCount": 0.8},
            review_reasons=("BOARD_CANDIDATE_COUNT",),
        )


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


def test_v9_appearance_scan_builds_descriptor_without_geometry_or_ocr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "00000001.jpg"
    y, x = np.indices((480, 320))
    rgb = np.stack(
        (
            (x % 256).astype(np.uint8),
            (y % 256).astype(np.uint8),
            ((x + y) % 256).astype(np.uint8),
        ),
        axis=2,
    )
    Image.fromarray(rgb, mode="RGB").save(path, format="JPEG", quality=92)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "game_predictor_worker.images.selection.adapters.ClassicalPageBoardDetector",
        lambda: (_ for _ in ()).throw(AssertionError("PageBoardDetector must not be built.")),
    )
    telemetry = StageTimingCollector()

    analyzer, _ = build_default_adapters(
        tmp_path,
        manifest=APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
        telemetry=telemetry,
    )
    observation = analyzer.analyze(_source(checksum))

    config = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.appearance_descriptor
    expected_size = (
        config.phash_size**2
        + config.hue_bins
        + config.saturation_bins
        + config.value_bins
        + config.edge_grid_rows * config.edge_grid_columns
        + config.edge_orientation_bins
    )
    assert len(observation.appearance_signature) == expected_size
    assert observation.geometry_signature == ()
    assert observation.board_count is None
    assert observation.geometry_confidence == 0.0
    counters = telemetry.snapshot()["counters"]
    assert counters.get("detectorCalls", 0) == 0
    assert counters.get("ocrCalls", 0) == 0


def test_v9_appearance_adapters_are_deterministic_on_the_same_frame() -> None:
    y, x = np.indices((240, 320))
    rgb = np.stack(
        (
            ((x * 3) % 256).astype(np.uint8),
            ((y * 5) % 256).astype(np.uint8),
            ((x + y * 2) % 256).astype(np.uint8),
        ),
        axis=2,
    )
    frame = ThumbnailFrame(rgb=rgb, source_width=320, source_height=240)
    config = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.appearance_descriptor
    fingerprint = OpenCvAppearanceFingerprintAnalyzer(config)
    quality = OpenCvAppearanceQualityAnalyzer(
        APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.quality_weights,
        config,
    )

    first = fingerprint.analyze(frame)
    second = fingerprint.analyze(frame)

    assert first == second
    assert quality.measure(frame, first) == quality.measure(frame, second)


def test_v9_private_real_page_tolerates_a_small_perspective_change() -> None:
    path = ROOT / "examples" / "imgs" / "5983122166590934317.jpg"
    if not path.is_file():
        pytest.skip("The private user-provided perspective corpus is not present.")
    with Image.open(path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        normalized.thumbnail((960, 960), resample=Image.Resampling.LANCZOS)
        original = np.asarray(normalized, dtype=np.uint8)
    height, width = original.shape[:2]
    source_quad = np.float32(((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)))
    destination_quad = np.float32(
        (
            (width * 0.03, height * 0.01),
            (width * 0.98, height * 0.03),
            (width * 0.99, height * 0.98),
            (width * 0.01, height * 0.99),
        )
    )
    transformed = cv2.warpPerspective(
        original,
        cv2.getPerspectiveTransform(source_quad, destination_quad),
        (width, height),
        borderMode=cv2.BORDER_REFLECT,
    )
    config = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.appearance_descriptor
    analyzer = OpenCvAppearanceFingerprintAnalyzer(config)
    original_descriptor = analyzer.analyze(ThumbnailFrame(original, width, height))
    transformed_descriptor = analyzer.analyze(ThumbnailFrame(transformed, width, height))

    distance = appearance_distance(
        original_descriptor.appearance_signature,
        transformed_descriptor.appearance_signature,
        config,
    )

    assert distance < (
        APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.appearance_thresholds.adjacent_boundary_distance
    )


def test_corrupted_jpeg_is_isolated_as_a_bounded_scan_observation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "00000001.jpg"
    path.write_bytes(b"not-a-jpeg")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    analyzer = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(tmp_path, max_edge=320),
        _FixedLatticeAnalyzer(),
        _FixedQualityAnalyzer(),
    )

    observation = analyzer.analyze(_source(checksum))

    assert observation.reason_codes == ("IMAGE_SELECTION_SCAN_DECODE_FAILED",)
    assert observation.quality.overall_score == 0.0
    assert (observation.width, observation.height) == (1, 1)


def test_geometry_statistics_error_is_isolated_in_cheap_scan_and_full_verification(
    tmp_path: Path,
) -> None:
    checksum = _write_jpeg(tmp_path / "00000001.jpg")
    source = _source(checksum)
    cheap = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(tmp_path, max_edge=320),
        _StatisticsLatticeAnalyzer(),
        _FixedQualityAnalyzer(),
    ).analyze(source)

    assert cheap.reason_codes == ("IMAGE_SELECTION_SCAN_GEOMETRY_FAILED",)
    assert cheap.quality.overall_score == 0.0

    original = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(tmp_path, max_edge=320),
        _FixedLatticeAnalyzer(),
        _FixedQualityAnalyzer(),
    ).analyze(source)
    verified = FullCandidateVerifier(
        tmp_path,
        NoRangeRecognizer(),
        detector=_StatisticsDetector(),  # type: ignore[arg-type]
    ).verify(original, expected_board_count=9)

    assert verified.reason_codes == ("IMAGE_SELECTION_VERIFY_GEOMETRY_FAILED",)
    assert verified.recognized_range is None


def test_full_verifier_enables_guarded_grid_recovery_only_when_requested(
    tmp_path: Path,
) -> None:
    checksum = _write_jpeg(tmp_path / "00000001.jpg")
    source = _source(checksum)
    observation = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(tmp_path, max_edge=320),
        _FixedLatticeAnalyzer(),
        _FixedQualityAnalyzer(),
    ).analyze(source)
    legacy_detector = _RecoveryProbeDetector()
    adaptive_detector = _RecoveryProbeDetector()

    FullCandidateVerifier(
        tmp_path,
        NoRangeRecognizer(),
        detector=legacy_detector,
    ).verify(observation, expected_board_count=9)
    FullCandidateVerifier(
        tmp_path,
        NoRangeRecognizer(),
        detector=adaptive_detector,
        allow_grid_recovery=True,
    ).verify(observation, expected_board_count=9)

    assert legacy_detector.recovery_flags == [False]
    assert adaptive_detector.recovery_flags == [True]


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


class _VisibleLabelRecognizer(_AnchorRecognizer):
    def recognize_many(self, rgb_images: tuple[np.ndarray, ...]) -> tuple[Recognition, ...]:
        return tuple(Recognition(str(index + 10), 0.99) for index, _ in enumerate(rgb_images))


def test_visible_label_adapter_recovers_range_without_red_board_geometry() -> None:
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for position in range(9):
        row, column = divmod(position, 3)
        x = 420 + column * 360
        y = 300 + row * 90
        image[y : y + 11, x : x + 42] = 255

    recognized, reasons = VisibleSequenceLabelRangeRecognizer(_VisibleLabelRecognizer()).recognize(
        image, ()
    )

    assert reasons == ()
    assert recognized is not None
    assert (recognized.start, recognized.end) == (10, 18)
    assert recognized.confidence >= 0.9


class _AdaptiveVisibleLabelRecognizer(_AnchorRecognizer):
    def recognize_many(self, rgb_images: tuple[np.ndarray, ...]) -> tuple[Recognition, ...]:
        return tuple(Recognition(str(index + 271), 0.99) for index, _ in enumerate(rgb_images))


def test_adaptive_visible_label_adapter_keeps_wide_digits_and_low_bottom_row() -> None:
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for position in range(9):
        row, column = divmod(position, 3)
        x = 420 + column * 450
        y = (300, 405, 510)[row]
        image[y : y + 13, x : x + 90] = 255

    legacy = VisibleSequenceLabelRangeRecognizer(_AdaptiveVisibleLabelRecognizer())
    adaptive = AdaptiveVisibleSequenceLabelRangeRecognizer(_AdaptiveVisibleLabelRecognizer())
    legacy_range, legacy_reasons = legacy.recognize(image, ())
    recognized, reasons = adaptive.recognize(image, ())

    assert legacy_range is None
    assert legacy_reasons == ("RANGE_LABEL_LATTICE_MISSING",)
    assert reasons == ()
    assert recognized is not None
    assert (recognized.start, recognized.end) == (271, 279)


class _BestEffortVisibleLabelRecognizer(_AnchorRecognizer):
    def recognize_many(self, rgb_images: tuple[np.ndarray, ...]) -> tuple[Recognition, ...]:
        return tuple(
            Recognition(str(index + 73), 0.51 if index == 8 else 0.99)
            for index, _ in enumerate(rgb_images)
        )


def test_best_effort_visible_label_adapter_reads_warm_tinted_labels() -> None:
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for position in range(9):
        row, column = divmod(position, 3)
        x = 420 + column * 450
        y = (280, 390, 500)[row]
        image[y : y + 13, x : x + 90] = (255, 130, 10)

    adaptive = AdaptiveVisibleSequenceLabelRangeRecognizer(_BestEffortVisibleLabelRecognizer())
    best_effort = BestEffortVisibleSequenceLabelRangeRecognizer(_BestEffortVisibleLabelRecognizer())
    adaptive_range, adaptive_reasons = adaptive.recognize(image, ())
    recognized, reasons = best_effort.recognize(image, ())

    assert adaptive_range is None
    assert adaptive_reasons == ("RANGE_LABEL_LATTICE_MISSING",)
    assert reasons == ()
    assert recognized is not None
    assert (recognized.start, recognized.end) == (73, 81)


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
    assert report["selectorVersion"] == "fast-image-selector-v8"
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


@pytest.mark.parametrize("max_edge", (384, 480))
def test_small_reduced_scan_variants_are_rejected_by_real_board_golden(max_edge: int) -> None:
    source_root = ROOT / "examples" / "imgs"
    golden_path = ROOT / "ai_docs" / "quality" / "fast-image-selector-v1-real-observations.json"
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    values = payload["observations"]
    if any(not (source_root / value["relativePath"]).is_file() for value in values):
        pytest.skip("The private user-provided image corpus is not present.")
    analyzer, _ = build_default_adapters(
        source_root,
        manifest=SelectorManifest(thumbnail_max_edge=max_edge),
    )

    observations = [
        analyzer.analyze(
            ImageSelectionSource(
                order_index=index,
                relative_path=value["relativePath"],
                stored_relative_path=value["relativePath"],
                checksum_sha256=value["sha256"],
                size_bytes=value["sizeBytes"],
            )
        )
        for index, value in enumerate(values)
    ]

    expected_counts = {
        384: [None, 9, None, None, 9],
        480: [None, 9, None, 9, 9],
    }
    assert [observation.board_count for observation in observations] == expected_counts[max_edge]
    assert expected_counts[max_edge] != [value["expectedBoardCount"] for value in values]
