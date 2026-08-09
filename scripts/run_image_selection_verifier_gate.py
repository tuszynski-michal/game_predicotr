"""Run and evaluate the bounded one-vs-two verifier image-selection gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCRIPT = REPOSITORY_ROOT / "scripts" / "profile_image_selection_slice.py"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--scan-workers", type=int, default=3)
    parser.add_argument("--max-seconds-per-run", type=int, default=900)
    parser.add_argument("--minimum-improvement-percent", type=float, default=10.0)
    parser.add_argument(
        "--ocr-model-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
    )
    return parser.parse_args()


def _canonical_group_decisions(report: dict[str, Any]) -> list[dict[str, Any]]:
    groups = report.get("groups")
    if not isinstance(groups, list):
        raise ValueError("Verifier report does not contain a groups array")
    stable_fields = (
        "group",
        "sourceCount",
        "firstSourceIndex",
        "lastSourceIndex",
        "status",
        "recognizedRange",
        "selectedChecksumSha256",
        "selectedSourceRelativePath",
        "topCandidates",
    )
    return [
        {field: group.get(field) for field in stable_fields}
        for group in groups
        if isinstance(group, dict)
    ]


def evaluate_reports(
    single: dict[str, Any],
    dual: dict[str, Any],
    *,
    minimum_improvement_percent: float,
) -> dict[str, Any]:
    single_source = single.get("source")
    dual_source = dual.get("source")
    single_selector = single.get("selector")
    dual_selector = dual.get("selector")
    if (
        not isinstance(single_source, dict)
        or not isinstance(dual_source, dict)
        or not isinstance(single_selector, dict)
        or not isinstance(dual_selector, dict)
    ):
        raise ValueError("Verifier reports do not contain valid source and selector metadata")
    comparable_source = {
        key: single_source.get(key)
        for key in ("manifestSha256", "analyzedImageCount", "firstOrderIndex", "lastOrderIndex")
    } == {
        key: dual_source.get(key)
        for key in ("manifestSha256", "analyzedImageCount", "firstOrderIndex", "lastOrderIndex")
    }
    comparable_selector = {key: single_selector.get(key) for key in ("version", "fingerprint")} == {
        key: dual_selector.get(key) for key in ("version", "fingerprint")
    }
    single_decisions = _canonical_group_decisions(single)
    dual_decisions = _canonical_group_decisions(dual)
    canonical_match = single_decisions == dual_decisions
    single_seconds = float(single["summary"]["totalSeconds"])
    dual_seconds = float(dual["summary"]["totalSeconds"])
    improvement_percent = round((single_seconds - dual_seconds) / single_seconds * 100, 6)
    activate_dual = (
        comparable_source
        and comparable_selector
        and canonical_match
        and improvement_percent >= minimum_improvement_percent
    )
    return {
        "comparableSource": comparable_source,
        "comparableSelector": comparable_selector,
        "canonicalDecisionMatch": canonical_match,
        "singleVerifierSeconds": single_seconds,
        "dualVerifierSeconds": dual_seconds,
        "dualImprovementPercent": improvement_percent,
        "minimumImprovementPercent": minimum_improvement_percent,
        "decision": "activate_two_verifiers" if activate_dual else "keep_one_verifier",
    }


def _run_profile(
    *,
    source_root: Path,
    output: Path,
    start_index: int,
    limit: int,
    scan_workers: int,
    verification_workers: int,
    max_seconds: int,
    ocr_model_root: Path,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(PROFILE_SCRIPT),
        "--source-root",
        str(source_root),
        "--output",
        str(output),
        "--start-index",
        str(start_index),
        "--limit",
        str(limit),
        "--scan-workers",
        str(scan_workers),
        "--verification-workers",
        str(verification_workers),
        "--max-seconds",
        str(max_seconds),
        "--ocr-model-root",
        str(ocr_model_root),
    ]
    environment = os.environ.copy()
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        environment[name] = "1"
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=max_seconds + 30,
    )
    if completed.returncode != 0:
        tail = "\n".join(completed.stderr.splitlines()[-20:])
        raise RuntimeError(f"Verifier profile with {verification_workers} worker(s) failed: {tail}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Verifier profile output must be a JSON object")
    return cast(dict[str, Any], payload)


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pending.replace(path)


def main() -> None:
    args = _arguments()
    if not 1 <= args.limit <= 5_000:
        raise ValueError("--limit must be between 1 and 5000")
    if args.start_index < 0:
        raise ValueError("--start-index cannot be negative")
    if not 1 <= args.scan_workers <= 8:
        raise ValueError("--scan-workers must be between 1 and 8")
    if not 30 <= args.max_seconds_per_run <= 43_200:
        raise ValueError("--max-seconds-per-run must be between 30 and 43200")
    if not 0 <= args.minimum_improvement_percent <= 100:
        raise ValueError("--minimum-improvement-percent must be between 0 and 100")

    source_root = args.source_root.resolve(strict=True)
    if not (source_root / "_browser_manifest.json").is_file():
        raise ValueError("Source root does not contain _browser_manifest.json")
    output = args.output.resolve()
    workspace_prefix = REPOSITORY_ROOT.resolve()
    if not output.is_relative_to(workspace_prefix):
        raise ValueError("Gate output must remain inside the repository")
    if output.exists():
        raise ValueError(f"Gate output already exists: {output}")
    single_output = output.with_name(f"{output.stem}-one-verifier.json")
    dual_output = output.with_name(f"{output.stem}-two-verifiers.json")
    if single_output.exists() or dual_output.exists():
        raise ValueError("Verifier gate intermediate report already exists")

    single = _run_profile(
        source_root=source_root,
        output=single_output,
        start_index=args.start_index,
        limit=args.limit,
        scan_workers=args.scan_workers,
        verification_workers=1,
        max_seconds=args.max_seconds_per_run,
        ocr_model_root=args.ocr_model_root.resolve(strict=True),
    )
    dual = _run_profile(
        source_root=source_root,
        output=dual_output,
        start_index=args.start_index,
        limit=args.limit,
        scan_workers=args.scan_workers,
        verification_workers=2,
        max_seconds=args.max_seconds_per_run,
        ocr_model_root=args.ocr_model_root.resolve(strict=True),
    )
    evaluation = evaluate_reports(
        single,
        dual,
        minimum_improvement_percent=args.minimum_improvement_percent,
    )
    report = {
        "schemaVersion": 1,
        "profile": "image-selection-verifier-gate-v1",
        "source": {
            "root": str(source_root),
            "startIndex": args.start_index,
            "limit": args.limit,
        },
        "reports": {
            "oneVerifier": single_output.name,
            "twoVerifiers": dual_output.name,
        },
        "evaluation": evaluation,
    }
    _write_atomic(output, report)
    print(json.dumps(evaluation, indent=2, sort_keys=True), flush=True)
    print(f"REPORT {output}", flush=True)


if __name__ == "__main__":
    main()
