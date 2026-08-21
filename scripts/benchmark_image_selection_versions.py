"""Compare two immutable selector versions on one read-only staging prefix."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from threading import Lock
from time import perf_counter

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
API_SOURCE = REPOSITORY_ROOT / "services" / "api" / "src"
sys.path.insert(0, str(WORKER_SOURCE))
sys.path.insert(0, str(API_SOURCE))

from game_predictor_worker.images.selection.cache import (  # noqa: E402
    CachedCandidateVerifier,
    CachedCheapImageAnalyzer,
    FileImageScanObservationCache,
    FileImageVerificationCache,
)
from game_predictor_worker.images.selection.contracts import (  # noqa: E402
    CheapImageAnalyzer,
    CheapImageObservation,
    ImageSelectionSource,
    SequenceRange,
)
from game_predictor_worker.images.selection.engine import FastImageSelector  # noqa: E402
from game_predictor_worker.images.selection.io import (  # noqa: E402
    load_browser_selection_manifest,
)
from game_predictor_worker.images.selection.job import ImageSelectionJobHandler  # noqa: E402
from game_predictor_worker.images.selection.manifest import (  # noqa: E402
    ADAPTIVE_CARDINALITY_SELECTOR_MANIFEST_V1015,
    PROOF_FIRST_SELECTOR_MANIFEST_V1019,
    QUANTILE_SAMPLED_SELECTOR_MANIFEST_V1017,
    SEQUENCE_STABLE_SELECTOR_MANIFEST_V1021,
    SEQUENCE_VALIDATED_SELECTOR_MANIFEST_V1020,
    SINGLE_FRAME_EARLY_EXIT_SELECTOR_MANIFEST_V1018,
    STAGED_OCR_SELECTOR_MANIFEST_V1016,
    SelectorManifest,
)
from game_predictor_worker.images.selection.range_proof import (  # noqa: E402
    has_strong_local_range_proof,
)
from game_predictor_worker.images.selection.recovery import (  # noqa: E402
    RecoveryProjection,
    reconcile_projection_to_sequence_bounds,
)
from game_predictor_worker.images.selection.sequence_bounds import (  # noqa: E402
    SequenceBounds,
)
from game_predictor_worker.images.selection.telemetry import (  # noqa: E402
    StageTimingCollector,
)

MANIFESTS = {
    "v10.15": ADAPTIVE_CARDINALITY_SELECTOR_MANIFEST_V1015,
    "v10.16": STAGED_OCR_SELECTOR_MANIFEST_V1016,
    "v10.17": QUANTILE_SAMPLED_SELECTOR_MANIFEST_V1017,
    "v10.18": SINGLE_FRAME_EARLY_EXIT_SELECTOR_MANIFEST_V1018,
    "v10.19": PROOF_FIRST_SELECTOR_MANIFEST_V1019,
    "v10.20": SEQUENCE_VALIDATED_SELECTOR_MANIFEST_V1020,
    "v10.21": SEQUENCE_STABLE_SELECTOR_MANIFEST_V1021,
}
_JPEG_SUFFIXES = {".jpeg", ".jpg"}
_NATURAL_PART = re.compile(r"(\d+)")


class _ProgressAnalyzer:
    def __init__(self, delegate: CheapImageAnalyzer, *, total: int) -> None:
        self._delegate = delegate
        self._total = total
        self._completed = 0
        self._lock = Lock()
        self._step = max(100, min(500, total // 20 or 1))

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        observation = self._delegate.analyze(source)
        with self._lock:
            self._completed += 1
            completed = self._completed
        if completed == self._total or completed % self._step == 0:
            print(f"Scanned {completed}/{self._total} sources.", flush=True)
        return observation


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--expected-groups", type=int, required=True)
    parser.add_argument("--first-sequence-number", type=int, required=True)
    parser.add_argument("--last-sequence-number", type=int)
    parser.add_argument(
        "--sequence-direction",
        choices=("ascending", "descending"),
        default="ascending",
    )
    parser.add_argument(
        "--source-order",
        choices=("natural", "reverse"),
        default="natural",
        help="Read the source manifest or raw JPEG directory in natural or reverse order.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--annotations",
        type=Path,
        help=(
            "Optional manually reviewed corpus contract. When supplied, every path, "
            "checksum, range, and readability decision is verified before the run."
        ),
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts",
        help="Isolated cache root; use a fresh directory for a cold comparison.",
    )
    parser.add_argument(
        "--order",
        nargs="+",
        choices=tuple(MANIFESTS),
        default=("v10.21", "v10.20"),
        help=(
            "One candidate version for a cold production gate, or candidate and "
            "baseline versions for an in-process comparison."
        ),
    )
    return parser.parse_args()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _natural_path_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in _NATURAL_PART.split(value)
    )


def _load_sources(
    source_root: Path,
    *,
    source_order: str,
    limit: int | None = None,
) -> tuple[tuple[ImageSelectionSource, ...], str, str]:
    manifest_path = source_root / "_browser_manifest.json"
    if manifest_path.is_file():
        sources, fingerprint = load_browser_selection_manifest(manifest_path)
        source_kind = "browser_staging"
    else:
        files = tuple(
            sorted(
                (
                    path
                    for path in source_root.rglob("*")
                    if path.is_file() and path.suffix.casefold() in _JPEG_SUFFIXES
                ),
                key=lambda path: (
                    _natural_path_key(path.relative_to(source_root).as_posix()),
                    path.relative_to(source_root).as_posix(),
                ),
            )
        )
        if limit is not None:
            files = files[:limit]
        if not files:
            raise SystemExit("--source-root contains no JPEG files.")
        raw_sources: list[ImageSelectionSource] = []
        digest_entries: list[dict[str, object]] = []
        for order_index, path in enumerate(files):
            relative_path = path.relative_to(source_root).as_posix()
            content_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            size_bytes = path.stat().st_size
            raw_sources.append(
                ImageSelectionSource(
                    order_index=order_index,
                    relative_path=relative_path,
                    stored_relative_path=relative_path,
                    checksum_sha256=content_sha256,
                    size_bytes=size_bytes,
                )
            )
            digest_entries.append(
                {
                    "checksumSha256": content_sha256,
                    "relativePath": relative_path,
                    "sizeBytes": size_bytes,
                }
            )
        sources = tuple(raw_sources)
        fingerprint = hashlib.sha256(_canonical_bytes(digest_entries)).hexdigest()
        source_kind = "raw_jpeg_directory"
    if source_order == "reverse":
        sources = tuple(
            replace(source, order_index=index) for index, source in enumerate(reversed(sources))
        )
        fingerprint = hashlib.sha256(
            _canonical_bytes(
                {
                    "baseFingerprint": fingerprint,
                    "sourceOrder": "reverse",
                }
            )
        ).hexdigest()
    return sources, fingerprint, source_kind


def _read_annotation_contract(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Unable to read --annotations: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit("--annotations must contain one JSON object.")
    if value.get("contract") != "image-selection-real-corpus-annotations-v2":
        raise SystemExit("--annotations uses an unsupported contract.")
    if value.get("schemaVersion") != 2:
        raise SystemExit("--annotations uses an unsupported schema version.")
    cases = value.get("cases")
    corpus = value.get("corpus")
    expected = value.get("expectedSequence")
    if not isinstance(cases, list) or not cases:
        raise SystemExit("--annotations must contain at least one reviewed case.")
    if not isinstance(corpus, dict) or not isinstance(expected, dict):
        raise SystemExit("--annotations is missing corpus or expectedSequence metadata.")
    return value


def _validated_annotation_cases(
    path: Path,
    *,
    sources: tuple[ImageSelectionSource, ...],
    input_manifest_sha256: str,
    source_order: str,
    expected_group_count: int,
    first_sequence_number: int,
    last_sequence_number: int | None,
    sequence_direction: str,
) -> tuple[dict[str, object], ...]:
    contract = _read_annotation_contract(path)
    corpus = contract["corpus"]
    expected = contract["expectedSequence"]
    cases = contract["cases"]
    assert isinstance(corpus, dict)
    assert isinstance(expected, dict)
    assert isinstance(cases, list)
    if corpus.get("inputManifestSha256") != input_manifest_sha256:
        raise SystemExit("--annotations does not match the source corpus fingerprint.")
    if corpus.get("sourceOrder") != source_order or corpus.get("imageCount") != len(sources):
        raise SystemExit("--annotations does not match the source order or image count.")
    if last_sequence_number is None:
        raise SystemExit("--annotations requires --last-sequence-number.")
    bounds = SequenceBounds(
        first_sequence_number,
        last_sequence_number,
        sequence_direction,
    )
    declared_bounds = (
        expected.get("first"),
        expected.get("last"),
        expected.get("direction"),
        expected.get("groupSize"),
        expected.get("groupCount"),
    )
    actual_bounds = (
        bounds.first,
        bounds.last,
        bounds.direction,
        bounds.group_size,
        bounds.expected_group_count,
    )
    if declared_bounds != actual_bounds or expected_group_count != bounds.expected_group_count:
        raise SystemExit("--annotations does not match the requested sequence bounds.")

    by_path = {source.relative_path: source for source in sources}
    reviewed: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    clear_ranges: set[tuple[int, int]] = set()
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            raise SystemExit("--annotations contains a non-object case.")
        relative_path = raw_case.get("relativePath")
        checksum = raw_case.get("checksumSha256")
        size_bytes = raw_case.get("sizeBytes")
        order_index = raw_case.get("orderIndex")
        readability = raw_case.get("readability")
        expected_range = raw_case.get("expectedRange")
        if not isinstance(relative_path, str) or relative_path in seen_paths:
            raise SystemExit("--annotations contains a missing or duplicate relativePath.")
        source = by_path.get(relative_path)
        if source is None:
            raise SystemExit(f"Annotated source is missing: {relative_path}")
        if (
            checksum != source.checksum_sha256
            or size_bytes != source.size_bytes
            or order_index != source.order_index
        ):
            raise SystemExit(f"Annotated source identity changed: {relative_path}")
        if readability not in {"clear", "borderline", "unreadable"}:
            raise SystemExit(f"Annotated readability is invalid: {relative_path}")
        if not isinstance(expected_range, dict):
            raise SystemExit(f"Annotated expected range is missing: {relative_path}")
        range_start = expected_range.get("start")
        range_end = expected_range.get("end")
        if not isinstance(range_start, int) or not isinstance(range_end, int):
            raise SystemExit(f"Annotated expected range is invalid: {relative_path}")
        annotated_range = (range_start, range_end)
        if bounds.group_index_for_range(SequenceRange(*annotated_range, 1.0)) is None:
            raise SystemExit(f"Annotated range is outside the declared grid: {relative_path}")
        if raw_case.get("automaticCandidateEligible") is True:
            clear_ranges.add(annotated_range)
        seen_paths.add(relative_path)
        reviewed.append(raw_case)

    expected_ranges = {
        (value.start, value.end)
        for value in (bounds.range_for_group(index) for index in range(bounds.expected_group_count))
    }
    if clear_ranges != expected_ranges:
        raise SystemExit(
            "--annotations must contain an automatic-quality reference for every range."
        )
    return tuple(reviewed)


def _run(
    source_root: Path,
    *,
    artifact_root: Path,
    manifest: SelectorManifest,
    sources: tuple[ImageSelectionSource, ...],
    expected_group_count: int,
    first_sequence_number: int,
    last_sequence_number: int | None,
    sequence_direction: str,
    annotation_cases: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    telemetry = StageTimingCollector()
    handler = ImageSelectionJobHandler(
        object(),  # type: ignore[arg-type]
        browser_upload_root=REPOSITORY_ROOT / "imports",
        artifact_root=artifact_root,
        repository_root=REPOSITORY_ROOT,
        selector_manifest=manifest,
        verification_workers=1,
        scan_workers=4,
        scan_prefetch=8,
    )
    analyzer, verifier = handler.build_runtime_adapters(source_root, manifest, telemetry)
    cached_analyzer = CachedCheapImageAnalyzer(
        analyzer,
        FileImageScanObservationCache(artifact_root),
        scan_adapter_fingerprint=manifest.scan_adapter_fingerprint,
    )
    cached_verifier = CachedCandidateVerifier(
        verifier,
        FileImageVerificationCache(artifact_root),
        selector_fingerprint=manifest.fingerprint,
    )
    started_at = perf_counter()
    result = FastImageSelector(
        manifest,
        scan_workers=4,
        scan_prefetch=8,
    ).select(
        sources,
        analyzer=_ProgressAnalyzer(cached_analyzer, total=len(sources)),
        verifier=cached_verifier,
        sequence_direction=sequence_direction,
        first_sequence_number=first_sequence_number,
        last_sequence_number=last_sequence_number,
        expected_group_count_for_partitioning=(
            None if manifest is SEQUENCE_STABLE_SELECTOR_MANIFEST_V1021 else expected_group_count
        ),
    )
    bounds: SequenceBounds | None = None
    if last_sequence_number is not None:
        bounds = SequenceBounds(
            first_sequence_number,
            last_sequence_number,
            sequence_direction,
        )
        if bounds.expected_group_count != expected_group_count:
            raise SystemExit("--expected-groups does not match the inclusive sequence bounds.")
        projection = reconcile_projection_to_sequence_bounds(
            RecoveryProjection(
                groups=result.groups,
                group_sources={},
                origin_group_ids={},
            ),
            bounds=bounds,
            require_local_range_proof=(
                manifest.algorithm_version
                in {
                    "fast-image-selector-v10.19",
                    "fast-image-selector-v10.20",
                    "fast-image-selector-v10.21",
                }
            ),
            allow_expected_sequence_confirmation=(
                manifest.algorithm_version
                in {"fast-image-selector-v10.20", "fast-image-selector-v10.21"}
            ),
        )
        result = replace(result, groups=projection.groups)
    elapsed_seconds = perf_counter() - started_at
    annotation_gate = _evaluate_annotation_cases(
        annotation_cases,
        sources=sources,
        analyzer=cached_analyzer,
        verifier=cached_verifier,
        manifest=manifest,
    )
    serialized_groups = tuple(group.to_dict() for group in result.groups)
    statuses = Counter(group.status.value for group in result.groups)
    serialized_projection = tuple(
        {
            "range": (
                None
                if group.range is None
                else {
                    "confidence": group.range.confidence,
                    "end": group.range.end,
                    "start": group.range.start,
                }
            ),
            "selectedChecksumSha256": (
                None
                if group.selected_candidate is None
                else group.selected_candidate.source.checksum_sha256
            ),
            "status": group.status.value,
        }
        for group in result.groups
    )
    timing = telemetry.snapshot()
    verification_distribution = _verification_distribution(timing)
    automatic = tuple(group for group in result.groups if group.status.value == "auto_selected")
    logical_owners = tuple(
        group for group in result.groups if group.status.value != "skipped_existing_range"
    )
    covered_slots = (
        frozenset()
        if bounds is None
        else frozenset(
            slot
            for group in logical_owners
            if group.range is not None
            and (slot := bounds.group_index_for_range(group.range)) is not None
        )
    )
    proof_violations = sum(
        1
        for group in automatic
        if group.selected_candidate is None
        or not has_strong_local_range_proof(
            group.selected_candidate.recognized_range,
            group.selected_candidate.reason_codes,
            minimum_confidence=manifest.thresholds.minimum_range_confidence,
            label_observations=group.selected_candidate.range_label_observations,
            require_position_evidence=(
                manifest.algorithm_version
                in {
                    "fast-image-selector-v10.19",
                    "fast-image-selector-v10.20",
                    "fast-image-selector-v10.21",
                }
            ),
        )
    )
    return {
        "annotationGate": annotation_gate,
        "automaticRangeProofViolationCount": proof_violations,
        "cardinalityInferredAutomaticCount": sum(
            1
            for group in automatic
            if group.selected_candidate is not None
            and "RANGE_CARDINALITY_INFERRED" in group.selected_candidate.reason_codes
        ),
        "elapsedSeconds": round(elapsed_seconds, 6),
        "groupCount": len(serialized_groups),
        "logicalOwnerCount": len(logical_owners),
        "groups": [
            {
                "boardCountConsensus": group.board_count_consensus,
                "groupOrder": group.group_order,
                "range": None if group.range is None else group.range.to_dict(),
                "selectedCandidate": (
                    None if group.selected_candidate is None else group.selected_candidate.to_dict()
                ),
                "sourceCount": group.source_count,
                "status": group.status.value,
                "topCandidates": [candidate.to_dict() for candidate in group.top_candidates],
            }
            for group in result.groups
        ],
        "scanCache": cached_analyzer.snapshot(),
        "verificationCache": cached_verifier.snapshot(),
        "projectionSha256": hashlib.sha256(_canonical_bytes(serialized_projection)).hexdigest(),
        "selectorFingerprint": manifest.fingerprint,
        "selectorVersion": manifest.algorithm_version,
        "sequenceCoverageCount": len(covered_slots),
        "sequenceCoverageComplete": (
            bounds is not None
            and len(logical_owners) == bounds.expected_group_count
            and len(covered_slots) == bounds.expected_group_count
        ),
        "stageTiming": timing,
        "statusCounts": dict(sorted(statuses.items())),
        "verificationCount": result.verification_count,
        **verification_distribution,
    }


def _evaluate_annotation_cases(
    cases: tuple[dict[str, object], ...],
    *,
    sources: tuple[ImageSelectionSource, ...],
    analyzer: CachedCheapImageAnalyzer,
    verifier: CachedCandidateVerifier,
    manifest: SelectorManifest,
) -> dict[str, object] | None:
    if not cases:
        return None
    policy = manifest.representative_policy
    if policy is None:
        raise SystemExit("The annotated gate requires a representative quality policy.")
    by_path = {source.relative_path: source for source in sources}
    results: list[dict[str, object]] = []
    for case in cases:
        relative_path = case["relativePath"]
        expected_value = case["expectedRange"]
        assert isinstance(relative_path, str)
        assert isinstance(expected_value, dict)
        expected = SequenceRange(
            int(expected_value["start"]),
            int(expected_value["end"]),
            1.0,
        )
        source = by_path[relative_path]
        observation = analyzer.analyze(source)
        should_be_eligible = case["automaticCandidateEligible"] is True
        verification = (
            verifier.verify_expected(
                observation,
                expected_board_count=expected.board_count,
                expected_range=expected,
            )
            if should_be_eligible
            else verifier.verify(
                observation,
                expected_board_count=expected.board_count,
            )
        )
        strong_observations = tuple(
            item
            for item in verification.range_evidence.label_observations
            if item.confidence >= 0.82
        )
        matching_positions = {
            item.position_index
            for item in strong_observations
            if item.sequence_number == expected.start + item.position_index
        }
        conflicting_positions = {
            item.position_index
            for item in strong_observations
            if item.sequence_number != expected.start + item.position_index
        }
        recognized = verification.recognized_range
        recognized_matches = recognized is not None and (
            recognized.start,
            recognized.end,
        ) == (expected.start, expected.end)
        ordered_evidence_matches = len(matching_positions) >= 2 and not conflicting_positions
        quality = observation.quality
        quality_eligible = (
            quality.overall_score >= policy.minimum_quality_score
            and quality.sharpness >= policy.minimum_sharpness
            and quality.exposure >= policy.minimum_exposure
            and quality.highlight_retention >= policy.minimum_highlight_retention
            and quality.board_visibility >= policy.minimum_board_visibility
        )
        hard_reason = any(
            reason.startswith("IMAGE_SELECTION_SCAN_")
            or reason in {"IMAGE_OCCLUDED", "QUALITY_LAYOUT_BLUR"}
            for reason in (
                *observation.reason_codes,
                *verification.reason_codes,
            )
        )
        representative_eligible = not hard_reason and (
            manifest is SEQUENCE_STABLE_SELECTOR_MANIFEST_V1021 or quality_eligible
        )
        passed = (
            representative_eligible and (recognized_matches or ordered_evidence_matches)
            if should_be_eligible
            else hard_reason or not quality_eligible
        )
        results.append(
            {
                "actualRange": (
                    None
                    if recognized is None
                    else {"end": recognized.end, "start": recognized.start}
                ),
                "conflictingStrongPositionCount": len(conflicting_positions),
                "expectedAutomaticCandidateEligible": should_be_eligible,
                "expectedRange": {"end": expected.end, "start": expected.start},
                "matchingStrongPositionCount": len(matching_positions),
                "passed": passed,
                "qualityEligible": quality_eligible,
                "reasonCodes": list(verification.reason_codes),
                "relativePath": relative_path,
                "representativeBoardCount": verification.board_count,
                "representativeEligible": representative_eligible,
                "representativeFullFrameVisible": verification.full_frame_visible,
                "representativeGeometryComplete": verification.geometry_complete,
            }
        )
    failures = tuple(result for result in results if result["passed"] is not True)
    return {
        "caseCount": len(results),
        "failureCount": len(failures),
        "passed": not failures,
        "results": results,
    }


def _verification_distribution(timing: dict[str, object]) -> dict[str, float | int]:
    counters = timing.get("counters")
    if not isinstance(counters, dict):
        return {"meanVerifiedJpegsPerGroup": 0.0, "p95VerifiedJpegsPerGroup": 0}
    distribution: list[tuple[int, int]] = []
    for name, count in counters.items():
        if not isinstance(name, str) or not name.startswith("rangeEvidenceGroupSize."):
            continue
        if not isinstance(count, int):
            continue
        try:
            size = int(name.rsplit(".", 1)[1])
        except ValueError:
            continue
        distribution.append((size, count))
    total_groups = sum(count for _, count in distribution)
    if total_groups == 0:
        return {"meanVerifiedJpegsPerGroup": 0.0, "p95VerifiedJpegsPerGroup": 0}
    target = max(1, int(total_groups * 0.95 + 0.999999))
    cumulative = 0
    p95 = 0
    for size, count in sorted(distribution):
        cumulative += count
        if cumulative >= target:
            p95 = size
            break
    return {
        "meanVerifiedJpegsPerGroup": round(
            sum(size * count for size, count in distribution) / total_groups,
            6,
        ),
        "p95VerifiedJpegsPerGroup": p95,
    }


def main() -> None:
    args = _parse_args()
    if len(args.order) not in {1, 2}:
        raise SystemExit("--order accepts one candidate or one candidate and one baseline.")
    source_root = args.source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise SystemExit("--source-root must be a managed staging directory.")
    all_sources, input_manifest_sha256, source_kind = _load_sources(
        source_root,
        source_order=args.source_order,
        limit=args.limit,
    )
    if args.limit < 1 or args.limit > len(all_sources):
        raise SystemExit("--limit must fit within the staging manifest.")
    if args.expected_groups < 1 or args.expected_groups > args.limit:
        raise SystemExit("--expected-groups must be between one and --limit.")
    sources = tuple(all_sources[: args.limit])
    annotation_cases = (
        ()
        if args.annotations is None
        else _validated_annotation_cases(
            args.annotations.resolve(strict=True),
            sources=sources,
            input_manifest_sha256=input_manifest_sha256,
            source_order=args.source_order,
            expected_group_count=args.expected_groups,
            first_sequence_number=args.first_sequence_number,
            last_sequence_number=args.last_sequence_number,
            sequence_direction=args.sequence_direction,
        )
    )
    artifact_root = args.artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, object]] = []
    for name in args.order:
        print(f"Starting {name} on {args.limit} sources.", flush=True)
        run = _run(
            source_root,
            artifact_root=artifact_root,
            manifest=MANIFESTS[name],
            sources=sources,
            expected_group_count=args.expected_groups,
            first_sequence_number=args.first_sequence_number,
            last_sequence_number=args.last_sequence_number,
            sequence_direction=args.sequence_direction,
            annotation_cases=annotation_cases,
        )
        runs.append(run)
        print(
            f"Completed {name} in {run['elapsedSeconds']} seconds with "
            f"{run['verificationCount']} verifications.",
            flush=True,
        )
    candidate_elapsed = runs[0]["elapsedSeconds"]
    if not isinstance(candidate_elapsed, int | float):
        raise RuntimeError("Benchmark elapsed time must be numeric.")
    candidate_seconds = float(candidate_elapsed)
    baseline_name: str | None = None
    speedup_percent: float | None = None
    if len(runs) == 2:
        baseline_elapsed = runs[1]["elapsedSeconds"]
        if not isinstance(baseline_elapsed, int | float):
            raise RuntimeError("Benchmark elapsed time must be numeric.")
        baseline_seconds = float(baseline_elapsed)
        baseline_name = args.order[1]
        speedup_percent = round(
            (baseline_seconds - candidate_seconds) / baseline_seconds * 100.0,
            6,
        )
    report = {
        "baseline": baseline_name,
        "candidate": args.order[0],
        "contract": "image-selection-version-comparison-v1",
        "expectedGroupCount": args.expected_groups,
        "firstSequenceNumber": args.first_sequence_number,
        "lastSequenceNumber": args.last_sequence_number,
        "inputManifestSha256": input_manifest_sha256,
        "limit": args.limit,
        "order": list(args.order),
        "sequenceDirection": args.sequence_direction,
        "sourceKind": source_kind,
        "sourceOrder": args.source_order,
        "runs": runs,
        "speedupPercent": speedup_percent,
    }
    output = args.output.resolve()
    artifact_root = (REPOSITORY_ROOT / "artifacts").resolve()
    if output.parent != artifact_root and artifact_root not in output.parents:
        raise SystemExit("--output must be inside the repository artifacts directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(output.suffix + ".pending")
    pending.write_bytes(_canonical_bytes(report))
    pending.replace(output)
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
