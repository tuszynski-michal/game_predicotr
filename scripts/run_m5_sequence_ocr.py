"""Run local sequence-number OCR and continuity validation for M5."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.sequence_ocr import (  # noqa: E402
    SequenceOcrError,
    run_sequence_ocr_corpus,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_manifest", type=Path)
    parser.add_argument("golden_annotations", type=Path)
    parser.add_argument("normalization_report", type=Path)
    parser.add_argument("detection_report", type=Path)
    parser.add_argument("--normalization-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that --output already contains the deterministic report.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Return exit code 1 unless exactly 108 positions were measured.",
    )
    return parser.parse_args()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _validate_report_path(normalization_root: Path, output: Path) -> Path:
    normalization = normalization_root.resolve(strict=True)
    resolved = output.resolve()
    if resolved == normalization or resolved.is_relative_to(normalization):
        raise SequenceOcrError(
            "SEQUENCE_OCR_REPORT_IN_NORMALIZATION_ROOT",
            "OCR report must be outside the normalization artifact root.",
        )
    return resolved


def main() -> int:
    args = _parse_args()
    try:
        report = run_sequence_ocr_corpus(
            args.corpus_manifest,
            args.golden_annotations,
            args.normalization_report,
            args.detection_report,
            args.normalization_root,
            args.model_root,
            args.artifact_root,
        )
        content = report.to_json_bytes()
        if args.check and args.output is None:
            raise SequenceOcrError(
                "SEQUENCE_OCR_CHECK_OUTPUT_REQUIRED",
                "--check requires --output.",
            )
        if args.output is None:
            sys.stdout.buffer.write(content)
        else:
            output = _validate_report_path(args.normalization_root, args.output)
            if args.check:
                try:
                    existing = output.read_bytes()
                except OSError as error:
                    raise SequenceOcrError(
                        "SEQUENCE_OCR_REPORT_MISSING",
                        "Expected OCR report cannot be read.",
                    ) from error
                if existing != content:
                    raise SequenceOcrError(
                        "SEQUENCE_OCR_REPORT_DRIFT",
                        "OCR report differs from current artifacts.",
                    )
            else:
                _write_atomic(output, content)
            payload = report.to_dict()
            print(
                json.dumps(
                    {
                        "continuityConflictCount": payload["continuityConflictCount"],
                        "exactAccuracy": payload["exactAccuracy"],
                        "exactCount": payload["exactCount"],
                        "positionCount": payload["positionCount"],
                        "reportSha256": hashlib.sha256(content).hexdigest(),
                        "reviewCount": payload["reviewCount"],
                        "status": payload["status"],
                    },
                    sort_keys=True,
                )
            )
        if args.require_complete and len(report.results) != 108:
            return 1
        return 0
    except SequenceOcrError as error:
        print(
            json.dumps(
                {"code": error.code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
