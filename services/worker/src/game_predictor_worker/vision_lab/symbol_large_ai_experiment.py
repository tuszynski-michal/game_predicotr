"""D-506 immutable multi-reference AI inputs, preserving all older human cohorts."""

import argparse
import hashlib
import json
import logging
import stat
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from .annotations import digest, read_checked
from .geometry import crop_cell
from .snapshot import canonical, reject_links, safe_file, sha
from .symbol_ai_experiment import SymbolAiExperimentAdapter, consensus, digest_bytes
from .symbol_batch import checked_publish, load_photo, validate_batch
from .symbol_batch_labels import BatchReviewStore, separate
from .symbol_large_rgb_protocol import PROTOCOL, PROTOCOL_DIGEST, PURPOSE
from .symbol_store import publish_file
from .symbol_training_manifest import SymbolTrainingInputs

FORMAT = "lab-symbol-large-ai-experiment-v1"
BASE_MANIFEST_ID = "8adaaaf621e5506c5618559ec433f06f4eed13b75465d394ae2af0be3717f40d"
BASE_QUALIFICATION_SHA = "3b8a8a9676729b5f7473470159500777135bf9a36e8489c4d7eab2670f4a9d0e"
LOG = logging.getLogger(__name__)


def pins_valid(pins: dict[str, str]) -> None:
    # Keep every declared pin: Path equality on Windows ignores letter case,
    # so deduplicating endpoints could silently discard a conflicting SHA.
    paths = [(Path(name), expected) for name, expected in pins.items()]
    parts: set[Path] = set()
    for path, _expected in paths:
        if not path.is_absolute():
            raise ValueError("LARGE_AI_ABSOLUTE_PATH_REQUIRED")
        parts.update((path, *path.parents))

    def links() -> None:
        # Shared parents are inspected once per pass. Inspect all endpoints and
        # ancestors before AND after hashing; keep Windows reparse protection.
        for part in parts:
            try:
                metadata = part.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 1024:
                raise ValueError("SNAPSHOT_REPARSE_POINT")

    links()
    for path, expected in paths:
        if sha(path) != expected:
            raise ValueError("LARGE_AI_INPUT_DRIFT")
    links()


def qualification(descriptor: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    LOG.info("Checking frozen qualification and source hashes")
    pointer = Path(descriptor["pointer"])
    pins_valid({str(pointer): descriptor["pointer_sha256"]})
    link = read_checked(pointer)
    path = Path(link["path"])
    pins_valid({str(path): descriptor["file_sha256"]})
    value = read_checked(path)
    if (
        link["id"] != descriptor["id"]
        or path.stem != descriptor["id"]
        or digest(value) != descriptor["id"]
        or value.get("format") != "mumie-large-visual-qualification-v1"
        or value.get("origin") != "ai_visual_assessment"
        or value.get("human_approved") is not False
        or value.get("human_labels_written") != 0
        or value.get("super_targets") != 0
        or value.get("cnn_started") is not False
        or value.get("accuracy") is not None
    ):
        raise ValueError("LARGE_AI_QUALIFICATION_INVALID")
    pins_valid(value["pins"])
    selected = read_checked(Path(value["selection"]))
    if (
        selected.get("format") != "mumie-large-candidate-selection-v1"
        or digest(selected) != value["selection_id"]
        or selected["training_targets_created"] != 0
        or selected["human_labels_written"] != 0
        or selected["cnn_started"] is not False
        or selected["accuracy"] is not None
        or not 1 <= len(value["references"]) == selected["packets"] <= 20
        or not 1 <= selected["selected"] == len(selected["cases"]) <= 2000
        or selected["packets"] != (selected["selected"] + 99) // 100
        or value["selected"] != selected["selected"]
        or value["assessed_twice"] != selected["selected"]
        or any(value["pins"].get(k) != v for k, v in selected["pins"].items())
    ):
        raise ValueError("LARGE_AI_SELECTION_INVALID")
    return value, selected


def base_qualification(base: Path, qualified: dict[str, Any]) -> dict[str, str]:
    candidates = [
        Path(name)
        for name, value in qualified["pins"].items()
        if Path(name).name == "qualified-frozen.json" and value == BASE_QUALIFICATION_SHA
    ]
    if base.stem != BASE_MANIFEST_ID or len(candidates) != 1:
        raise ValueError("LARGE_AI_ACCEPTED_R2_BASE_REQUIRED")
    path = candidates[0]
    pins_valid({str(path): BASE_QUALIFICATION_SHA})
    receipt = read_checked(path)
    if receipt.get("manifest_id") != BASE_MANIFEST_ID or receipt.get("manifest") != str(base):
        raise ValueError("LARGE_AI_ACCEPTED_R2_BASE_REQUIRED")
    return {"path": str(path), "sha256": BASE_QUALIFICATION_SHA, "manifest_id": BASE_MANIFEST_ID}


def compose(
    base: Path, descriptor: dict[str, str], run_root: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    for path in (base, run_root):
        if not path.is_absolute():
            raise ValueError("LARGE_AI_ABSOLUTE_PATH_REQUIRED")
        reject_links(path)
    qualified, selected = qualification(descriptor)
    base_receipt = base_qualification(base, qualified)
    if qualified["pins"].get(str(base)) != sha(base):
        raise ValueError("LARGE_AI_BASE_NOT_PINNED")
    LOG.info("Validating unchanged R2 human and AI inputs")
    previous = SymbolAiExperimentAdapter(base).validate()
    LOG.info("R2 validated; composing %s exact crop cases", selected["selected"])
    batch_root = Path(selected["batch"])
    batch = validate_batch(batch_root)
    if (
        digest(batch) != selected["batch_id"]
        or str(batch_root) != previous.payload["batch"]
        or selected["classes"]
        != [e["display_name"] for e in previous.preparation["dictionary"]["entries"]]
    ):
        raise ValueError("LARGE_AI_BATCH_DICTIONARY_INVALID")
    pins = {
        **qualified["pins"],
        descriptor["pointer"]: descriptor["pointer_sha256"],
        read_checked(Path(descriptor["pointer"]))["path"]: descriptor["file_sha256"],
    }
    preparation = deepcopy(previous.preparation)
    assignments = dict(previous.payload["assignments"])
    files = {
        "crops/" + s["decision"]["binding"]["byte_sha256"] + ".png": (
            previous.bundle / "crops" / (s["decision"]["binding"]["byte_sha256"] + ".png")
        ).read_bytes()
        for s in preparation["samples"]
    }
    old_pixels = {s["decision"]["binding"]["pixel_sha256"] for s in preparation["samples"]}
    pixels: set[str] = set()
    class_ids = {e["display_name"]: e["id"] for e in preparation["dictionary"]["entries"]}
    groups: dict[str, str] = {}
    decoded_sources: dict[str, np.ndarray] = {}
    all_rows = []
    ai_ids = []
    for index, marker in enumerate(qualified["references"]):
        LOG.info("Checking and rendering reference %s/%s", index + 1, len(qualified["references"]))
        path = Path(marker["path"])
        pins_valid({str(path): marker["sha256"]})
        proof = read_checked(path)
        if (
            digest(proof) != marker["id"]
            or proof["format"] != "mumie-large-packet-assessment-v1"
            or proof["packet_index"] != index
            or proof["selection_id"] != digest(selected)
            or proof["selection_sha256"] != pins[qualified["selection"]]
            or proof["origin"] != "ai_visual_assessment"
            or proof["human_approved"] is not False
            or proof["human_labels_written"] != 0
            or proof["super_targets"] != 0
            or proof["cnn_started"] is not False
            or any(pins.get(k) != v for k, v in proof["pins"].items())
        ):
            raise ValueError("LARGE_AI_PACKET_PROOF_INVALID")
        reference_path = Path(proof["reference"])
        store = BatchReviewStore(reference_path, path.parent / "unused-large-ai-labels")
        reference = store.reference_payload()
        if (
            digest(reference) != proof["reference_id"]
            or reference["dictionary"] != preparation["dictionary"]
            or reference["batch_id"] != selected["batch_id"]
        ):
            raise ValueError("LARGE_AI_REFERENCE_INVALID")
        store.validate_live(reference)
        reviews = [Path(p) for p in proof["reviews"]]
        if any(str(p) not in proof["pins"] for p in reviews):
            raise ValueError("LARGE_AI_REVIEW_NOT_PINNED")
        rows = consensus(reference, reviews)
        expected = [dict(row, case=c) for row, c in zip(rows, reference["cases"], strict=True)]
        original_cases = selected["cases"][index * 100 : (index + 1) * 100]
        if expected != proof["rows"] or len(original_cases) != len(expected):
            raise ValueError("LARGE_AI_CONSENSUS_INVALID")
        all_rows.extend(expected)
        for original, row in zip(original_cases, expected, strict=True):
            case = row["case"]
            pixel = case["pixel_sha256"]
            source = case["source"]
            photo_index = original["photo_index"]
            if (
                pixel in pixels
                or pixel in old_pixels
                or pixel in selected["forbidden_pixels"]
                or original["human_approved"] is not False
                or any(original[k] != case[k] for k in ("source", "quad", "board", "field"))
                or original["crop_pixel_sha256"] != pixel
                or type(photo_index) is not int
                or not 0 <= photo_index < len(batch["rows"])
                or source != batch["rows"][photo_index]
                or photo_index in selected["withheld_photo_indices"]
                or source["sha256"] in selected["protected_sources"]
            ):
                raise ValueError("LARGE_AI_CASE_EXCLUSION_INVALID")
            pixels.add(pixel)
            if source["sha256"] not in groups:
                image = load_photo(source, reference["forbidden_photo_pixels"])
                decoded_sources[source["sha256"]] = np.asarray(image)
                groups[source["sha256"]] = digest(
                    [image.size, hashlib.sha256(image.tobytes()).hexdigest()]
                )
            if (
                groups[source["sha256"]] != selected["third_photo_groups"][source["sha256"]]
                or groups[source["sha256"]] in selected["protected_photo_groups"]
                or groups[source["sha256"]] in reference["forbidden_photo_pixels"]
            ):
                raise ValueError("LARGE_AI_PROTECTED_PHOTO_ALIAS")
            # Decode each of the 41 source photos once per composition. The
            # existing reader still checks actual source, PNG and pixel hashes
            # for every case; every quad is independently rendered below.
            data = store.png(case, reference)
            rendered = crop_cell(
                decoded_sources[source["sha256"]], np.asarray(case["quad"], dtype=np.float32)
            )
            if rendered is None or hashlib.sha256(rendered.tobytes()).hexdigest() != pixel:
                raise ValueError("SYMBOL_BATCH_REVIEW_PIXEL_DRIFT")
            if not row["accepted"]:
                continue
            identity = digest(
                {"qualification": descriptor["id"], "case": case, "class": row["class"]}
            )
            source_id = "ai:" + source["sha256"]
            if assignments.get(source_id, "development") != "development":
                raise ValueError("LARGE_AI_CROSS_PARTITION_SOURCE")
            assignments[source_id] = "development"
            target = {
                "decision_id": identity,
                "symbol_id": class_ids[row["class"]],
                "origin": "ai_visual_assessment",
                "human_approved": False,
                "trainable": False,
                "binding": {
                    "source_id": source_id,
                    "source_sha256": source["sha256"],
                    "byte_sha256": case["byte_sha256"],
                    "pixel_sha256": pixel,
                    "quad": case["quad"],
                    "geometry_scope": "exact_ai_assessed_crop",
                },
            }
            preparation["samples"].append({"decision": target, "ai_audit": False})
            ai_ids.append(identity)
            files["crops/" + case["byte_sha256"] + ".png"] = data
    counts = dict(Counter(row["class"] for row in all_rows if row["accepted"]))
    if (
        all_rows != qualified["rows"]
        or counts != qualified["counts"]
        or len(ai_ids) != qualified["accepted"]
        or len(all_rows) - len(ai_ids) != qualified["rejected"]
        or not ai_ids
    ):
        raise ValueError("LARGE_AI_AGGREGATE_INVALID")
    pins_valid(pins)
    if any(digest_bytes(data) != Path(name).stem for name, data in files.items()):
        raise ValueError("LARGE_AI_COPIED_CROP_DRIFT")
    files["preparation.json"] = canonical(preparation)
    file_hashes = {name: digest_bytes(data) for name, data in files.items()}
    result = {
        "format": FORMAT,
        "purpose": PURPOSE,
        "decision": "D-506",
        "experimental": True,
        "trainable": True,
        "origin": "human_and_ai_separate",
        "base_manifest": str(base),
        "base_qualification": base_receipt,
        "qualification": descriptor,
        "protocol": PROTOCOL,
        "symbol_protocol_digest": PROTOCOL_DIGEST,
        "run_root": str(run_root),
        "assignments": assignments,
        "feedback_sample_ids": previous.payload["feedback_sample_ids"],
        "ai_sample_ids": [*previous.payload["ai_sample_ids"], *ai_ids],
        "ai_audit_ids": previous.payload["ai_audit_ids"],
        "new_ai_sample_ids": ai_ids,
        "live_bindings": pins,
        "files": file_hashes,
        "bundle_id": digest(file_hashes),
        "counts": {
            "base": previous.payload["counts"],
            "new_ai_development": len(ai_ids),
            "new_classes": counts,
        },
        "limitation": (
            "Fallible AI targets; same-film audit and small human controls "
            "are not population accuracy."
        ),
    }
    return result, preparation, files


def freeze(base: Path, descriptor: dict[str, str], output: Path) -> Path:
    payload, _preparation, files = compose(base, descriptor, output / "runs")
    separate(output, [Path(p).parent for p in payload["live_bindings"]])
    bundle = output / "bundles" / payload["bundle_id"]
    payload["bundle"] = str(bundle)
    for name, data in files.items():
        publish_file(bundle / name, data)
    pins_valid(payload["live_bindings"])
    destination = output / "manifests" / (digest(payload) + ".json")
    checked_publish(destination, payload)
    # Full fresh-process verification precedes admission; do not repeat a whole
    # large-cohort compose inside one finite publication command.
    return destination


class LargeAiExperimentAdapter:
    def __init__(self, manifest: Path):
        if not manifest.is_absolute():
            raise ValueError("LARGE_AI_ABSOLUTE_PATH_REQUIRED")
        self.manifest = manifest
        self._validated: SymbolTrainingInputs | None = None
        self._manifest_sha: str | None = None

    def validate(self, request: Any = None) -> SymbolTrainingInputs:
        reject_links(self.manifest)
        manifest_sha = sha(self.manifest)
        payload = read_checked(self.manifest)
        identity = digest(payload)
        if (
            payload.get("format") != FORMAT
            or payload.get("purpose") != PURPOSE
            or payload.get("decision") != "D-506"
            or payload.get("experimental") is not True
            or payload.get("trainable") is not True
            or self.manifest.stem != identity
            or payload.get("protocol") != PROTOCOL
            or payload.get("symbol_protocol_digest") != PROTOCOL_DIGEST
            or (request is not None and request.manifest_id != identity)
        ):
            raise ValueError("LARGE_AI_MANIFEST_INVALID")
        pins_valid(payload["live_bindings"])
        if self._validated is None:
            expected, preparation, _files = compose(
                Path(payload["base_manifest"]), payload["qualification"], Path(payload["run_root"])
            )
            expected["bundle"] = payload["bundle"]
            if expected != payload:
                raise ValueError("LARGE_AI_MANIFEST_DRIFT")
        else:
            if manifest_sha != self._manifest_sha or payload != self._validated.payload:
                raise ValueError("LARGE_AI_MANIFEST_DRIFT")
            preparation = self._validated.preparation
        bundle = Path(payload["bundle"])
        reject_links(bundle)
        if not bundle.is_absolute() or bundle.name != payload["bundle_id"]:
            raise ValueError("LARGE_AI_BUNDLE_INVALID")
        if json.loads((bundle / "preparation.json").read_bytes()) != preparation:
            raise ValueError("LARGE_AI_BUNDLE_INVALID")
        if {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()} != set(
            payload["files"]
        ):
            raise ValueError("LARGE_AI_BUNDLE_INVALID")
        for name, expected_sha in payload["files"].items():
            if sha(safe_file(bundle, name)) != expected_sha:
                raise ValueError("LARGE_AI_BUNDLE_INVALID")
        pins_valid({**payload["live_bindings"], str(self.manifest): manifest_sha})
        if self._validated is None:
            self._manifest_sha = manifest_sha
            self._validated = SymbolTrainingInputs(
                identity, deepcopy(payload), deepcopy(preparation), bundle
            )
        # Callers cannot mutate the trusted cache. Every process first rerenders
        # all quads; subsequent calls still check every frozen live and bundle SHA.
        return SymbolTrainingInputs(identity, deepcopy(payload), deepcopy(preparation), bundle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    start = sub.add_parser("freeze")
    for name in ("base", "pointer", "output"):
        start.add_argument("--" + name, type=Path, required=True)
    for name in ("pointer-sha256", "qualification-id", "qualification-sha256"):
        start.add_argument("--" + name, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.action == "freeze":
        descriptor = {
            "pointer": str(args.pointer),
            "pointer_sha256": args.pointer_sha256,
            "id": args.qualification_id,
            "file_sha256": args.qualification_sha256,
        }
        path = freeze(args.base, descriptor, args.output)
        value = read_checked(path)
    else:
        path = args.manifest
        value = LargeAiExperimentAdapter(path).validate().payload
    print(
        json.dumps(
            {"manifest": str(path), "counts": value["counts"], "run_root": value["run_root"]}
        )
    )


if __name__ == "__main__":
    main()
