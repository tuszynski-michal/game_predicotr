"""Frozen metadata verification never supplies holdout images to the training adapter."""

import copy
import json
from collections import Counter

import pytest
from game_predictor_worker.vision_lab.annotations import digest, write_atomic
from game_predictor_worker.vision_lab.run_contracts import StartRunRequest
from game_predictor_worker.vision_lab.training_manifest import ManifestAdapter, TrainingTarget
from test_vision_lab_whole_game_split import pilot_store


def manifest_case(tmp_path):
    store, split_request = pilot_store(tmp_path)
    state = store.mutate(split_request)
    split = state.split
    catalog = store.catalog
    targets = []
    for key in split.geometry_target_fingerprints:
        annotation = state.annotations[key]
        source = catalog.sources[annotation.source_id]
        targets.append(
            {
                "source_id": source.id,
                "source_sha256": source.sha256,
                "source_relative_path": source.filename,
                "snapshot_image_relative_path": catalog.paths[source.asset_id]
                .relative_to(catalog.root)
                .as_posix(),
                "game_id": source.game_id,
                "game_name": source.game_name,
                "partition": split.assignments[source.id],
                "board_index": annotation.board_index,
                "revision": annotation.revision,
                "topology": annotation.topology.model_dump(),
                "nodes": [node.model_dump() for node in annotation.nodes],
                "geometry_sha256": annotation.geometry_sha256,
            }
        )
    payload = {
        "format": "vision-lab-whole-game-pilot-manifest-v1",
        "status": "frozen",
        "decision_reference": "D-456",
        "policy": split.policy_version,
        "snapshot_id": state.snapshot_id,
        "snapshot_manifest_id": json.loads((catalog.root / "manifest.json").read_bytes())[
            "snapshotId"
        ],
        "split_fingerprint": split.fingerprint,
        "game_partitions": split.game_partitions,
        "source_cohort": split.geometry_source_ids,
        "seed": split.seed,
        "targets": targets,
        "target_partition_counts": dict(Counter(t["partition"] for t in targets)),
        "measurement": {},
    }
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    manifest_id = digest(payload)
    write_atomic(manifests / f"{manifest_id}.json", payload)
    request = StartRunRequest(
        request_id="start-test",
        manifest_id=manifest_id,
        model_version="test",
        preprocessing_version="rgb-v1",
        seed=17,
        purpose="smoke",
        configuration={"max_steps": 5, "epochs": 1},
    )
    return store, manifests, payload, request


def test_manifest_complete_and_holdouts_never_loaded(tmp_path, monkeypatch):
    store, manifests, payload, request = manifest_case(tmp_path)
    inputs = ManifestAdapter(manifests, store.catalog, store.root)(request)
    calls = []
    original = store.catalog.image

    def image(source):
        calls.append(source.id)
        return original(source)

    monkeypatch.setattr(store.catalog, "image", image)
    for target in (*inputs.development, *inputs.validation):
        inputs.image(target)
    assert len(calls) == 3
    assert all(
        store.read().split.assignments[source] in {"development", "validation"} for source in calls
    )
    holdout = next(target for target in payload["targets"] if target["partition"] == "final_test")
    with pytest.raises(ValueError, match="NOT_ALLOWED"):
        inputs.image(TrainingTarget(holdout["source_id"], 0, 1, ()))


@pytest.mark.parametrize(
    "mutation", ["proposal", "missing", "duplicate", "node", "path", "snapshot", "partition"]
)
def test_manifest_tamper_even_with_recomputed_envelope_fails(tmp_path, mutation):
    store, manifests, original, request = manifest_case(tmp_path)
    payload = copy.deepcopy(original)
    if mutation == "proposal":
        payload["status"] = "proposal"
    if mutation == "missing":
        payload["targets"].pop()
    if mutation == "duplicate":
        payload["targets"][0] = payload["targets"][1]
    if mutation == "node":
        payload["targets"][0]["nodes"][0]["x"] += 1
    if mutation == "path":
        payload["targets"][0]["snapshot_image_relative_path"] = "../secret"
    if mutation == "snapshot":
        payload["snapshot_id"] = payload["snapshot_manifest_id"]
    if mutation == "partition":
        payload["targets"][0]["partition"] = "development"
    if payload == original:
        payload["targets"][0]["partition"] = "final_test"
    manifest_id = digest(payload)
    write_atomic(manifests / f"{manifest_id}.json", payload)
    with pytest.raises(ValueError, match="RUN_MANIFEST"):
        ManifestAdapter(manifests, store.catalog, store.root)(
            request.model_copy(update={"manifest_id": manifest_id})
        )
