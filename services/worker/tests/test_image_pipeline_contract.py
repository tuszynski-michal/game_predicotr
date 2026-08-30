from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from game_predictor_worker.images.pipeline_contract import (
    FILE_CHECKPOINT_VERSION,
    PIPELINE_STAGES,
    SYMBOL_RGB_PREPROCESSING_VERSION,
    CellAssetRolloutMode,
    GeometryPipelineRolloutSnapshot,
    GeometryRolloutMode,
    ImagePipelineContractError,
    StructuredGeometryCandidateSnapshot,
    build_pipeline_envelope,
    current_pipeline_manifest,
    effective_pipeline_fingerprint,
    file_execution_key,
    pipeline_fingerprint,
    validate_checkpoint_transition,
    validate_file_checkpoint,
    validate_pipeline_envelope,
    validate_pipeline_manifest,
    verify_manifest_artifacts,
)
from game_predictor_worker.images.structured_geometry import (
    DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2,
    STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
)
from game_predictor_worker.images.virtual_cell_extraction import VIRTUAL_CELL_RENDERER_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_MANIFEST = REPOSITORY_ROOT / "ai_docs/quality/m7-image-pipeline-manifest-v1.json"
MANIFEST_SCHEMA = REPOSITORY_ROOT / "ai_docs/quality/image-pipeline-manifest-v1.schema.json"
SOURCE_SHA256 = "a" * 64


def _rollout(mode: GeometryRolloutMode) -> GeometryPipelineRolloutSnapshot:
    return GeometryPipelineRolloutSnapshot(
        geometry_mode=mode,
        cell_asset_mode=(
            CellAssetRolloutMode.LEGACY_FILES
            if mode is GeometryRolloutMode.LEGACY
            else (
                CellAssetRolloutMode.VIRTUAL_DEFAULT
                if mode is GeometryRolloutMode.STRUCTURED_DEFAULT
                else CellAssetRolloutMode.VIRTUAL_SHADOW
            )
        ),
        rollout_revision=0 if mode is GeometryRolloutMode.LEGACY else 3,
        geometry_engine_version=STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
        virtual_renderer_version=VIRTUAL_CELL_RENDERER_VERSION,
        preprocessing_version=SYMBOL_RGB_PREPROCESSING_VERSION,
    )


def _candidate_rollout() -> GeometryPipelineRolloutSnapshot:
    base = _rollout(GeometryRolloutMode.STRUCTURED_SHADOW)
    return GeometryPipelineRolloutSnapshot(
        geometry_mode=base.geometry_mode,
        cell_asset_mode=base.cell_asset_mode,
        rollout_revision=base.rollout_revision,
        geometry_engine_version=base.geometry_engine_version,
        virtual_renderer_version=base.virtual_renderer_version,
        preprocessing_version=base.preprocessing_version,
        candidate_geometry=StructuredGeometryCandidateSnapshot.from_config_payload(
            DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2.to_payload()
        ),
    )


def _manifest() -> dict[str, object]:
    return deepcopy(current_pipeline_manifest())


def _component(manifest: dict[str, object], stage: str) -> dict[str, object]:
    components = cast(dict[str, object], manifest["components"])
    return cast(dict[str, object], components[stage])


def _checkpoint(
    fingerprint: str,
    completed_count: int,
    status: str = "processing",
) -> dict[str, object]:
    completed = PIPELINE_STAGES[:completed_count]
    return {
        "completedStages": list(completed),
        "contractVersion": FILE_CHECKPOINT_VERSION,
        "fileExecutionKey": file_execution_key(SOURCE_SHA256, fingerprint),
        "nextStage": (
            PIPELINE_STAGES[completed_count] if completed_count < len(PIPELINE_STAGES) else None
        ),
        "pipelineFingerprint": fingerprint,
        "schemaVersion": 1,
        "sourceChecksumSha256": SOURCE_SHA256,
        "status": status,
    }


def test_current_manifest_is_valid_and_all_local_artifacts_match() -> None:
    manifest = _manifest()

    assert validate_pipeline_manifest(manifest) == manifest
    verify_manifest_artifacts(manifest, REPOSITORY_ROOT)

    components = cast(dict[str, dict[str, object]], manifest["components"])
    assert components["sequence_ocr"]["maturity"] == "manual_review_only"
    assert components["symbol_inference"]["maturity"] == "bootstrap_manual_review_only"


@pytest.mark.parametrize(
    ("relative_path", "sha256", "code"),
    [
        ("artifacts/not-present.bin", "b" * 64, "IMAGE_PIPELINE_ARTIFACT_MISSING"),
        (
            "ai_docs/quality/m5-image-benchmark-report.json",
            "b" * 64,
            "IMAGE_PIPELINE_ARTIFACT_DRIFT",
        ),
    ],
)
def test_artifact_verification_fails_closed(
    relative_path: str,
    sha256: str,
    code: str,
) -> None:
    manifest = _manifest()
    artifacts = cast(
        list[dict[str, object]],
        _component(manifest, "board_detection")["artifacts"],
    )
    artifacts[0]["relativePath"] = relative_path
    artifacts[0]["sha256"] = sha256

    with pytest.raises(ImagePipelineContractError) as error:
        verify_manifest_artifacts(manifest, REPOSITORY_ROOT)

    assert error.value.code == code


def test_golden_envelope_and_schema_are_current() -> None:
    expected = build_pipeline_envelope(_manifest())
    golden = json.loads(GOLDEN_MANIFEST.read_text(encoding="utf-8"))
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))

    assert validate_pipeline_envelope(golden) == expected
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["manifest"]["$ref"] == "#/$defs/manifest"


def test_fingerprint_is_independent_of_json_key_order() -> None:
    manifest = _manifest()
    reordered = json.loads(json.dumps(manifest, sort_keys=True))

    assert pipeline_fingerprint(reordered) == pipeline_fingerprint(manifest)


@pytest.mark.parametrize(
    ("stage", "field", "replacement"),
    [
        ("sequence_ocr", "modelVersion", "replacement-ocr-v2"),
        ("symbol_inference", "modelVersion", "replacement-symbol-v2"),
        ("symbol_inference", "calibrationVersion", "replacement-calibration-v2"),
        ("board_detection", "adapterVersion", "replacement-detector-v3"),
    ],
)
def test_component_drift_changes_fingerprint_and_file_execution_key(
    stage: str,
    field: str,
    replacement: str,
) -> None:
    baseline = _manifest()
    changed = _manifest()
    _component(changed, stage)[field] = replacement

    baseline_fingerprint = pipeline_fingerprint(baseline)
    changed_fingerprint = pipeline_fingerprint(changed)

    assert changed_fingerprint != baseline_fingerprint
    assert file_execution_key(SOURCE_SHA256, changed_fingerprint) != file_execution_key(
        SOURCE_SHA256,
        baseline_fingerprint,
    )


def test_same_source_and_pipeline_have_one_execution_key() -> None:
    fingerprint = pipeline_fingerprint(_manifest())

    first = file_execution_key(SOURCE_SHA256, fingerprint)
    second = file_execution_key(SOURCE_SHA256, fingerprint)

    assert first == second
    assert len(first) == 64


def test_legacy_rollout_preserves_historical_pipeline_fingerprint() -> None:
    historical = pipeline_fingerprint(_manifest())

    assert effective_pipeline_fingerprint(historical, _rollout(GeometryRolloutMode.LEGACY)) == (
        historical
    )


def test_structured_rollout_is_checksum_bound_and_rejects_checkpoint_drift() -> None:
    historical = pipeline_fingerprint(_manifest())
    snapshot = _rollout(GeometryRolloutMode.STRUCTURED_DEFAULT)
    payload = snapshot.to_payload()

    assert GeometryPipelineRolloutSnapshot.from_payload(payload) == snapshot
    assert effective_pipeline_fingerprint(historical, snapshot) != historical

    payload["rolloutRevision"] = 4
    with pytest.raises(ImagePipelineContractError) as error:
        GeometryPipelineRolloutSnapshot.from_payload(payload)
    assert error.value.code == "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_DRIFT"


def test_shadow_candidate_config_is_pinned_without_changing_v1_snapshots() -> None:
    historical = pipeline_fingerprint(_manifest())
    v1_shadow = _rollout(GeometryRolloutMode.STRUCTURED_SHADOW)
    candidate = _candidate_rollout()

    assert v1_shadow.to_payload()["schemaVersion"] == "virtual-geometry-rollout-snapshot-v1"
    assert "candidateGeometry" not in v1_shadow.to_payload()
    assert candidate.to_payload()["schemaVersion"] == "virtual-geometry-rollout-snapshot-v2"
    assert GeometryPipelineRolloutSnapshot.from_payload(candidate.to_payload()) == candidate
    assert candidate.candidate_geometry is not None
    assert (
        candidate.candidate_geometry.config_checksum_sha256
        == DEFAULT_STRUCTURED_GEOMETRY_CONFIG_V2.checksum_sha256
    )
    assert effective_pipeline_fingerprint(historical, candidate) != effective_pipeline_fingerprint(
        historical, v1_shadow
    )


def test_shadow_candidate_snapshot_rejects_config_tampering_and_non_shadow_use() -> None:
    payload = _candidate_rollout().to_payload()
    candidate = cast(dict[str, object], payload["candidateGeometry"])
    config = cast(dict[str, object], candidate["config"])
    config["activationAllowed"] = True

    with pytest.raises(ImagePipelineContractError) as drift:
        GeometryPipelineRolloutSnapshot.from_payload(payload)
    assert drift.value.code in {
        "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_INVALID",
        "IMAGE_STRUCTURED_GEOMETRY_CANDIDATE_SNAPSHOT_DRIFT",
    }

    with pytest.raises(ImagePipelineContractError) as invalid_mode:
        GeometryPipelineRolloutSnapshot(
            geometry_mode=GeometryRolloutMode.STRUCTURED_DEFAULT,
            cell_asset_mode=CellAssetRolloutMode.VIRTUAL_DEFAULT,
            rollout_revision=1,
            geometry_engine_version=STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
            virtual_renderer_version=VIRTUAL_CELL_RENDERER_VERSION,
            preprocessing_version=SYMBOL_RGB_PREPROCESSING_VERSION,
            candidate_geometry=_candidate_rollout().candidate_geometry,
        )
    assert invalid_mode.value.code == "IMAGE_GEOMETRY_ROLLOUT_SNAPSHOT_INVALID"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda manifest: manifest.update({"contractVersion": "unsupported-v2"}),
            "IMAGE_PIPELINE_VERSION_UNSUPPORTED",
        ),
        (
            lambda manifest: manifest.update({"stages": [*PIPELINE_STAGES[:-1], "manual_review"]}),
            "IMAGE_PIPELINE_STAGE_ORDER_INVALID",
        ),
        (
            lambda manifest: cast(
                list[dict[str, object]],
                _component(manifest, "sequence_ocr")["artifacts"],
            )[0].update({"sha256": "ABC"}),
            "IMAGE_PIPELINE_CHECKSUM_INVALID",
        ),
        (
            lambda manifest: cast(
                list[dict[str, object]],
                _component(manifest, "sequence_ocr")["artifacts"],
            )[0].update({"relativePath": "../model.bin"}),
            "IMAGE_PIPELINE_PATH_UNSAFE",
        ),
        (
            lambda manifest: cast(
                dict[str, object],
                cast(dict[str, object], manifest["policies"])["reviewBoundary"],
            ).update({"required": False}),
            "IMAGE_PIPELINE_REVIEW_BOUNDARY_INVALID",
        ),
    ],
)
def test_manifest_rejects_contract_drift(
    mutation: Callable[[dict[str, object]], object],
    code: str,
) -> None:
    manifest = _manifest()
    mutation(manifest)

    with pytest.raises(ImagePipelineContractError) as error:
        validate_pipeline_manifest(manifest)

    assert error.value.code == code


def test_envelope_rejects_fingerprint_drift() -> None:
    envelope = build_pipeline_envelope(_manifest())
    envelope["pipelineFingerprint"] = "b" * 64

    with pytest.raises(ImagePipelineContractError) as error:
        validate_pipeline_envelope(envelope)

    assert error.value.code == "IMAGE_PIPELINE_FINGERPRINT_MISMATCH"


def test_checkpoint_requires_ordered_prefix_and_review_boundary() -> None:
    fingerprint = pipeline_fingerprint(_manifest())
    before_review = _checkpoint(fingerprint, 6, "waiting_for_review")

    assert validate_file_checkpoint(before_review) == before_review

    wrong_status = _checkpoint(fingerprint, 6, "processing")
    with pytest.raises(ImagePipelineContractError) as error:
        validate_file_checkpoint(wrong_status)
    assert error.value.code == "IMAGE_PIPELINE_REVIEW_BOUNDARY_INVALID"

    gap = _checkpoint(fingerprint, 3)
    cast(list[str], gap["completedStages"])[1] = "board_detection"
    with pytest.raises(ImagePipelineContractError) as error:
        validate_file_checkpoint(gap)
    assert error.value.code == "IMAGE_PIPELINE_CHECKPOINT_INVALID"


def test_checkpoint_transition_is_idempotent_or_one_stage_forward() -> None:
    fingerprint = pipeline_fingerprint(_manifest())
    initial = _checkpoint(fingerprint, 0)
    after_discovery = _checkpoint(fingerprint, 1)

    validate_checkpoint_transition(initial, initial)
    validate_checkpoint_transition(initial, after_discovery)

    with pytest.raises(ImagePipelineContractError) as error:
        validate_checkpoint_transition(initial, _checkpoint(fingerprint, 2))
    assert error.value.code == "IMAGE_PIPELINE_CHECKPOINT_INVALID"


def test_waiting_checkpoint_can_resume_after_manual_review() -> None:
    fingerprint = pipeline_fingerprint(_manifest())
    waiting = _checkpoint(fingerprint, 6, "waiting_for_review")
    after_review = _checkpoint(fingerprint, 7, "processing")
    completed = _checkpoint(fingerprint, 8, "completed")

    validate_checkpoint_transition(waiting, after_review)
    validate_checkpoint_transition(after_review, completed)


def test_checkpoint_rejects_provenance_drift() -> None:
    fingerprint = pipeline_fingerprint(_manifest())
    previous = _checkpoint(fingerprint, 0)
    current = _checkpoint("b" * 64, 1)

    with pytest.raises(ImagePipelineContractError) as error:
        validate_checkpoint_transition(previous, current)

    assert error.value.code == "IMAGE_PIPELINE_CHECKPOINT_PROVENANCE_MISMATCH"
