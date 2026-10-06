"""Prepare the explicitly selected Mumie RGB pilot; no database writes or activation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from game_predictor_api.domain.lab_symbol_candidate import (
    MUMIE_CLASS_CODES,
    MUMIE_ELIGIBILITY_ID,
    prepare_mumie_candidate,
)
from game_predictor_api.domain.symbol_model_snapshots import LAB_RGB_SYMBOL_MODEL_VERSION
from game_predictor_worker.images.symbol_onnx import (
    LocalSymbolOnnxAdapter,
    preprocess_rgb_batch,
)


def prepare(evidence_root: Path, artifact_root: Path, game_id: UUID) -> dict[str, Any]:
    # These existing, locally owned evidence helpers perform the complete
    # original pin and source-report semantic checks. They are not imported by
    # API/runtime; the public API will accept only a managed fingerprint.
    helper = evidence_root / "common.py"
    sys.path.insert(0, str(evidence_root))
    specification = importlib.util.spec_from_file_location("mumie_pilot_frozen", helper)
    if specification is None or specification.loader is None:
        raise ValueError("MUMIE_PILOT_EVIDENCE_HELPER_MISSING")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    evidence, batch = module.frozen()
    if module.digest(evidence) != MUMIE_ELIGIBILITY_ID:
        raise ValueError("MUMIE_PILOT_ELIGIBILITY_DRIFT")
    import hashlib

    from game_predictor_worker.images.virtual_cell_extraction import source_direct_warp_rgb
    from game_predictor_worker.vision_lab.geometry import crop_cell
    from game_predictor_worker.vision_lab.symbol_batch import (
        load_photo,
        preprocess,
        validate_result,
    )

    crops = []
    production_crops = []
    bindings = []
    for index in range(3):
        baseline = validate_result(module.BATCH, batch, index)
        row = batch["rows"][index]
        photo = np.asarray(load_photo(row, evidence["forbidden_photo_pixels"]))
        for cell in baseline["cells"]:
            crop = crop_cell(photo, np.asarray(cell["quad"], dtype=np.float32))
            if (
                crop is None
                or hashlib.sha256(crop.tobytes()).hexdigest() != cell["crop_pixel_sha256"]
            ):
                raise ValueError("MUMIE_PILOT_CROP_DRIFT")
            crops.append(crop)
            production_crop = source_direct_warp_rgb(
                photo, source_quad=cell["quad"], output_width=96, output_height=96
            )
            if not np.array_equal(production_crop, crop):
                raise ValueError("MUMIE_PILOT_SOURCE_RENDER_PARITY_FAILED")
            production_crops.append(production_crop)
            bindings.append(
                {
                    "photoIndex": index,
                    "boardIndex": cell["board_index"],
                    "cellIndex": cell["cell_index"],
                    "pixelSha256": cell["crop_pixel_sha256"],
                }
            )
    model = evidence["models"]["r2_rgb"]
    adapter = LocalSymbolOnnxAdapter(
        Path(model["path"]),
        expected_sha256=model["sha256"],
        class_codes=MUMIE_CLASS_CODES,
        input_size=64,
        model_version=LAB_RGB_SYMBOL_MODEL_VERSION,
    )
    max_input = 0.0
    max_logits = 0.0
    differences = 0
    for start in range(0, len(crops), 135):
        images = production_crops[start : start + 135]
        reference = preprocess(crops[start : start + 135])
        prepared = preprocess_rgb_batch(
            images, input_size=64, model_version=LAB_RGB_SYMBOL_MODEL_VERSION
        )
        expected = adapter.infer(reference).logits
        result = adapter.infer(prepared).logits
        max_input = max(max_input, float(np.max(np.abs(reference - prepared))))
        max_logits = max(max_logits, float(np.max(np.abs(expected - result))))
        differences += int(np.sum(expected.argmax(1) != result.argmax(1)))
    if max_input > 1e-6 or max_logits > 1e-5 or differences:
        raise ValueError("MUMIE_PILOT_RUNTIME_PARITY_FAILED")
    # Repeat the original live pin/semantic validation after all rendering and
    # inference. A moving raw input cannot be admitted by the initial check.
    evidence_after, _ = module.frozen()
    if module.digest(evidence_after) != MUMIE_ELIGIBILITY_ID:
        raise ValueError("MUMIE_PILOT_EVIDENCE_CHANGED")
    candidate = prepare_mumie_candidate(
        artifact_root,
        game_id=game_id,
        onnx_content=Path(model["path"]).read_bytes(),
        eligibility_content=(evidence_root / "eligibility.json").read_bytes(),
    )
    return {
        "candidateFingerprint": candidate.fingerprint,
        "manifestRelativePath": candidate.manifest_relative_path,
        "manifestSha256": candidate.manifest_sha256,
        "artifactRoot": str(artifact_root),
        "gameId": str(game_id),
        "sources": 3,
        "cells": len(crops),
        "cropBindingsSha256": module.digest(bindings),
        "productionRenderVersion": "source-direct-full-quad-rgb96-v1",
        "paddingFraction": 0.0,
        "productionPixelDifferences": 0,
        "inputMaxAbs": max_input,
        "logitMaxAbs": max_logits,
        "classDifferences": differences,
        "databaseWrites": 0,
        "activations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.evidence_root, args.artifact_root, args.report):
        if not path.is_absolute():
            parser.error("All paths must be absolute.")
    report = prepare(args.evidence_root, args.artifact_root, args.game_id)
    content = json.dumps(report, indent=2) + "\n"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.report.exists() and args.report.read_text(encoding="utf-8") != content:
        # Numerical/clock variance isn't silently substituted for the already
        # published qualification. Keep separate evidence per explicit request.
        raise ValueError("MUMIE_PILOT_REPORT_DRIFT")
    args.report.write_text(content, encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
