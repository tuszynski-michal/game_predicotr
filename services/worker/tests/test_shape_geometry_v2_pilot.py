from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from game_predictor_api.domain.global_geometry_library import (
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    FRAME_APPEARANCE_SCHEMA_VERSION,
    GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
    NORMALIZED_TEMPLATE_SCHEMA_VERSION,
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_worker.images.shape_geometry_v2.corpus import (
    ShapeGeometryCorpusError,
    ShapeGeometryCorpusManifest,
    ShapeGeometryManualAnnotations,
)
from game_predictor_worker.images.shape_geometry_v2.pilot import (
    ShapeGeometryPilotError,
    ShapeGeometryPilotInput,
    run_shape_geometry_pilot,
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


def _write(root: Path, relative_path: str, content: bytes) -> str:
    path = root / Path(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _source(
    game_id: str,
    source_id: str,
    relative_path: str,
    checksum: str,
    *,
    split: str = "development",
) -> dict[str, object]:
    return {
        "sourceId": source_id,
        "gameId": game_id,
        "relativePath": relative_path,
        "sourceChecksumSha256": checksum,
        "split": split,
        "corpusRole": "measurement",
        "captureFamilyId": f"{game_id}-family",
        "sourceOrdinal": 1,
        "scenarios": ["clear_frame"],
    }


def _manifest_mapping(root: Path, *, mummies_split: str = "development") -> dict[str, object]:
    baseline_checksum = _write(root, "777/source.jpg", b"777-source")
    mummies_checksum = _write(root, "mummies/source.jpg", b"mummies-source")
    gang_checksum = _write(root, "gang/source.jpg", b"gang-source")
    return {
        "schemaVersion": 2,
        "geometryFamily": SUPPORTED_GEOMETRY_FAMILY,
        "visibility": "executor",
        "corpusRoot": str(root),
        "games": [_game("777"), _game("mummies"), _game("gang")],
        "sources": [
            _source("777", "777-source", "777/source.jpg", baseline_checksum),
            _source(
                "mummies",
                "mummies-source",
                "mummies/source.jpg",
                mummies_checksum,
                split=mummies_split,
            ),
            _source("gang", "gang-source", "gang/source.jpg", gang_checksum),
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
                    "anchorCandidate": False,
                    "activeOperatorSeconds": 9,
                }
                for source in manifest.sources
            ],
        }
    )


def _candidate() -> dict[str, object]:
    return {
        "geometryFamily": SUPPORTED_GEOMETRY_FAMILY,
        "topology": {
            "pageBoardRows": 3,
            "pageBoardColumns": 3,
            "boardCellRows": 3,
            "boardCellColumns": 5,
        },
        "normalizedTemplate": {
            "schemaVersion": NORMALIZED_TEMPLATE_SCHEMA_VERSION,
            "topology": {
                "pageBoardRows": 3,
                "pageBoardColumns": 3,
                "boardCellRows": 3,
                "boardCellColumns": 5,
            },
            "frameQuad": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            "aspectRatioRange": {"minimum": 0.5, "maximum": 2.0},
        },
        "frameAppearance": {
            "schemaVersion": FRAME_APPEARANCE_SCHEMA_VERSION,
            "sides": {
                "top": {
                    "clusters": [{"lab": [44.0, 12.0, -8.0], "hsv": [23.0, 0.5, 0.7]}],
                    "contrast": {"minimum": 0.2, "median": 0.4, "maximum": 0.8},
                    "continuity": 0.9,
                }
            },
        },
        "evidenceSummary": {
            "schemaVersion": EVIDENCE_SUMMARY_SCHEMA_VERSION,
            "fullSourceCount": 1,
            "partialSourceCount": 0,
            "sourceGameRefs": ["mummies"],
            "extractorVersion": "shape-geometry-v2-core-v1",
            "qualityMetrics": {"candidateCount": 1},
        },
        "evidence": [
            {
                "sourceGameRef": "mummies",
                "evidencePayload": {
                    "schemaVersion": GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
                    "coverageKind": "full",
                    "visibleFrameSides": ["top", "right", "bottom", "left"],
                    "extractorVersion": "shape-geometry-v2-core-v1",
                    "metrics": {"frameSupport": 0.91},
                },
            }
        ],
    }


def _candidate_checksum(candidate: dict[str, object]) -> str:
    topology = cast(dict[str, int], candidate["topology"])
    evidence = cast(list[dict[str, object]], candidate["evidence"])
    parsed = build_global_geometry_candidate(
        geometry_family=cast(str, candidate["geometryFamily"]),
        topology=GlobalGeometryTopology(
            page_board_rows=topology["pageBoardRows"],
            page_board_columns=topology["pageBoardColumns"],
            board_cell_rows=topology["boardCellRows"],
            board_cell_columns=topology["boardCellColumns"],
        ),
        normalized_template=cast(dict[str, object], candidate["normalizedTemplate"]),
        frame_appearance=cast(dict[str, object], candidate["frameAppearance"]),
        evidence_summary=cast(dict[str, object], candidate["evidenceSummary"]),
        evidence=[
            (
                cast(str, item["sourceGameRef"]),
                cast(dict[str, object], item["evidencePayload"]),
            )
            for item in evidence
        ],
    )
    return parsed.profile_checksum_sha256


def _observation(
    source: object,
    phase: str,
    outcome: str,
    profile_checksum: str,
    *,
    active_operator_seconds: int,
    correction_accepted: bool = False,
) -> dict[str, object]:
    source_mapping = cast(dict[str, str], source)
    return {
        "sourceId": source_mapping["sourceId"],
        "sourceChecksumSha256": source_mapping["sourceChecksumSha256"],
        "profileChecksumSha256": profile_checksum,
        "phase": phase,
        "outcome": outcome,
        "activeOperatorSeconds": active_operator_seconds,
        "correctionAccepted": correction_accepted,
    }


def _pilot_mapping(
    manifest: ShapeGeometryCorpusManifest,
    annotations: ShapeGeometryManualAnnotations,
    *,
    accepted: bool = True,
    include_transfer: bool = True,
    candidate: dict[str, object] | None = None,
) -> dict[str, object]:
    inventory = manifest.freeze_inventory()
    source_by_game = {
        source.game_id: {
            "sourceId": source.source_id,
            "sourceChecksumSha256": source.source_checksum_sha256,
        }
        for source in manifest.sources
    }
    candidate_payload = _candidate() if candidate is None else candidate
    candidate_checksum = _candidate_checksum(candidate_payload)
    baseline_checksum = "a" * 64
    observations: list[dict[str, object]] = [
        _observation(
            source_by_game["mummies"],
            "mummies_correction",
            "correction_required",
            candidate_checksum,
            active_operator_seconds=12,
            correction_accepted=accepted,
        ),
        _observation(
            source_by_game["mummies"],
            "mummies_replay",
            "confirmation_only",
            candidate_checksum,
            active_operator_seconds=2,
        ),
        _observation(
            source_by_game["777"],
            "regression_baseline",
            "correction_required",
            baseline_checksum,
            active_operator_seconds=8,
        ),
        _observation(
            source_by_game["777"],
            "regression_candidate",
            "confirmation_only",
            candidate_checksum,
            active_operator_seconds=2,
        ),
    ]
    if include_transfer:
        observations.append(
            _observation(
                source_by_game["gang"],
                "transfer",
                "automatic_correct",
                candidate_checksum,
                active_operator_seconds=0,
            )
        )
    return {
        "schemaVersion": 1,
        "corpusManifestFingerprint": manifest.fingerprint(),
        "inventoryFingerprint": inventory.fingerprint(),
        "annotationFingerprint": annotations.fingerprint(),
        "baselineActiveProfileChecksumSha256": baseline_checksum,
        "baselineContributorGameRefs": ["777"],
        "correctionGameRef": "mummies",
        "transferTargetGameRef": "gang",
        "candidate": candidate_payload,
        "observations": observations,
    }


def _fixture(
    tmp_path: Path,
) -> tuple[dict[str, object], ShapeGeometryCorpusManifest, ShapeGeometryManualAnnotations]:
    mapping = _manifest_mapping(tmp_path)
    manifest = ShapeGeometryCorpusManifest.from_mapping(mapping)
    return mapping, manifest, _annotations(manifest)


def test_pilot_builds_descriptor_candidate_and_g07_report(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    pilot = ShapeGeometryPilotInput.from_mapping(_pilot_mapping(manifest, annotations))

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "measured"
    assert result.candidate is not None
    assert result.qualification_report is not None
    assert result.qualification_report.replay_expected_source_count == 1
    assert result.qualification_report.regression_evaluated_source_count == 1
    assert result.qualification_report.transfer_expected_source_count == 1
    assert result.qualification_report.transfer_target_game_ref == "gang"
    assert result.publication_inputs() == (result.candidate, result.qualification_report)
    report = result.as_dict()
    assert report["candidate"]["profileChecksumSha256"] == result.candidate.profile_checksum_sha256
    assert "sourceId" not in json.dumps(report["candidate"])
    assert "game_id" not in json.dumps(report["candidate"])


def test_pilot_reports_work_reduction_for_the_same_prior_game_cohort(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    pilot = ShapeGeometryPilotInput.from_mapping(_pilot_mapping(manifest, annotations))

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    baseline, candidate = result.phases[2:4]
    assert baseline.expected_source_ids == ("777-source",)
    assert baseline.correction_required_source_count == 1
    assert baseline.review_required_source_count == 0
    assert candidate.confirmation_only_source_count == 1
    assert result.work_reduction == {
        "correctionRequiredSourceCountReduction": 1,
        "operatorActiveSecondsReduction": 6,
        "reviewRequiredSourceCountReduction": 0,
    }


def test_pilot_omits_work_reduction_when_both_regression_phases_are_missing(
    tmp_path: Path,
) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    mapping = _pilot_mapping(manifest, annotations)
    mapping["observations"] = [
        observation
        for observation in mapping["observations"]
        if observation["phase"] not in {"regression_baseline", "regression_candidate"}
    ]
    pilot = ShapeGeometryPilotInput.from_mapping(mapping)

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "not_evaluable"
    assert result.phases[2].evaluated_source_ids == ()
    assert result.phases[3].evaluated_source_ids == ()
    assert result.work_reduction is None


def test_pilot_omits_work_reduction_for_matching_incomplete_regression_subset(
    tmp_path: Path,
) -> None:
    manifest_mapping = _manifest_mapping(tmp_path)
    second_baseline_checksum = _write(tmp_path, "777/source-2.jpg", b"777-source-2")
    second_baseline_source = _source(
        "777", "777-source-2", "777/source-2.jpg", second_baseline_checksum
    )
    second_baseline_source["sourceOrdinal"] = 2
    cast(list[dict[str, object]], manifest_mapping["sources"]).append(second_baseline_source)
    manifest = ShapeGeometryCorpusManifest.from_mapping(manifest_mapping)
    annotations = _annotations(manifest)
    pilot = ShapeGeometryPilotInput.from_mapping(_pilot_mapping(manifest, annotations))

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    baseline, candidate = result.phases[2:4]
    assert result.status == "not_evaluable"
    assert baseline.evaluated_source_ids == candidate.evaluated_source_ids
    assert baseline.evaluated_source_ids != baseline.expected_source_ids
    assert result.work_reduction is None


def test_pilot_keeps_candidate_but_marks_missing_transfer_not_evaluable(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    pilot = ShapeGeometryPilotInput.from_mapping(
        _pilot_mapping(manifest, annotations, include_transfer=False)
    )

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "not_evaluable"
    assert result.candidate is not None
    assert result.qualification_report is not None
    assert "PILOT_PHASE_OBSERVATIONS_INCOMPLETE" in result.reason_codes
    assert result.qualification_report.transfer_evaluated_source_count == 0
    with pytest.raises(ShapeGeometryPilotError) as blocked:
        result.publication_inputs()
    assert blocked.value.code == "SHAPE_GEOMETRY_V2_PILOT_PUBLICATION_BLOCKED"


def test_pilot_does_not_build_candidate_without_accepted_correction(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    pilot = ShapeGeometryPilotInput.from_mapping(
        _pilot_mapping(manifest, annotations, accepted=False)
    )

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "not_evaluable"
    assert result.candidate is None
    assert result.qualification_report is None
    assert "PILOT_CORRECTION_NOT_ACCEPTED" in result.reason_codes


def test_pilot_rejects_transfer_game_as_candidate_contributor(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    candidate = _candidate()
    cast(list[dict[str, object]], candidate["evidence"])[0]["sourceGameRef"] = "gang"
    cast(dict[str, object], candidate["evidenceSummary"])["sourceGameRefs"] = ["gang"]
    pilot = ShapeGeometryPilotInput.from_mapping(
        _pilot_mapping(manifest, annotations, candidate=candidate)
    )

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "not_evaluable"
    assert result.candidate is None
    assert "PILOT_CANDIDATE_CONTRIBUTOR_MISMATCH" in result.reason_codes


def test_pilot_counts_incorrect_transfer_automatic_separately(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    mapping = _pilot_mapping(manifest, annotations)
    transfer = next(value for value in mapping["observations"] if value["phase"] == "transfer")
    transfer["outcome"] = "automatic_incorrect"
    pilot = ShapeGeometryPilotInput.from_mapping(mapping)

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "measured"
    assert result.qualification_report is not None
    assert result.qualification_report.transfer_automatic_incorrect_source_count == 1


def test_pilot_rejects_changed_candidate_when_observations_reference_old_profile(
    tmp_path: Path,
) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    mapping = _pilot_mapping(manifest, annotations)
    changed_candidate = cast(dict[str, object], mapping["candidate"])
    normalized_template = cast(dict[str, object], changed_candidate["normalizedTemplate"])
    aspect_ratio = cast(dict[str, float], normalized_template["aspectRatioRange"])
    aspect_ratio["maximum"] = 1.9
    pilot = ShapeGeometryPilotInput.from_mapping(mapping)

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "not_evaluable"
    assert result.candidate is None
    assert result.qualification_report is None
    assert "PILOT_OBSERVATION_PROFILE_MISMATCH" in result.reason_codes
    with pytest.raises(ShapeGeometryPilotError) as blocked:
        result.publication_inputs()
    assert blocked.value.code == "SHAPE_GEOMETRY_V2_PILOT_PUBLICATION_BLOCKED"


def test_pilot_rejects_regression_that_omits_the_prior_game_cohort(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    mapping = _pilot_mapping(manifest, annotations)
    mapping["observations"] = [
        observation
        for observation in mapping["observations"]
        if observation["phase"] != "regression_baseline"
    ]
    pilot = ShapeGeometryPilotInput.from_mapping(mapping)

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "not_evaluable"
    baseline = result.phases[2]
    assert baseline.expected_source_ids == ("777-source",)
    assert baseline.evaluated_source_ids == ()
    assert "PILOT_PHASE_OBSERVATIONS_INCOMPLETE" in result.reason_codes


def test_pilot_input_requires_profile_checksum_on_each_observation(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    mapping = _pilot_mapping(manifest, annotations)
    del mapping["observations"][0]["profileChecksumSha256"]

    with pytest.raises(ShapeGeometryPilotError) as rejected:
        ShapeGeometryPilotInput.from_mapping(mapping)

    assert rejected.value.code == "SHAPE_GEOMETRY_V2_PILOT_INVALID"


def test_executor_corpus_blocks_acceptance_before_pilot_creation(tmp_path: Path) -> None:
    manifest_mapping = _manifest_mapping(tmp_path, mummies_split="acceptance")

    with pytest.raises(ShapeGeometryCorpusError) as rejected:
        ShapeGeometryCorpusManifest.from_mapping(manifest_mapping)

    assert rejected.value.code == "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN"


def test_pilot_requires_existing_baseline_before_publication(tmp_path: Path) -> None:
    _, manifest, annotations = _fixture(tmp_path)
    mapping = _pilot_mapping(manifest, annotations)
    mapping["baselineActiveProfileChecksumSha256"] = None
    pilot = ShapeGeometryPilotInput.from_mapping(mapping)

    result = run_shape_geometry_pilot(manifest, manifest.freeze_inventory(), annotations, pilot)

    assert result.status == "not_evaluable"
    assert result.candidate is not None
    assert result.qualification_report is None
    assert "PILOT_BASELINE_PROFILE_MISSING" in result.reason_codes


def test_pilot_command_writes_then_rechecks_identical_report(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    manifest_mapping, manifest, annotations = _fixture(tmp_path)
    inventory = manifest.freeze_inventory()
    pilot_mapping = _pilot_mapping(manifest, annotations)
    manifest_path = tmp_path / "manifest.json"
    inventory_path = tmp_path / "inventory.json"
    annotations_path = tmp_path / "annotations.json"
    pilot_path = tmp_path / "pilot.json"
    output_path = tmp_path / "report.json"
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
    pilot_path.write_text(json.dumps(pilot_mapping), encoding="utf-8")
    script = repository_root / "scripts" / "run_shape_geometry_v2_pilot.py"
    command = [
        sys.executable,
        str(script),
        "--manifest",
        str(manifest_path),
        "--inventory",
        str(inventory_path),
        "--annotations",
        str(annotations_path),
        "--pilot",
        str(pilot_path),
        "--output",
        str(output_path),
    ]
    first = subprocess.run(
        command,
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    second = subprocess.run(
        [*command, "--check"],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
