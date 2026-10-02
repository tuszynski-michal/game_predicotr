"""Validate frozen provenance, then expose only development and validation inputs."""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from .annotations import AnnotationStore, digest, read_checked
from .catalog import Catalog
from .run_contracts import StartRunRequest
from .snapshot import safe_file


@dataclass(frozen=True)
class TrainingTarget:
    source_id: str
    board_index: int
    revision: int
    nodes: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class TrainingInputs:
    manifest_id: str
    split_fingerprint: str
    development: tuple[TrainingTarget, ...]
    validation: tuple[TrainingTarget, ...]
    _catalog: Catalog

    def image(self, target: TrainingTarget) -> NDArray[np.uint8]:
        if target not in (*self.development, *self.validation):
            raise ValueError("RUN_TARGET_NOT_ALLOWED")
        return np.asarray(self._catalog.image(self._catalog.sources[target.source_id]))


class ManifestAdapter:
    def __init__(self, manifest_root: Path, catalog: Catalog, annotation_root: Path) -> None:
        self.manifest_root = manifest_root
        self.catalog = catalog
        self.annotation_root = annotation_root

    def __call__(self, request: StartRunRequest) -> TrainingInputs:
        path = safe_file(self.manifest_root, f"{request.manifest_id}.json")
        if not path.is_file():
            raise KeyError("MANIFEST_NOT_FOUND")
        payload = read_checked(path)
        if digest(payload) != request.manifest_id:
            raise ValueError("RUN_MANIFEST_CHECKSUM_MISMATCH")
        if payload.get("status") != "frozen" or not payload.get("split_fingerprint"):
            raise ValueError("RUN_MANIFEST_NOT_FROZEN")
        state = AnnotationStore(self.annotation_root, self.catalog).read()
        split = state.split
        if split is None or state.split_stale:
            raise ValueError("RUN_DATA_DRIFT")
        if self.catalog.root is None:
            raise ValueError("RUN_SNAPSHOT_REQUIRED")
        snapshot = json.loads(safe_file(self.catalog.root, "manifest.json").read_bytes())
        identity = {"format": snapshot.get("format"), "entries": snapshot.get("entries")}
        if snapshot.get("format") == "vision-lab-folder-v1" and digest(identity) != snapshot.get(
            "snapshotId"
        ):
            raise ValueError("RUN_SNAPSHOT_INTEGRITY_ERROR")
        if (
            payload.get("format") != "vision-lab-whole-game-pilot-manifest-v1"
            or payload.get("decision_reference") != "D-456"
            or payload.get("policy") != "lab-geometry-whole-game-pilot-v1"
            or split.policy_version != payload["policy"]
            or payload.get("snapshot_id") != state.snapshot_id
            or payload.get("snapshot_manifest_id") != snapshot["snapshotId"]
            or payload["split_fingerprint"] != split.fingerprint
            or payload.get("game_partitions") != split.game_partitions
            or payload.get("source_cohort") != split.geometry_source_ids
            or payload.get("seed") != split.seed
            or payload.get("measurement") != {}
            or request.topology.columns != 5
        ):
            raise ValueError("RUN_MANIFEST_BINDING_MISMATCH")
        expected = []
        for key, fingerprint in sorted(split.geometry_target_fingerprints.items()):
            annotation = state.annotations.get(key)
            if annotation is None or digest(annotation.model_dump()) != fingerprint:
                raise ValueError("RUN_DATA_DRIFT")
            source = self.catalog.sources[annotation.source_id]
            image_path = self.catalog.paths[source.asset_id]
            relative = image_path.relative_to(self.catalog.root).as_posix()
            safe_file(self.catalog.root, relative)
            expected.append(
                {
                    "source_id": source.id,
                    "source_sha256": source.sha256,
                    "source_relative_path": source.filename,
                    "snapshot_image_relative_path": relative,
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
        targets = payload.get("targets")
        if not isinstance(targets, list) or len(targets) != len(expected):
            raise ValueError("RUN_MANIFEST_TARGET_MISMATCH")
        # Canonical dictionaries validate every field without trusting claimed target checksums.
        if sorted(digest(item) for item in targets) != sorted(digest(item) for item in expected):
            raise ValueError("RUN_MANIFEST_TARGET_MISMATCH")
        if payload.get("target_partition_counts") != dict(
            Counter(item["partition"] for item in expected)
        ):
            raise ValueError("RUN_MANIFEST_TARGET_MISMATCH")
        # Check registered training bytes without decoding holdouts or trusting manifest paths.
        from .snapshot import sha

        for source_id, partition in split.assignments.items():
            if partition in {"development", "validation"}:
                source = self.catalog.sources[source_id]
                if (
                    sha(
                        safe_file(
                            self.catalog.root,
                            self.catalog.paths[source.asset_id]
                            .relative_to(self.catalog.root)
                            .as_posix(),
                        )
                    )
                    != source.sha256
                ):
                    raise ValueError("RUN_DATA_DRIFT")
        selected: dict[str, list[TrainingTarget]] = {"development": [], "validation": []}
        for key in sorted(split.geometry_target_fingerprints):
            annotation = state.annotations[key]
            partition = split.assignments[annotation.source_id]
            if partition in selected:
                selected[partition].append(
                    TrainingTarget(
                        annotation.source_id,
                        annotation.board_index,
                        annotation.revision,
                        tuple((node.x, node.y) for node in annotation.nodes),
                    )
                )
        if not all(selected.values()):
            raise ValueError("RUN_TRAINING_SPLIT_EMPTY")
        return TrainingInputs(
            request.manifest_id,
            split.fingerprint,
            tuple(selected["development"]),
            tuple(selected["validation"]),
            self.catalog,
        )
