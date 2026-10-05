"""D-498: scoped symbol qualification without changing geometry or label stores."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .annotations import AnnotationStore, digest, read_checked
from .catalog import Catalog
from .snapshot import canonical, reject_links, sha
from .splits import build_components
from .symbol_preparation import build_bundle, check_destination, verify_bundle
from .symbol_store import SymbolLabelStore, publish_file

FORMAT = "lab-symbol-training-manifest-v1"


class FamilyDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family_id: str = Field(min_length=1)
    partition: Literal["development", "validation"]
    recording_reference: str = Field(min_length=1)


class QualificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: Literal[True]
    reference: str = Field(min_length=1)
    independent_recordings: Literal[True]
    families: list[FamilyDeclaration] = Field(min_length=2)


def merged_components(*graphs: dict[str, list[str]]) -> dict[str, list[str]]:
    """Union old and current links, retaining every alias, including unselected sources."""
    parent = {sid: sid for graph in graphs for ids in graph.values() for sid in ids}

    def find(sid: str) -> str:
        while parent[sid] != sid:
            parent[sid] = parent[parent[sid]]
            sid = parent[sid]
        return sid

    for graph in graphs:
        for ids in graph.values():
            if not ids:
                raise ValueError("SYMBOL_COMPONENT_EMPTY")
            for sid in ids[1:]:
                parent[find(sid)] = find(ids[0])
    result: dict[str, list[str]] = defaultdict(list)
    for sid in sorted(parent):
        result[find(sid)].append(sid)
    return {min(ids): ids for ids in result.values()}


def assignments_for(
    evidence: list[dict[str, Any]],
    request: QualificationRequest,
    game_id: str,
    protected: list[str],
) -> dict[str, str]:
    declarations = {d.family_id: d for d in request.families}
    if len(declarations) != len(request.families):
        raise ValueError("SYMBOL_FAMILY_DECLARATION_DUPLICATE")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence:
        groups[item["component_id"]].append(item)
    assignments: dict[str, str] = {}
    used = set()
    for members in groups.values():
        family_ids = {m["family"]["family_id"] for m in members if m["family"]}
        if len(family_ids) != 1 or not family_ids.issubset(declarations):
            raise ValueError("SYMBOL_COMPONENT_FAMILY_CONFLICT")
        family_id = next(iter(family_ids))
        used.add(family_id)
        part = declarations[family_id].partition
        for item in members:
            source = item["source"]
            if source["id"] in protected:
                raise ValueError("HOLDOUT_NOT_RELEASED")
            if source["role"] != "data" or source["game_id"] != game_id:
                raise ValueError("SYMBOL_COMPONENT_ROLE_CONFLICT")
            if source["id"] in assignments:
                raise ValueError("SYMBOL_COMPONENT_SOURCE_DUPLICATE")
            assignments[source["id"]] = part
    if used != set(declarations) or set(assignments.values()) != {"development", "validation"}:
        raise ValueError("SYMBOL_DECLARATIONS_NOT_COVERED")
    return assignments


def sample_counts(preparation: dict[str, Any], assignments: dict[str, str]) -> dict[str, Any]:
    classes = preparation["dictionary"]["entries"]
    counts: Counter[tuple[str, str]] = Counter()
    pixels: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for sample in preparation["samples"]:
        decision = sample["decision"]
        part = assignments[decision["binding"]["source_id"]]
        symbol = decision["symbol_id"]
        counts[(part, symbol)] += 1
        pixels[decision["binding"]["pixel_sha256"]].append((part, symbol))
    if any(len({p for p, _ in rows}) > 1 for rows in pixels.values()):
        raise ValueError("SYMBOL_CROSS_PARTITION_PIXEL_DUPLICATE")
    if any(len({s for _, s in rows}) > 1 for rows in pixels.values()):
        raise ValueError("SYMBOL_PIXEL_CLASS_CONFLICT")
    if {s for _, s in counts} != {c["id"] for c in classes} or any(
        not counts[(part, c["id"])] for part in ("development", "validation") for c in classes
    ):
        raise ValueError("SYMBOL_PARTITION_CLASS_COVERAGE_REQUIRED")
    return {
        "parts": {
            p: sum(n for (part, _), n in counts.items() if part == p)
            for p in ("development", "validation")
        },
        "classes": [
            {
                "id": c["id"],
                "name": c["display_name"],
                **{p: counts[(p, c["id"])] for p in ("development", "validation")},
            }
            for c in classes
        ],
        "final_test": False,
        "super_labels": 0,
    }


def freeze(
    store: SymbolLabelStore, bundle: Path, request: QualificationRequest, output: Path
) -> Path:
    check_destination(output, store)
    if store.dataset_version is None or store.catalog.root is None:
        raise ValueError("SYMBOL_REFERENCE_REQUIRED")
    preparation = read_checked(bundle / "manifest.json")
    if preparation["format"] != "lab-symbol-preparation-v1":
        raise ValueError("SYMBOL_PREPARATION_REQUIRED")
    selected = {s["decision"]["binding"]["source_id"] for s in preparation["samples"]}
    # Metadata guards run before any selected image or crop is decoded.
    with store.locked() as (symbols, state, geometry):
        grant = store.preview_grant(symbols, state, geometry)
        if grant is None or preparation["dataset_version_id"] != grant.version_id:
            raise ValueError("SYMBOL_REFERENCE_REQUIRED")
        if (
            digest(geometry) != preparation["geometry_payload_sha256"]
            or digest(symbols) != preparation["symbols_payload_sha256"]
        ):
            raise ValueError("SYMBOL_TRAINING_INPUT_DRIFT")
        if state.split is None:
            raise ValueError("SYMBOL_REFERENCE_REQUIRED")
        graph = merged_components(
            state.split.leakage_components or {}, build_components(store.catalog, state)
        )
        relevant = {k: ids for k, ids in graph.items() if selected.intersection(ids)}
        evidence = [
            {
                "component_id": k,
                "source": store.catalog.sources[sid].model_dump(mode="json"),
                "family": state.families[sid].model_dump(mode="json")
                if sid in state.families
                else None,
                "selected": sid in selected,
            }
            for k, ids in sorted(relevant.items())
            for sid in ids
        ]
        assignments = assignments_for(
            evidence, request, preparation["game_id"], sorted(grant.protected)
        )
        counts = sample_counts(preparation, assignments)
        for sid in selected:
            if grant.reason(state, store.catalog, sid):
                raise ValueError("SYMBOL_DATASET_SOURCE_EXCLUDED")
        photo_pixels: dict[str, list[str]] = defaultdict(list)
        live_files = [
            store.root / "state.json",
            store.annotations.root / "state.json",
            store.dataset_version / "manifest.json",
            store.catalog.root / "manifest.json",
        ]
        for sid in sorted(selected):
            source = store.catalog.sources[sid]
            image = store.catalog.image(source)
            pixel = digest([image.size, hashlib.sha256(image.tobytes()).hexdigest()])
            photo_pixels[pixel].append(sid)
            live_files.append(store.catalog.paths[source.asset_id])
        if any(len({assignments[sid] for sid in ids}) > 1 for ids in photo_pixels.values()):
            raise ValueError("SYMBOL_CROSS_PARTITION_PHOTO_DUPLICATE")
        bindings = {str(p): sha(p) for p in live_files}
    verified, _ = build_bundle(store)
    if verified != preparation or verify_bundle(bundle) != preparation:
        raise ValueError("SYMBOL_TRAINING_INPUT_DRIFT")
    payload = {
        "format": FORMAT,
        "decision": "D-498",
        "trainable": True,
        "purpose": "symbols",
        "game_id": preparation["game_id"],
        "preparation_path": str(bundle),
        "preparation_id": digest(preparation),
        "qualification": request.model_dump(mode="json"),
        "component_evidence": evidence,
        "graph": graph,
        "graph_sha256": digest(graph),
        "assignments": assignments,
        "counts": counts,
        "photo_pixel_groups": dict(sorted(photo_pixels.items())),
        "live_bindings": bindings,
        "protected_source_ids": sorted(grant.protected),
    }
    for name, checksum in bindings.items():
        if sha(Path(name)) != checksum:
            raise ValueError("SYMBOL_TRAINING_INPUT_DRIFT")
    target = output / (digest(payload) + ".json")
    publish_file(target, canonical({"payload": payload, "sha256": digest(payload)}))
    SymbolTrainingAdapter(target).validate()
    return target


@dataclass(frozen=True)
class SymbolTrainingInputs:
    manifest_id: str
    payload: dict[str, Any]
    preparation: dict[str, Any]
    bundle: Path


class SymbolTrainingAdapter:
    def __init__(self, manifest: Path):
        if not manifest.is_absolute():
            raise ValueError("SYMBOL_TRAINING_ABSOLUTE_PATH_REQUIRED")
        self.manifest = manifest

    def validate(self, request: Any = None) -> SymbolTrainingInputs:
        reject_links(self.manifest)
        payload = read_checked(self.manifest)
        manifest_id = digest(payload)
        if (
            payload.get("format") != FORMAT
            or payload.get("decision") != "D-498"
            or payload.get("purpose") != "symbols"
            or payload.get("trainable") is not True
            or self.manifest.stem != manifest_id
            or (request is not None and request.manifest_id != manifest_id)
        ):
            raise ValueError("SYMBOL_TRAINING_MANIFEST_INVALID")
        qualification = QualificationRequest.model_validate(payload["qualification"])
        if digest(payload["graph"]) != payload["graph_sha256"]:
            raise ValueError("SYMBOL_GRAPH_INTEGRITY_ERROR")
        selected = {m["source"]["id"] for m in payload["component_evidence"] if m["selected"]}
        expected_members = {
            sid: k
            for k, ids in payload["graph"].items()
            if selected.intersection(ids)
            for sid in ids
        }
        actual_members = {
            m["source"]["id"]: m["component_id"] for m in payload["component_evidence"]
        }
        if actual_members != expected_members:
            raise ValueError("SYMBOL_FULL_COMPONENT_REQUIRED")
        assignments = assignments_for(
            payload["component_evidence"],
            qualification,
            payload["game_id"],
            payload["protected_source_ids"],
        )
        if assignments != payload["assignments"]:
            raise ValueError("SYMBOL_TRAINING_ASSIGNMENTS_INVALID")
        for ids in payload["photo_pixel_groups"].values():
            if len({assignments[sid] for sid in ids}) > 1:
                raise ValueError("SYMBOL_CROSS_PARTITION_PHOTO_DUPLICATE")
        bundle = Path(payload["preparation_path"])
        if not bundle.is_absolute() or bundle.name != payload["preparation_id"]:
            raise ValueError("SYMBOL_PREPARATION_BINDING_INVALID")
        preparation = verify_bundle(bundle)
        if preparation["game_id"] != payload["game_id"] or selected != {
            s["decision"]["binding"]["source_id"] for s in preparation["samples"]
        }:
            raise ValueError("SYMBOL_PREPARATION_BINDING_INVALID")
        if sample_counts(preparation, assignments) != payload["counts"]:
            raise ValueError("SYMBOL_TRAINING_COUNTS_INVALID")
        for name, checksum in payload["live_bindings"].items():
            path = Path(name)
            if not path.is_absolute():
                raise ValueError("SYMBOL_TRAINING_ABSOLUTE_PATH_REQUIRED")
            reject_links(path)
            if sha(path) != checksum:
                raise ValueError("SYMBOL_TRAINING_INPUT_DRIFT")
        return SymbolTrainingInputs(manifest_id, payload, preparation, bundle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    freeze_parser = sub.add_parser("freeze")
    for name in ("runtime", "bundle", "qualification", "output"):
        freeze_parser.add_argument("--" + name, type=Path, required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "freeze":
        if not all(
            getattr(args, n).is_absolute() for n in ("runtime", "bundle", "qualification", "output")
        ):
            parser.error("all paths must be absolute")
        settings = json.loads(args.runtime.read_bytes())
        store = SymbolLabelStore(
            Path(settings["Symbols"]),
            AnnotationStore(Path(settings["Annotations"]), Catalog(Path(settings["Snapshot"]))),
            dataset_version=Path(settings["DatasetVersion"]),
        )
        request = QualificationRequest.model_validate_json(args.qualification.read_bytes())
        path = freeze(store, args.bundle, request, args.output)
    else:
        path = args.manifest
    inputs = SymbolTrainingAdapter(path).validate()
    print(
        json.dumps(
            {
                "manifest_id": inputs.manifest_id,
                "path": str(path),
                "counts": inputs.payload["counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
