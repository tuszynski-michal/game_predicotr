"""Prepare immutable human-control bindings; never install or change DB labels."""
# ruff: noqa: E402 -- pin imports to this worktree instead of the editable main checkout.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPOSITORY / "services/api/src"), str(REPOSITORY / "services/worker/src")]

import numpy as np  # noqa: E402
from game_predictor_api.domain.lab_symbol_candidate import (  # noqa: E402
    MUMIE_CLASS_CODES,
    MUMIE_CLASS_LABELS,
)
from game_predictor_api.domain.protected_control_truth import (
    TRUTH_VERSION,
    ControlTruth,
    truth_quad,
)  # noqa: E402
from game_predictor_worker.images.normalization import (
    CanonicalSourceLoader,
    rgb_pixel_checksum_sha256,
)  # noqa: E402
from game_predictor_worker.images.virtual_cell_extraction import (
    source_direct_warp_rgb,  # noqa: E402
)
from game_predictor_worker.vision_lab.annotations import digest, read_checked  # noqa: E402
from PIL import Image  # noqa: E402


def prepare(artifact_root: Path, output: Path) -> dict[str, object]:
    pilot = artifact_root / "mumie-main-app-pilot-20261006"
    base = read_checked(pilot / "protected-source-exclusions-v1.json")
    membership = read_checked(pilot / "protected-source-membership-preflight.json")
    eligibility = read_checked(
        artifact_root / "mumie-rgb-only-diagnostic-20261006/eligibility.json"
    )
    if digest(eligibility) != base["eligibilityId"] or not eligibility["eligible"]:
        raise ValueError("The R2 eligibility identity has changed.")
    pins = {
        str(Path(p)).replace("\\", "/").casefold(): sha for p, sha in eligibility["pins"].items()
    }
    qualified = read_checked(artifact_root / "mumie-ai-round2-20261006/qualified-frozen.json")
    manifest = read_checked(Path(qualified["manifest"]))
    preparation_path = Path(manifest["bundle"]) / "preparation.json"
    preparation = json.loads(preparation_path.read_bytes())
    source_rows = {row["sourceByteSha256"]: row for row in membership["rows"]}
    source_root = "training/" + base["gameId"].replace("-", "") + "/protected-control-proofs/"
    proofs: dict[str, dict[str, str]] = {}
    copy_plan: dict[str, dict[str, str]] = {}

    def proof(path: Path, kind: str) -> str:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if pins.get(str(path).replace("\\", "/").casefold()) != checksum:
            raise ValueError(f"The human proof is not in frozen eligibility pins: {path}")
        relative = source_root + checksum + (".png" if kind == "crop_png" else ".json")
        if checksum in proofs and proofs[checksum]["kind"] != kind:
            raise ValueError("A proof has ambiguous provenance.")
        proofs[checksum] = {
            "proofId": checksum,
            "kind": kind,
            "fileChecksumSha256": checksum,
            "relativePath": relative,
        }
        copy_plan[checksum] = {
            "sourcePath": str(path),
            "relativePath": relative,
            "fileChecksumSha256": checksum,
        }
        return checksum

    loader = CanonicalSourceLoader()
    frames: dict[str, Any] = {}
    truths: list[dict[str, Any]] = []

    def add(
        decision: dict[str, Any],
        binding: dict[str, Any],
        group: str,
        proof_id: str,
        crop_path: Path,
        *,
        batch: bool,
    ) -> None:
        byte = binding["source"]["sha256"] if batch else binding["source_sha256"]
        position = binding["board"] - 1 if batch else binding["board_index"]
        cell = binding["field"] - 1 if batch else binding["cell_index"]
        source = source_rows[byte]
        quad = truth_quad(binding["quad"])
        with Image.open(crop_path) as image:
            rgb = np.asarray(image.convert("RGB"))
        if (
            rgb.shape != (96, 96, 3)
            or hashlib.sha256(rgb.tobytes()).hexdigest() != binding["pixel_sha256"]
        ):
            raise ValueError("The frozen approval does not describe these RGB96 pixels.")
        if byte not in frames:
            frames[byte] = loader.load(
                Path(source["sourcePath"]), expected_source_checksum_sha256=byte
            )
        frame = frames[byte]
        if frame.source.normalized_pixel_checksum_sha256 != source["normalizedPixelChecksumSha256"]:
            raise ValueError("Frozen source pixels changed.")
        rendered = source_direct_warp_rgb(
            frame.rgb, source_quad=quad, output_width=96, output_height=96
        )
        if not np.array_equal(rendered, rgb):
            raise ValueError("Frozen human pixels do not re-render from their source quad.")
        row = {
            "controlId": digest(
                {"group": group, "decisionId": decision["decision_id"], "quad": quad}
            ),
            "group": group,
            "sourceByteSha256": byte,
            "normalizedPixelChecksumSha256": source["normalizedPixelChecksumSha256"],
            "sourceWidth": frame.source.width,
            "sourceHeight": frame.source.height,
            "positionIndex": position,
            "cellIndex": cell,
            "sourceQuad": [list(point) for point in quad],
            "renderedPixelChecksumSha256": rgb_pixel_checksum_sha256(rgb),
            "labPixelSha256": binding["pixel_sha256"],
            "expectedSymbolId": decision["symbol_id"],
            "expectedSymbolCode": codes[decision["symbol_id"]],
            "origin": decision["origin"],
            "actor": decision["actor"],
            "action": decision["action"],
            "decisionId": decision["decision_id"],
            "decisionRevision": decision["revision"],
            "proofId": proof_id,
            "cropProofId": proof(crop_path, "crop_png"),
        }
        ControlTruth.from_payload(row)
        truths.append(row)

    prep_proof = proof(preparation_path, "preparation")
    entries = preparation["dictionary"]["entries"]
    if (
        tuple(entry["display_name"] for entry in entries) != MUMIE_CLASS_LABELS
        or tuple(eligibility["classes"]) != MUMIE_CLASS_LABELS
    ):
        raise ValueError("The frozen lab dictionary differs from the qualified R2 class order.")
    mappings = [
        {
            "labSymbolId": entry["id"],
            "labCode": entry["code"],
            "labDisplayName": entry["display_name"],
            "dbSymbolCode": code,
            "proofId": prep_proof,
        }
        for entry, code in zip(entries, MUMIE_CLASS_CODES, strict=True)
    ]
    codes = {row["labSymbolId"]: row["dbSymbolCode"] for row in mappings}
    for sample in preparation["samples"]:
        decision = sample["decision"]
        binding = decision["binding"]
        group = manifest["assignments"][binding["source_id"]]
        if sample.get("ai_audit") or group not in {"validation", "diagnostic_test"}:
            continue
        add(
            decision,
            binding,
            group,
            prep_proof,
            Path(manifest["bundle"]) / "crops" / (binding["byte_sha256"] + ".png"),
            batch=False,
        )
    h8_pointer = read_checked(
        artifact_root / "mumie-first-human-check-20261006/qualified-evaluation.json"
    )
    for group, path in (
        ("human26", Path(qualified["frozen_references"]["human26"]["path"])),
        ("human8", Path(h8_pointer["path"])),
    ):
        evaluation = read_checked(path)
        pack = Path(evaluation["human_pack"])
        human = read_checked(pack / "manifest.json")
        human_proof = proof(pack / "manifest.json", "feedback_manifest")
        proof(path, "json")
        proof(pack / "decisions.json", "json")
        proof(pack / "reference.json", "json")
        cases = {case["case_id"]: case for case in human["cases"]}
        for decision in human["decisions"]:
            binding = cases[decision["case_id"]]
            add(
                decision,
                binding,
                group,
                human_proof,
                pack / "crops" / (binding["byte_sha256"] + ".png"),
                batch=True,
            )
    loader.clear()
    if Counter(row["group"] for row in truths) != {
        "validation": 84,
        "diagnostic_test": 9,
        "human26": 26,
        "human8": 8,
    }:
        raise ValueError("Frozen human control counts changed.")
    payload = {
        **base,
        "controlTruthVersion": TRUTH_VERSION,
        "controlTruthSymbolMappings": mappings,
        "controlTruthRows": sorted(truths, key=lambda row: row["controlId"]),
        "controlTruthProofs": sorted(proofs.values(), key=lambda row: row["proofId"]),
    }
    checksum = digest(payload)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "protected-source-exclusions-with-truth-v1.json": {"payload": payload, "sha256": checksum},
        "control-truth-copy-plan.json": {
            "descriptorChecksumSha256": checksum,
            "proofs": sorted(copy_plan.values(), key=lambda row: row["relativePath"]),
            "humanCounts": dict(Counter(row["group"] for row in truths)),
            "productionWrites": 0,
            "currentApprovalComparisons": 0,
            "currentConflictStatus": "NO_CONFLICT",
        },
    }
    for filename, content in files.items():
        target = output / filename
        encoded = json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        if target.exists():
            if target.read_bytes() != encoded:
                raise ValueError(
                    "Immutable preparation output already exists with different bytes."
                )
        else:
            with target.open("xb") as stream:
                stream.write(encoded)
    return {
        "descriptorChecksumSha256": checksum,
        "controls": len(truths),
        "proofs": len(proofs),
        "sourceRenders": len(truths),
        "currentApprovalComparisons": 0,
        "currentConflictStatus": "NO_CONFLICT",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.artifact_root, args.output), sort_keys=True), flush=True)
