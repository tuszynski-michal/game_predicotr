from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from game_predictor_worker.images.selection.benchmark import (
    BenchmarkDeadlineExceeded,
    BenchmarkProfile,
    ImageSelectionBenchmarkError,
    RealCorpusGolden,
    RealCorpusScreenAnnotation,
    ScaleAnnotations,
    build_accuracy_first_group_annotations,
    build_group_annotations,
    canonical_pretty_json,
    load_scale_annotations,
    run_real_corpus_baseline,
    run_scale_benchmark,
    validate_scale_report,
)
from game_predictor_worker.images.selection.contracts import (
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
)
from game_predictor_worker.images.selection.manifest import (
    APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
)

ROOT = Path(__file__).resolve().parents[3]
ANNOTATIONS_PATH = ROOT / "ai_docs" / "quality" / "image-selection-scale-annotations-v1.json"


def test_scale_annotations_define_bounded_10k_and_30k_profiles() -> None:
    annotations = load_scale_annotations(ANNOTATIONS_PATH)

    assert annotations.profiles["10000"].input_count == 10_000
    assert annotations.profiles["10000"].max_processing_seconds == 900
    assert annotations.profiles["30000"].input_count == 30_000
    assert annotations.profiles["30000"].max_processing_seconds == 2_700
    assert annotations.expected_automatic_labels == {
        "complete_sharp",
        "angled_complete",
    }


def test_group_annotations_cover_jumps_duplicates_manual_and_short_final_page() -> None:
    annotations = load_scale_annotations(ANNOTATIONS_PATH)
    profile = BenchmarkProfile("test", input_count=1_200, group_size=20, max_processing_seconds=30)

    groups = build_group_annotations(profile, annotations)

    assert len(groups) == 60
    assert any(group.manual_required for group in groups)
    assert any(group.duplicate_of_group_order is not None for group in groups)
    before_jump = groups[profile.group_count // 2 - 1]
    after_jump = groups[profile.group_count // 2]
    assert after_jump.range_start > before_jump.range_end + 1
    assert groups[-1].board_count == 5


def test_uncertain_duplicate_is_expected_to_remain_manual() -> None:
    annotations = load_scale_annotations(ANNOTATIONS_PATH)
    profile = BenchmarkProfile("test", input_count=1_200, group_size=20, max_processing_seconds=30)
    groups = build_group_annotations(profile, annotations)

    uncertain_duplicate = next(
        group
        for group in groups
        if group.manual_required and group.duplicate_of_group_order is not None
    )

    assert uncertain_duplicate.group_order == 57


def test_accuracy_first_annotations_are_gap_free_and_keep_short_final_page() -> None:
    annotations = load_scale_annotations(ANNOTATIONS_PATH)
    profile = BenchmarkProfile("test", input_count=65, group_size=20, max_processing_seconds=30)

    groups = build_accuracy_first_group_annotations(profile, annotations)

    assert [(group.range_start, group.range_end) for group in groups] == [
        (1, 9),
        (10, 18),
        (19, 27),
        (28, 32),
    ]
    assert all(not group.manual_required for group in groups)
    assert all(group.duplicate_of_group_order is None for group in groups)


def test_smoke_benchmark_uses_production_scan_and_preserves_source(tmp_path: Path) -> None:
    annotations = load_scale_annotations(ANNOTATIONS_PATH)
    profile = BenchmarkProfile("test", input_count=24, group_size=6, max_processing_seconds=30)
    test_annotations = ScaleAnnotations(
        fingerprint=annotations.fingerprint,
        seed=annotations.seed,
        candidate_cycle=annotations.candidate_cycle,
        expected_automatic_labels=annotations.expected_automatic_labels,
        manual_divisor=annotations.manual_divisor,
        manual_remainder=annotations.manual_remainder,
        duplicate_divisor=annotations.duplicate_divisor,
        duplicate_remainder=annotations.duplicate_remainder,
        duplicate_offset=annotations.duplicate_offset,
        jump_offset=annotations.jump_offset,
        page_size=annotations.page_size,
        final_page_board_count=annotations.final_page_board_count,
        profiles={"test": profile},
    )

    report = run_scale_benchmark(
        work_root=tmp_path / "benchmark",
        profile=profile,
        annotations=test_annotations,
        max_seconds=30,
    )

    metrics = report["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["technicalGatePassed"] is True, json.dumps(report, indent=2)
    assert report["sourceIntegrity"]["sourceUnchanged"] is True
    assert metrics["quality"]["falseMergeCount"] == 0
    assert metrics["quality"]["unsafeAutomaticCount"] == 0
    assert metrics["boundedVerification"]["passed"] is True
    stage_timing = report["stageTiming"]
    assert isinstance(stage_timing, dict)
    assert stage_timing["counters"]["checksumReads"] == profile.input_count
    assert stage_timing["counters"]["decoderCalls"] == profile.input_count
    assert stage_timing["stages"]["decode"]["count"] == profile.input_count
    assert len(report["selectionCodeFingerprint"]) == 64
    validate_scale_report(
        report,
        expected_profile=profile,
        expected_annotation_fingerprint=annotations.fingerprint,
    )


def test_report_validation_rejects_annotation_drift() -> None:
    annotations = load_scale_annotations(ANNOTATIONS_PATH)
    profile = annotations.profiles["smoke"]
    report = {
        "annotationFingerprint": "0" * 64,
        "benchmarkContract": "image-selection-scale-benchmark-v1",
        "inputCount": profile.input_count,
        "metrics": {"technicalGatePassed": True},
        "profile": profile.name,
        "schemaVersion": 1,
        "selectorFingerprint": "0" * 64,
        "sourceIntegrity": {"sourceUnchanged": True},
    }

    with pytest.raises(ImageSelectionBenchmarkError):
        validate_scale_report(
            report,
            expected_profile=profile,
            expected_annotation_fingerprint=annotations.fingerprint,
        )


def test_annotation_json_is_canonical_enough_for_stable_fingerprint() -> None:
    first = load_scale_annotations(ANNOTATIONS_PATH)
    payload = json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    assert payload["contract"] == "image-selection-scale-annotations-v1"
    assert load_scale_annotations(ANNOTATIONS_PATH).fingerprint == first.fingerprint


def test_acceptance_report_binds_each_canonical_profile_report() -> None:
    acceptance_path = ROOT / "ai_docs" / "quality" / "image-selection-acceptance-report.json"
    acceptance_content = acceptance_path.read_bytes()
    acceptance = json.loads(acceptance_content)

    assert acceptance_content.replace(b"\r\n", b"\n") == canonical_pretty_json(acceptance)
    assert acceptance["decision"] == "ready"
    assert acceptance["ownerAcceptance"] == "pending"
    assert acceptance["task0076Allowed"] is False
    for profile in acceptance["profiles"]:
        report_path = ROOT / profile["reportPath"]
        report_content = report_path.read_bytes()
        normalized_report = report_content.replace(b"\r\n", b"\n")
        assert normalized_report == canonical_pretty_json(json.loads(report_content))
        assert hashlib.sha256(normalized_report).hexdigest() == profile["reportSha256"]
        assert profile["technicalGatePassed"] is True


def test_internal_deadline_fails_closed_before_unbounded_work(tmp_path: Path) -> None:
    annotations = load_scale_annotations(ANNOTATIONS_PATH)
    profile = BenchmarkProfile("deadline", input_count=200, group_size=20, max_processing_seconds=1)

    with pytest.raises(BenchmarkDeadlineExceeded):
        run_scale_benchmark(
            work_root=tmp_path / "deadline",
            profile=profile,
            annotations=annotations,
            max_seconds=0.000001,
        )


@dataclass
class _RealGoldenAnalyzer:
    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        page = source.order_index // 100
        signature = _appearance_signature(page)
        return CheapImageObservation(
            source=source,
            width=960,
            height=1280,
            fingerprint_hex=hashlib.sha256(repr(signature).encode("ascii")).hexdigest(),
            geometry_signature=(),
            board_count=None,
            geometry_confidence=0.0,
            quality=ImageQualityMetrics(*(0.8 for _ in range(8))),
            appearance_signature=signature,
        )


@dataclass
class _ForbiddenRealVerifier:
    calls: int = 0

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del observation, expected_board_count
        self.calls += 1
        raise AssertionError("The v9 real-corpus benchmark cannot invoke verification.")


def _appearance_signature(page: int) -> tuple[float, ...]:
    config = APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.appearance_descriptor
    phash = [float(page % 2)] * (config.phash_size**2)
    hue = [0.0] * config.hue_bins
    hue[(page * 3) % config.hue_bins] = 1.0
    saturation = [0.0] * config.saturation_bins
    saturation[page % config.saturation_bins] = 1.0
    value = [0.0] * config.value_bins
    value[(page + 1) % config.value_bins] = 1.0
    edge_grid = [min(1.0, 0.1 + page * 0.2)] * (config.edge_grid_rows * config.edge_grid_columns)
    orientation = [0.0] * config.edge_orientation_bins
    orientation[page % config.edge_orientation_bins] = 1.0
    return tuple((*phash, *hue, *saturation, *value, *edge_grid, *orientation))


def test_real_corpus_gate_measures_golden_cache_and_forbidden_operations(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    sources: list[ImageSelectionSource] = []
    for index in range(500):
        content = f"jpeg-{index}".encode("ascii")
        stored_name = f"{index + 1:08d}.jpg"
        (source_root / stored_name).write_bytes(content)
        sources.append(
            ImageSelectionSource(
                order_index=index,
                relative_path=f"camera/{stored_name}",
                stored_relative_path=stored_name,
                checksum_sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
            )
        )
    manifest_sha256 = "5" * 64
    golden = RealCorpusGolden(
        fingerprint="6" * 64,
        input_manifest_sha256=manifest_sha256,
        annotated_input_count=500,
        screens=tuple(
            RealCorpusScreenAnnotation(
                label=f"screen-{page + 1}",
                minimum_start_order_index=page * 100,
                maximum_start_order_index=page * 100,
            )
            for page in range(5)
        ),
    )
    verifier = _ForbiddenRealVerifier()

    report = run_real_corpus_baseline(
        source_root=source_root,
        sources=tuple(sources),
        input_manifest_sha256=manifest_sha256,
        limit=500,
        max_seconds=30,
        scan_workers=2,
        cache_artifact_root=tmp_path / "cache-artifacts",
        golden=golden,
        manifest=APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
        adapter_factory=lambda _root, _telemetry: (_RealGoldenAnalyzer(), verifier),
    )

    assert report["technicalGatePassed"] is True, json.dumps(report, indent=2)
    assert report["expensiveOperations"] == {
        "boardDetectorCalls": 0,
        "cellCropperCalls": 0,
        "homographyCalls": 0,
        "ocrCalls": 0,
        "ocrCrops": 0,
        "symbolInferenceCalls": 0,
    }
    assert verifier.calls == 0
    assert report["golden"]["falseMergeCount"] == 0
    assert report["golden"]["recall"] == 1.0
    assert report["output"]["publishedRepresentativeCount"] == 5
    assert report["cache"]["cold"]["missCount"] == 500
    assert report["cache"]["warm"]["hitCount"] == 500
    assert report["cache"]["warmResultIdentical"] is True
