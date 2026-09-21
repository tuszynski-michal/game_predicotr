"""Read-only v7 label-crop and OCR probe for a selected source image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionRange
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (
    build_middle_row_paddle_adapter,
)
from game_predictor_worker.semi_automatic_selection.v7_label_locator import recognize_grid_labels
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7FrameEvidence,
    V7RangeProofResolver,
)
from PIL import Image, ImageOps


def _range(value: str) -> SemiAutomaticSelectionRange:
    try:
        start_text, end_text = value.split("-", maxsplit=1)
        return SemiAutomaticSelectionRange(int(start_text), int(end_text))
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("Expected range must use e.g. 301870-301878.") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--expected-range", type=_range, required=True)
    arguments = parser.parse_args()
    started = perf_counter()
    with Image.open(arguments.source) as image:
        rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    recognizer = build_middle_row_paddle_adapter(arguments.model_root)
    labels = recognize_grid_labels(rgb, recognizer)
    proof = V7RangeProofResolver((arguments.expected_range,)).resolve_frame(
        V7FrameEvidence(
            source_id=str(arguments.source),
            occurrence_id="read-only-probe",
            visual_cluster_id="read-only-probe",
            labels=labels,
        )
    )
    print(
        json.dumps(
            {
                "elapsedMilliseconds": round((perf_counter() - started) * 1000),
                "labels": [
                    {
                        "positionIndex": item.position_index,
                        "recognitionConfidence": item.recognition_confidence,
                        "sequenceNumber": item.sequence_number,
                    }
                    for item in labels
                ],
                "proof": {
                    "kind": proof.kind,
                    "range": None
                    if proof.sequence_range is None
                    else [proof.sequence_range.start, proof.sequence_range.end],
                    "reasonCodes": proof.reason_codes,
                },
                "source": str(arguments.source),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
