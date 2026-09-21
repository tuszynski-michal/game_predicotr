from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import cv2
import game_predictor_worker.images.shape_geometry_v2.acceptance as acceptance_module
import numpy as np
import pytest
from game_predictor_api.domain.global_geometry_library import (
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    FRAME_APPEARANCE_SCHEMA_VERSION,
    GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
    NORMALIZED_TEMPLATE_SCHEMA_VERSION,
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileVersion,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_worker.images.shape_geometry_v2.acceptance import (
    ShapeGeometryAcceptanceError,
    ShapeGeometryAcceptanceInput,
    ShapeGeometryAcceptanceStatus,
    require_matching_shape_geometry_v2_acceptance,
    run_shape_geometry_v2_acceptance,
)
from game_predictor_worker.images.shape_geometry_v2.core import (
    SHAPE_GEOMETRY_V2_CORE_VERSION,
    ShapeGeometryV2Config,
)
from game_predictor_worker.images.shape_geometry_v2.corpus import (
    ShapeGeometryCorpusManifest,
    ShapeGeometryManualAnnotations,
    canonical_json_bytes,
)
from game_predictor_worker.images.shape_geometry_v2.pilot import (
    ShapeGeometryPilotInput,
    run_shape_geometry_pilot,
)
from game_predictor_worker.images.shape_geometry_v2.preflight import (
    ShapeGeometryV2LocalVerification,
    build_shape_geometry_v2_preflight_profile,
)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _image_bytes() -> bytes:
    image = np.zeros((120, 120, 3), dtype=np.uint8)
    encoded, payload = cv2.imencode(".jpg", image)
    assert encoded
    return payload.tobytes()


def _write_image(root: Path, relative_path: str, payload: bytes) -> str:
    path = root / Path(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _game(game_id: str = "mummies") -> dict[str, object]:
    return {
        "gameId": game_id,
        "pageBoardRows": 3,
        "pageBoardColumns": 3,
        "cellRows": 3,
        "cellColumns": 5,
        "activeBoardSlots": list(range(9)),
        "v11Profile": None,
    }


def _source_mapping(
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


def _manifest_mapping(
    root: Path,
    *,
    visibility: str,
    split: str,
    source_id: str,
    capture_family_id: str,
    payload: bytes,
) -> dict[str, object]:
    checksum = _write_image(root, f"{source_id}.jpg", payload)
    return {
        "schemaVersion": 2,
        "geometryFamily": SUPPORTED_GEOMETRY_FAMILY,
        "visibility": visibility,
        "corpusRoot": str(root),
        "games": [_game()],
        "sources": [
            {
                "sourceId": source_id,
                "gameId": "mummies",
                "relativePath": f"{source_id}.jpg",
                "sourceChecksumSha256": checksum,
                "split": split,
                "corpusRole": "measurement",
                "captureFamilyId": capture_family_id,
                "sourceOrdinal": 1,
                "scenarios": ["clear_frame"],
            }
        ],
    }


def _executor_manifest_mapping(
    root: Path, *, shared_acceptance_payload: bytes | None = None
) -> dict[str, object]:
    source_payloads = {
        "777": b"shape-geometry-v2-executor-777",
        "mummies": (
            b"shape-geometry-v2-executor-mummies"
            if shared_acceptance_payload is None
            else shared_acceptance_payload
        ),
        "gang": b"shape-geometry-v2-executor-gang",
    }
    sources: list[dict[str, object]] = []
    for game_id, payload in source_payloads.items():
        source_id = f"{game_id}-source"
        relative_path = f"{game_id}/source.jpg"
        checksum = _write_image(root, relative_path, payload)
        sources.append(_source_mapping(game_id, source_id, relative_path, checksum))
    return {
        "schemaVersion": 2,
        "geometryFamily": SUPPORTED_GEOMETRY_FAMILY,
        "visibility": "executor",
        "corpusRoot": str(root),
        "games": [_game("777"), _game("mummies"), _game("gang")],
        "sources": sources,
    }


def _executor_annotations_mapping(executor: ShapeGeometryCorpusManifest) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "corpusManifestFingerprint": executor.fingerprint(),
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
            for source in executor.sources
        ],
    }


def _json_object(value: object) -> dict[str, object]:
    decoded = json.loads(json.dumps(value, sort_keys=True))
    assert isinstance(decoded, dict)
    return cast(dict[str, object], decoded)


def _candidate_payloads() -> tuple[dict[str, object], dict[str, object], dict[str, object], object]:
    topology = GlobalGeometryTopology(3, 3, 3, 5)
    candidate_input = {
        "geometryFamily": SUPPORTED_GEOMETRY_FAMILY,
        "topology": topology.to_dict(),
        "normalizedTemplate": {
            "schemaVersion": NORMALIZED_TEMPLATE_SCHEMA_VERSION,
            "topology": topology.to_dict(),
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
    candidate = build_global_geometry_candidate(
        geometry_family=SUPPORTED_GEOMETRY_FAMILY,
        topology=topology,
        normalized_template=cast(dict[str, object], candidate_input["normalizedTemplate"]),
        frame_appearance=cast(dict[str, object], candidate_input["frameAppearance"]),
        evidence_summary=cast(dict[str, object], candidate_input["evidenceSummary"]),
        evidence=[
            (
                "mummies",
                cast(dict[str, object], candidate_input["evidence"])[0]["evidencePayload"],
            )
        ],
    )
    profile = GlobalGeometryProfileVersion(
        id=uuid4(),
        profile_number=1,
        status=GlobalGeometryProfileStatus.ACTIVE,
        geometry_family=candidate.geometry_family,
        topology=candidate.topology,
        normalized_template=candidate.normalized_template,
        frame_appearance=candidate.frame_appearance,
        evidence_summary=candidate.evidence_summary,
        profile_checksum_sha256=candidate.profile_checksum_sha256,
        created_at=datetime.now(UTC),
    )
    candidate_output = {
        "geometryFamily": candidate.geometry_family,
        "topology": candidate.topology.to_dict(),
        "normalizedTemplate": _json_object(candidate.normalized_template),
        "frameAppearance": _json_object(candidate.frame_appearance),
        "evidenceSummary": _json_object(candidate.evidence_summary),
        "evidence": [
            {
                "sourceGameRef": item.source_game_ref,
                "evidencePayload": _json_object(item.evidence_payload),
                "evidenceChecksumSha256": item.evidence_checksum_sha256,
            }
            for item in candidate.evidence
        ],
        "profileChecksumSha256": candidate.profile_checksum_sha256,
    }
    return (
        candidate_input,
        candidate_output,
        build_shape_geometry_v2_preflight_profile(profile),
        candidate,
    )


def _pilot_observation(
    source_id: str,
    source_checksum: str,
    phase: str,
    outcome: str,
    profile_checksum: str,
    *,
    active_operator_seconds: int,
    correction_accepted: bool = False,
) -> dict[str, object]:
    return {
        "sourceId": source_id,
        "sourceChecksumSha256": source_checksum,
        "profileChecksumSha256": profile_checksum,
        "phase": phase,
        "outcome": outcome,
        "activeOperatorSeconds": active_operator_seconds,
        "correctionAccepted": correction_accepted,
    }


def _frozen_input(
    executor: ShapeGeometryCorpusManifest, source_id: str, checksum: str
) -> dict[str, object]:
    candidate_input, _, preflight_profile, candidate = _candidate_payloads()
    annotations_mapping = _executor_annotations_mapping(executor)
    annotations = ShapeGeometryManualAnnotations.from_mapping(annotations_mapping)
    sources = {source.game_id: source for source in executor.sources}
    baseline_checksum = "a" * 64
    candidate_checksum = cast(str, candidate.profile_checksum_sha256)
    pilot_input = {
        "schemaVersion": 1,
        "corpusManifestFingerprint": executor.fingerprint(),
        "inventoryFingerprint": executor.freeze_inventory().fingerprint(),
        "annotationFingerprint": annotations.fingerprint(),
        "baselineActiveProfileChecksumSha256": baseline_checksum,
        "baselineContributorGameRefs": ["777"],
        "correctionGameRef": "mummies",
        "transferTargetGameRef": "gang",
        "candidate": candidate_input,
        "observations": [
            _pilot_observation(
                sources["mummies"].source_id,
                sources["mummies"].source_checksum_sha256,
                "mummies_correction",
                "correction_required",
                candidate_checksum,
                active_operator_seconds=12,
                correction_accepted=True,
            ),
            _pilot_observation(
                sources["mummies"].source_id,
                sources["mummies"].source_checksum_sha256,
                "mummies_replay",
                "confirmation_only",
                candidate_checksum,
                active_operator_seconds=2,
            ),
            _pilot_observation(
                sources["777"].source_id,
                sources["777"].source_checksum_sha256,
                "regression_baseline",
                "correction_required",
                baseline_checksum,
                active_operator_seconds=8,
            ),
            _pilot_observation(
                sources["777"].source_id,
                sources["777"].source_checksum_sha256,
                "regression_candidate",
                "confirmation_only",
                candidate_checksum,
                active_operator_seconds=2,
            ),
            _pilot_observation(
                sources["gang"].source_id,
                sources["gang"].source_checksum_sha256,
                "transfer",
                "automatic_correct",
                candidate_checksum,
                active_operator_seconds=0,
            ),
        ],
    }
    pilot = ShapeGeometryPilotInput.from_mapping(pilot_input)
    pilot_report = run_shape_geometry_pilot(
        executor, executor.freeze_inventory(), annotations, pilot
    )
    assert pilot_report.status == "measured"
    assert pilot_report.qualification_report is not None
    qualification_payload = pilot_report.qualification_report.as_dict()
    truth = [
        {
            "sourceId": source_id,
            "sourceChecksumSha256": checksum,
            "expectedVerdict": "needs_manual_review",
            "expectedReasonCode": "SHAPE_GEOMETRY_V2_CORE_REVIEW_REQUIRED",
        }
    ]
    pilot_payload = pilot_report.as_dict()
    return {
        "schemaVersion": 1,
        "coreVersion": SHAPE_GEOMETRY_V2_CORE_VERSION,
        "coreConfig": ShapeGeometryV2Config().as_dict(),
        "preflightProfile": preflight_profile,
        "pilotInput": pilot_input,
        "executorAnnotations": annotations_mapping,
        "pilotReport": pilot_payload,
        "pilotReportChecksumSha256": _fingerprint(pilot_payload),
        "qualificationReport": qualification_payload,
        "qualificationReportChecksumSha256": pilot_report.qualification_report.checksum_sha256(),
        "truth": truth,
        "truthChecksumSha256": _fingerprint({"truth": truth}),
    }


def _fixture(
    tmp_path: Path,
    *,
    shared_payload: bool = False,
) -> tuple[
    dict[str, object],
    ShapeGeometryCorpusManifest,
    dict[str, object],
    ShapeGeometryCorpusManifest,
    dict[str, object],
]:
    acceptance_payload = _image_bytes()
    executor_mapping = _executor_manifest_mapping(
        tmp_path / "executor",
        shared_acceptance_payload=acceptance_payload if shared_payload else None,
    )
    acceptance_mapping = _manifest_mapping(
        tmp_path / "acceptance",
        visibility="acceptance",
        split="acceptance",
        source_id="acceptance-source",
        capture_family_id="acceptance-family",
        payload=acceptance_payload,
    )
    executor_manifest = ShapeGeometryCorpusManifest.from_mapping(executor_mapping)
    acceptance_manifest = ShapeGeometryCorpusManifest.from_mapping(acceptance_mapping)
    acceptance_source = acceptance_manifest.sources[0]
    frozen = _frozen_input(
        executor_manifest, acceptance_source.source_id, acceptance_source.source_checksum_sha256
    )
    return executor_mapping, executor_manifest, acceptance_mapping, acceptance_manifest, frozen


def _run(
    executor: ShapeGeometryCorpusManifest,
    acceptance: ShapeGeometryCorpusManifest,
    frozen: dict[str, object],
):
    return run_shape_geometry_v2_acceptance(
        executor_manifest=executor,
        executor_inventory=executor.freeze_inventory().as_dict(),
        acceptance_manifest=acceptance,
        acceptance_inventory=acceptance.freeze_inventory().as_dict(),
        frozen_input=ShapeGeometryAcceptanceInput.from_mapping(frozen),
    )


def test_acceptance_without_operator_artifacts_is_not_evaluable() -> None:
    result = run_shape_geometry_v2_acceptance()

    assert result.status is ShapeGeometryAcceptanceStatus.NOT_EVALUABLE
    assert result.reason_codes == ("SHAPE_GEOMETRY_V2_ACCEPTANCE_ARTIFACTS_MISSING",)
    assert result.source_results == ()


def test_acceptance_replays_frozen_chain_and_truth_deterministically(tmp_path: Path) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path)

    first = _run(executor, acceptance, frozen)
    second = _run(executor, acceptance, frozen)

    assert first.status is ShapeGeometryAcceptanceStatus.PASSED
    assert first.as_dict() == second.as_dict()
    assert first.source_results[0].matches_truth is True
    assert first.acceptance_snapshot_checksum_sha256 is not None
    require_matching_shape_geometry_v2_acceptance(first.as_dict(), second)


def test_acceptance_rejects_cross_split_checksum_leakage(tmp_path: Path) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path, shared_payload=True)

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert "SHAPE_GEOMETRY_V2_CHECKSUM_SPLIT_LEAKAGE" in result.reason_codes


def test_acceptance_rejects_cross_split_capture_family_leakage(tmp_path: Path) -> None:
    _, executor, acceptance_mapping, _, frozen = _fixture(tmp_path)
    acceptance_sources = cast(list[dict[str, object]], acceptance_mapping["sources"])
    acceptance_sources[0]["captureFamilyId"] = "mummies-family"
    acceptance = ShapeGeometryCorpusManifest.from_mapping(acceptance_mapping)

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert "SHAPE_GEOMETRY_V2_CAPTURE_FAMILY_SPLIT_LEAKAGE" in result.reason_codes


def test_acceptance_rejects_frozen_core_or_profile_chain_drift(tmp_path: Path) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path)
    frozen["coreVersion"] = "shape-frame-geometry-v2-core-v0"
    frozen["pilotReportChecksumSha256"] = _fingerprint(frozen["pilotReport"])

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert "SHAPE_GEOMETRY_V2_ACCEPTANCE_CORE_VERSION_MISMATCH" in result.reason_codes


def test_acceptance_rejects_truth_mismatch_without_publishing(tmp_path: Path) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path)
    truth = cast(list[dict[str, object]], frozen["truth"])
    truth[0]["expectedReasonCode"] = "SHAPE_GEOMETRY_V2_TEST_EXPECTATION"
    frozen["truthChecksumSha256"] = _fingerprint({"truth": truth})

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert result.reason_codes == ("SHAPE_GEOMETRY_V2_ACCEPTANCE_TRUTH_MISMATCH",)
    assert result.source_results[0].matches_truth is False


def test_acceptance_rejects_incomplete_truth_source_set(tmp_path: Path) -> None:
    _, executor, acceptance_mapping, _, frozen = _fixture(tmp_path)
    second_payload = _image_bytes()
    second_checksum = _write_image(tmp_path / "acceptance", "second.jpg", second_payload)
    second_source = {
        "sourceId": "acceptance-second",
        "gameId": "mummies",
        "relativePath": "second.jpg",
        "sourceChecksumSha256": second_checksum,
        "split": "acceptance",
        "corpusRole": "measurement",
        "captureFamilyId": "acceptance-second-family",
        "sourceOrdinal": 2,
        "scenarios": ["clear_frame"],
    }
    cast(list[dict[str, object]], acceptance_mapping["sources"]).append(second_source)
    acceptance = ShapeGeometryCorpusManifest.from_mapping(acceptance_mapping)

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert result.reason_codes == ("SHAPE_GEOMETRY_V2_ACCEPTANCE_TRUTH_SOURCE_SET_MISMATCH",)


def test_acceptance_rejects_candidate_descriptor_drift_in_pilot_report(tmp_path: Path) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path)
    pilot_report = cast(dict[str, object], frozen["pilotReport"])
    candidate = cast(dict[str, object], pilot_report["candidate"])
    normalized = cast(dict[str, object], candidate["normalizedTemplate"])
    aspect_ratio = cast(dict[str, float], normalized["aspectRatioRange"])
    aspect_ratio["maximum"] = 1.9
    frozen["pilotReportChecksumSha256"] = _fingerprint(pilot_report)

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert "SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_CANDIDATE_DRIFT" in result.reason_codes


def test_acceptance_rejects_pilot_report_not_reproduced_from_frozen_input(tmp_path: Path) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path)
    pilot_report = cast(dict[str, object], frozen["pilotReport"])
    work_reduction = cast(dict[str, int], pilot_report["workReduction"])
    work_reduction["operatorActiveSecondsReduction"] = 999
    frozen["pilotReportChecksumSha256"] = _fingerprint(pilot_report)

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert result.source_results == ()
    assert "SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_REPLAY_DRIFT" in result.reason_codes


def test_acceptance_rejects_pilot_input_without_correction_replay(tmp_path: Path) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path)
    pilot_input = cast(dict[str, object], frozen["pilotInput"])
    observations = cast(list[dict[str, object]], pilot_input["observations"])
    pilot_input["observations"] = [
        observation for observation in observations if observation["phase"] != "mummies_correction"
    ]
    pilot_report = cast(dict[str, object], frozen["pilotReport"])
    pilot_report["inputFingerprint"] = ShapeGeometryPilotInput.from_mapping(
        pilot_input
    ).fingerprint()
    frozen["pilotReportChecksumSha256"] = _fingerprint(pilot_report)

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert result.source_results == ()
    assert "SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_REPLAY_DRIFT" in result.reason_codes


def test_acceptance_rejects_executor_not_bound_to_pilot_input(tmp_path: Path) -> None:
    _, _, _, acceptance, frozen = _fixture(tmp_path)
    other_mapping = _manifest_mapping(
        tmp_path / "other-executor",
        visibility="executor",
        split="development",
        source_id="other-executor-source",
        capture_family_id="other-executor-family",
        payload=b"other-executor-source",
    )
    other_executor = ShapeGeometryCorpusManifest.from_mapping(other_mapping)

    result = _run(other_executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert "SHAPE_GEOMETRY_V2_ACCEPTANCE_EXECUTOR_MANIFEST_MISMATCH" in result.reason_codes
    assert "SHAPE_GEOMETRY_V2_ACCEPTANCE_EXECUTOR_INVENTORY_MISMATCH" in result.reason_codes


def _verification(marker: int) -> ShapeGeometryV2LocalVerification:
    return ShapeGeometryV2LocalVerification(
        verdict="needs_manual_review",
        reason_code="SHAPE_GEOMETRY_V2_CORE_REVIEW_REQUIRED",
        observed_aspect_ratio=None,
        core_result={
            "coreVersion": SHAPE_GEOMETRY_V2_CORE_VERSION,
            "status": "needs_manual_review",
            "reasonCodes": [],
            "marker": marker,
        },
    )


def test_acceptance_rejects_replay_when_full_verification_payload_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path)
    results = iter((_verification(1), _verification(2)))
    monkeypatch.setattr(
        acceptance_module,
        "verify_shape_geometry_v2_profile",
        lambda _rgb, _profile: next(results),
    )

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert result.reason_codes == ("SHAPE_GEOMETRY_V2_ACCEPTANCE_REPLAY_DRIFT",)


def test_acceptance_rejects_source_changed_between_inventory_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, executor, _, acceptance, frozen = _fixture(tmp_path)
    source_path = acceptance.resolve_source_path(acceptance.sources[0])

    def mutate_after_first_verification(
        _rgb: np.ndarray, _profile: object
    ) -> ShapeGeometryV2LocalVerification:
        source_path.write_bytes(b"changed-after-frozen-inventory")
        return _verification(1)

    monkeypatch.setattr(
        acceptance_module,
        "verify_shape_geometry_v2_profile",
        mutate_after_first_verification,
    )

    result = _run(executor, acceptance, frozen)

    assert result.status is ShapeGeometryAcceptanceStatus.REJECTED
    assert result.reason_codes == ("SHAPE_GEOMETRY_V2_ACCEPTANCE_SOURCE_DRIFT",)


def test_acceptance_command_writes_and_replay_checks_report(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    executor_mapping, executor, acceptance_mapping, acceptance, frozen = _fixture(tmp_path)
    executor_manifest = tmp_path / "executor-manifest.json"
    executor_inventory = tmp_path / "executor-inventory.json"
    acceptance_manifest = tmp_path / "acceptance-manifest.json"
    acceptance_inventory = tmp_path / "acceptance-inventory.json"
    frozen_input = tmp_path / "frozen-input.json"
    output = tmp_path / "acceptance-report.json"
    executor_manifest.write_text(json.dumps(executor_mapping), encoding="utf-8")
    executor_inventory.write_text(
        json.dumps(executor.freeze_inventory().as_dict()), encoding="utf-8"
    )
    acceptance_manifest.write_text(json.dumps(acceptance_mapping), encoding="utf-8")
    acceptance_inventory.write_text(
        json.dumps(acceptance.freeze_inventory().as_dict()), encoding="utf-8"
    )
    frozen_input.write_text(json.dumps(frozen), encoding="utf-8")
    command = [
        sys.executable,
        str(repository_root / "scripts" / "run_shape_geometry_v2_acceptance.py"),
        "--executor-manifest",
        str(executor_manifest),
        "--executor-inventory",
        str(executor_inventory),
        "--acceptance-manifest",
        str(acceptance_manifest),
        "--acceptance-inventory",
        str(acceptance_inventory),
        "--frozen-input",
        str(frozen_input),
        "--output",
        str(output),
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


def test_acceptance_command_rejects_partial_artifact_set(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    command = [
        sys.executable,
        str(repository_root / "scripts" / "run_shape_geometry_v2_acceptance.py"),
        "--executor-manifest",
        str(tmp_path / "only-one-artifact.json"),
        "--output",
        str(tmp_path / "report.json"),
    ]

    result = subprocess.run(
        command,
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert "SHAPE_GEOMETRY_V2_ACCEPTANCE_ARGUMENTS_INCOMPLETE" in result.stderr


def test_acceptance_input_requires_complete_truth() -> None:
    with pytest.raises(ShapeGeometryAcceptanceError) as rejected:
        ShapeGeometryAcceptanceInput.from_mapping(
            {
                "schemaVersion": 1,
                "coreVersion": SHAPE_GEOMETRY_V2_CORE_VERSION,
                "coreConfig": {},
                "preflightProfile": {},
                "pilotInput": {},
                "executorAnnotations": {},
                "pilotReport": {},
                "pilotReportChecksumSha256": "a" * 64,
                "qualificationReport": {},
                "qualificationReportChecksumSha256": "b" * 64,
                "truth": [],
                "truthChecksumSha256": "c" * 64,
            }
        )

    assert rejected.value.code == "SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID"
