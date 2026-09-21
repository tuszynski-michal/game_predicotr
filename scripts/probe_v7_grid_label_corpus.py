"""Read-only, bounded v7 OCR probe: one deterministic JPEG from each direct corpus case."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from time import perf_counter

import numpy as np
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (
    build_middle_row_paddle_adapter,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import (
    V7CorpusSplit,
    load_v7_corpus_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_label_locator import recognize_grid_labels
from game_predictor_worker.semi_automatic_selection.v7_range_proof import V7LabelEvidence
from PIL import Image, ImageOps


def _frozen_inventory(manifest_path: Path) -> tuple[str, tuple[dict[str, object], ...]]:
    try:
        payload = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Frozen v7 corpus inventory cannot be read.") from error
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if (
        not isinstance(cases, list)
        or payload.get("schemaVersion") != 1
        or not isinstance(payload.get("manifestFingerprint"), str)
        or not all(isinstance(item, dict) for item in cases)
    ):
        raise ValueError("Frozen v7 corpus inventory has an invalid contract.")
    fingerprint = payload["manifestFingerprint"]
    assert isinstance(fingerprint, str)
    return fingerprint, tuple(cases)


def _direct_jpegs(directory: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg"}
            ),
            key=lambda path: (path.name.casefold(), path.name),
        )
    )


def _summarize(labels: Iterable[V7LabelEvidence]) -> dict[str, object]:
    values = tuple(labels)
    reliable = tuple(
        item
        for item in values
        if item.recognition_confidence >= 0.90 and item.position_confidence >= 0.90
    )
    starts = Counter(item.sequence_number - item.position_index for item in reliable)
    highest_consensus = max(starts.values(), default=0)
    return {
        "fiveLabelConsensus": highest_consensus >= 5,
        "numericLabels": len(values),
        "reliableLabels": len(reliable),
        "strongCandidateStarts": sorted(start for start, count in starts.items() if count >= 5),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--samples-per-case", type=int, default=1)
    parser.add_argument(
        "--include-split",
        choices=(
            V7CorpusSplit.DEVELOPMENT.value,
            V7CorpusSplit.CALIBRATION.value,
            V7CorpusSplit.VALIDATION.value,
            V7CorpusSplit.HOLDOUT.value,
        ),
        action="append",
        default=None,
        help="Defaults to development and calibration.",
    )
    arguments = parser.parse_args()
    if arguments.samples_per_case < 1 or arguments.samples_per_case > 3:
        parser.error("--samples-per-case must be between 1 and 3.")
    manifest = load_v7_corpus_manifest(arguments.manifest)
    inventory = manifest.freeze_inventory()
    frozen_fingerprint, frozen_cases = _frozen_inventory(arguments.inventory)
    if (
        frozen_fingerprint != manifest.fingerprint()
        or tuple(item.as_dict() for item in inventory) != frozen_cases
    ):
        raise ValueError("V7 corpus manifest or source inventory drifted; probe is blocked.")
    selected_splits = {
        V7CorpusSplit(value)
        for value in (
            arguments.include_split
            or [V7CorpusSplit.DEVELOPMENT.value, V7CorpusSplit.CALIBRATION.value]
        )
    }
    recognizer = build_middle_row_paddle_adapter(arguments.model_root)
    results: list[dict[str, object]] = []
    started = perf_counter()
    for case in manifest.cases:
        if case.split not in selected_splits:
            continue
        directory = manifest.corpus_root / case.directory_name
        for source in _direct_jpegs(directory)[: arguments.samples_per_case]:
            with Image.open(source) as image:
                rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
            labels = recognize_grid_labels(rgb, recognizer)
            results.append(
                {
                    "case": case.case_id,
                    "source": str(source.relative_to(manifest.corpus_root)),
                    **_summarize(labels),
                }
            )
    print(
        json.dumps(
            {
                "corpusInventory": [item.as_dict() for item in inventory],
                "corpusManifestFingerprint": manifest.fingerprint(),
                "elapsedMilliseconds": round((perf_counter() - started) * 1000),
                "results": results,
                "sampleCount": len(results),
                "splits": sorted(item.value for item in selected_splits),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
