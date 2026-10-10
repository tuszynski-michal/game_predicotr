"""Classifier-only qualification of exact operator-reviewed batch rasters (D-502)."""

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .annotations import digest, exclusive_bounded, read_checked
from .catalog import Catalog
from .geometry import crop_cell
from .snapshot import canonical, reject_links, safe_file, sha
from .symbol_batch import load_photo
from .symbol_batch_labels import BatchReviewStore, separate
from .symbol_contracts import BatchLabelDecide
from .symbol_preparation import read_crop
from .symbol_store import publish_file
from .symbol_training_manifest import (
    SymbolTrainingAdapter,
    SymbolTrainingInputs,
    merged_components,
)

PACK_FORMAT = "lab-symbol-feedback-pack-v1"
FORMAT = "lab-symbol-feedback-training-v1"


class SourceLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["lab-symbol-source-location-v1"] = "lab-symbol-source-location-v1"
    manifest_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_folder: str
    source_root: str
    inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference: str = Field(min_length=1)


def resolve_source(path: Path, original: Path, current: Path | None) -> Path:
    """Relocate only direct source images; metadata and raster bundles never move."""
    if (
        current is not None
        and path.parent == original
        and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ):
        path = current / path.name
    reject_links(path)
    return path


class FeedbackQualification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: Literal[True]
    reference: str = Field(min_length=1)
    recording_reference: str = Field(min_length=1)
    independent_from_validation: Literal[True]
    independent_from_diagnostic: Literal[True]
    diagnostic_family_id: str = Field(min_length=1)
    geometry_scope: Literal["exact_reviewed_crop"] = "exact_reviewed_crop"


def latest_decisions(state: dict[str, Any], reference: dict[str, Any]) -> list[dict[str, Any]]:
    cases = {c["case_id"] for c in reference["cases"]}
    classes = {e["id"] for e in reference["dictionary"]["entries"]}
    if state["reference_id"] != digest(reference) or not (
        state["revision"] == len(state["decisions"]) == len(state["history"])
    ):
        raise ValueError("SYMBOL_FEEDBACK_HISTORY_INVALID")
    latest = {}
    for revision, (decision, history) in enumerate(
        zip(state["decisions"], state["history"], strict=True), 1
    ):
        request = BatchLabelDecide.model_validate(
            {k: v for k, v in decision.items() if k in BatchLabelDecide.model_fields}
        )
        fingerprint = digest(request.model_dump())
        receipt = state["receipts"].get(request.request_id, {})
        if (
            decision["decision_id"] != fingerprint
            or decision["revision"] != revision
            or request.expected_revision != revision - 1
            or decision.get("origin") != "batch_crop_review"
            or decision.get("trainable") is not False
            or request.reference_id != state["reference_id"]
            or request.case_id not in cases
            or history
            != {
                "request_id": request.request_id,
                "decision_id": fingerprint,
                "revision": revision,
            }
            or receipt.get("fingerprint") != fingerprint
            or receipt.get("result", {}).get("decision_ids") != [fingerprint]
        ):
            raise ValueError("SYMBOL_FEEDBACK_HISTORY_INVALID")
        if request.action == "approve" and request.symbol_id not in classes:
            raise ValueError("SYMBOL_FEEDBACK_CLASS_INVALID")
        latest[request.case_id] = decision
    result = [d for _, d in sorted(latest.items()) if d["action"] == "approve"]
    if not result:
        raise ValueError("SYMBOL_FEEDBACK_EMPTY")
    return result


def verify_pack(root: Path, *, expected_id: str | None = None) -> dict[str, Any]:
    reject_links(root)
    payload = read_checked(root / "manifest.json")
    if (
        payload.get("format") != PACK_FORMAT
        or payload.get("trainable") is not False
        or digest(payload) != (expected_id or root.name)
    ):
        raise ValueError("SYMBOL_FEEDBACK_PACK_INVALID")
    if {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} != {
        "manifest.json",
        *payload["files"],
    }:
        raise ValueError("SYMBOL_FEEDBACK_INVENTORY_INVALID")
    for name, expected in payload["files"].items():
        if sha(safe_file(root, name)) != expected:
            raise ValueError("SYMBOL_FEEDBACK_PACK_DRIFT")
    reference = read_checked(root / "reference.json")
    state = read_checked(root / "decisions.json")
    decisions = latest_decisions(state, reference)
    if (
        payload["reference_id"] != digest(reference)
        or payload["dictionary"] != reference["dictionary"]
        or payload["decisions"] != decisions
    ):
        raise ValueError("SYMBOL_FEEDBACK_PACK_LINEAGE_INVALID")
    by_case = {c["case_id"]: c for c in reference["cases"]}
    if payload["cases"] != [by_case[d["case_id"]] for d in decisions]:
        raise ValueError("SYMBOL_FEEDBACK_PACK_LINEAGE_INVALID")
    for case in payload["cases"]:
        read_crop(root, case)
    return payload


def prepare(store: BatchReviewStore, output: Path) -> Path:
    separate(output, [store.reference, store.root, *store.guards])
    with store.locked():
        reference = store.reference_payload()
        store.validate_live(reference)
        state = store.state(digest(reference))
        decisions = latest_decisions(state, reference)
        by_case = {c["case_id"]: c for c in reference["cases"]}
        cases = [by_case[d["case_id"]] for d in decisions]
        separate(output, [Path(c["source"]["path"]).parent for c in cases])
        files = {
            "reference.json": canonical({"payload": reference, "sha256": digest(reference)}),
            "decisions.json": canonical({"payload": state, "sha256": digest(state)}),
        }
        live = dict(reference["live_bindings"])
        for path in [store.reference / "reference.json", store.root / "state.json"]:
            live[str(path)] = sha(path)
        for case in cases:
            files["crops/" + case["byte_sha256"] + ".png"] = store.png(case, reference, render=True)
            live[case["source"]["path"]] = case["source"]["sha256"]
        payload = {
            "format": PACK_FORMAT,
            "purpose": "qualification_only",
            "trainable": False,
            "reference_id": digest(reference),
            "dictionary": reference["dictionary"],
            "decisions": decisions,
            "cases": cases,
            "live_bindings": live,
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        }
        root = output / digest(payload)
        with exclusive_bounded(output):
            if root.exists():
                if verify_pack(root) != payload:
                    raise ValueError("SYMBOL_FEEDBACK_PACK_CONFLICT")
                return root
            temporary = Path(tempfile.mkdtemp(prefix=".prepare-", dir=output))
            for name, data in files.items():
                publish_file(safe_file(temporary, name), data)
            publish_file(
                temporary / "manifest.json",
                canonical({"payload": payload, "sha256": digest(payload)}),
            )
            verify_pack(temporary, expected_id=root.name)
            os.rename(temporary, root)
        return root


def folder_rows(folder: Path, logical_root: Path | None = None) -> list[dict[str, str]]:
    if not folder.is_absolute():
        raise ValueError("SYMBOL_FEEDBACK_ABSOLUTE_PATH_REQUIRED")
    reject_links(folder)
    rows = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            reject_links(path)
            checksum = sha(path)
            logical = path if logical_root is None else logical_root / path.name
            rows.append({"path": str(logical), "sha256": checksum, "id": "feedback:" + checksum})
            if len(rows) > 10000:
                raise ValueError("SYMBOL_FEEDBACK_FOLDER_TOO_LARGE")
    if not rows:
        raise ValueError("SYMBOL_FEEDBACK_FOLDER_EMPTY")
    return rows


def assign_components(
    inputs: SymbolTrainingInputs,
    rows: list[dict[str, str]],
    catalog: Catalog,
    qualification: FeedbackQualification,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    diagnostic = {
        m["source"]["id"]
        for m in inputs.payload["component_evidence"]
        if m["family"] and m["family"]["family_id"] == qualification.diagnostic_family_id
    }
    if not diagnostic:
        raise ValueError("SYMBOL_FEEDBACK_DIAGNOSTIC_FAMILY_REQUIRED")
    original = {
        sid: "diagnostic_test" if sid in diagnostic else part
        for sid, part in inputs.payload["assignments"].items()
    }
    if any(
        original[sid] == "diagnostic_test" and part != "development"
        for sid, part in inputs.payload["assignments"].items()
    ):
        raise ValueError("SYMBOL_FEEDBACK_VALIDATION_UNCHANGED_REQUIRED")
    aliases = {}
    for row in rows:
        aliases[row["id"]] = [
            row["id"],
            *[sid for sid, source in catalog.sources.items() if source.sha256 == row["sha256"]],
        ]
    graph = merged_components(inputs.payload["graph"], aliases, {"folder": [r["id"] for r in rows]})
    feedback_ids = {r["id"] for r in rows}
    assignments = dict(original)
    for members in graph.values():
        if not feedback_ids.intersection(members):
            continue
        if set(members).intersection(inputs.payload["protected_source_ids"]):
            raise ValueError("HOLDOUT_NOT_RELEASED")
        if any(original.get(sid) in {"validation", "diagnostic_test"} for sid in members):
            raise ValueError("SYMBOL_FEEDBACK_COMPONENT_CROSSES_PARTITIONS")
        for sid in members:
            if sid in catalog.sources:
                source = catalog.sources[sid]
                if source.role != "data" or source.game_id != inputs.payload["game_id"]:
                    raise ValueError("SYMBOL_FEEDBACK_COMPONENT_ROLE_INVALID")
            assignments[sid] = "development"
    # Original components must also remain wholly inside one part.
    if any(
        len({assignments[sid] for sid in members if sid in assignments}) > 1
        for members in graph.values()
    ):
        raise ValueError("SYMBOL_FEEDBACK_COMPONENT_CROSSES_PARTITIONS")
    return graph, assignments


def counts(
    samples: list[dict[str, Any]], assignments: dict[str, str], dictionary: dict[str, Any]
) -> dict[str, Any]:
    totals = Counter(
        (assignments[s["decision"]["binding"]["source_id"]], s["decision"]["symbol_id"])
        for s in samples
    )
    pixels: dict[str, tuple[str, str]] = {}
    allowed_classes = {entry["id"] for entry in dictionary["entries"]}
    for sample in samples:
        d = sample["decision"]
        value = (assignments[d["binding"]["source_id"]], d["symbol_id"])
        if (
            value[0] not in {"development", "validation", "diagnostic_test"}
            or value[1] not in allowed_classes
        ):
            raise ValueError("SYMBOL_FEEDBACK_CLASS_INVALID")
        pixel = d["binding"]["pixel_sha256"]
        if pixel in pixels and pixels[pixel] != value:
            raise ValueError("SYMBOL_FEEDBACK_PIXEL_CONFLICT")
        pixels[pixel] = value
    classes = dictionary["entries"]
    if any(not totals[(part, c["id"])] for part in ["development", "validation"] for c in classes):
        raise ValueError("SYMBOL_PARTITION_CLASS_COVERAGE_REQUIRED")
    return {
        "parts": {
            p: sum(n for (part, _), n in totals.items() if part == p)
            for p in ["development", "validation", "diagnostic_test"]
        },
        "classes": [
            {
                "id": c["id"],
                "name": c["display_name"],
                **{
                    p: totals[(p, c["id"])]
                    for p in ["development", "validation", "diagnostic_test"]
                },
            }
            for c in classes
        ],
        "independent_final_test": False,
        "super_labels": 0,
    }


def compose(
    base: Path,
    pack: Path,
    catalog_root: Path,
    qualification: FeedbackQualification,
    *,
    source_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    for path in [base, pack, catalog_root]:
        if not path.is_absolute():
            raise ValueError("SYMBOL_FEEDBACK_ABSOLUTE_PATH_REQUIRED")
        reject_links(path)
    inputs = SymbolTrainingAdapter(base).validate()
    metadata = read_checked(pack / "manifest.json")  # No feedback pixels before component checks.
    if metadata["dictionary"] != inputs.preparation["dictionary"]:
        raise ValueError("SYMBOL_FEEDBACK_DICTIONARY_MISMATCH")
    if str(catalog_root / "manifest.json") not in inputs.payload["live_bindings"]:
        raise ValueError("SYMBOL_FEEDBACK_CATALOG_BINDING_INVALID")
    original = Path(qualification.recording_reference)
    rows = folder_rows(source_root or original, original)
    catalog = Catalog(catalog_root)
    graph, assignments = assign_components(inputs, rows, catalog, qualification)
    allowed = {row["path"]: row["sha256"] for row in rows}
    if any(allowed.get(c["source"]["path"]) != c["source"]["sha256"] for c in metadata["cases"]):
        raise ValueError("SYMBOL_FEEDBACK_SOURCE_OUTSIDE_RECORDING")
    verified = verify_pack(pack)
    if verified != metadata:
        raise ValueError("SYMBOL_FEEDBACK_PACK_DRIFT")
    samples = json.loads(canonical(inputs.preparation["samples"]))
    files = {
        "crops/" + s["decision"]["binding"]["byte_sha256"] + ".png": read_crop(
            inputs.bundle, s["decision"]["binding"]
        )
        for s in samples
    }
    photo_parts: dict[str, str] = {}
    for pixel, members in inputs.payload["photo_pixel_groups"].items():
        parts = {assignments[sid] for sid in members}
        if len(parts) != 1:
            raise ValueError("SYMBOL_FEEDBACK_PHOTO_CONFLICT")
        photo_parts[pixel] = next(iter(parts))
    photos = {}
    for decision, case in zip(metadata["decisions"], metadata["cases"], strict=True):
        source = case["source"]
        if source["path"] not in photos:
            image = load_photo(
                {
                    **source,
                    "path": str(resolve_source(Path(source["path"]), original, source_root)),
                },
                [],
            )
            pixel = digest([image.size, hashlib.sha256(image.tobytes()).hexdigest()])
            if pixel in photo_parts and photo_parts[pixel] != "development":
                raise ValueError("SYMBOL_FEEDBACK_PHOTO_CONFLICT")
            photo_parts[pixel] = "development"
            photos[source["path"]] = image
        rendered = crop_cell(
            np.asarray(photos[source["path"]]), np.asarray(case["quad"], dtype=np.float32)
        )
        if (
            rendered is None
            or hashlib.sha256(rendered.tobytes()).hexdigest() != case["pixel_sha256"]
        ):
            raise ValueError("SYMBOL_FEEDBACK_GEOMETRY_DRIFT")
        binding = {
            "source_id": "feedback:" + source["sha256"],
            "game_id": inputs.payload["game_id"],
            "board_index": case["board"] - 1,
            "cell_index": case["field"] - 1,
            "byte_sha256": case["byte_sha256"],
            "pixel_sha256": case["pixel_sha256"],
            "source_sha256": source["sha256"],
            "quad": case["quad"],
            "geometry_scope": "exact_reviewed_crop",
        }
        samples.append({"decision": {**decision, "binding": binding}, "feedback": True})
        files["crops/" + case["byte_sha256"] + ".png"] = read_crop(pack, case)
    preparation = {"dictionary": metadata["dictionary"], "samples": samples}
    live = {
        **inputs.payload["live_bindings"],
        **metadata["live_bindings"],
        **{row["path"]: row["sha256"] for row in rows},
    }
    for path in [base, pack / "manifest.json"]:
        live[str(path)] = sha(path)
    for path in [*inputs.bundle.rglob("*"), *pack.rglob("*")]:
        if path.is_file():
            live[str(path)] = sha(path)
    payload = {
        "format": FORMAT,
        "purpose": "symbol_crop_feedback",
        "decision": "D-502",
        "trainable": True,
        "base_manifest": str(base),
        "feedback_pack": str(pack),
        "catalog": str(catalog_root),
        "game_id": inputs.payload["game_id"],
        "qualification": qualification.model_dump(),
        "graph": graph,
        "assignments": assignments,
        "folder_rows": rows,
        "counts": counts(samples, assignments, metadata["dictionary"]),
        "feedback_sample_ids": [d["decision_id"] for d in metadata["decisions"]],
        "photo_partitions": photo_parts,
        "protected_source_ids": inputs.payload["protected_source_ids"],
        "live_bindings": live,
        "bundle_id": digest(preparation),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    return payload, preparation, files


def freeze(
    base: Path, pack: Path, catalog: Path, qualification: FeedbackQualification, output: Path
) -> Path:
    separate(output, [base.parent, pack, catalog, Path(qualification.recording_reference)])
    payload, preparation, files = compose(base, pack, catalog, qualification)
    separate(output, [Path(p).parent for p in payload["live_bindings"]])
    bundle = output / "bundles" / payload["bundle_id"]
    for name, data in files.items():
        publish_file(safe_file(bundle, name), data)
    publish_file(bundle / "preparation.json", canonical(preparation))
    payload["bundle"] = str(bundle)
    target = output / "manifests" / (digest(payload) + ".json")
    for name, expected in payload["live_bindings"].items():
        if sha(Path(name)) != expected:
            raise ValueError("SYMBOL_FEEDBACK_INPUT_DRIFT")
    publish_file(target, canonical({"payload": payload, "sha256": digest(payload)}))
    SymbolFeedbackAdapter(target).validate()
    return target


class SymbolFeedbackAdapter:
    def __init__(self, manifest: Path, *, source_root: Path | None = None):
        if not manifest.is_absolute():
            raise ValueError("SYMBOL_FEEDBACK_ABSOLUTE_PATH_REQUIRED")
        self.manifest = manifest
        self.source_root = source_root
        self._explicit_source_root = source_root

    @property
    def location_path(self) -> Path:
        return self.manifest.with_suffix(".sources.json")

    def protected_paths(self) -> list[Path]:
        return [self.location_path, self.source_root] if self.source_root is not None else []

    def validate(self, request: Any = None) -> SymbolTrainingInputs:
        self.source_root = self._explicit_source_root
        reject_links(self.manifest)
        payload = read_checked(self.manifest)
        identity = digest(payload)
        if (
            payload.get("format") != FORMAT
            or payload.get("purpose") != "symbol_crop_feedback"
            or payload.get("decision") != "D-502"
            or payload.get("trainable") is not True
            or self.manifest.stem != identity
            or (request is not None and request.manifest_id != identity)
        ):
            raise ValueError("SYMBOL_FEEDBACK_MANIFEST_INVALID")
        qualification = FeedbackQualification.model_validate(payload["qualification"])
        original = Path(qualification.recording_reference)
        location = None
        if self.location_path.exists():
            reject_links(self.location_path)
            location = SourceLocation.model_validate(read_checked(self.location_path))
            if (
                location.manifest_id != identity
                or location.original_folder != str(original)
                or location.inventory_sha256 != digest(payload["folder_rows"])
            ):
                raise ValueError("SYMBOL_SOURCE_LOCATION_BINDING_INVALID")
            self.source_root = Path(location.source_root)
        if (
            self.source_root is not None
            and folder_rows(self.source_root, original) != payload["folder_rows"]
        ):
            raise ValueError("SYMBOL_SOURCE_LOCATION_INVENTORY_DRIFT")
        expected, preparation, _files = compose(
            Path(payload["base_manifest"]),
            Path(payload["feedback_pack"]),
            Path(payload["catalog"]),
            qualification,
            source_root=self.source_root,
        )
        expected["bundle"] = payload["bundle"]
        if expected != payload:
            raise ValueError("SYMBOL_FEEDBACK_INPUT_DRIFT")
        bundle = Path(payload["bundle"])
        reject_links(bundle)
        if not bundle.is_absolute() or bundle.name != payload["bundle_id"]:
            raise ValueError("SYMBOL_FEEDBACK_BUNDLE_INVALID")
        if json.loads((bundle / "preparation.json").read_bytes()) != preparation:
            raise ValueError("SYMBOL_FEEDBACK_BUNDLE_INVALID")
        if {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()} != {
            "preparation.json",
            *payload["files"],
        }:
            raise ValueError("SYMBOL_FEEDBACK_INVENTORY_INVALID")
        for name, expected_hash in payload["live_bindings"].items():
            if sha(resolve_source(Path(name), original, self.source_root)) != expected_hash:
                raise ValueError("SYMBOL_FEEDBACK_INPUT_DRIFT")
        for name, expected_hash in payload["files"].items():
            if sha(safe_file(bundle, name)) != expected_hash:
                raise ValueError("SYMBOL_FEEDBACK_BUNDLE_INVALID")
        if location is not None and read_checked(self.location_path) != location.model_dump():
            raise ValueError("SYMBOL_SOURCE_LOCATION_DRIFT")
        return SymbolTrainingInputs(identity, payload, preparation, bundle)


def bind_source_location(manifest: Path, source_root: Path, reference: str) -> Path:
    """Create an explicit durable read location after exact inventory and crop validation."""
    adapter = SymbolFeedbackAdapter(manifest, source_root=source_root)
    inputs = adapter.validate()
    if adapter.source_root != source_root:
        raise ValueError("SYMBOL_SOURCE_LOCATION_CONFLICT")
    location = SourceLocation(
        manifest_id=inputs.manifest_id,
        original_folder=inputs.payload["qualification"]["recording_reference"],
        source_root=str(source_root),
        inventory_sha256=digest(inputs.payload["folder_rows"]),
        reference=reference,
    )
    publish_file(
        adapter.location_path,
        canonical({"payload": location.model_dump(), "sha256": digest(location.model_dump())}),
    )
    SymbolFeedbackAdapter(manifest).validate()
    return adapter.location_path


def training_adapter(manifest: Path) -> Any:
    metadata = read_checked(manifest)
    if metadata.get("format") == "lab-symbol-ai-experiment-v1":
        from .symbol_ai_experiment import SymbolAiExperimentAdapter

        return SymbolAiExperimentAdapter(manifest)
    return (
        SymbolFeedbackAdapter(manifest)
        if metadata.get("format") == FORMAT
        else SymbolTrainingAdapter(manifest)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare")
    for name in ["reference", "labels", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    f = sub.add_parser("freeze")
    for name in ["base", "pack", "catalog", "qualification", "output"]:
        f.add_argument("--" + name, type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--manifest", type=Path, required=True)
    relocate = sub.add_parser("relocate")
    relocate.add_argument("--manifest", type=Path, required=True)
    relocate.add_argument("--source-root", type=Path, required=True)
    relocate.add_argument("--reference", required=True)
    args = parser.parse_args()
    if not all(v.is_absolute() for v in vars(args).values() if isinstance(v, Path)):
        parser.error("all paths must be absolute")
    if args.action == "relocate":
        path = bind_source_location(args.manifest, args.source_root, args.reference)
        print(json.dumps({"location": str(path), "manifest_id": args.manifest.stem}))
    elif args.action == "prepare":
        path = prepare(BatchReviewStore(args.reference, args.labels), args.output)
        print(json.dumps({"pack": str(path), "samples": len(verify_pack(path)["decisions"])}))
    else:
        path = (
            args.manifest
            if args.action == "verify"
            else freeze(
                args.base,
                args.pack,
                args.catalog,
                FeedbackQualification.model_validate_json(args.qualification.read_bytes()),
                args.output,
            )
        )
        inputs = SymbolFeedbackAdapter(path).validate()
        print(json.dumps({"manifest": str(path), "counts": inputs.payload["counts"]}))


if __name__ == "__main__":
    main()
