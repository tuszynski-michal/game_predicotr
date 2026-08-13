"""Run a fail-closed range-recognition gate on explicitly annotated JPEGs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image, ImageOps

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.geometry import ClassicalPageBoardDetector  # noqa: E402
from game_predictor_worker.images.selection.adapters import (  # noqa: E402
    LabelLatticeSafeVisibleSequenceLabelRangeRecognizer,
)
from game_predictor_worker.images.selection.manifest import (  # noqa: E402
    DEFAULT_SELECTOR_MANIFEST,
)
from game_predictor_worker.images.sequence_ocr import (  # noqa: E402
    PaddleSequenceNumberRecognizer,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument(
        "--ocr-model-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _parse_case(value: str) -> tuple[str, tuple[int, int]]:
    filename, separator, expected = value.partition("=")
    start, range_separator, end = expected.partition("-")
    if not separator or not range_separator or not filename:
        raise ValueError(f"Invalid case {value!r}; expected filename=start-end.")
    return filename, (int(start), int(end))


def main() -> int:
    args = _arguments()
    source_root = args.source_root.resolve(strict=True)
    model_root = args.ocr_model_root.resolve(strict=True)
    manifest = DEFAULT_SELECTOR_MANIFEST
    fallback_policy = manifest.progressive_visible_label_fallback_policy
    layout_policy = manifest.layout_anchor_policy
    window_policy = manifest.contiguous_sequence_window_policy
    if fallback_policy is None or layout_policy is None or window_policy is None:
        raise RuntimeError("The active selector does not expose the v10.10 policies.")

    recognizer = LabelLatticeSafeVisibleSequenceLabelRangeRecognizer(
        PaddleSequenceNumberRecognizer(model_root),
        fallback_policy,
        layout_policy,
        window_policy,
    )
    detector = ClassicalPageBoardDetector()
    results: list[dict[str, object]] = []
    passed = True
    started_at = perf_counter()
    for raw_case in args.case:
        filename, expected = _parse_case(raw_case)
        path = (source_root / filename).resolve(strict=True)
        if not path.is_relative_to(source_root):
            raise ValueError(f"Case escapes source root: {filename!r}.")
        content = path.read_bytes()
        with Image.open(path) as image:
            rgb = ImageOps.exif_transpose(image).convert("RGB")
            rgb_array = np.asarray(rgb, dtype=np.uint8)
        detection = detector.detect(
            rgb_array,
            expected_board_count=layout_policy.expected_layout_count,
            allow_grid_recovery=True,
            allow_occluded_grid_recovery=True,
            allow_partial_grid_recovery=True,
        )
        if detection.layout_hypotheses:
            recognized, reasons = recognizer.recognize_layout_hypotheses(
                rgb_array,
                detection.layout_hypotheses,
            )
        else:
            recognized, reasons = recognizer.recognize(rgb_array, detection.boards)
        actual = None if recognized is None else (recognized.start, recognized.end)
        case_passed = actual == expected
        passed = passed and case_passed
        results.append(
            {
                "actualRange": None if actual is None else list(actual),
                "candidateCount": detection.candidate_count,
                "expectedRange": list(expected),
                "filename": filename,
                "layoutHypothesisCount": len(detection.layout_hypotheses),
                "passed": case_passed,
                "reasons": list(reasons),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    payload = {
        "elapsedSeconds": round(perf_counter() - started_at, 6),
        "passed": passed,
        "results": results,
        "selectorFingerprint": manifest.fingerprint,
        "selectorVersion": manifest.algorithm_version,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
