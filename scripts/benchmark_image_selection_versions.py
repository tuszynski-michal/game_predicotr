"""Compare two immutable selector versions on one read-only staging prefix."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
API_SOURCE = REPOSITORY_ROOT / "services" / "api" / "src"
sys.path.insert(0, str(WORKER_SOURCE))
sys.path.insert(0, str(API_SOURCE))

from game_predictor_worker.images.selection.contracts import ImageSelectionSource  # noqa: E402
from game_predictor_worker.images.selection.engine import FastImageSelector  # noqa: E402
from game_predictor_worker.images.selection.io import (  # noqa: E402
    load_browser_selection_manifest,
)
from game_predictor_worker.images.selection.job import ImageSelectionJobHandler  # noqa: E402
from game_predictor_worker.images.selection.manifest import (  # noqa: E402
    ADAPTIVE_CARDINALITY_SELECTOR_MANIFEST_V1015,
    QUANTILE_SAMPLED_SELECTOR_MANIFEST_V1017,
    SINGLE_FRAME_EARLY_EXIT_SELECTOR_MANIFEST_V1018,
    STAGED_OCR_SELECTOR_MANIFEST_V1016,
    SelectorManifest,
)
from game_predictor_worker.images.selection.telemetry import (  # noqa: E402
    StageTimingCollector,
)

MANIFESTS = {
    "v10.15": ADAPTIVE_CARDINALITY_SELECTOR_MANIFEST_V1015,
    "v10.16": STAGED_OCR_SELECTOR_MANIFEST_V1016,
    "v10.17": QUANTILE_SAMPLED_SELECTOR_MANIFEST_V1017,
    "v10.18": SINGLE_FRAME_EARLY_EXIT_SELECTOR_MANIFEST_V1018,
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--expected-groups", type=int, required=True)
    parser.add_argument("--first-sequence-number", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts",
        help="Isolated cache root; use a fresh directory for a cold comparison.",
    )
    parser.add_argument(
        "--order",
        nargs=2,
        choices=tuple(MANIFESTS),
        default=("v10.18", "v10.17"),
    )
    return parser.parse_args()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _run(
    source_root: Path,
    *,
    artifact_root: Path,
    manifest: SelectorManifest,
    sources: tuple[ImageSelectionSource, ...],
    expected_group_count: int,
    first_sequence_number: int,
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
    started_at = perf_counter()
    result = FastImageSelector(
        manifest,
        scan_workers=4,
        scan_prefetch=8,
    ).select(
        sources,
        analyzer=analyzer,
        verifier=verifier,
        first_sequence_number=first_sequence_number,
        expected_group_count_for_partitioning=expected_group_count,
    )
    elapsed_seconds = perf_counter() - started_at
    serialized_groups = tuple(group.to_dict() for group in result.groups)
    statuses = Counter(group.status.value for group in result.groups)
    projection = tuple(
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
    return {
        "elapsedSeconds": round(elapsed_seconds, 6),
        "groupCount": len(serialized_groups),
        "projectionSha256": hashlib.sha256(_canonical_bytes(projection)).hexdigest(),
        "selectorFingerprint": manifest.fingerprint,
        "selectorVersion": manifest.algorithm_version,
        "stageTiming": telemetry.snapshot(),
        "statusCounts": dict(sorted(statuses.items())),
        "verificationCount": result.verification_count,
    }


def main() -> None:
    args = _parse_args()
    source_root = args.source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise SystemExit("--source-root must be a managed staging directory.")
    all_sources, input_manifest_sha256 = load_browser_selection_manifest(
        source_root / "_browser_manifest.json"
    )
    if args.limit < 1 or args.limit > len(all_sources):
        raise SystemExit("--limit must fit within the staging manifest.")
    if args.expected_groups < 1 or args.expected_groups > args.limit:
        raise SystemExit("--expected-groups must be between one and --limit.")
    sources = tuple(all_sources[: args.limit])
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
        )
        runs.append(run)
        print(
            f"Completed {name} in {run['elapsedSeconds']} seconds with "
            f"{run['verificationCount']} verifications.",
            flush=True,
        )
    candidate_elapsed = runs[0]["elapsedSeconds"]
    baseline_elapsed = runs[1]["elapsedSeconds"]
    if not isinstance(candidate_elapsed, int | float) or not isinstance(
        baseline_elapsed, int | float
    ):
        raise RuntimeError("Benchmark elapsed time must be numeric.")
    candidate_seconds = float(candidate_elapsed)
    baseline_seconds = float(baseline_elapsed)
    report = {
        "baseline": args.order[1],
        "candidate": args.order[0],
        "contract": "image-selection-version-comparison-v1",
        "expectedGroupCount": args.expected_groups,
        "firstSequenceNumber": args.first_sequence_number,
        "inputManifestSha256": input_manifest_sha256,
        "limit": args.limit,
        "order": list(args.order),
        "runs": runs,
        "speedupPercent": round(
            (baseline_seconds - candidate_seconds) / baseline_seconds * 100.0,
            6,
        ),
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
