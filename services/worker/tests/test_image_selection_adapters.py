from __future__ import annotations

import hashlib
import json
from _thread import LockType
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import StatisticsError
from threading import Lock
from time import sleep

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.image_selections import IMAGE_SELECTION_SELECTOR_FINGERPRINT
from game_predictor_worker.cli import main
from game_predictor_worker.images.geometry import BoardDetection, DetectionResult, Point
from game_predictor_worker.images.selection.adapters import (
    AccuracyFirstVisibleSequenceLabelRangeRecognizer,
    AdaptiveVisibleSequenceLabelRangeRecognizer,
    AnchoredSequenceRangeRecognizer,
    BestEffortVisibleSequenceLabelRangeRecognizer,
    BoundedGridCandidateVerifier,
    ComposedCheapImageAnalyzer,
    ContiguousWindowVisibleSequenceLabelRangeRecognizer,
    DeterministicParallelCandidateVerifier,
    FullCandidateVerifier,
    FusedRangeEvidenceVisibleSequenceLabelRangeRecognizer,
    GridFirstVisibleSequenceLabelRangeRecognizer,
    IndependentEndpointVisibleSequenceLabelRangeRecognizer,
    LabelLatticeSafeVisibleSequenceLabelRangeRecognizer,
    LayoutAnchoredVisibleSequenceLabelRangeRecognizer,
    NoRangeRecognizer,
    OpenCvAppearanceFingerprintAnalyzer,
    OpenCvAppearanceQualityAnalyzer,
    OpenCvImageQualityAnalyzer,
    PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer,
    PillowThumbnailLoader,
    ProgressiveVisibleSequenceLabelRangeRecognizer,
    TwoLabelConsensusVisibleSequenceLabelRangeRecognizer,
    VisibleSequenceLabelRangeRecognizer,
    _VisibleLabel,
    build_default_adapters,
    configure_opencv_thread_budget,
)
from game_predictor_worker.images.selection.cache import (
    CachedCandidateVerifier,
    CachedCheapImageAnalyzer,
    FileImageScanObservationCache,
    FileImageVerificationCache,
)
from game_predictor_worker.images.selection.contracts import (
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    RangeEvidence,
    RepresentativeAssessment,
    SequenceRange,
)
from game_predictor_worker.images.selection.engine import appearance_distance
from game_predictor_worker.images.selection.manifest import (
    APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
    DEFAULT_SELECTOR_MANIFEST,
    FIRST_USABLE_SELECTOR_MANIFEST_V8,
    QUALITY_RECOVERY_SELECTOR_MANIFEST_V105,
    REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8,
    REDUCED_JPEG_THUMBNAIL_ADAPTER_VERSION,
    ContiguousSequenceWindowPolicy,
    FullGeometryPolicy,
    LayoutAnchorPolicy,
    ProgressiveVisibleLabelFallbackPolicy,
    SelectorManifest,
    selector_manifest_for_fingerprint,
)
from game_predictor_worker.images.selection.ports import LatticeFingerprint, ThumbnailFrame
from game_predictor_worker.images.selection.telemetry import StageTimingCollector
from game_predictor_worker.images.sequence_ocr import Recognition
from PIL import Image, ImageOps, JpegImagePlugin

ROOT = Path(__file__).resolve().parents[3]
RANGE_55_63_REGRESSION_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "image_selection_range_55_63.json"
)


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

    assert manifest.to_dict()["algorithmVersion"] == "fast-image-selector-v10.17"
    assert len(manifest.fingerprint) == 64
    assert manifest.fingerprint == IMAGE_SELECTION_SELECTOR_FINGERPRINT
    assert manifest.canonical_bytes() == DEFAULT_SELECTOR_MANIFEST.canonical_bytes()


def test_v10_5_uses_lightweight_range_verification_without_full_geometry(
    tmp_path: Path,
) -> None:
    _analyzer, verifier = build_default_adapters(
        tmp_path,
        range_recognizer=NoRangeRecognizer(),
        fallback_range_recognizer=NoRangeRecognizer(),
        manifest=QUALITY_RECOVERY_SELECTOR_MANIFEST_V105,
    )

    assert isinstance(verifier, BoundedGridCandidateVerifier)


def test_scan_adapter_fingerprint_excludes_domain_grouping_policy() -> None:
    manifest = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9
    compatible = replace(
        manifest,
        scan_batch_size=manifest.scan_batch_size + 1,
        top_k=manifest.top_k + 1,
    )
    changed_decode = replace(manifest, thumbnail_max_edge=800)

    assert compatible.fingerprint != manifest.fingerprint
    assert compatible.scan_adapter_fingerprint == manifest.scan_adapter_fingerprint
    assert changed_decode.scan_adapter_fingerprint != manifest.scan_adapter_fingerprint


class _CountingCheapAnalyzer:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        self.calls.append(source.order_index)
        return CheapImageObservation(
            source=source,
            width=640,
            height=480,
            fingerprint_hex="a" * 64,
            geometry_signature=(),
            board_count=None,
            geometry_confidence=0.0,
            quality=ImageQualityMetrics(*(0.75 for _ in range(8))),
            appearance_signature=(0.1, 0.2, 0.3),
        )


def test_scan_cache_reuses_observation_and_rebinds_current_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = FileImageScanObservationCache(tmp_path)
    fingerprint = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.scan_adapter_fingerprint
    source = _source("1" * 64)
    first_delegate = _CountingCheapAnalyzer()
    times = iter((10.0, 10.25))
    monkeypatch.setattr(
        "game_predictor_worker.images.selection.cache.perf_counter",
        lambda: next(times),
    )
    first = CachedCheapImageAnalyzer(
        first_delegate,
        cache,
        scan_adapter_fingerprint=fingerprint,
    )

    expected = first.analyze(source)
    rebound_source = replace(
        source,
        order_index=7,
        relative_path="another/session-photo.jpg",
        stored_relative_path="00000008.jpg",
    )
    second_delegate = _CountingCheapAnalyzer()
    second = CachedCheapImageAnalyzer(
        second_delegate,
        cache,
        scan_adapter_fingerprint=fingerprint,
    )
    actual = second.analyze(rebound_source)

    assert first_delegate.calls == [0]
    assert second_delegate.calls == []
    assert replace(actual, source=source) == expected
    assert actual.source == rebound_source
    assert second.snapshot()["hitCount"] == 1
    assert second.snapshot()["estimatedSavedSeconds"] == 0.25
    entry = next(cache.root.rglob("*.json"))
    assert b"camera/photo1.jpg" not in entry.read_bytes()


def test_scan_cache_misses_after_key_change_and_rebuilds_corrupt_entry(
    tmp_path: Path,
) -> None:
    cache = FileImageScanObservationCache(tmp_path)
    fingerprint = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.scan_adapter_fingerprint
    source = _source("2" * 64)
    initial_delegate = _CountingCheapAnalyzer()
    CachedCheapImageAnalyzer(
        initial_delegate,
        cache,
        scan_adapter_fingerprint=fingerprint,
    ).analyze(source)
    entry = next(cache.root.rglob("*.json"))
    entry.write_text('{"partial":', encoding="utf-8")

    repair_delegate = _CountingCheapAnalyzer()
    repaired = CachedCheapImageAnalyzer(
        repair_delegate,
        cache,
        scan_adapter_fingerprint=fingerprint,
    )
    repaired.analyze(source)
    changed_delegate = _CountingCheapAnalyzer()
    changed = CachedCheapImageAnalyzer(
        changed_delegate,
        cache,
        scan_adapter_fingerprint="3" * 64,
    )
    changed.analyze(source)
    checksum_delegate = _CountingCheapAnalyzer()
    checksum_changed = CachedCheapImageAnalyzer(
        checksum_delegate,
        cache,
        scan_adapter_fingerprint=fingerprint,
    )
    checksum_changed.analyze(replace(source, checksum_sha256="4" * 64))

    assert repair_delegate.calls == [0]
    assert repaired.snapshot()["invalidEntryCount"] == 1
    assert json.loads(entry.read_text(encoding="utf-8"))["contract"] == (
        "image-selection-scan-cache-v1"
    )
    assert changed_delegate.calls == [0]
    assert checksum_delegate.calls == [0]
    entries = tuple(cache.root.rglob("*.json"))
    assert len(entries) == 3
    assert sum(item.stat().st_size for item in entries) < 48 * 1024


class _BatchCandidateVerifier:
    def __init__(self) -> None:
        self.batch_calls: list[tuple[tuple[int, ...], bool]] = []
        self.fast_calls: list[tuple[int, ...]] = []
        self.representative_calls: list[int] = []

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        return self._result(observation, include_range_evidence=True)

    def assess_representative(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del expected_board_count
        self.representative_calls.append(observation.source.order_index)
        return self._result(observation, include_range_evidence=False)

    def verify_many(
        self,
        observations: tuple[CheapImageObservation, ...],
        *,
        expected_board_count: int | None,
        include_range_evidence: bool,
    ) -> tuple[CandidateVerification, ...]:
        del expected_board_count
        self.batch_calls.append(
            (tuple(item.source.order_index for item in observations), include_range_evidence)
        )
        return tuple(
            self._result(item, include_range_evidence=include_range_evidence)
            for item in observations
        )

    def verify_fast_many(
        self,
        observations: tuple[CheapImageObservation, ...],
        *,
        expected_board_count: int | None,
    ) -> tuple[CandidateVerification, ...]:
        del expected_board_count
        self.fast_calls.append(tuple(item.source.order_index for item in observations))
        return tuple(self._result(item, include_range_evidence=True) for item in observations)

    @staticmethod
    def _result(
        observation: CheapImageObservation,
        *,
        include_range_evidence: bool,
    ) -> CandidateVerification:
        start = observation.source.order_index * 9 + 1
        return CandidateVerification(
            representative=RepresentativeAssessment(
                board_count=9,
                geometry_complete=True,
                full_frame_visible=True,
                reason_codes=(),
            ),
            range_evidence=RangeEvidence(
                recognized_range=(
                    SequenceRange(start, start + 8, 0.95) if include_range_evidence else None
                ),
                reason_codes=(),
            ),
        )


def test_verification_cache_preserves_batch_order_and_separates_modes(
    tmp_path: Path,
) -> None:
    cache = FileImageVerificationCache(tmp_path)
    fingerprint = "5" * 64
    observations = tuple(
        replace(
            _CountingCheapAnalyzer().analyze(_source(str(index + 6) * 64)),
            source=replace(
                _source(str(index + 6) * 64),
                order_index=index,
            ),
        )
        for index in range(2)
    )
    cold_delegate = _BatchCandidateVerifier()
    cold = CachedCandidateVerifier(
        cold_delegate,
        cache,
        selector_fingerprint=fingerprint,
    )

    expected = cold.verify_many(
        observations,
        expected_board_count=9,
        include_range_evidence=True,
    )
    warm_delegate = _BatchCandidateVerifier()
    warm = CachedCandidateVerifier(
        warm_delegate,
        cache,
        selector_fingerprint=fingerprint,
    )
    actual = warm.verify_many(
        observations,
        expected_board_count=9,
        include_range_evidence=True,
    )
    representative = warm.assess_representative(
        observations[0],
        expected_board_count=9,
    )

    assert actual == expected
    assert cold_delegate.batch_calls == [((0, 1), True)]
    assert warm_delegate.batch_calls == []
    assert warm.snapshot()["hitCount"] == 2
    assert representative.range_evidence.recognized_range is None
    assert warm_delegate.representative_calls == [0]
    assert len(tuple(cache.root.rglob("*.json"))) == 3


def test_verification_cache_ignores_corruption_and_fingerprint_change(
    tmp_path: Path,
) -> None:
    cache = FileImageVerificationCache(tmp_path)
    source = _source("8" * 64)
    observation = _CountingCheapAnalyzer().analyze(source)
    first = CachedCandidateVerifier(
        _BatchCandidateVerifier(),
        cache,
        selector_fingerprint="9" * 64,
    )
    first.verify(observation, expected_board_count=9)
    entry = next(cache.root.rglob("*.json"))
    entry.write_text('{"partial":', encoding="utf-8")
    repair_delegate = _BatchCandidateVerifier()
    repaired = CachedCandidateVerifier(
        repair_delegate,
        cache,
        selector_fingerprint="9" * 64,
    )
    repaired.verify(observation, expected_board_count=9)
    changed_delegate = _BatchCandidateVerifier()
    changed = CachedCandidateVerifier(
        changed_delegate,
        cache,
        selector_fingerprint="a" * 64,
    )
    changed.verify(observation, expected_board_count=9)

    assert repaired.snapshot()["invalidEntryCount"] == 1
    assert changed.snapshot()["missCount"] == 1
    assert len(tuple(cache.root.rglob("*.json"))) == 2


def test_verification_cache_promotes_explicitly_compatible_selector_entry(
    tmp_path: Path,
) -> None:
    cache = FileImageVerificationCache(tmp_path)
    observation = _CountingCheapAnalyzer().analyze(_source("b" * 64))
    previous = CachedCandidateVerifier(
        _BatchCandidateVerifier(),
        cache,
        selector_fingerprint="c" * 64,
    )
    expected = previous.verify_many(
        (observation,),
        expected_board_count=9,
        include_range_evidence=True,
    )
    current_delegate = _BatchCandidateVerifier()
    current = CachedCandidateVerifier(
        current_delegate,
        cache,
        selector_fingerprint="d" * 64,
        compatible_selector_fingerprints=("c" * 64,),
    )

    actual = current.verify_many(
        (observation,),
        expected_board_count=9,
        include_range_evidence=True,
    )

    assert actual == expected
    assert current_delegate.batch_calls == []
    assert current.snapshot()["compatibleHitCount"] == 1
    assert current.snapshot()["writeCount"] == 1
    assert len(tuple(cache.root.rglob("*.json"))) == 2


def test_staged_fast_verification_bypasses_full_result_cache(tmp_path: Path) -> None:
    cache = FileImageVerificationCache(tmp_path)
    observation = _CountingCheapAnalyzer().analyze(_source("e" * 64))
    previous = CachedCandidateVerifier(
        _BatchCandidateVerifier(),
        cache,
        selector_fingerprint="f" * 64,
    )
    previous.verify(observation, expected_board_count=9)
    delegate = _BatchCandidateVerifier()
    current = CachedCandidateVerifier(
        delegate,
        cache,
        selector_fingerprint="1" * 64,
        compatible_selector_fingerprints=("f" * 64,),
    )

    fast = current.verify_fast_many((observation,), expected_board_count=9)

    assert fast[0].recognized_range == SequenceRange(1, 9, 0.95)
    assert delegate.fast_calls == [(0,)]
    assert current.snapshot()["hitCount"] == 0
    assert current.snapshot()["compatibleHitCount"] == 0
    assert current.snapshot()["writeCount"] == 0
    assert len(tuple(cache.root.rglob("*.json"))) == 1


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
    assert REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8.thumbnail_max_edge == 960
    assert (
        REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8.thumbnail_adapter_version
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


class _FixedFallbackRangeRecognizer:
    version = "fixed-fallback-range-v1"

    def recognize(
        self,
        rgb_image: np.ndarray,
        boards: tuple[BoardDetection, ...],
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        del rgb_image, boards
        return SequenceRange(73, 81, 0.99), ()


class _DetectedBoardsDetector:
    version = "detected-boards-v1"

    def __init__(self, board_count: int, *, confidence: float = 0.95) -> None:
        self._board_count = board_count
        self._confidence = confidence

    def detect(
        self,
        rgb_image: np.ndarray,
        *args: object,
        **kwargs: object,
    ) -> DetectionResult:
        del args, kwargs
        height, width = rgb_image.shape[:2]
        boards = tuple(
            BoardDetection(
                position_index=index,
                quad=(
                    Point(20 + index * 2, 30),
                    Point(80 + index * 2, 30),
                    Point(80 + index * 2, 80),
                    Point(20 + index * 2, 80),
                ),
                bounding_box=(20 + index * 2, 30, 60, 50),
                red_border_score=0.9,
                refined_from_grid=False,
            )
            for index in range(self._board_count)
        )
        return DetectionResult(
            status="detected",
            image_width=width,
            image_height=height,
            candidate_count=self._board_count,
            page_quad=(
                Point(5, 5),
                Point(width - 6, 5),
                Point(width - 6, height - 6),
                Point(5, height - 6),
            ),
            boards=boards,
            confidence=self._confidence,
            confidence_components={"candidateCount": self._confidence},
            review_reasons=(),
        )


class _RecordingRangeRecognizer:
    version = "recording-range-v1"

    def __init__(
        self,
        recognized_range: SequenceRange | None,
        reasons: tuple[str, ...] = (),
    ) -> None:
        self._recognized_range = recognized_range
        self._reasons = reasons
        self.board_counts: list[int] = []

    def recognize(
        self,
        rgb_image: np.ndarray,
        boards: tuple[BoardDetection, ...],
    ) -> tuple[SequenceRange | None, tuple[str, ...]]:
        del rgb_image
        self.board_counts.append(len(boards))
        return self._recognized_range, self._reasons


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
    config = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.appearance_descriptor
    analyzer = OpenCvAppearanceFingerprintAnalyzer(config)
    descriptors = []
    for progress in np.linspace(0.0, 1.0, 13):
        intermediate_quad = np.asarray(
            source_quad + (destination_quad - source_quad) * progress,
            dtype=np.float32,
        )
        transformed = cv2.warpPerspective(
            original,
            cv2.getPerspectiveTransform(source_quad, intermediate_quad),
            (width, height),
            borderMode=cv2.BORDER_REFLECT,
        )
        descriptors.append(analyzer.analyze(ThumbnailFrame(transformed, width, height)))

    adjacent_distances = [
        appearance_distance(
            first.appearance_signature,
            second.appearance_signature,
            config,
        )
        for first, second in zip(descriptors, descriptors[1:], strict=False)
    ]
    full_drift_distance = appearance_distance(
        descriptors[0].appearance_signature,
        descriptors[-1].appearance_signature,
        config,
    )

    assert max(adjacent_distances) < (
        APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.appearance_thresholds.adjacent_boundary_distance
    )
    assert full_drift_distance > max(adjacent_distances)


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


def test_v10_1_fallback_range_does_not_claim_complete_representative_geometry(
    tmp_path: Path,
) -> None:
    checksum = _write_jpeg(tmp_path / "00000001.jpg")
    source = _source(checksum)
    observation = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(tmp_path, max_edge=320),
        _FixedLatticeAnalyzer(),
        _FixedQualityAnalyzer(),
    ).analyze(source)

    verified = FullCandidateVerifier(
        tmp_path,
        NoRangeRecognizer(),
        fallback_range_recognizer=_FixedFallbackRangeRecognizer(),
        detector=_RecoveryProbeDetector(),
        allow_grid_recovery=True,
        couple_fallback_to_representative=False,
    ).verify(observation, expected_board_count=9)

    assert verified.range_evidence.recognized_range == SequenceRange(73, 81, 0.99)
    assert verified.representative.board_count is None
    assert verified.representative.geometry_complete is False
    assert verified.representative.full_frame_visible is False


def test_v10_1_stable_full_geometry_uses_anchored_ocr_without_fallback(
    tmp_path: Path,
) -> None:
    checksum = _write_jpeg(tmp_path / "00000001.jpg")
    observation = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(tmp_path, max_edge=320),
        _FixedLatticeAnalyzer(),
        _FixedQualityAnalyzer(),
    ).analyze(_source(checksum))
    anchored = _RecordingRangeRecognizer(SequenceRange(7300, 7308, 0.98))
    fallback = _RecordingRangeRecognizer(SequenceRange(7300, 7308, 0.99))
    telemetry = StageTimingCollector()

    verifier = FullCandidateVerifier(
        tmp_path,
        anchored,
        fallback_range_recognizer=fallback,
        detector=_DetectedBoardsDetector(9),
        allow_grid_recovery=True,
        couple_fallback_to_representative=False,
        full_geometry_policy=FullGeometryPolicy(),
        telemetry=telemetry,
    )
    verified = verifier.verify(observation, expected_board_count=None)
    verifier.record_adaptive_range_stop(
        "confirmed",
        evidence_count=2,
        candidate_count=12,
    )

    assert verified.range_evidence.recognized_range == SequenceRange(7300, 7308, 0.98)
    assert verified.representative.board_count == 9
    assert verified.representative.geometry_complete is True
    assert verified.representative.full_frame_visible is True
    assert anchored.board_counts == [9]
    assert fallback.board_counts == []
    counters = telemetry.snapshot()["counters"]
    assert isinstance(counters, dict)
    assert counters["anchoredOcrAttempts"] == 1
    assert counters["anchoredOcrSuccesses"] == 1
    assert counters["rangeEvidenceVerifications"] == 1
    assert counters["rangeConsensusConfirmed"] == 1
    assert counters["rangeConsensusEvidenceCount"] == 2
    assert counters["rangeConsensusCandidateCount"] == 12
    assert "fallbackOcrAttempts" not in counters


def test_v10_1_anchor_failure_runs_fallback_and_preserves_terminal_board_count(
    tmp_path: Path,
) -> None:
    checksum = _write_jpeg(tmp_path / "00000001.jpg")
    observation = ComposedCheapImageAnalyzer(
        PillowThumbnailLoader(tmp_path, max_edge=320),
        _FixedLatticeAnalyzer(),
        _FixedQualityAnalyzer(),
    ).analyze(_source(checksum))
    anchored = _RecordingRangeRecognizer(None, ("RANGE_ANCHOR_INCONSISTENT",))
    fallback = _RecordingRangeRecognizer(SequenceRange(100, 104, 0.97))
    telemetry = StageTimingCollector()

    verified = FullCandidateVerifier(
        tmp_path,
        anchored,
        fallback_range_recognizer=fallback,
        detector=_DetectedBoardsDetector(5),
        allow_grid_recovery=True,
        couple_fallback_to_representative=False,
        full_geometry_policy=FullGeometryPolicy(),
        telemetry=telemetry,
    ).verify(observation, expected_board_count=None)

    assert verified.range_evidence.recognized_range == SequenceRange(100, 104, 0.97)
    assert verified.representative.board_count == 5
    assert verified.representative.geometry_complete is True
    assert anchored.board_counts == [5]
    assert fallback.board_counts == [5]
    counters = telemetry.snapshot()["counters"]
    assert isinstance(counters, dict)
    assert counters["anchoredOcrAttempts"] == 1
    assert counters["anchoredOcrFailures"] == 1
    assert counters["fallbackOcrAttempts"] == 1
    assert counters["fallbackOcrSuccesses"] == 1


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


class _WideAnchorRecognizer(_AnchorRecognizer):
    def recognize_many(self, rgb_images: tuple[np.ndarray, ...]) -> tuple[Recognition, ...]:
        assert len(rgb_images) == 3
        return (
            Recognition("7300", 0.99),
            Recognition("7304", 0.98),
            Recognition("7308", 0.97),
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


def test_range_adapter_preserves_first_digit_of_four_digit_anchor() -> None:
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

    recognized, reasons = AnchoredSequenceRangeRecognizer(_WideAnchorRecognizer()).recognize(
        np.zeros((420, 340, 3), dtype=np.uint8),
        boards,
    )

    assert reasons == ()
    assert recognized == SequenceRange(7300, 7308, 0.97)


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


class _ProgressiveLabelOcr(_AnchorRecognizer):
    def __init__(self, recognitions: dict[int, Recognition]) -> None:
        self._recognitions = recognitions
        self.batch_sizes: list[int] = []

    def recognize_many(self, rgb_images: tuple[np.ndarray, ...]) -> tuple[Recognition, ...]:
        self.batch_sizes.append(len(rgb_images))
        return tuple(self._recognitions[id(image)] for image in rgb_images)


def _scripted_progressive_recognizer(
    *,
    first_complete_level: int,
    telemetry: StageTimingCollector,
) -> tuple[ProgressiveVisibleSequenceLabelRangeRecognizer, _ProgressiveLabelOcr]:
    labels: list[_VisibleLabel] = []
    recognitions: dict[int, Recognition] = {}
    first_good_index = first_complete_level - 9
    for index in range(72):
        crop = np.full((20, 80, 3), index, dtype=np.uint8)
        if first_good_index <= index < first_complete_level:
            position = index - first_good_index
            row, column = divmod(position, 3)
            center = (400.0 + column * 360.0, 300.0 + row * 100.0)
            recognition = Recognition(str(7300 + position), 0.99)
        else:
            center = (50.0 + index, 50.0 + index)
            recognition = Recognition("", 0.0)
        labels.append(_VisibleLabel(crop=crop, center=center))
        recognitions[id(crop)] = recognition

    class _ScriptedProgressiveRecognizer(ProgressiveVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    ocr = _ProgressiveLabelOcr(recognitions)
    return (
        _ScriptedProgressiveRecognizer(
            ocr,
            ProgressiveVisibleLabelFallbackPolicy(),
            telemetry=telemetry,
        ),
        ocr,
    )


@pytest.mark.parametrize(
    ("resolved_level", "expected_batches"),
    (
        (18, [9, 9]),
        (36, [9, 9, 9, 9]),
        (72, [9, 9, 9, 9, 9, 9, 9, 9]),
    ),
)
def test_progressive_visible_label_fallback_resolves_at_bounded_level(
    resolved_level: int,
    expected_batches: list[int],
) -> None:
    telemetry = StageTimingCollector()
    recognizer, ocr = _scripted_progressive_recognizer(
        first_complete_level=resolved_level,
        telemetry=telemetry,
    )

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert reasons == ()
    assert recognized == SequenceRange(7300, 7308, 0.98025)
    assert ocr.batch_sizes == expected_batches
    counters = telemetry.snapshot()["counters"]
    assert isinstance(counters, dict)
    assert counters["progressiveFallbackCrops"] == resolved_level
    assert counters["progressiveFallbackResolvedCropCount"] == resolved_level
    assert counters[f"progressiveFallbackResolvedAtLevel{resolved_level}"] == 1


def test_progressive_visible_label_fallback_keeps_v10_result_at_level_72() -> None:
    progressive_telemetry = StageTimingCollector()
    progressive, ocr = _scripted_progressive_recognizer(
        first_complete_level=72,
        telemetry=progressive_telemetry,
    )
    labels = progressive._ranked_label_candidates(np.zeros((1080, 1920, 3), dtype=np.uint8))

    class _ScriptedLegacyRecognizer(AccuracyFirstVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return labels

    legacy = _ScriptedLegacyRecognizer(ocr)
    legacy_range, legacy_reasons = legacy.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )
    progressive_range, progressive_reasons = progressive.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert len(labels) == 72
    assert legacy_reasons == progressive_reasons == ()
    assert legacy_range == progressive_range == SequenceRange(7300, 7308, 0.98025)


def test_progressive_visible_label_candidates_keep_multi_digit_horizontal_margin() -> None:
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[300:313, 420:510] = 255

    labels = ProgressiveVisibleSequenceLabelRangeRecognizer._ranked_label_candidates(image)

    assert len(labels) == 1
    assert labels[0].crop.shape[1] >= 108
    assert labels[0].crop.shape[0] >= 23


def test_independent_endpoint_fallback_recovers_checksum_bound_55_63_case() -> None:
    regression = json.loads(RANGE_55_63_REGRESSION_PATH.read_text(encoding="utf-8"))
    assert regression["sourceChecksumSha256"] == (
        "2ea1a6bf2708d384537ddcf2ce11cad80c6d5c8fa7c45da959242447af9b4037"
    )
    labels: list[_VisibleLabel] = []
    recognitions: dict[int, Recognition] = {}
    for index, item in enumerate(regression["evidence"]):
        crop = np.full((20, 80, 3), index + 1, dtype=np.uint8)
        labels.append(
            _VisibleLabel(
                crop=crop,
                center=(float(item["center"][0]), float(item["center"][1])),
            )
        )
        recognitions[id(crop)] = Recognition(
            str(item["number"]),
            float(item["confidence"]),
        )
    while len(labels) < 72:
        index = len(labels)
        crop = np.full((20, 80, 3), index + 1, dtype=np.uint8)
        labels.append(_VisibleLabel(crop=crop, center=(50.0 + index, 50.0 + index)))
        recognitions[id(crop)] = Recognition("", 0.0)

    class _HistoricalProgressive(ProgressiveVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    class _IndependentEndpoint(IndependentEndpointVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    class _ContiguousWindow(ContiguousWindowVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    class _LayoutAnchored(LayoutAnchoredVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _prioritized_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    image_shape = regression["imageShape"]
    image = np.zeros((int(image_shape[0]), int(image_shape[1]), 3), dtype=np.uint8)
    historical = _HistoricalProgressive(
        _ProgressiveLabelOcr(recognitions),
        ProgressiveVisibleLabelFallbackPolicy(),
    )
    independent = _IndependentEndpoint(
        _ProgressiveLabelOcr(recognitions),
        ProgressiveVisibleLabelFallbackPolicy(),
    )
    contiguous = _ContiguousWindow(
        _ProgressiveLabelOcr(recognitions),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18, 36)),
        ContiguousSequenceWindowPolicy(),
    )
    layout_anchored = _LayoutAnchored(
        _ProgressiveLabelOcr(recognitions),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18, 36)),
        LayoutAnchorPolicy(),
    )

    historical_range, historical_reasons = historical.recognize(image, ())
    recognized, reasons = independent.recognize(image, ())
    contiguous_range, contiguous_reasons = contiguous.recognize(image, ())
    anchored_range, anchored_reasons = layout_anchored.recognize(image, ())

    assert historical_range is None
    assert historical_reasons == ("RANGE_LABEL_LATTICE_INCOMPLETE",)
    assert reasons == ()
    assert recognized is not None
    assert [recognized.start, recognized.end] == regression["expectedRange"]
    assert contiguous_reasons == ()
    assert contiguous_range == recognized
    assert anchored_reasons == ()
    assert anchored_range == recognized


def test_layout_anchored_window_accepts_four_positions_despite_unrelated_misread() -> None:
    recognizer = LayoutAnchoredVisibleSequenceLabelRangeRecognizer(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18, 36)),
        LayoutAnchorPolicy(),
    )
    middle = tuple(
        Recognition(str(7300 + position), 0.98) if 4 <= position <= 7 else Recognition("", 0.0)
        for position in range(9)
    )
    unrelated_misread = (*middle[:8], Recognition("99999", 0.99))

    assert recognizer._anchored_window_hypotheses(middle) == (SequenceRange(7300, 7308, 0.97),)
    assert recognizer._anchored_window_hypotheses(unrelated_misread) == (
        SequenceRange(7300, 7308, 0.97),
    )


def test_layout_anchored_window_rejects_two_competing_four_label_sequences() -> None:
    recognizer = LayoutAnchoredVisibleSequenceLabelRangeRecognizer(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18)),
        LayoutAnchorPolicy(),
    )
    competing = tuple(
        Recognition(str(7300 + position), 0.98)
        if position <= 3
        else Recognition(str(8000 + position), 0.98)
        if position >= 5
        else Recognition("", 0.0)
        for position in range(9)
    )

    hypotheses = recognizer._anchored_window_hypotheses(competing)

    assert tuple(candidate.start for candidate in hypotheses) == (7300, 8000)


def test_layout_anchor_requires_five_observed_frames_across_every_axis() -> None:
    recognizer = LayoutAnchoredVisibleSequenceLabelRangeRecognizer(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18, 36)),
        LayoutAnchorPolicy(),
    )

    def boards(observed: set[int]) -> tuple[BoardDetection, ...]:
        return tuple(
            BoardDetection(
                position_index=position,
                quad=(Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)),
                bounding_box=(0, 0, 10, 10),
                red_border_score=0.8 if position in observed else 0.0,
                refined_from_grid=position not in observed,
            )
            for position in range(9)
        )

    assert recognizer._layout_anchor_is_safe(boards({0, 1, 2, 3, 6}))
    assert not recognizer._layout_anchor_is_safe(boards({0, 1, 3, 4, 6}))
    assert not recognizer._layout_anchor_is_safe(boards({0, 1, 2, 3}))
    assert not recognizer._layout_anchor_is_safe(boards({0, 1, 2, 3, 4, 5}))


def test_partial_layout_anchor_accepts_three_frames_across_two_axes() -> None:
    recognizer = PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
    )

    def boards(observed: set[int]) -> tuple[BoardDetection, ...]:
        return tuple(
            BoardDetection(
                position_index=position,
                quad=(Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)),
                bounding_box=(0, 0, 10, 10),
                red_border_score=0.8 if position in observed else 0.0,
                refined_from_grid=position not in observed,
            )
            for position in range(9)
        )

    assert recognizer._layout_anchor_is_safe(boards({1, 4, 6}))
    assert not recognizer._layout_anchor_is_safe(boards({0, 1, 2}))
    assert not recognizer._layout_anchor_is_safe(boards({0, 3, 6}))


def test_partial_layout_anchor_tiers_three_labels_and_two_label_confirmation() -> None:
    recognizer = PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
    )
    strong = {position: Recognition(str(7300 + position), 0.96) for position in (1, 4, 7)}
    weak = {position: Recognition(str(7300 + position), 0.96) for position in (4, 7)}

    assert recognizer._anchored_evidence_hypotheses(strong) == (
        (SequenceRange(7300, 7308, 0.94), "three"),
    )
    weak_evidence = recognizer._anchored_evidence_hypotheses(weak)
    assert weak_evidence == ((SequenceRange(7300, 7308, 0.82), "two"),)
    recognized, reasons = recognizer._record_anchored_resolution(weak_evidence[0])
    assert recognized == SequenceRange(7300, 7308, 0.82)
    assert "RANGE_OCR_FUZZY_CANDIDATE" in reasons


def test_partial_layout_anchor_resolves_preprocessing_variants_as_one_lattice() -> None:
    recognizer = PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
    )
    variants = {
        1: (Recognition("29919", 0.95), Recognition("7301", 0.86)),
        4: (Recognition("29922", 0.94), Recognition("7304", 0.88)),
        7: (Recognition("7307", 0.87),),
    }

    assert recognizer._anchored_evidence_hypotheses(
        variants,
        observed_positions={1, 4, 7},
    ) == ((SequenceRange(7300, 7308, 0.94), "three"),)


def test_v10_10_prioritizes_all_three_label_rows_before_non_label_noise() -> None:
    real_labels = tuple(
        _VisibleLabel(
            crop=np.full((20, 120, 3), position + 1, dtype=np.uint8),
            center=(500.0 + (position % 3) * 460.0, 300.0 + (position // 3) * 110.0),
        )
        for position in range(9)
    )
    noise = tuple(
        _VisibleLabel(
            crop=np.full((22, 60, 3), 100 + index, dtype=np.uint8),
            center=(450.0 + index * 90.0, 430.0),
        )
        for index in range(9)
    )

    class _Ranked(LabelLatticeSafeVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return (*noise, *real_labels)

    prioritized = _Ranked._prioritized_label_candidates(np.zeros((1080, 1920, 3), dtype=np.uint8))

    assert {id(label) for label in prioritized[:9]} == {id(label) for label in real_labels}
    assert {id(label) for label in real_labels[:3]} <= {id(label) for label in prioritized[:9]}


def test_v10_10_label_lattice_ignores_narrow_noise_when_fitting_axes() -> None:
    labels = tuple(
        _VisibleLabel(
            crop=np.full((20, 120, 3), position + 1, dtype=np.uint8),
            center=(500.0 + (position % 3) * 460.0, 300.0 + (position // 3) * 110.0),
        )
        for position in range(9)
    )
    noise = tuple(
        _VisibleLabel(
            crop=np.full((20, 55, 3), 100 + position, dtype=np.uint8),
            center=(420.0 + (position % 3) * 180.0, 420.0 + (position // 3) * 35.0),
        )
        for position in range(9)
    )

    positions = LabelLatticeSafeVisibleSequenceLabelRangeRecognizer._label_lattice_positions(
        (*noise, *labels),
        (1080, 1920),
    )

    assert {positions[index + len(noise)] for index in range(9)} == set(range(9))
    assert not any(index in positions for index in range(len(noise)))


def test_v10_10_recovers_range_from_four_spatial_labels_in_broad_fallback() -> None:
    labels: list[_VisibleLabel] = []
    recognitions: dict[int, Recognition] = {}
    for position in range(9):
        crop = np.full((20, 120, 3), position + 1, dtype=np.uint8)
        labels.append(
            _VisibleLabel(
                crop=crop,
                center=(500.0 + (position % 3) * 460.0, 300.0 + (position // 3) * 110.0),
            )
        )
        recognitions[id(crop)] = (
            Recognition(str(208090 + position), 0.96) if position <= 3 else Recognition("", 0.0)
        )

    class _Scripted(LabelLatticeSafeVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    recognizer = _Scripted(
        _ProgressiveLabelOcr(recognitions),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
        ContiguousSequenceWindowPolicy(),
    )

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert recognized is not None
    assert (recognized.start, recognized.end) == (208090, 208098)
    assert reasons == ("RANGE_OCR_LABEL_LATTICE_WINDOW",)


def test_v10_10_rejects_partial_anchor_without_an_observed_top_row() -> None:
    def boards(observed: set[int]) -> tuple[BoardDetection, ...]:
        return tuple(
            BoardDetection(
                position_index=position,
                quad=(Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)),
                bounding_box=(0, 0, 10, 10),
                red_border_score=0.8 if position in observed else 0.0,
                refined_from_grid=position not in observed,
            )
            for position in range(9)
        )

    v10_9 = PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
    )
    v10_10 = LabelLatticeSafeVisibleSequenceLabelRangeRecognizer(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(12, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
        ContiguousSequenceWindowPolicy(),
    )

    partial = boards({3, 4, 7})
    assert v10_9._layout_anchor_is_safe(partial)
    assert not v10_10._layout_anchor_is_safe(partial)
    assert v10_10._layout_anchor_is_safe(boards({0, 4, 7}))


def test_v10_11_strong_lattice_survives_ambiguous_partial_geometry() -> None:
    expected = SequenceRange(1648, 1656, 0.97)

    class _Scripted(FusedRangeEvidenceVisibleSequenceLabelRangeRecognizer):
        def _recognize_broad_fallback(
            self,
            rgb_image: np.ndarray,
        ) -> tuple[SequenceRange | None, tuple[str, ...]]:
            del rgb_image
            return expected, ("RANGE_OCR_LABEL_LATTICE_WINDOW",)

        def _recognize_progressive_layout(
            self,
            rgb_image: np.ndarray,
            boards: tuple[BoardDetection, ...],
            *,
            cache: dict[tuple[tuple[int, int], ...], tuple[Recognition, ...]],
        ) -> tuple[SequenceRange | None, tuple[str, ...]] | None:
            del rgb_image, boards, cache
            return None, ("RANGE_OCR_LAYOUT_ANCHORED_AMBIGUOUS",)

    recognizer = _Scripted(
        _ProgressiveLabelOcr({}),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(12, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
        ContiguousSequenceWindowPolicy(),
    )

    recognized, reasons = recognizer.recognize_layout_hypotheses(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        ((BoardDetection(0, (), (0, 0, 1, 1), 0.8, False),),),
    )

    assert recognized == expected
    assert reasons == ("RANGE_OCR_LABEL_LATTICE_WINDOW",)


def test_v10_11_fails_closed_when_strong_routes_disagree() -> None:
    lattice = SequenceRange(1648, 1656, 0.97)
    anchored = SequenceRange(1657, 1665, 0.96)

    recognized, reasons = FusedRangeEvidenceVisibleSequenceLabelRangeRecognizer._fuse_routes(
        (lattice, ("RANGE_OCR_LABEL_LATTICE_WINDOW",)),
        (anchored, ("RANGE_OCR_LAYOUT_ANCHORED_FOUR_LABEL",)),
    )

    assert recognized is None
    assert reasons[0] == "RANGE_OCR_FUSED_EVIDENCE_CONFLICT"


def test_v10_11_exposes_three_position_lattice_only_as_fuzzy_evidence() -> None:
    labels: list[_VisibleLabel] = []
    recognitions: dict[int, Recognition] = {}
    for position in range(9):
        crop = np.full((20, 120, 3), position + 1, dtype=np.uint8)
        labels.append(
            _VisibleLabel(
                crop=crop,
                center=(500.0 + (position % 3) * 460.0, 300.0 + (position // 3) * 110.0),
            )
        )
        recognitions[id(crop)] = (
            Recognition(str(3358 + position), 0.93)
            if position in {1, 4, 7}
            else Recognition("", 0.0)
        )

    class _Scripted(FusedRangeEvidenceVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    recognizer = _Scripted(
        _ProgressiveLabelOcr(recognitions),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(12, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
        ContiguousSequenceWindowPolicy(),
    )

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert recognized == SequenceRange(3358, 3366, 0.82)
    assert "RANGE_OCR_FUZZY_CANDIDATE" in reasons
    assert "RANGE_OCR_LABEL_LATTICE_THREE_LABEL" in reasons


def test_v10_12_exposes_two_high_confidence_lattice_labels_as_fuzzy_evidence() -> None:
    labels: list[_VisibleLabel] = []
    recognitions: dict[int, Recognition] = {}
    for position in range(9):
        crop = np.full((20, 120, 3), position + 1, dtype=np.uint8)
        labels.append(
            _VisibleLabel(
                crop=crop,
                center=(500.0 + (position % 3) * 460.0, 300.0 + (position // 3) * 110.0),
            )
        )
        recognitions[id(crop)] = (
            Recognition(str(3520 + position), 0.94) if position in {2, 7} else Recognition("", 0.0)
        )

    class _Scripted(TwoLabelConsensusVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    recognizer = _Scripted(
        _ProgressiveLabelOcr(recognitions),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(12, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
        ContiguousSequenceWindowPolicy(),
    )

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert recognized == SequenceRange(3520, 3528, 0.82)
    assert reasons == (
        "RANGE_OCR_FUZZY_CANDIDATE",
        "RANGE_OCR_LABEL_LATTICE_TWO_LABEL",
    )


def test_v10_12_rejects_ambiguous_two_label_lattice_hypotheses() -> None:
    labels: list[_VisibleLabel] = []
    recognitions: dict[int, Recognition] = {}
    values = {0: (100, 0.95), 1: (101, 0.95), 3: (202, 0.95), 4: (203, 0.95)}
    for position in range(9):
        crop = np.full((20, 120, 3), position + 1, dtype=np.uint8)
        labels.append(
            _VisibleLabel(
                crop=crop,
                center=(500.0 + (position % 3) * 460.0, 300.0 + (position // 3) * 110.0),
            )
        )
        number, confidence = values.get(position, (0, 0.0))
        recognitions[id(crop)] = Recognition(str(number) if number else "", confidence)

    class _Scripted(TwoLabelConsensusVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    recognizer = _Scripted(
        _ProgressiveLabelOcr(recognitions),
        ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(12, 18)),
        LayoutAnchorPolicy(enable_partial_grid_recovery=True),
        ContiguousSequenceWindowPolicy(),
    )

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert recognized is None
    assert reasons == ("RANGE_LABEL_LATTICE_WEAK_AMBIGUOUS",)


def test_layout_blur_gate_rejects_only_when_a_majority_is_severely_blurred(
    tmp_path: Path,
) -> None:
    verifier = BoundedGridCandidateVerifier(
        tmp_path,
        NoRangeRecognizer(),
        layout_anchor_policy=LayoutAnchorPolicy(),
    )
    boards = tuple(
        BoardDetection(
            position_index=position,
            quad=(Point(0, 0), Point(20, 0), Point(20, 20), Point(0, 20)),
            bounding_box=((position % 3) * 30, (position // 3) * 30, 20, 20),
            red_border_score=0.8,
            refined_from_grid=False,
        )
        for position in range(9)
    )
    detection = DetectionResult(
        status="detected",
        image_width=90,
        image_height=90,
        candidate_count=9,
        page_quad=None,
        boards=boards,
        confidence=1.0,
        confidence_components={},
        review_reasons=(),
    )
    blurred = np.full((90, 90, 3), 128, dtype=np.uint8)
    sharp = blurred.copy()
    for position in range(5):
        x = (position % 3) * 30
        y = (position // 3) * 30
        sharp[y : y + 20, x : x + 20] = np.indices((20, 20)).sum(axis=0)[..., None] % 2 * 255

    assert verifier._layout_quality_reasons(blurred, detection) == ("QUALITY_LAYOUT_BLUR",)
    assert verifier._layout_quality_reasons(sharp, detection) == ()


def test_independent_endpoint_fallback_does_not_infer_without_either_edge() -> None:
    positions = (1, 2, 3, 4, 5, 6, 7)
    recognizer = IndependentEndpointVisibleSequenceLabelRangeRecognizer

    assert not recognizer._candidate_position_coverage_is_valid(positions)
    assert not recognizer._inlier_position_coverage_is_valid(positions)


def _scripted_contiguous_window_recognizer(
    evidence: tuple[tuple[int, int, float], ...],
    *,
    telemetry: StageTimingCollector | None = None,
    center_overrides: dict[int, tuple[float, float]] | None = None,
) -> tuple[
    ContiguousWindowVisibleSequenceLabelRangeRecognizer,
    _ProgressiveLabelOcr,
]:
    labels: list[_VisibleLabel] = []
    recognitions: dict[int, Recognition] = {}
    for index, (position, number, confidence) in enumerate(evidence):
        crop = np.full((20, 80, 3), index + 1, dtype=np.uint8)
        row, column = divmod(position, 3)
        labels.append(
            _VisibleLabel(
                crop=crop,
                center=(
                    (400.0 + column * 360.0, 300.0 + row * 100.0)
                    if center_overrides is None or position not in center_overrides
                    else center_overrides[position]
                ),
            )
        )
        recognitions[id(crop)] = Recognition(str(number), confidence)
    used_positions = {position for position, _, _ in evidence}
    for position in range(9):
        if position in used_positions:
            continue
        crop = np.full((20, 80, 3), len(labels) + 1, dtype=np.uint8)
        row, column = divmod(position, 3)
        labels.append(
            _VisibleLabel(
                crop=crop,
                center=(400.0 + column * 360.0, 300.0 + row * 100.0),
            )
        )
        recognitions[id(crop)] = Recognition("", 0.0)

    class _ScriptedContiguousWindow(ContiguousWindowVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _ranked_label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return tuple(labels)

    ocr = _ProgressiveLabelOcr(recognitions)
    return (
        _ScriptedContiguousWindow(
            ocr,
            ProgressiveVisibleLabelFallbackPolicy(candidate_levels=(9, 18, 36)),
            ContiguousSequenceWindowPolicy(),
            telemetry=telemetry,
        ),
        ocr,
    )


@pytest.mark.parametrize("window_start", (0, 4))
def test_contiguous_window_recognizer_resolves_any_four_position_run(
    window_start: int,
) -> None:
    evidence = tuple(
        (position, 1 + position, 0.98) for position in range(window_start, window_start + 4)
    )
    telemetry = StageTimingCollector()
    recognizer, ocr = _scripted_contiguous_window_recognizer(
        evidence,
        telemetry=telemetry,
    )

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert recognized == SequenceRange(1, 9, 0.97)
    assert reasons == ("RANGE_OCR_CONTIGUOUS_WINDOW",)
    assert ocr.batch_sizes == [9]
    counters = telemetry.snapshot()["counters"]
    assert isinstance(counters, dict)
    assert counters["contiguousSequenceWindowResolved"] == 1
    assert counters["progressiveFallbackResolvedAtLevel9"] == 1


def test_contiguous_window_recognizer_projects_a_multi_digit_middle_run() -> None:
    recognizer, _ = _scripted_contiguous_window_recognizer(
        tuple((position, 7300 + position, 0.99) for position in range(4, 8))
    )

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert recognized == SequenceRange(7300, 7308, 0.97)
    assert reasons == ("RANGE_OCR_CONTIGUOUS_WINDOW",)


def test_contiguous_window_recognizer_rejects_three_labels_and_bad_geometry() -> None:
    incomplete, _ = _scripted_contiguous_window_recognizer(
        tuple((position, 100 + position, 0.99) for position in range(3))
    )
    invalid_geometry, _ = _scripted_contiguous_window_recognizer(
        tuple((position, 100 + position, 0.99) for position in range(4)),
        center_overrides={1: (1500.0, 300.0)},
    )
    incomplete_range, _ = incomplete.recognize(np.zeros((1080, 1920, 3), dtype=np.uint8), ())
    invalid_range, _ = invalid_geometry.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert incomplete_range is None
    assert invalid_range is None


def test_contiguous_window_recognizer_fails_closed_on_equal_range_hypotheses() -> None:
    recognizer, _ = _scripted_contiguous_window_recognizer(
        tuple(
            [(position, 1 + position, 0.98) for position in range(4)]
            + [(position, 101 + position, 0.98) for position in range(4)]
        ),
    )

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert recognized is None
    assert reasons == ("RANGE_LABEL_CONTIGUOUS_WINDOW_AMBIGUOUS",)


def test_grid_first_recognizer_corrects_one_missing_leading_digit_from_lattice() -> None:
    labels = tuple(
        _VisibleLabel(
            crop=np.full((20, 80, 3), position + 1, dtype=np.uint8),
            center=(400.0 + (position % 3) * 360.0, 300.0 + (position // 3) * 100.0),
        )
        for position in range(9)
    )
    recognitions = (
        Recognition("300", 0.98),
        *(Recognition(str(7300 + position), 0.98) for position in range(1, 9)),
    )

    recognized, reasons = GridFirstVisibleSequenceLabelRangeRecognizer._resolve_range(
        labels,
        recognitions,
        (1080, 1920),
    )

    assert recognized == SequenceRange(7300, 7308, 0.96)
    assert reasons == ("RANGE_OCR_EXACT",)


def test_grid_first_recognizer_uses_one_nine_crop_ocr_batch() -> None:
    labels = tuple(
        _VisibleLabel(
            crop=np.full((20, 80, 3), position + 1, dtype=np.uint8),
            center=(400.0 + (position % 3) * 360.0, 300.0 + (position // 3) * 100.0),
        )
        for position in range(9)
    )
    recognitions = {
        id(label.crop): Recognition(str(7300 + position), 0.98)
        for position, label in enumerate(labels)
    }

    class _GridRecognizer(GridFirstVisibleSequenceLabelRangeRecognizer):
        @classmethod
        def _label_candidates(cls, rgb_image: np.ndarray) -> tuple[_VisibleLabel, ...]:
            del cls, rgb_image
            return labels

    ocr = _ProgressiveLabelOcr(recognitions)
    telemetry = StageTimingCollector()
    recognizer = _GridRecognizer(ocr, telemetry=telemetry)

    recognized, reasons = recognizer.recognize(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        (),
    )

    assert recognized == SequenceRange(7300, 7308, 0.96)
    assert reasons == ("RANGE_OCR_EXACT",)
    assert ocr.batch_sizes == [9]
    assert telemetry.snapshot()["counters"] == {"ocrCalls": 1, "ocrCrops": 9}


@dataclass
class _ParallelProbeState:
    lock: LockType = field(default_factory=Lock)
    active: int = 0
    maximum_active: int = 0


@dataclass
class _IsolatedVerifierProbe:
    slot: int
    state: _ParallelProbeState
    calls: list[int] = field(default_factory=list)
    active: bool = False

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del expected_board_count
        with self.state.lock:
            assert self.active is False
            self.active = True
            self.state.active += 1
            self.state.maximum_active = max(self.state.maximum_active, self.state.active)
        try:
            sleep(0.02)
            self.calls.append(observation.source.order_index)
            start = 100 + observation.source.order_index * 9
            return CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(SequenceRange(start, start + 8, 0.99)),
            )
        finally:
            with self.state.lock:
                self.active = False
                self.state.active -= 1


def test_parallel_candidate_verifier_isolates_workers_and_preserves_input_order() -> None:
    state = _ParallelProbeState()
    workers = (_IsolatedVerifierProbe(0, state), _IsolatedVerifierProbe(1, state))
    telemetry = StageTimingCollector()
    verifier = DeterministicParallelCandidateVerifier(workers, telemetry=telemetry)
    observations = tuple(
        CheapImageObservation(
            source=replace(
                _source(str(index) * 64),
                order_index=index,
                checksum_sha256=str(index) * 64,
            ),
            width=640,
            height=480,
            fingerprint_hex="a" * 64,
            geometry_signature=(),
            board_count=None,
            geometry_confidence=0.0,
            quality=ImageQualityMetrics(*(0.75 for _ in range(8))),
            appearance_signature=(0.1, 0.2, 0.3),
        )
        for index in range(1, 5)
    )

    results = verifier.verify_many(
        observations,
        expected_board_count=None,
        include_range_evidence=True,
    )

    assert verifier.worker_count == 2
    assert state.maximum_active == 2
    assert workers[0].calls == [1, 3]
    assert workers[1].calls == [2, 4]
    assert [result.recognized_range.start for result in results if result.recognized_range] == [
        109,
        118,
        127,
        136,
    ]
    counters = telemetry.snapshot()["counters"]
    assert isinstance(counters, dict)
    assert counters["parallelVerificationBatches"] == 1
    assert counters["parallelVerificationItems"] == 4
    assert counters["parallelVerificationWorkerSlots"] == 2


def test_standalone_cli_uses_v10_17_and_fails_closed_without_ocr_model(
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

    with pytest.raises(SystemExit) as missing_anchor:
        main(
            (
                "--image-selection-manifest",
                str(manifest_path),
                "--image-selection-output",
                str(output_root),
            )
        )

    assert missing_anchor.value.code == 2

    exit_code = main(
        (
            "--image-selection-manifest",
            str(manifest_path),
            "--image-selection-output",
            str(output_root),
            "--first-sequence-number",
            "1",
        )
    )

    report = json.loads((output_root / "selection-report.json").read_text("utf-8"))
    assert exit_code == 0
    assert report["selectorVersion"] == "fast-image-selector-v10.17"
    assert report["groups"][0]["status"] == "skipped_unreadable"
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
    analyzer, _ = build_default_adapters(
        source_root,
        manifest=REDUCED_FIRST_USABLE_SELECTOR_MANIFEST_V8,
    )
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
