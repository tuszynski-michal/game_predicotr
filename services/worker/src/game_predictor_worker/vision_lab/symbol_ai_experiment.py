"""Explicit AI-origin experimental inputs; never operator approval (D-505)."""

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .annotations import digest, read_checked
from .catalog import Catalog
from .snapshot import canonical, reject_links, safe_file, sha
from .symbol_batch import checked_publish, excluded_sources, validate_batch
from .symbol_batch_inputs import batch_inputs, exclusion_hashes
from .symbol_batch_labels import BatchReviewStore, separate
from .symbol_feedback import folder_rows, verify_pack
from .symbol_store import publish_file
from .symbol_training_manifest import SymbolTrainingInputs

FORMAT = "lab-symbol-ai-experiment-v1"
PURPOSE = "symbol_ai_experiment"
REVIEW_FORMAT = "mumie-ai-visual-review-v1"


def review_items(path: Path, reference: dict[str, Any]) -> dict[str, dict[str, Any]]:
    review = read_checked(path)
    cases = {c["case_id"]: c for c in reference["cases"]}
    classes = {e["display_name"] for e in reference["dictionary"]["entries"]}
    if (
        review.get("format") != REVIEW_FORMAT
        or review.get("origin") != "ai_visual_assessment"
        or review.get("human_approved") is not False
        or review.get("reference_id") != digest(reference)
        or not review.get("reviewer")
        or review.get("model") != "gpt-6.1-sol"
        or len(review.get("items", [])) != len(cases)
    ):
        raise ValueError("SYMBOL_AI_REVIEW_INVALID")
    rows = {}
    for i, row in enumerate(review["items"], 1):
        case = cases.get(row.get("case_id"))
        if (
            case is None
            or row["case_id"] in rows
            or row.get("index") != i
            or row["case_id"] != reference["cases"][i - 1]["case_id"]
            or row.get("byte_sha256") != case["byte_sha256"]
            or row.get("pixel_sha256") != case["pixel_sha256"]
            or row.get("status") not in {"readable", "unreadable", "grid_issue"}
            or row.get("confidence") not in {"high", "medium", "low"}
            or row.get("gold_frame") not in {"present", "absent", "uncertain"}
            or not isinstance(row.get("reason"), str)
            or not row["reason"].strip()
            or (row["status"] == "readable" and row.get("class") not in classes)
            or (row["status"] != "readable" and row.get("class") is not None)
        ):
            raise ValueError("SYMBOL_AI_REVIEW_BINDING_INVALID")
        rows[row["case_id"]] = row
    return rows


def consensus(reference: dict[str, Any], reviews: list[Path]) -> list[dict[str, Any]]:
    if len(reviews) != 2 or reviews[0].resolve() == reviews[1].resolve():
        raise ValueError("SYMBOL_AI_TWO_REVIEWS_REQUIRED")
    metadata = [read_checked(p) for p in reviews]
    if metadata[0]["reviewer"] == metadata[1]["reviewer"]:
        raise ValueError("SYMBOL_AI_TWO_REVIEWERS_REQUIRED")
    a, b = [review_items(p, reference) for p in reviews]
    result = []
    for c in reference["cases"]:
        left, right = a[c["case_id"]], b[c["case_id"]]
        accepted = (
            left["status"] == right["status"] == "readable"
            and left["confidence"] == right["confidence"] == "high"
            and left["class"] == right["class"]
        )
        result.append(
            {
                "case_id": c["case_id"],
                "accepted": accepted,
                "class": left["class"] if accepted else None,
                "reason": "high/high readable consensus"
                if accepted
                else "review disagreement or uncertainty",
            }
        )
    return result


def compose(
    selection: Path, reviews: list[Path]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    for path in [selection, *reviews]:
        if not path.is_absolute():
            raise ValueError("SYMBOL_AI_ABSOLUTE_PATH_REQUIRED")
        reject_links(path)
    chosen = read_checked(selection)
    if (
        chosen.get("format") != "mumie-ai-pretraining-selection-v1"
        or chosen.get("human_labels_written") != 0
        or chosen.get("accuracy") is not None
        or not chosen.get("recording_reference")
    ):
        raise ValueError("SYMBOL_AI_SELECTION_INVALID")
    base, batch, reference = [Path(chosen[n]) for n in ("base", "batch", "reference")]
    context = batch_inputs(base, 3)
    inputs = context.inputs
    payload = validate_batch(batch)
    if payload["training_manifest"] != str(base) or payload.get("generation") != 3:
        raise ValueError("SYMBOL_AI_BASE_BATCH_MISMATCH")
    excluded = excluded_sources(inputs.payload)
    excluded_sha = exclusion_hashes(context, Catalog(Path(inputs.payload["catalog"])), excluded)
    if (
        payload["excluded_source_ids"] != sorted(excluded)
        or payload["excluded_sha256"] != sorted(excluded_sha)
        or payload["training_photo_pixel_groups"] != context.photo_pixels
    ):
        raise ValueError("SYMBOL_AI_EXCLUSION_BINDING_INVALID")
    store = BatchReviewStore(reference, reference.parent.parent / "unused-ai-labels")
    ref = store.reference_payload()
    if ref["batch_id"] != digest(payload) or ref["dictionary"] != inputs.preparation["dictionary"]:
        raise ValueError("SYMBOL_AI_DICTIONARY_BATCH_MISMATCH")
    if ref["forbidden_photo_pixels"] != context.photo_pixels:
        raise ValueError("SYMBOL_AI_PHOTO_EXCLUSION_INVALID")
    store.validate_live(ref)
    folder = Path(payload["folder"])
    # Entire recording remains development. SHA aliases override declarations.
    inventory = folder_rows(folder, folder)
    checksums = [r["sha256"] for r in inventory]
    if len(set(checksums)) != len(checksums) or set(checksums) & set(payload["excluded_sha256"]):
        raise ValueError("SYMBOL_AI_RECORDING_ALIAS_CONFLICT")
    withheld = chosen["withheld_photo_indices"]
    training = chosen["training_photo_indices"]
    source_rows = {row["path"]: row for row in payload["rows"]}
    human_pack = Path(chosen["human_pack"]) if chosen.get("human_pack") else None
    human = verify_pack(human_pack) if human_pack else None
    human_photos: set[str] = set()
    human_pixels: set[str] = set()
    if human is not None:
        assert human_pack is not None
        if human["dictionary"] != ref["dictionary"]:
            raise ValueError("SYMBOL_AI_HUMAN_DICTIONARY_MISMATCH")
        old_ref = read_checked(human_pack / "reference.json")
        state = read_checked(human_pack / "decisions.json")
        human_pixels = {
            c["pixel_sha256"]
            for c in old_ref["cases"]
            if any(d["case_id"] == c["case_id"] for d in state["decisions"])
        }
        human_photos = {c["source"]["sha256"] for c in human["cases"]}
    expected_withheld = [
        i
        for i in range(len(payload["rows"]))
        if i % 3 == 0 and payload["rows"][i]["sha256"] not in human_photos
    ]
    if withheld != expected_withheld or training != [
        i for i in range(len(payload["rows"])) if i not in withheld
    ]:
        raise ValueError("SYMBOL_AI_WITHHELD_SELECTION_INVALID")
    withheld_sha = {payload["rows"][i]["sha256"] for i in withheld}
    rows = consensus(ref, reviews)
    class_ids = {e["display_name"]: e["id"] for e in ref["dictionary"]["entries"]}
    preparation = deepcopy(inputs.preparation)
    assignments = dict(inputs.payload["assignments"])
    files = {
        "crops/" + s["decision"]["binding"]["byte_sha256"] + ".png": (
            inputs.bundle / "crops" / (s["decision"]["binding"]["byte_sha256"] + ".png")
        ).read_bytes()
        for s in preparation["samples"]
    }
    pixels = {s["decision"]["binding"]["pixel_sha256"] for s in preparation["samples"]}
    ai_ids: list[str] = []
    audit_ids: list[str] = []
    audit_photos: set[str] = set()
    train_photos: set[str] = set()
    human_ids: list[str] = []
    live = {**context.live, **payload["live_bindings"], **ref["live_bindings"]}
    for path in [base, selection, *reviews, reference / "reference.json", batch / "manifest.json"]:
        live[str(path)] = sha(path)
    if human is not None:
        assert human_pack is not None
        live.update(human["live_bindings"])
        for path in human_pack.rglob("*"):
            if path.is_file():
                live[str(path)] = sha(path)
        ai_cases = {c["pixel_sha256"]: c for c in ref["cases"]}
        for d, c in zip(human["decisions"], human["cases"], strict=True):
            exact = ai_cases.get(c["pixel_sha256"])
            if (
                exact is None
                or c["source"] != source_rows.get(c["source"]["path"])
                or any(exact[k] != c[k] for k in ("source", "quad", "byte_sha256"))
            ):
                raise ValueError("SYMBOL_AI_HUMAN_BINDING_MISMATCH")
            if c["pixel_sha256"] in pixels:
                raise ValueError("SYMBOL_AI_PIXEL_DUPLICATE")
            data = store.png(exact, ref, render=True)
            source_id = "ai:" + c["source"]["sha256"]
            assignments[source_id] = "development"
            target = {
                **d,
                "binding": {
                    "source_id": source_id,
                    "source_sha256": c["source"]["sha256"],
                    "byte_sha256": c["byte_sha256"],
                    "pixel_sha256": c["pixel_sha256"],
                    "quad": c["quad"],
                    "geometry_scope": "exact_reviewed_crop",
                },
            }
            preparation["samples"].append({"decision": target, "feedback": True})
            files["crops/" + c["byte_sha256"] + ".png"] = data
            human_ids.append(d["decision_id"])
            pixels.add(c["pixel_sha256"])
            train_photos.add(c["source"]["sha256"])
    for c, decision in zip(ref["cases"], rows, strict=True):
        if c["source"] != source_rows.get(c["source"]["path"]):
            raise ValueError("SYMBOL_AI_SOURCE_NOT_IN_BATCH")
        # Verify every assessed PNG and exact quad even when not accepted.
        data = store.png(c, ref, render=True)
        live[str(reference / "crops" / (c["byte_sha256"] + ".png"))] = c["byte_sha256"]
        if not decision["accepted"] or c["pixel_sha256"] in human_pixels:
            continue
        if c["pixel_sha256"] in pixels:
            raise ValueError("SYMBOL_AI_PIXEL_DUPLICATE")
        pixels.add(c["pixel_sha256"])
        source_id = "ai:" + c["source"]["sha256"]
        assignments[source_id] = "development"
        is_audit = c["source"]["sha256"] in withheld_sha
        identity = digest(
            {
                "origin": "ai_visual_assessment",
                "case": c,
                "class": decision["class"],
                "reviews": [sha(p) for p in reviews],
            }
        )
        target = {
            "decision_id": identity,
            "symbol_id": class_ids[decision["class"]],
            "origin": "ai_visual_assessment",
            "human_approved": False,
            "trainable": False,
            "binding": {
                "source_id": source_id,
                "source_sha256": c["source"]["sha256"],
                "byte_sha256": c["byte_sha256"],
                "pixel_sha256": c["pixel_sha256"],
                "quad": c["quad"],
                "geometry_scope": "exact_ai_assessed_crop",
            },
        }
        preparation["samples"].append({"decision": target, "ai_audit": is_audit})
        files["crops/" + c["byte_sha256"] + ".png"] = data
        (audit_ids if is_audit else ai_ids).append(identity)
        (audit_photos if is_audit else train_photos).add(c["source"]["sha256"])
    if len(audit_ids) < 20 or not ai_ids or audit_photos & train_photos:
        raise ValueError("SYMBOL_AI_COHORT_COVERAGE_REQUIRED")
    preparation_bytes = canonical(preparation)
    files["preparation.json"] = preparation_bytes
    file_hashes = {name: digest_bytes(data) for name, data in files.items()}
    result = {
        "format": FORMAT,
        "purpose": PURPOSE,
        "decision": "D-505",
        "experimental": True,
        "trainable": True,
        "origin": "human_and_ai_separate",
        "base_manifest": str(base),
        "selection": str(selection),
        "reviews": [str(p) for p in reviews],
        "reference": str(reference),
        "batch": str(batch),
        "recording_partition": "development",
        "folder_inventory": inventory,
        "assignments": assignments,
        "feedback_sample_ids": [*inputs.payload["feedback_sample_ids"], *human_ids],
        "new_human_sample_ids": human_ids,
        "ai_sample_ids": ai_ids,
        "ai_audit_ids": audit_ids,
        "consensus": rows,
        "live_bindings": live,
        "files": file_hashes,
        "bundle_id": digest(file_hashes),
        "counts": {
            "human": inputs.payload["counts"],
            "ai_development": len(ai_ids),
            "ai_audit": len(audit_ids),
            "new_human_development": len(human_ids),
        },
        "limitation": (
            "AI-origin targets and same-film audit; not human accuracy or independent film test"
        ),
    }
    return result, preparation, files


def digest_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def freeze(selection: Path, reviews: list[Path], output: Path) -> Path:
    payload, _preparation, files = compose(selection, reviews)
    protected = [Path(p).parent for p in payload["live_bindings"]]
    protected.extend(
        [
            Path(payload["reference"]),
            Path(payload["batch"]),
            Path(payload["folder_inventory"][0]["path"]).parent,
        ]
    )
    # compose already validated the base and resolved physical live paths.
    protected.append(Path(read_checked(Path(payload["base_manifest"]))["bundle"]))
    separate(output, protected)
    bundle = output / "bundles" / payload["bundle_id"]
    payload["bundle"] = str(bundle)
    for name, data in files.items():
        publish_file(bundle / name, data)
    target = output / "manifests" / (digest(payload) + ".json")
    checked_publish(target, payload)
    SymbolAiExperimentAdapter(target).validate()
    return target


class SymbolAiExperimentAdapter:
    def __init__(self, manifest: Path):
        if not manifest.is_absolute():
            raise ValueError("SYMBOL_AI_ABSOLUTE_PATH_REQUIRED")
        self.manifest = manifest

    def protected_paths(self) -> list[Path]:
        payload = read_checked(self.manifest)
        return [
            Path(payload["reference"]),
            Path(payload["batch"]),
            Path(payload["folder_inventory"][0]["path"]).parent,
        ]

    def validate(self, request: Any = None) -> SymbolTrainingInputs:
        reject_links(self.manifest)
        payload = read_checked(self.manifest)
        identity = digest(payload)
        if (
            payload.get("format") != FORMAT
            or payload.get("purpose") != PURPOSE
            or payload.get("decision") != "D-505"
            or payload.get("experimental") is not True
            or self.manifest.stem != identity
            or (request is not None and request.manifest_id != identity)
        ):
            raise ValueError("SYMBOL_AI_MANIFEST_INVALID")
        expected, preparation, _files = compose(
            Path(payload["selection"]), [Path(p) for p in payload["reviews"]]
        )
        expected["bundle"] = payload["bundle"]
        if expected != payload:
            raise ValueError("SYMBOL_AI_INPUT_DRIFT")
        bundle = Path(payload["bundle"])
        reject_links(bundle)
        if not bundle.is_absolute() or bundle.name != payload["bundle_id"]:
            raise ValueError("SYMBOL_AI_BUNDLE_INVALID")
        if json.loads((bundle / "preparation.json").read_bytes()) != preparation:
            raise ValueError("SYMBOL_AI_BUNDLE_INVALID")
        if {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()} != set(
            payload["files"]
        ):
            raise ValueError("SYMBOL_AI_BUNDLE_INVENTORY_INVALID")
        for name, expected_sha in payload["live_bindings"].items():
            reject_links(Path(name))
            if sha(Path(name)) != expected_sha:
                raise ValueError("SYMBOL_AI_INPUT_DRIFT")
        for name, expected_sha in payload["files"].items():
            if sha(safe_file(bundle, name)) != expected_sha:
                raise ValueError("SYMBOL_AI_BUNDLE_INVALID")
        return SymbolTrainingInputs(identity, payload, preparation, bundle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--selection", type=Path, required=True)
    f.add_argument("--review", type=Path, action="append", required=True)
    f.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    path = (
        args.manifest
        if args.action == "verify"
        else freeze(args.selection, args.review, args.output)
    )
    if args.action == "verify":
        metadata = SymbolAiExperimentAdapter(path).validate().payload
    else:
        metadata = read_checked(path)  # freeze already verifies the published artifact.
    print(json.dumps({"manifest": str(path), "counts": metadata["counts"], "experimental": True}))


if __name__ == "__main__":
    main()
