from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from game_predictor_worker.images.shape_geometry_v2.corpus import (
    ShapeGeometryCorpusError,
    ShapeGeometryCorpusManifest,
    ShapeGeometryManualAnnotations,
)
from game_predictor_worker.images.shape_geometry_v2.experiment import (
    ShapeGeometryExperimentObservations,
    run_shape_geometry_experiment,
)


def _game(game_id: str) -> dict[str, object]:
    return {
        "gameId": game_id,
        "pageBoardRows": 3,
        "pageBoardColumns": 3,
        "cellRows": 3,
        "cellColumns": 5,
        "activeBoardSlots": list(range(9)),
        "v11Profile": None,
    }


def _source(
    game_id: str,
    source_id: str,
    relative_path: str,
    checksum: str,
    *,
    role: str,
    family: str,
) -> dict[str, object]:
    return {
        "sourceId": source_id,
        "gameId": game_id,
        "relativePath": relative_path,
        "sourceChecksumSha256": checksum,
        "split": "development",
        "corpusRole": role,
        "captureFamilyId": family,
        "sourceOrdinal": 1,
        "scenarios": ["clear_frame"],
    }


def _write(root: Path, relative_path: str, content: bytes) -> str:
    path = root / Path(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _manifest_mapping(root: Path) -> dict[str, object]:
    mummies_anchor = _write(root, "mummies/anchor.jpg", b"mummies-anchor")
    mummies_measurement = _write(root, "mummies/measurement.jpg", b"mummies-measurement")
    gang_anchor = _write(root, "gang/anchor.jpg", b"gang-anchor")
    gang_measurement = _write(root, "gang/measurement.jpg", b"gang-measurement")
    return {
        "schemaVersion": 2,
        "geometryFamily": "framed_full_page_v2",
        "visibility": "executor",
        "corpusRoot": str(root),
        "games": [_game("mummies"), _game("gang")],
        "sources": [
            _source(
                "mummies",
                "mummies-anchor",
                "mummies/anchor.jpg",
                mummies_anchor,
                role="anchor_pool",
                family="mummies-anchor-family",
            ),
            _source(
                "mummies",
                "mummies-measurement",
                "mummies/measurement.jpg",
                mummies_measurement,
                role="measurement",
                family="mummies-measurement-family",
            ),
            _source(
                "gang",
                "gang-anchor",
                "gang/anchor.jpg",
                gang_anchor,
                role="anchor_pool",
                family="gang-anchor-family",
            ),
            _source(
                "gang",
                "gang-measurement",
                "gang/measurement.jpg",
                gang_measurement,
                role="measurement",
                family="gang-measurement-family",
            ),
        ],
    }


def _annotations(manifest: ShapeGeometryCorpusManifest) -> ShapeGeometryManualAnnotations:
    return ShapeGeometryManualAnnotations.from_mapping(
        {
            "schemaVersion": 1,
            "corpusManifestFingerprint": manifest.fingerprint(),
            "annotations": [
                {
                    "sourceId": source.source_id,
                    "sourceChecksumSha256": source.source_checksum_sha256,
                    "pageState": "complete",
                    "topologyConfirmed": True,
                    "visibleGrid": True,
                    "anchorCandidate": source.corpus_role.value == "anchor_pool",
                    "activeOperatorSeconds": 7,
                }
                for source in manifest.sources
            ],
        }
    )


def _observation_mapping(
    manifest: ShapeGeometryCorpusManifest,
    inventory_fingerprint: str,
    annotations: ShapeGeometryManualAnnotations,
) -> dict[str, object]:
    observations: list[dict[str, object]] = []
    for source in manifest.sources:
        if source.corpus_role.value != "measurement":
            continue
        for variant in (
            "shape_contrast_v1",
            "shape_contrast_color_assist_v1",
            "shape_contrast_local_anchor_v1",
            "shape_contrast_shared_profile_v1",
        ):
            shared = variant == "shape_contrast_shared_profile_v1"
            other_game = "gang" if source.game_id == "mummies" else "mummies"
            observations.append(
                {
                    "gameId": source.game_id,
                    "sourceId": source.source_id,
                    "sourceChecksumSha256": source.source_checksum_sha256,
                    "variant": variant,
                    "outcome": "automatic_correct",
                    "activeOperatorSeconds": 0,
                    "profileContributorGameIds": [other_game] if shared else [],
                    "profileFingerprint": ("a" if source.game_id == "mummies" else "b") * 64
                    if shared
                    else None,
                }
            )
    return {
        "schemaVersion": 1,
        "corpusManifestFingerprint": manifest.fingerprint(),
        "inventoryFingerprint": inventory_fingerprint,
        "annotationFingerprint": annotations.fingerprint(),
        "algorithm": {
            "algorithmId": "shape_geometry_v2",
            "algorithmVersion": "g01_observation_contract",
            "parameters": {"variantSet": "four"},
        },
        "observations": observations,
    }


def _fixture(
    tmp_path: Path,
) -> tuple[
    dict[str, object],
    ShapeGeometryCorpusManifest,
    ShapeGeometryManualAnnotations,
    dict[str, object],
]:
    manifest_mapping = _manifest_mapping(tmp_path)
    manifest = ShapeGeometryCorpusManifest.from_mapping(manifest_mapping)
    annotations = _annotations(manifest)
    inventory = manifest.freeze_inventory()
    observations = _observation_mapping(manifest, inventory.fingerprint(), annotations)
    return manifest_mapping, manifest, annotations, observations


def test_schema_v2_allows_compatible_new_game_without_relaxing_v1(tmp_path: Path) -> None:
    mapping, manifest, _, _ = _fixture(tmp_path)

    assert {game.game_id for game in manifest.games} == {"gang", "mummies"}
    assert manifest.schema_version == 2

    legacy = {
        "schemaVersion": 1,
        "visibility": "executor",
        "corpusRoot": str(tmp_path),
        "games": [_game("mummies")],
        "sources": [],
    }
    with pytest.raises(ShapeGeometryCorpusError) as legacy_error:
        ShapeGeometryCorpusManifest.from_mapping(legacy)
    assert legacy_error.value.code == "SHAPE_GEOMETRY_V2_GAME_SET_INVALID"

    mapping["games"] = [_game("treasure")]
    mapping["sources"] = []
    with pytest.raises(ShapeGeometryCorpusError) as treasure_error:
        ShapeGeometryCorpusManifest.from_mapping(mapping)
    assert treasure_error.value.code == "SHAPE_GEOMETRY_V2_GAME_UNSUPPORTED"


def test_experiment_reports_complete_variant_matrix_with_transfer_isolation(
    tmp_path: Path,
) -> None:
    _, manifest, annotations, observation_mapping = _fixture(tmp_path)
    inventory = manifest.freeze_inventory()
    observations = ShapeGeometryExperimentObservations.from_mapping(observation_mapping)

    report = run_shape_geometry_experiment(manifest, inventory, annotations, observations)

    assert report["schemaVersion"] == "shape-geometry-v2-experiment-v1"
    assert {game["status"] for game in report["games"]} == {"measured"}
    for game in report["games"]:
        assert {variant["status"] for variant in game["variants"]} == {"measured"}
        shared = next(
            variant
            for variant in game["variants"]
            if variant["variant"] == "shape_contrast_shared_profile_v1"
        )
        assert game["gameId"] not in shared["profileContributorGameIds"]
        assert shared["automaticCorrectSourceCount"] == 1


def test_experiment_rejects_target_game_contribution_to_transfer_profile(
    tmp_path: Path,
) -> None:
    _, manifest, annotations, observation_mapping = _fixture(tmp_path)
    inventory = manifest.freeze_inventory()
    shared = next(
        value
        for value in observation_mapping["observations"]
        if value["variant"] == "shape_contrast_shared_profile_v1"
        and value["gameId"] == "mummies"
    )
    shared["profileContributorGameIds"] = ["mummies"]

    observations = ShapeGeometryExperimentObservations.from_mapping(observation_mapping)
    with pytest.raises(ShapeGeometryCorpusError) as leakage_error:
        run_shape_geometry_experiment(manifest, inventory, annotations, observations)
    assert leakage_error.value.code == "SHAPE_GEOMETRY_V2_SHARED_PROFILE_TARGET_LEAKAGE"


def test_experiment_marks_missing_variant_observation_not_evaluable(tmp_path: Path) -> None:
    _, manifest, annotations, observation_mapping = _fixture(tmp_path)
    inventory = manifest.freeze_inventory()
    observation_mapping["observations"] = [
        value
        for value in observation_mapping["observations"]
        if not (
            value["gameId"] == "mummies"
            and value["variant"] == "shape_contrast_local_anchor_v1"
        )
    ]

    report = run_shape_geometry_experiment(
        manifest,
        inventory,
        annotations,
        ShapeGeometryExperimentObservations.from_mapping(observation_mapping),
    )

    mummies = next(value for value in report["games"] if value["gameId"] == "mummies")
    local_anchor = next(
        value
        for value in mummies["variants"]
        if value["variant"] == "shape_contrast_local_anchor_v1"
    )
    assert mummies["status"] == "not_evaluable"
    assert local_anchor["status"] == "not_evaluable"
    assert local_anchor["reasons"] == ["OBSERVATIONS_INCOMPLETE"]


def test_experiment_marks_missing_measurement_annotation_not_evaluable(tmp_path: Path) -> None:
    _, manifest, annotations, observation_mapping = _fixture(tmp_path)
    inventory = manifest.freeze_inventory()
    partial_annotations = ShapeGeometryManualAnnotations(
        corpus_manifest_fingerprint=annotations.corpus_manifest_fingerprint,
        annotations=tuple(
            annotation
            for annotation in annotations.annotations
            if annotation.source_id != "mummies-measurement"
        ),
    )
    observation_mapping["annotationFingerprint"] = partial_annotations.fingerprint()

    report = run_shape_geometry_experiment(
        manifest,
        inventory,
        partial_annotations,
        ShapeGeometryExperimentObservations.from_mapping(observation_mapping),
    )

    mummies = next(value for value in report["games"] if value["gameId"] == "mummies")
    assert mummies["status"] == "not_evaluable"
    assert {
        tuple(value["reasons"])
        for value in mummies["variants"]
    } == {("MEASUREMENT_ANNOTATIONS_INCOMPLETE",)}
    assert {
        tuple(value["missingAnnotationSourceIds"])
        for value in mummies["variants"]
    } == {("mummies-measurement",)}


def test_experiment_counts_confirmation_only_as_automatic(tmp_path: Path) -> None:
    _, manifest, annotations, observation_mapping = _fixture(tmp_path)
    inventory = manifest.freeze_inventory()
    confirmation = next(
        value
        for value in observation_mapping["observations"]
        if value["gameId"] == "mummies" and value["variant"] == "shape_contrast_v1"
    )
    confirmation["outcome"] = "confirmation_only"

    report = run_shape_geometry_experiment(
        manifest,
        inventory,
        annotations,
        ShapeGeometryExperimentObservations.from_mapping(observation_mapping),
    )

    mummies = next(value for value in report["games"] if value["gameId"] == "mummies")
    shape = next(value for value in mummies["variants"] if value["variant"] == "shape_contrast_v1")
    assert shape["automaticSourceCount"] == 1
    assert shape["confirmationOnlySourceCount"] == 1


def test_experiment_rechecks_current_inventory_before_reporting(tmp_path: Path) -> None:
    _, manifest, annotations, observation_mapping = _fixture(tmp_path)
    inventory = manifest.freeze_inventory()
    (tmp_path / "mummies" / "measurement.jpg").write_bytes(b"changed-after-freeze")

    with pytest.raises(ShapeGeometryCorpusError) as drift_error:
        run_shape_geometry_experiment(
            manifest,
            inventory,
            annotations,
            ShapeGeometryExperimentObservations.from_mapping(observation_mapping),
        )
    assert drift_error.value.code == "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_DRIFT"


def test_experiment_command_supports_write_then_check(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    manifest_mapping, manifest, annotations, observation_mapping = _fixture(tmp_path)
    inventory = manifest.freeze_inventory()
    manifest_path = tmp_path / "manifest.json"
    inventory_path = tmp_path / "inventory.json"
    annotations_path = tmp_path / "annotations.json"
    observations_path = tmp_path / "observations.json"
    output_path = tmp_path / "experiment.json"
    manifest_path.write_text(json.dumps(manifest_mapping), encoding="utf-8")
    inventory_path.write_text(json.dumps(inventory.as_dict()), encoding="utf-8")
    annotations_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "corpusManifestFingerprint": manifest.fingerprint(),
                "annotations": [
                    {
                        "sourceId": annotation.source_id,
                        "sourceChecksumSha256": annotation.source_checksum_sha256,
                        "pageState": annotation.page_state.value,
                        "topologyConfirmed": annotation.topology_confirmed,
                        "visibleGrid": annotation.visible_grid,
                        "anchorCandidate": annotation.anchor_candidate,
                        "activeOperatorSeconds": annotation.active_operator_seconds,
                    }
                    for annotation in annotations.annotations
                ],
            }
        ),
        encoding="utf-8",
    )
    observations_path.write_text(json.dumps(observation_mapping), encoding="utf-8")
    script = repository_root / "scripts" / "run_shape_geometry_v2_experiment.py"

    for extra in ([], ["--check"]):
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--manifest",
                str(manifest_path),
                "--inventory",
                str(inventory_path),
                "--annotations",
                str(annotations_path),
                "--observations",
                str(observations_path),
                "--output",
                str(output_path),
                *extra,
            ],
            cwd=repository_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
