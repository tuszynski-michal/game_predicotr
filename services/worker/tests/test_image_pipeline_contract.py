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
    ImagePipelineContractError,
    build_pipeline_envelope,
    current_pipeline_manifest,
    file_execution_key,
    pipeline_fingerprint,
    validate_checkpoint_transition,
    validate_file_checkpoint,
    validate_pipeline_envelope,
    validate_pipeline_manifest,
    verify_manifest_artifacts,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_MANIFEST = REPOSITORY_ROOT / "ai_docs/quality/m7-image-pipeline-manifest-v1.json"
MANIFEST_SCHEMA = REPOSITORY_ROOT / "ai_docs/quality/image-pipeline-manifest-v1.schema.json"
SOURCE_SHA256 = "a" * 64


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
