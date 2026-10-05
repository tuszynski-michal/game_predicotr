"""D-496: immutable label authorization; never replaces a split or approval."""

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .annotation_contracts import AnnotationState
from .annotations import digest, read_checked
from .catalog import Catalog
from .photo_review import photo_accepted
from .snapshot import canonical, reject_links, safe_file
from .splits import build_components

if TYPE_CHECKING:
    from .symbol_store import SymbolLabelStore

FORMAT = "lab-symbol-label-reference-v1"
SPLIT_KEYS = {
    "purpose",
    "policy_version",
    "revision",
    "unseen_game_id",
    "seed",
    "game_partitions",
    "geometry_source_ids",
    "assignments",
    "measurement",
    "exclusions",
    "annotation_fingerprints",
    "geometry_target_fingerprints",
    "geometry_qualification_fingerprints",
    "leakage_components",
    "leakage_component_fingerprints",
}


def catalog_fingerprint(catalog: Catalog) -> str:
    return digest([s.model_dump() for _, s in sorted(catalog.sources.items())])


def protected_sources(catalog: Catalog, state: AnnotationState) -> set[str]:
    """Preserve original roles and the transitive union of old/current leakage links."""
    split = state.split
    if (
        split is None
        or split.policy_version != "lab-geometry-whole-game-pilot-v1"
        or split.purpose != "geometry"
        or digest([state.snapshot_id, split.model_dump(include=SPLIT_KEYS)]) != split.fingerprint
    ):
        raise ValueError("SYMBOL_DATASET_SPLIT_INTEGRITY_ERROR")
    roles = split.game_partitions or {}
    counts: Counter[str] = Counter(roles.values())
    if (
        set(roles) != {s.game_id for s in catalog.sources.values()}
        or counts["development"] < 1
        or any(counts[r] != 1 for r in ("validation", "final_test", "unseen_game"))
        or set(roles.values()) - {"development", "validation", "final_test", "unseen_game"}
        or roles.get(split.unseen_game_id) != "unseen_game"
        or any(
            s not in catalog.sources or p != roles[catalog.sources[s].game_id]
            for s, p in split.assignments.items()
        )
    ):
        raise ValueError("SYMBOL_DATASET_SPLIT_INTEGRITY_ERROR")
    parent = {sid: sid for sid in catalog.sources}

    def find(sid: str) -> str:
        while parent[sid] != sid:
            parent[sid] = parent[parent[sid]]
            sid = parent[sid]
        return sid

    for components in (split.leakage_components or {}, build_components(catalog, state)):
        for members in components.values():
            if not members or any(sid not in parent for sid in members):
                raise ValueError("SYMBOL_DATASET_SPLIT_INTEGRITY_ERROR")
            for sid in members[1:]:
                parent[find(sid)] = find(members[0])
    forbidden = {
        find(sid)
        for sid, source in catalog.sources.items()
        if roles[source.game_id] in {"final_test", "unseen_game"}
        or split.assignments.get(sid) in {"final_test", "unseen_game"}
    }
    return {sid for sid in parent if find(sid) in forbidden}


@dataclass(frozen=True)
class LabelPreviewGrant:
    """Request-local capability, bound to the locked geometry and catalog instances."""

    version_id: str
    state: AnnotationState
    catalog: Catalog
    sources: frozenset[str]
    protected: frozenset[str]

    def reason(self, state: AnnotationState, catalog: Catalog, source_id: str) -> str | None:
        if state is not self.state or catalog is not self.catalog:
            raise ValueError("SYMBOL_DATASET_VERSION_STALE")
        if source_id in self.protected:
            return "HOLDOUT_NOT_RELEASED"
        if source_id not in self.sources:
            return "SYMBOL_DATASET_SOURCE_EXCLUDED"
        return None


def prepare_reference(
    store: "SymbolLabelStore",
    source_ids: list[str],
    authorization: dict[str, Any],
    historical_usage: dict[str, Any],
) -> dict[str, Any]:
    """Read-only preview, including verbatim consent history and source byte verification."""
    if not source_ids or len(set(source_ids)) != len(source_ids):
        raise ValueError("SYMBOL_DATASET_SOURCES_INVALID")
    if authorization.get("accepted") is not True or not authorization.get("reference"):
        raise ValueError("SYMBOL_DATASET_AUTHORIZATION_REQUIRED")
    with store.locked() as (symbols, state, geometry):
        blocked = protected_sources(store.catalog, state)
        games = {store.catalog.sources[sid].game_id for sid in source_ids}
        if len(games) != 1:
            raise ValueError("SYMBOL_DATASET_GAME_CONFLICT")
        game_id = next(iter(games))
        dictionary = next((d for d in store.dictionaries(symbols, game_id) if d.active), None)
        if dictionary is None or not dictionary.entries:
            raise ValueError("SYMBOL_DICTIONARY_NOT_APPROVED")
        boards = 0
        cells = 0
        for sid in sorted(source_ids):
            source = store.catalog.sources[sid]
            if sid in blocked:
                raise ValueError("HOLDOUT_NOT_RELEASED")
            if source.role == "comparison_only":
                raise ValueError("SYMBOL_ROLE_EXCLUDED")
            if not photo_accepted(state, source):
                raise ValueError("SYMBOL_GEOMETRY_STALE")
            targets = [
                a
                for a in state.annotations.values()
                if a.source_id == sid and a.presence == "present"
            ]
            if not targets or any(
                not a.full_approved
                or a.source_sha256 != source.sha256
                or not a.nodes
                or any(n.provenance != "human" for n in a.nodes)
                for a in targets
            ):
                raise ValueError("SYMBOL_GEOMETRY_STALE")
            path = store.catalog.paths[source.asset_id]
            reject_links(path)
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != source.sha256:
                    raise ValueError("SYMBOL_SOURCE_INTEGRITY_ERROR")
            boards += len(targets)
            cells += sum(a.topology.rows * a.topology.columns for a in targets)
        if cells > 10000:
            raise ValueError("STORE_LIMIT_REACHED")
        return {
            "format": FORMAT,
            "snapshot_id": store.annotations.snapshot_id,
            "snapshot_manifest_id": store.snapshot.id,
            "snapshot_manifest_digest": store.snapshot.manifest_digest,
            "catalog_fingerprint": catalog_fingerprint(store.catalog),
            "game_id": game_id,
            "source_ids": sorted(source_ids),
            "source_sha256": {sid: store.catalog.sources[sid].sha256 for sid in sorted(source_ids)},
            "counts": {"photos": len(source_ids), "boards": boards, "cells": cells},
            "dictionary": dictionary.model_dump(),
            "protected_source_ids": sorted(blocked),
            "lineage": {
                "geometry_sha256": digest(geometry),
                "geometry_payload": geometry,
                "symbols_sha256": digest(symbols),
                "symbols_payload": symbols,
            },
            "authorization": authorization,
            "historical_usage": historical_usage,
            "purpose": "labels_only",
            "trainable": False,
        }


def publish_reference(root: Path, payload: dict[str, Any], store: "SymbolLabelStore") -> Path:
    """One atomic create-only file; an interrupted/repeated publication has the same ID."""
    from .symbol_store import publish_file

    reject_links(root)
    for other in (store.root, store.annotations.root, store.catalog.root, *store.protected):
        if other is None:
            continue
        a, b = root.resolve(), other.resolve()
        if a.is_relative_to(b) or b.is_relative_to(a):
            raise ValueError("SYMBOL_DIRECTORY_OVERLAP")
    version_id = digest(payload)
    # Validate against live inputs again, under the same locks used by label writes.
    with store.locked() as (symbols, state, geometry):
        validate_inputs(payload, store, symbols, state, geometry)
        target = root / version_id
        data = canonical({"payload": payload, "sha256": version_id})
        if len(data) > 64 * 1024 * 1024:
            raise ValueError("SYMBOL_DATASET_TOO_LARGE")
        publish_file(target / "manifest.json", data)
    return target


def load_reference(root: Path) -> dict[str, Any]:
    payload = read_checked(safe_file(root, "manifest.json"))
    if (
        digest(payload) != root.name
        or payload.get("format") != FORMAT
        or payload.get("purpose") != "labels_only"
        or payload.get("trainable") is not False
        or digest(payload["lineage"]["geometry_payload"]) != payload["lineage"]["geometry_sha256"]
        or digest(payload["lineage"]["symbols_payload"]) != payload["lineage"]["symbols_sha256"]
    ):
        raise ValueError("SYMBOL_DATASET_INTEGRITY_ERROR")
    return payload


def validate_inputs(
    reference: dict[str, Any],
    store: "SymbolLabelStore",
    symbols: dict[str, Any],
    state: AnnotationState,
    geometry: dict[str, Any],
) -> LabelPreviewGrant:
    dictionary = next(
        (d for d in store.dictionaries(symbols, reference["game_id"]) if d.active), None
    )
    if (
        reference["snapshot_id"] != store.annotations.snapshot_id
        or reference["snapshot_manifest_id"] != store.snapshot.id
        or reference["snapshot_manifest_digest"] != store.snapshot.manifest_digest
        or reference["catalog_fingerprint"] != catalog_fingerprint(store.catalog)
        or reference["lineage"]["geometry_sha256"] != digest(geometry)
        or dictionary is None
        or dictionary.model_dump() != reference["dictionary"]
    ):
        raise ValueError("SYMBOL_DATASET_VERSION_STALE")
    blocked = protected_sources(store.catalog, state)
    if sorted(blocked) != reference["protected_source_ids"]:
        raise ValueError("SYMBOL_DATASET_VERSION_STALE")
    return LabelPreviewGrant(
        digest(reference),
        state,
        store.catalog,
        frozenset(reference["source_ids"]),
        frozenset(blocked),
    )


def main() -> None:
    from .annotations import AnnotationStore
    from .symbol_store import SymbolLabelStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--symbols", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    store = SymbolLabelStore(
        args.symbols, AnnotationStore(args.annotations, Catalog(args.snapshot))
    )
    payload = prepare_reference(
        store, request["source_ids"], request["authorization"], request["historical_usage"]
    )
    result = {
        "version_id": digest(payload),
        "counts": payload["counts"],
        "protected_sources": len(payload["protected_source_ids"]),
        "dictionary": payload["dictionary"],
        "geometry_sha256": payload["lineage"]["geometry_sha256"],
        "applied": args.apply,
    }
    if args.apply:
        result["path"] = str(publish_reference(args.output, payload, store))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
