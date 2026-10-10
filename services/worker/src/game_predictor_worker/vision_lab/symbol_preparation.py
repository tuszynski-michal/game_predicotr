"""Immutable qualification evidence for fresh labels; never a training manifest."""

import argparse
import hashlib
import io
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from PIL import Image

from .annotations import AnnotationStore, digest, exclusive_bounded, read_checked
from .catalog import Catalog
from .snapshot import canonical, reject_links, safe_file, sha
from .splits import build_components
from .symbol_store import SymbolLabelStore, publish_file

FORMAT = "lab-symbol-preparation-v1"
MAX_CROP_BYTES = 256 * 1024
MAX_METADATA_BYTES = 64 * 1024 * 1024


def latest_fresh_decisions(payload: dict[str, Any], version_id: str) -> list[dict[str, Any]]:
    latest = {}
    for decision in payload["decisions"]:
        b = decision["binding"]
        latest[(b["source_id"], b["board_index"], b["cell_index"])] = decision
    selected = [
        d
        for _, d in sorted(latest.items())
        if d.get("dataset_version_id") == version_id and d["action"] == "approve"
    ]
    if not selected:
        raise ValueError("SYMBOL_PREPARATION_EMPTY")
    if len(selected) > 10000:
        raise ValueError("SYMBOL_PREPARATION_TOO_LARGE")
    return selected


def read_crop(root: Path, binding: dict[str, Any]) -> bytes:
    path = safe_file(root, f"crops/{binding['byte_sha256']}.png")
    with path.open("rb") as stream:
        data = stream.read(MAX_CROP_BYTES + 1)
    if len(data) > MAX_CROP_BYTES or hashlib.sha256(data).hexdigest() != binding["byte_sha256"]:
        raise ValueError("SYMBOL_PREPARATION_CROP_INTEGRITY_ERROR")
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG" or image.mode != "RGB" or image.size != (96, 96):
            raise ValueError("SYMBOL_PREPARATION_CROP_FORMAT_INVALID")
        if hashlib.sha256(image.tobytes()).hexdigest() != binding["pixel_sha256"]:
            raise ValueError("SYMBOL_PREPARATION_PIXEL_INTEGRITY_ERROR")
    return data


def summarize(samples: list[dict[str, Any]], dictionary: dict[str, Any]) -> dict[str, Any]:
    pixels: dict[str, list[dict[str, Any]]] = defaultdict(list)
    classes = []
    for sample in samples:
        pixels[sample["decision"]["binding"]["pixel_sha256"]].append(sample)
    for entry in dictionary["entries"]:
        rows = [s for s in samples if s["decision"]["symbol_id"] == entry["id"]]
        classes.append(
            {
                "symbol_id": entry["id"],
                "name": entry["display_name"],
                "samples": len(rows),
                "unique_pixels": len({s["decision"]["binding"]["pixel_sha256"] for s in rows}),
                "sources": len({s["decision"]["binding"]["source_id"] for s in rows}),
                "components": len({s["component_id"] for s in rows}),
                "family_candidates": dict(Counter(s["family_id"] for s in rows)),
            }
        )
    duplicate_groups = [
        {
            "pixel_sha256": pixel,
            "decision_ids": [s["decision"]["decision_id"] for s in rows],
            "symbol_ids": sorted({s["decision"]["symbol_id"] for s in rows}),
        }
        for pixel, rows in sorted(pixels.items())
        if len(rows) > 1
    ]
    return {
        "samples": len(samples),
        "sources": len({s["decision"]["binding"]["source_id"] for s in samples}),
        "components": len({s["component_id"] for s in samples}),
        "classes": classes,
        "duplicate_pixel_groups": duplicate_groups,
        "conflicting_pixel_groups": [g for g in duplicate_groups if len(g["symbol_ids"]) > 1],
        "training_blockers": dict(Counter(b for s in samples for b in s["training_blockers"])),
        "super_labels": 0,
        "trainable": False,
    }


def build_bundle(store: SymbolLabelStore) -> tuple[dict[str, Any], dict[str, bytes]]:
    with store.locked() as (symbols, state, geometry):
        grant = store.preview_grant(symbols, state, geometry)
        if grant is None:
            raise ValueError("SYMBOL_PREPARATION_REFERENCE_REQUIRED")
        selected = latest_fresh_decisions(symbols, grant.version_id)
        game_ids = {d["binding"]["game_id"] for d in selected}
        if len(game_ids) != 1:
            raise ValueError("SYMBOL_PREPARATION_GAME_CONFLICT")
        game_id = next(iter(game_ids))
        dictionary = next(d for d in store.dictionaries(symbols, game_id) if d.active)
        components = build_components(store.catalog, state)
        component_ids = {sid: key for key, ids in components.items() for sid in ids}
        samples: list[dict[str, Any]] = []
        files = {"symbols-state.json": canonical({"payload": symbols, "sha256": digest(symbols)})}
        for decision in selected:
            b = decision["binding"]
            sid = b["source_id"]
            # A labels-only grant is not a training grant. Check before reading crop bytes.
            reason = grant.reason(state, store.catalog, sid)
            if reason or store.catalog.sources[sid].role != "data":
                raise ValueError(reason or "SYMBOL_ROLE_EXCLUDED")
            row = store.local_row(decision, symbols, state, grant)
            if not row.label_valid:
                raise ValueError("SYMBOL_PREPARATION_LABEL_INVALID:" + ",".join(row.reasons))
            files[f"crops/{b['byte_sha256']}.png"] = read_crop(store.root, b)
            family = state.families.get(sid)
            samples.append(
                {
                    "decision": decision,
                    "component_id": component_ids[sid],
                    "family_id": family.family_id if family else "unresolved",
                    "training_blockers": row.training_blockers,
                }
            )
        source_ids = {s["decision"]["binding"]["source_id"] for s in samples}
        component_keys = {component_ids[sid] for sid in source_ids}
        members = sorted({sid for key in component_keys for sid in components[key]})
        evidence = [
            {
                "source": store.catalog.sources[sid].model_dump(mode="json"),
                "family": state.families[sid].model_dump(mode="json")
                if sid in state.families
                else None,
                "component_id": component_ids[sid],
                "selected": sid in source_ids,
            }
            for sid in members
        ]
        payload = {
            "format": FORMAT,
            "purpose": "qualification_only",
            "trainable": False,
            "dataset_version_id": grant.version_id,
            "snapshot_manifest_id": store.snapshot.id,
            "snapshot_manifest_digest": store.snapshot.manifest_digest,
            "game_id": game_id,
            "dictionary": dictionary.model_dump(mode="json"),
            "symbols_revision": symbols["revision"],
            "symbols_payload_sha256": digest(symbols),
            "geometry_payload_sha256": digest(geometry),
            "geometry_revision": state.revision,
            "geometry_split_stale": state.split_stale,
            "geometry_split_fingerprint": state.split.fingerprint if state.split else None,
            "protected_source_ids": sorted(grant.protected),
            "sources": evidence,
            "samples": samples,
            "report": summarize(samples, dictionary.model_dump(mode="json")),
            "files": {
                name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())
            },
        }
        if (
            len(canonical(payload)) > MAX_METADATA_BYTES
            or len(files["symbols-state.json"]) > MAX_METADATA_BYTES
        ):
            raise ValueError("SYMBOL_PREPARATION_TOO_LARGE")
        return payload, files


def check_destination(output: Path, store: SymbolLabelStore) -> None:
    if not output.is_absolute():
        raise ValueError("SYMBOL_PREPARATION_ABSOLUTE_PATH_REQUIRED")
    reject_links(output)
    protected = [store.root, store.annotations.root, store.catalog.root, *store.protected]
    if store.dataset_version is not None:
        protected.append(store.dataset_version)
    for root in protected:
        if root is None:
            continue
        if output.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(
            output.resolve()
        ):
            raise ValueError("SYMBOL_PREPARATION_DIRECTORY_OVERLAP")


def publish_bundle(output: Path, payload: dict[str, Any], files: dict[str, bytes]) -> Path:
    reject_links(output)
    target = output / digest(payload)
    output.mkdir(parents=True, exist_ok=True)
    with exclusive_bounded(output):
        if target.exists():
            if verify_bundle(target) != payload:
                raise ValueError("SYMBOL_PREPARATION_CONFLICT")
            return target
        # A failed preparation leaves only unpublished evidence; never expose partial final data.
        temporary = Path(tempfile.mkdtemp(prefix=".prepare-", dir=output))
        for name, data in files.items():
            if hashlib.sha256(data).hexdigest() != payload["files"][name]:
                raise ValueError("SYMBOL_PREPARATION_FILE_INTEGRITY_ERROR")
            publish_file(safe_file(temporary, name), data)
        publish_file(
            temporary / "manifest.json", canonical({"payload": payload, "sha256": digest(payload)})
        )
        verify_bundle(temporary, expected_id=target.name)
        os.rename(temporary, target)
        return target


def verify_bundle(root: Path, *, expected_id: str | None = None) -> dict[str, Any]:
    reject_links(root)
    payload = read_checked(safe_file(root, "manifest.json"))
    if (
        digest(payload) != (expected_id or root.name)
        or payload.get("format") != FORMAT
        or payload.get("purpose") != "qualification_only"
        or payload.get("trainable") is not False
        or "assignments" in payload
    ):
        raise ValueError("SYMBOL_PREPARATION_INTEGRITY_ERROR")
    for sample in payload["samples"]:
        if sample["decision"]["binding"]["source_id"] in payload["protected_source_ids"]:
            raise ValueError("HOLDOUT_NOT_RELEASED")
    inventory = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if inventory != {"manifest.json", *payload["files"]}:
        raise ValueError("SYMBOL_PREPARATION_INVENTORY_MISMATCH")
    for name, checksum in payload["files"].items():
        path = safe_file(root, name)
        limit = MAX_CROP_BYTES if name.startswith("crops/") else MAX_METADATA_BYTES
        if path.stat().st_size > limit or sha(path) != checksum:
            raise ValueError("SYMBOL_PREPARATION_FILE_INTEGRITY_ERROR")
    symbols = read_checked(safe_file(root, "symbols-state.json"))
    if digest(symbols) != payload["symbols_payload_sha256"]:
        raise ValueError("SYMBOL_PREPARATION_LINEAGE_MISMATCH")
    decisions = latest_fresh_decisions(symbols, payload["dataset_version_id"])
    if decisions != [s["decision"] for s in payload["samples"]]:
        raise ValueError("SYMBOL_PREPARATION_LINEAGE_MISMATCH")
    for sample in payload["samples"]:
        read_crop(root, sample["decision"]["binding"])
    if summarize(payload["samples"], payload["dictionary"]) != payload["report"]:
        raise ValueError("SYMBOL_PREPARATION_REPORT_MISMATCH")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    prepare = subparsers.add_parser("prepare")
    for name in ("snapshot", "annotations", "symbols", "dataset-version", "output"):
        prepare.add_argument("--" + name, type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "verify":
        if not args.bundle.is_absolute():
            parser.error("bundle must be an absolute path")
        payload = verify_bundle(args.bundle)
        target = args.bundle
    else:
        if not all(
            getattr(args, name).is_absolute()
            for name in ("snapshot", "annotations", "symbols", "dataset_version", "output")
        ):
            parser.error("all paths must be absolute")
        store = SymbolLabelStore(
            args.symbols,
            AnnotationStore(args.annotations, Catalog(args.snapshot)),
            dataset_version=args.dataset_version,
        )
        check_destination(args.output, store)
        payload, files = build_bundle(store)
        target = publish_bundle(args.output, payload, files)
    print(
        json.dumps(
            {"bundle_id": digest(payload), "path": str(target), "report": payload["report"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
