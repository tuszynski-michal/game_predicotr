"""Scoped recording declarations preserve whole components and immutable live inputs."""

import json
import os
import subprocess
import sys
from copy import deepcopy

import pytest
from game_predictor_worker.vision_lab.symbol_contracts import LabelDecide, LabQueueRequest
from game_predictor_worker.vision_lab.symbol_dataset_version import (
    prepare_reference,
    publish_reference,
)
from game_predictor_worker.vision_lab.symbol_preparation import build_bundle, publish_bundle
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from game_predictor_worker.vision_lab.symbol_training_manifest import (
    QualificationRequest,
    SymbolTrainingAdapter,
    assignments_for,
    freeze,
    merged_components,
    sample_counts,
)
from test_vision_lab_annotations import approve_full_photo
from test_vision_lab_geometry_cohort import family
from test_vision_lab_symbol_labels import dictionary
from test_vision_lab_whole_game_split import pilot_store


def declared(ids):
    return QualificationRequest(
        accepted=True,
        independent_recordings=True,
        reference="operator confirms separate recordings",
        families=[
            {"family_id": sid, "partition": part, "recording_reference": sid}
            for sid, part in zip(ids, ("development", "validation"), strict=True)
        ],
    )


def prepared(tmp_path):
    geometry, split = pilot_store(tmp_path)
    sources = sorted(
        (s for s in geometry.catalog.sources.values() if s.game_name == "ordinary"),
        key=lambda s: s.id,
    )
    for source in sources:
        family(geometry, [source.id], provenance="unresolved")
        approve_full_photo(geometry, source.id)
    split.geometry_source_ids = sorted(set(split.geometry_source_ids + [s.id for s in sources]))
    split.expected_revision = geometry.read().revision
    geometry.mutate(split)
    store = SymbolLabelStore(tmp_path / "symbols", geometry)
    dictionary(store, sources[0])
    reference = prepare_reference(
        store,
        [s.id for s in sources],
        {"accepted": True, "reference": "fresh labeling consent"},
        {},
    )
    root = publish_reference(tmp_path / "versions", reference, store)
    store = SymbolLabelStore(store.root, geometry, dataset_version=root)
    queue = store.preview(LabQueueRequest(kind="lab_queue", game_id=sources[0].game_id))
    version = store.dictionary(sources[0].game_id, 1)
    for source in sources:
        item = next(item for item in queue.items if item.binding.source_id == source.id)
        store.mutate(
            LabelDecide(
                op="label_decide",
                request_id="label-" + source.id,
                expected_revision=store.load()["revision"],
                binding=item.binding,
                dictionary_version=1,
                dictionary_digest=version.digest,
                action="approve",
                symbol_id="a",
            )
        )
    payload, files = build_bundle(store)
    bundle = publish_bundle(tmp_path / "preparation", payload, files)
    return store, bundle, declared([s.id for s in sources])


def test_freeze_restart_replay_and_originals_unchanged(tmp_path):
    store, bundle, request = prepared(tmp_path)
    originals = {
        p: p.read_bytes()
        for p in (store.root / "state.json", store.annotations.root / "state.json")
    }
    path = freeze(store, bundle, request, tmp_path / "training")
    inputs = SymbolTrainingAdapter(path).validate()
    assert inputs.payload["counts"]["parts"] == {"development": 1, "validation": 1}
    assert freeze(store, bundle, request, path.parent) == path
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "game_predictor_worker.vision_lab.symbol_training_manifest",
            "verify",
            "--manifest",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
        env=os.environ.copy(),
    )
    assert path.stem in completed.stdout
    assert all(p.read_bytes() == data for p, data in originals.items())


@pytest.mark.parametrize("which", ["symbols", "geometry", "source"])
def test_live_drift_stops_adapter(tmp_path, which):
    store, bundle, request = prepared(tmp_path)
    path = freeze(store, bundle, request, tmp_path / "training")
    target = {
        "symbols": store.root / "state.json",
        "geometry": store.annotations.root / "state.json",
        "source": next(iter(store.catalog.paths.values())),
    }[which]
    # The adapter is also bound to selected source pixels, not just JSON revisions.
    if which == "source":
        inputs = SymbolTrainingAdapter(path).validate()
        target = next(
            p
            for p in map(__import__("pathlib").Path, inputs.payload["live_bindings"])
            if p.suffix == ".img"
        )
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SYMBOL_TRAINING_INPUT_DRIFT"):
        SymbolTrainingAdapter(path).validate()


def evidence():
    return [
        {
            "component_id": sid,
            "source": {"id": sid, "game_id": "g", "role": "data"},
            "family": {"family_id": sid},
            "selected": True,
        }
        for sid in ("a", "b")
    ]


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("family", "FAMILY_CONFLICT"),
        ("role", "ROLE_CONFLICT"),
        ("game", "ROLE_CONFLICT"),
        ("protected", "HOLDOUT_NOT_RELEASED"),
        ("alias", "FAMILY_CONFLICT"),
    ],
)
def test_component_metadata_guards(damage, reason):
    items = evidence()
    protected = []
    if damage == "family":
        items[0]["family"]["family_id"] = "other"
    elif damage in ("role", "game"):
        items[0]["source"]["role" if damage == "role" else "game_id"] = "excluded"
    elif damage == "protected":
        protected = ["a"]
    else:
        items[1]["component_id"] = "a"
    with pytest.raises(ValueError, match=reason):
        assignments_for(items, declared(["a", "b"]), "g", protected)


def test_old_and_current_edges_are_transitive():
    graph = merged_components({"old": ["a", "alias"]}, {"new": ["alias", "protected"], "b": ["b"]})
    assert graph == {"a": ["a", "alias", "protected"], "b": ["b"]}


def test_class_coverage_cross_part_pixels_and_conflict():
    prep = {
        "dictionary": {"entries": [{"id": "x", "display_name": "X"}]},
        "samples": [
            {"decision": {"symbol_id": "x", "binding": {"source_id": s, "pixel_sha256": s}}}
            for s in ("a", "b")
        ],
    }
    assert sample_counts(prep, {"a": "development", "b": "validation"})["parts"] == {
        "development": 1,
        "validation": 1,
    }
    duplicate = deepcopy(prep)
    duplicate["samples"][1]["decision"]["binding"]["pixel_sha256"] = "a"
    with pytest.raises(ValueError, match="CROSS_PARTITION_PIXEL_DUPLICATE"):
        sample_counts(duplicate, {"a": "development", "b": "validation"})
    prep["dictionary"]["entries"].append({"id": "missing", "display_name": "Missing"})
    with pytest.raises(ValueError, match="CLASS_COVERAGE"):
        sample_counts(prep, {"a": "development", "b": "validation"})


def test_explicit_consent_is_required():
    payload = declared(["a", "b"]).model_dump()
    payload["accepted"] = False
    with pytest.raises(ValueError):
        QualificationRequest.model_validate(payload)
    payload["accepted"] = True
    payload["independent_recordings"] = False
    with pytest.raises(ValueError):
        QualificationRequest.model_validate_json(json.dumps(payload))
