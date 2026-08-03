"""Deterministic scale benchmark for the M7.0 image selector."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from PIL import Image, ImageDraw

from game_predictor_worker.benchmarks.performance import PeakMemorySampler

from .adapters import build_default_adapters
from .contracts import (
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    SelectionGroupStatus,
    SequenceRange,
)
from .engine import FastImageSelector
from .manifest import DEFAULT_SELECTOR_MANIFEST

BENCHMARK_CONTRACT = "image-selection-scale-benchmark-v1"
ANNOTATION_CONTRACT = "image-selection-scale-annotations-v1"
RSS_BUDGET_BYTES = 768 * 1024 * 1024


class ImageSelectionBenchmarkError(RuntimeError):
    """Stable failure raised by the local benchmark harness."""


class BenchmarkDeadlineExceeded(ImageSelectionBenchmarkError):
    """Raised when an internal bounded benchmark step exceeds its deadline."""


@dataclass(frozen=True, slots=True)
class BenchmarkProfile:
    name: str
    input_count: int
    group_size: int
    max_processing_seconds: float

    @property
    def group_count(self) -> int:
        return (self.input_count + self.group_size - 1) // self.group_size


@dataclass(frozen=True, slots=True)
class ScaleAnnotations:
    fingerprint: str
    seed: int
    candidate_cycle: tuple[str, ...]
    expected_automatic_labels: frozenset[str]
    manual_divisor: int
    manual_remainder: int
    duplicate_divisor: int
    duplicate_remainder: int
    duplicate_offset: int
    jump_offset: int
    page_size: int
    final_page_board_count: int
    profiles: dict[str, BenchmarkProfile]


@dataclass(frozen=True, slots=True)
class GroupAnnotation:
    group_order: int
    first_order_index: int
    source_count: int
    range_start: int
    range_end: int
    board_count: int
    manual_required: bool
    duplicate_of_group_order: int | None
    fingerprint_hex: str


class BenchmarkDeadline:
    def __init__(self, seconds: float) -> None:
        if seconds <= 0:
            raise ImageSelectionBenchmarkError("Benchmark deadline must be positive.")
        self._started_at = perf_counter()
        self._seconds = seconds

    def check(self, stage: str) -> None:
        if perf_counter() - self._started_at > self._seconds:
            raise BenchmarkDeadlineExceeded(
                f"Image selection benchmark exceeded its deadline during {stage}."
            )


def canonical_pretty_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_scale_annotations(path: Path) -> ScaleAnnotations:
    try:
        content = path.read_bytes()
        value = cast(dict[str, Any], json.loads(content))
        if value["contract"] != ANNOTATION_CONTRACT or int(value["schemaVersion"]) != 1:
            raise ValueError
        manual = cast(dict[str, Any], value["manualGroupPolicy"])
        range_policy = cast(dict[str, Any], value["rangePolicy"])
        profiles_value = cast(dict[str, dict[str, Any]], value["profiles"])
        profiles = {
            name: BenchmarkProfile(
                name=name,
                input_count=int(profile["inputCount"]),
                group_size=int(profile["groupSize"]),
                max_processing_seconds=float(profile["maxProcessingSeconds"]),
            )
            for name, profile in profiles_value.items()
        }
        result = ScaleAnnotations(
            fingerprint=hashlib.sha256(content).hexdigest(),
            seed=int(value["seed"]),
            candidate_cycle=tuple(str(item) for item in value["candidateCycle"]),
            expected_automatic_labels=frozenset(
                str(item) for item in value["expectedAutomaticLabels"]
            ),
            manual_divisor=int(manual["divisor"]),
            manual_remainder=int(manual["remainder"]),
            duplicate_divisor=int(range_policy["duplicateDivisor"]),
            duplicate_remainder=int(range_policy["duplicateRemainder"]),
            duplicate_offset=int(range_policy["duplicateOffset"]),
            jump_offset=int(range_policy["jumpOffset"]),
            page_size=int(range_policy["pageSize"]),
            final_page_board_count=int(value["finalPageBoardCount"]),
            profiles=profiles,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ImageSelectionBenchmarkError(
            "The image-selection scale annotation contract is invalid."
        ) from error
    if (
        not result.candidate_cycle
        or not result.expected_automatic_labels
        or result.manual_divisor < 2
        or not 0 <= result.manual_remainder < result.manual_divisor
        or result.duplicate_offset < 1
        or result.page_size < 1
        or not result.profiles
    ):
        raise ImageSelectionBenchmarkError(
            "The image-selection scale annotation values are invalid."
        )
    for profile in result.profiles.values():
        if profile.input_count < 1 or profile.group_size < 2:
            raise ImageSelectionBenchmarkError("Benchmark profile values are invalid.")
    return result


def _is_manual(group_order: int, annotations: ScaleAnnotations) -> bool:
    return group_order % annotations.manual_divisor == annotations.manual_remainder


def _duplicate_target(group_order: int, annotations: ScaleAnnotations) -> int | None:
    if (
        group_order < annotations.duplicate_offset
        or group_order % annotations.duplicate_divisor != annotations.duplicate_remainder
    ):
        return None
    target = group_order - annotations.duplicate_offset
    while target >= 0 and _is_manual(target, annotations):
        target -= 1
    return target if target >= 0 else None


def build_group_annotations(
    profile: BenchmarkProfile,
    annotations: ScaleAnnotations,
) -> tuple[GroupAnnotation, ...]:
    groups: list[GroupAnnotation] = []
    jump_group = profile.group_count // 2
    for group_order in range(profile.group_count):
        first_index = group_order * profile.group_size
        source_count = min(profile.group_size, profile.input_count - first_index)
        duplicate_of = _duplicate_target(group_order, annotations)
        if duplicate_of is not None:
            start = groups[duplicate_of].range_start
            board_count = groups[duplicate_of].board_count
        else:
            jump = annotations.jump_offset if group_order >= jump_group else 0
            start = 1 + group_order * annotations.page_size + jump
            board_count = (
                annotations.final_page_board_count
                if group_order == profile.group_count - 1
                else annotations.page_size
            )
        end = start + board_count - 1
        fingerprint = hashlib.sha256(f"range:{start}:{end}".encode("ascii")).hexdigest()
        groups.append(
            GroupAnnotation(
                group_order=group_order,
                first_order_index=first_index,
                source_count=source_count,
                range_start=start,
                range_end=end,
                board_count=board_count,
                manual_required=_is_manual(group_order, annotations),
                duplicate_of_group_order=duplicate_of,
                fingerprint_hex=fingerprint,
            )
        )
    return tuple(groups)


def _quality(label: str, *, force_manual: bool) -> ImageQualityMetrics:
    if force_manual:
        label = "occluded"
    values = {
        "complete_sharp": (0.96, 0.92, 0.98, 0.94, 0.92, 0.90, 1.00, 0.96),
        "angled_complete": (0.88, 0.90, 0.97, 0.90, 0.76, 0.82, 1.00, 0.90),
        "blurred": (0.08, 0.90, 0.97, 0.92, 0.90, 0.88, 1.00, 0.50),
        "glare": (0.86, 0.88, 0.95, 0.40, 0.88, 0.86, 1.00, 0.55),
        "occluded": (0.84, 0.88, 0.96, 0.88, 0.86, 0.82, 0.50, 0.58),
        "clipped": (0.86, 0.88, 0.50, 0.86, 0.84, 0.80, 0.90, 0.52),
    }
    try:
        return ImageQualityMetrics(*values[label])
    except KeyError as error:
        raise ImageSelectionBenchmarkError(f"Unknown benchmark quality label: {label}") from error


class InstrumentedScaleAnalyzer:
    """Run the production cheap scan, then apply independent golden observations."""

    def __init__(
        self,
        source_root: Path,
        profile: BenchmarkProfile,
        annotations: ScaleAnnotations,
        groups: tuple[GroupAnnotation, ...],
        deadline: BenchmarkDeadline,
    ) -> None:
        self._production_analyzer, _ = build_default_adapters(source_root)
        self._profile = profile
        self._annotations = annotations
        self._groups = groups
        self._deadline = deadline
        self.scan_count = 0

    def label_for(self, order_index: int) -> str:
        return self._annotations.candidate_cycle[
            (order_index % self._profile.group_size) % len(self._annotations.candidate_cycle)
        ]

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        if source.order_index % 32 == 0:
            self._deadline.check("production cheap scan")
        measured = self._production_analyzer.analyze(source)
        group = self._groups[source.order_index // self._profile.group_size]
        label = self.label_for(source.order_index)
        self.scan_count += 1
        return CheapImageObservation(
            source=source,
            width=measured.width,
            height=measured.height,
            fingerprint_hex=group.fingerprint_hex,
            geometry_signature=(0.12, 0.24, 0.36, 0.48),
            board_count=group.board_count,
            geometry_confidence=0.95,
            quality=_quality(label, force_manual=group.manual_required),
            reason_codes=(),
        )


class InstrumentedRangeVerifier:
    """Count sparse range checks without loading the private OCR model."""

    def __init__(
        self,
        profile: BenchmarkProfile,
        annotations: ScaleAnnotations,
        groups: tuple[GroupAnnotation, ...],
        analyzer: InstrumentedScaleAnalyzer,
    ) -> None:
        self._profile = profile
        self._annotations = annotations
        self._groups = groups
        self._analyzer = analyzer
        self.invocation_count = 0

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        self.invocation_count += 1
        group = self._groups[observation.source.order_index // self._profile.group_size]
        label = self._analyzer.label_for(observation.source.order_index)
        safe = label in self._annotations.expected_automatic_labels and not group.manual_required
        return CandidateVerification(
            recognized_range=SequenceRange(
                start=group.range_start,
                end=group.range_end,
                confidence=0.98,
            ),
            board_count=expected_board_count,
            geometry_complete=safe,
            full_frame_visible=safe,
            reason_codes=() if safe else (f"BENCHMARK_{label.upper()}",),
        )


def _write_template(path: Path, seed: int) -> str:
    image = Image.new("RGB", (960, 720), (16, 20, 30))
    draw = ImageDraw.Draw(image)
    for index in range(36):
        x = 24 + (index * 73 + seed * 11) % 880
        y = 24 + (index * 47 + seed * 7) % 640
        color = (
            40 + (index * 31) % 210,
            40 + (index * 53) % 210,
            40 + (index * 71) % 210,
        )
        draw.rectangle((x, y, min(x + 42, 950), min(y + 30, 710)), outline=color, width=3)
    image.save(path, format="JPEG", quality=86)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_fixture(
    work_root: Path,
    profile: BenchmarkProfile,
    annotations: ScaleAnnotations,
    deadline: BenchmarkDeadline,
) -> tuple[Path, tuple[ImageSelectionSource, ...], dict[str, object]]:
    source_root = work_root / "source"
    source_root.mkdir(parents=True, exist_ok=False)
    template = work_root / "template-0000.jpg"
    checksum = _write_template(template, annotations.seed)
    size_bytes = template.stat().st_size
    sources: list[ImageSelectionSource] = []
    link_mode = "hardlink"
    started_at = perf_counter()
    for index in range(profile.input_count):
        if index % 128 == 0:
            deadline.check("fixture staging")
        file_name = f"{index + 1:08d}.jpg"
        target = source_root / file_name
        shard_index = index // 900
        shard = work_root / f"template-{shard_index:04d}.jpg"
        if shard_index > 0 and index % 900 == 0:
            shutil.copyfile(template, shard)
        try:
            os.link(shard, target)
        except OSError:
            link_mode = "copy"
            shutil.copyfile(template, target)
        sources.append(
            ImageSelectionSource(
                order_index=index,
                relative_path=f"camera/{file_name}",
                stored_relative_path=file_name,
                checksum_sha256=checksum,
                size_bytes=size_bytes,
            )
        )
    elapsed = perf_counter() - started_at
    unique_file_ids = {
        (path.stat().st_dev, path.stat().st_ino) for path in source_root.iterdir()
    }
    return (
        source_root,
        tuple(sources),
        {
            "elapsedSeconds": round(elapsed, 6),
            "inputLogicalBytes": profile.input_count * size_bytes,
            "stagingMode": link_mode,
            "uniquePhysicalFileIds": len(unique_file_ids),
        },
    )


def inventory_sha256(
    source_root: Path,
    sources: tuple[ImageSelectionSource, ...],
    deadline: BenchmarkDeadline,
    *,
    stage: str,
) -> str:
    digest = hashlib.sha256()
    for index, source in enumerate(sources):
        if index % 128 == 0:
            deadline.check(stage)
        path = source_root / source.stored_relative_path
        content_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(
            f"{source.order_index}:{source.stored_relative_path}:{path.stat().st_size}:"
            f"{content_checksum}\n".encode("ascii")
        )
    return digest.hexdigest()


def _expected_status(group: GroupAnnotation) -> str:
    if group.manual_required:
        return SelectionGroupStatus.MANUAL_REQUIRED.value
    if group.duplicate_of_group_order is not None:
        return SelectionGroupStatus.SKIPPED_EXISTING_RANGE.value
    return SelectionGroupStatus.AUTO_SELECTED.value


def evaluate_result(
    *,
    profile: BenchmarkProfile,
    annotations: ScaleAnnotations,
    expected_groups: tuple[GroupAnnotation, ...],
    result: Any,
    verifier: InstrumentedRangeVerifier,
    processing_seconds: float,
    memory: dict[str, int | None],
    source_file_size: int,
) -> dict[str, object]:
    predicted_groups = tuple(result.groups)
    exact_groups = 0
    false_merges = 0
    false_splits = 0
    status_errors = 0
    range_errors = 0
    unsafe_automatic = 0
    automatic_count = 0
    manual_count = 0
    selected_indexes: list[int] = []
    cursor = 0
    expected_boundaries = {
        item.first_order_index + item.source_count for item in expected_groups[:-1]
    }
    predicted_boundaries: set[int] = set()
    for group in predicted_groups:
        cursor += group.source_count
        if cursor < profile.input_count:
            predicted_boundaries.add(cursor)
    false_merges = len(expected_boundaries - predicted_boundaries)
    false_splits = len(predicted_boundaries - expected_boundaries)
    for index, predicted in enumerate(predicted_groups):
        if index >= len(expected_groups):
            continue
        expected = expected_groups[index]
        expected_range = (expected.range_start, expected.range_end)
        predicted_range = (
            None
            if predicted.range is None
            else (predicted.range.start, predicted.range.end)
        )
        if predicted.source_count == expected.source_count:
            exact_groups += 1
        if predicted.status.value != _expected_status(expected):
            status_errors += 1
        if predicted_range != expected_range:
            range_errors += 1
        if predicted.status is SelectionGroupStatus.MANUAL_REQUIRED:
            manual_count += 1
        if predicted.status is SelectionGroupStatus.AUTO_SELECTED:
            automatic_count += 1
            selected = predicted.selected_candidate
            if selected is None:
                unsafe_automatic += 1
            else:
                selected_indexes.append(selected.source.order_index)
                label = annotations.candidate_cycle[
                    (selected.source.order_index % profile.group_size)
                    % len(annotations.candidate_cycle)
                ]
                if label not in annotations.expected_automatic_labels:
                    unsafe_automatic += 1
    predicted_count = len(predicted_groups)
    expected_count = len(expected_groups)
    automatic_precision = (
        1.0 if automatic_count == 0 else (automatic_count - unsafe_automatic) / automatic_count
    )
    grouping_precision = exact_groups / predicted_count if predicted_count else 0.0
    grouping_recall = exact_groups / expected_count if expected_count else 0.0
    recognized_count = sum(group.range is not None for group in predicted_groups)
    unique_range_count = len(
        {
            (group.range_start, group.range_end)
            for group in expected_groups
        }
    )
    output_logical_bytes = unique_range_count * source_file_size
    max_verifications = predicted_count * DEFAULT_SELECTOR_MANIFEST.top_k
    throughput = profile.input_count / processing_seconds if processing_seconds > 0 else 0.0
    peak_delta = memory.get("peakRssDeltaBytes")
    memory_pass = peak_delta is None or int(peak_delta) <= RSS_BUDGET_BYTES
    quality_pass = (
        false_merges == 0
        and false_splits == 0
        and status_errors == 0
        and range_errors == 0
        and unsafe_automatic == 0
        and automatic_precision == 1.0
        and grouping_precision == 1.0
        and grouping_recall == 1.0
    )
    performance_pass = processing_seconds <= profile.max_processing_seconds
    bounded_verification_pass = verifier.invocation_count <= max_verifications
    return {
        "boundedVerification": {
            "maxAllowed": max_verifications,
            "passed": bounded_verification_pass,
            "sparseRangeVerificationCount": verifier.invocation_count,
            "topK": DEFAULT_SELECTOR_MANIFEST.top_k,
        },
        "comparisonWithFullPipeline": {
            "estimatedCuratedInputCount": unique_range_count,
            "estimatedInputReductionFactor": round(profile.input_count / unique_range_count, 4),
            "fullPipelineInputCount": profile.input_count,
        },
        "coverage": round(recognized_count / expected_count, 6),
        "groupingPrecision": round(grouping_precision, 6),
        "groupingRecall": round(grouping_recall, 6),
        "manualRate": round(manual_count / expected_count, 6),
        "outputStorage": {
            "estimatedLogicalBytes": output_logical_bytes,
            "representativeCount": unique_range_count,
        },
        "quality": {
            "automaticCount": automatic_count,
            "automaticSelectionPrecision": round(automatic_precision, 6),
            "falseMergeCount": false_merges,
            "falseSplitCount": false_splits,
            "manualCount": manual_count,
            "rangeErrorCount": range_errors,
            "selectedOrderIndexSample": selected_indexes[:20],
            "statusErrorCount": status_errors,
            "unsafeAutomaticCount": unsafe_automatic,
        },
        "runtime": {
            "maxProcessingSeconds": profile.max_processing_seconds,
            "passed": performance_pass,
            "processingSeconds": round(processing_seconds, 6),
            "throughputFilesPerSecond": round(throughput, 4),
        },
        "storageBudget": {
            "peakRssBudgetBytes": RSS_BUDGET_BYTES,
            "peakRssPassed": memory_pass,
        },
        "technicalGatePassed": (
            quality_pass and performance_pass and memory_pass and bounded_verification_pass
        ),
    }


def run_scale_benchmark(
    *,
    work_root: Path,
    profile: BenchmarkProfile,
    annotations: ScaleAnnotations,
    max_seconds: float,
) -> dict[str, object]:
    deadline = BenchmarkDeadline(max_seconds)
    work_root.mkdir(parents=True, exist_ok=False)
    source_root, sources, upload = stage_fixture(work_root, profile, annotations, deadline)
    before_inventory = inventory_sha256(
        source_root,
        sources,
        deadline,
        stage="pre-run source inventory",
    )
    groups = build_group_annotations(profile, annotations)
    analyzer = InstrumentedScaleAnalyzer(
        source_root,
        profile,
        annotations,
        groups,
        deadline,
    )
    verifier = InstrumentedRangeVerifier(profile, annotations, groups, analyzer)
    started_at = perf_counter()
    with PeakMemorySampler() as sampler:
        result = FastImageSelector().select(
            sources,
            analyzer=analyzer,
            verifier=verifier,
        )
    processing_seconds = perf_counter() - started_at
    memory = sampler.summary().to_dict()
    deadline.check("post-run validation")
    after_inventory = inventory_sha256(
        source_root,
        sources,
        deadline,
        stage="post-run source inventory",
    )
    source_unchanged = before_inventory == after_inventory
    metrics = evaluate_result(
        profile=profile,
        annotations=annotations,
        expected_groups=groups,
        result=result,
        verifier=verifier,
        processing_seconds=processing_seconds,
        memory=memory,
        source_file_size=sources[0].size_bytes,
    )
    metrics["technicalGatePassed"] = bool(metrics["technicalGatePassed"]) and source_unchanged
    return {
        "annotationFingerprint": annotations.fingerprint,
        "benchmarkContract": BENCHMARK_CONTRACT,
        "fixture": upload,
        "inputCount": profile.input_count,
        "memory": memory,
        "metrics": metrics,
        "profile": profile.name,
        "rangeVerificationMode": "deterministic-annotation-with-production-cheap-scan",
        "schemaVersion": 1,
        "selectorFingerprint": DEFAULT_SELECTOR_MANIFEST.fingerprint,
        "selectorVersion": DEFAULT_SELECTOR_MANIFEST.algorithm_version,
        "sourceIntegrity": {
            "afterInventorySha256": after_inventory,
            "beforeInventorySha256": before_inventory,
            "sourceUnchanged": source_unchanged,
        },
    }


def validate_scale_report(
    report: dict[str, Any],
    *,
    expected_profile: BenchmarkProfile,
    expected_annotation_fingerprint: str,
) -> None:
    try:
        if (
            report["benchmarkContract"] != BENCHMARK_CONTRACT
            or int(report["schemaVersion"]) != 1
            or report["profile"] != expected_profile.name
            or int(report["inputCount"]) != expected_profile.input_count
            or report["annotationFingerprint"] != expected_annotation_fingerprint
            or report["selectorFingerprint"] != DEFAULT_SELECTOR_MANIFEST.fingerprint
        ):
            raise ValueError
        metrics = cast(dict[str, Any], report["metrics"])
        integrity = cast(dict[str, Any], report["sourceIntegrity"])
        if not isinstance(metrics["technicalGatePassed"], bool):
            raise ValueError
        if integrity["sourceUnchanged"] is not True:
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ImageSelectionBenchmarkError(
            "The saved image-selection benchmark report is invalid."
        ) from error


__all__ = [
    "BENCHMARK_CONTRACT",
    "BenchmarkDeadlineExceeded",
    "BenchmarkProfile",
    "ImageSelectionBenchmarkError",
    "ScaleAnnotations",
    "canonical_pretty_json",
    "load_scale_annotations",
    "run_scale_benchmark",
    "validate_scale_report",
]
