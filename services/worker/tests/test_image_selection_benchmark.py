from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images.selection.benchmark import (
    BenchmarkDeadlineExceeded,
    BenchmarkProfile,
    ImageSelectionBenchmarkError,
    ScaleAnnotations,
    build_group_annotations,
    canonical_pretty_json,
    load_scale_annotations,
    run_scale_benchmark,
    validate_scale_report,
)

ROOT = Path(__file__).resolve().parents[3]
ANNOTATIONS_PATH = (
    ROOT / "ai_docs" / "quality" / "image-selection-scale-annotations-v1.json"
)


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
    assert metrics["technicalGatePassed"] is True
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
    acceptance_path = (
        ROOT / "ai_docs" / "quality" / "image-selection-acceptance-report.json"
    )
    acceptance_content = acceptance_path.read_bytes()
    acceptance = json.loads(acceptance_content)

    assert acceptance_content == canonical_pretty_json(acceptance)
    assert acceptance["decision"] == "ready"
    assert acceptance["ownerAcceptance"] == "pending"
    assert acceptance["task0076Allowed"] is False
    for profile in acceptance["profiles"]:
        report_path = ROOT / profile["reportPath"]
        report_content = report_path.read_bytes()
        assert report_content == canonical_pretty_json(json.loads(report_content))
        assert hashlib.sha256(report_content).hexdigest() == profile["reportSha256"]
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
