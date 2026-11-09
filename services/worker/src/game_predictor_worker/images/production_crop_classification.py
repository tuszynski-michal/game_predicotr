"""Pinned classifier and human evidence adapters for a paired crop diagnostic."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, cast

from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.symbol_model_snapshots import (
    LAB_RGB_SYMBOL_MODEL_VERSION,
    SymbolModelJobSnapshot,
)

from .lab_rgb_preprocessing import LAB_RGB_PREPROCESSING_VERSION
from .pipeline_contract import (
    SYMBOL_RGB_PREPROCESSING_VERSION,
    build_pipeline_envelope,
    current_pipeline_manifest,
    validate_pipeline_envelope,
)
from .production_crop_artifacts import safe_path
from .symbol_confidence import CALIBRATION_VERSION
from .symbol_model_release import build_symbol_predictions
from .symbol_onnx import LocalSymbolOnnxAdapter, preprocess_rgb_batch, symbol_onnx_variant_arguments


def current_runtime_pin(model: SymbolModelJobSnapshot) -> dict[str, Any]:
    """Pin today's actual manual boundary, never claim it was the import's policy."""
    body = {
        "version": "production-crop-diagnostic-runtime-v1",
        "scope": "current-diagnostic-runtime",
        "pipeline": build_pipeline_envelope(current_pipeline_manifest()),
        "model": model.to_payload(),
        "inputScope": {
            "modelVersion": model.model_version,
            "inputSize": model.input_size,
            "cropSize": model.crop_output_size,
            "preprocessingVersion": LAB_RGB_PREPROCESSING_VERSION
            if model.model_version == LAB_RGB_SYMBOL_MODEL_VERSION
            else SYMBOL_RGB_PREPROCESSING_VERSION,
        },
    }
    return {**body, "sha256": digest(body)}


def acceptance_policy(
    model: SymbolModelJobSnapshot, evidence: dict[str, Any] | None
) -> dict[str, Any]:
    unavailable = {"state": "unavailable", "reason": "CLASS_ACCEPTANCE_POLICY_UNAVAILABLE"}
    if evidence is None:
        return unavailable
    runtime = evidence.get("runtime")
    if not isinstance(runtime, dict):
        return unavailable
    expected = current_runtime_pin(model)
    if runtime.get("sha256") != digest({k: v for k, v in runtime.items() if k != "sha256"}) or any(
        runtime.get(k) != expected[k] for k in ("version", "scope", "model", "inputScope")
    ):
        return unavailable
    try:
        envelope = cast(dict[str, Any], validate_pipeline_envelope(runtime.get("pipeline")))
    except ValueError:
        return unavailable
    enabled = envelope["manifest"]["policies"]["reviewBoundary"]["autoAcceptEnabled"]
    if (
        type(evidence.get("runtimeAutoAccept")) is not bool
        or evidence["runtimeAutoAccept"] != enabled
    ):
        return unavailable
    report = evidence.get("report", {})
    inputs, policy = report.get("inputs", {}), report.get("policy", {})
    versions = {"symbol-temperature-calibration-v1", CALIBRATION_VERSION}
    if report.get("temperature") != model.temperature:
        return unavailable
    if "version" in report:
        # candidate_gate's actual calibration has no threshold policy. The
        # verified manifest/classes artifact binds its model and input scope.
        manifest = evidence.get("candidateManifest", {})
        onnx = manifest.get("artifacts", {}).get("onnx", {})
        if (
            report.get("version") not in versions
            or manifest.get("manifestVersion") != "symbol-candidate-manifest-v1"
            or evidence.get("candidateManifestSha256") != model.manifest_checksum_sha256
            or manifest.get("classCodes") != list(model.class_codes)
            or evidence.get("classCodes") != list(model.class_codes)
            or onnx.get("sha256") != model.onnx_checksum_sha256
            or onnx.get("relativePath") != model.onnx_relative_path
            or evidence.get("configurationInputSize") != model.input_size
            or model.model_version != "spatial-symbol-cnn-onnx-v1"
        ):
            return unavailable
    elif (
        report.get("schemaVersion") != 1
        or report.get("calibrationVersion") not in versions
        or inputs.get("modelVersion") != model.model_version
        or report.get("classes") != list(model.class_codes)
        or inputs.get("onnxArtifactSha256") != model.onnx_checksum_sha256
        or policy.get("policyVersion") != "symbol-confidence-policy-v1"
    ):
        return unavailable
    if enabled is False:
        return {"state": "disabled", "reason": "CLASS_AUTO_ACCEPT_DISABLED", "threshold": None}
    # M6 reports bind legacy model versions but do not attest RGB96 crop and
    # LAB preprocessing scope. Their threshold cannot certify that contract.
    if model.model_version == LAB_RGB_SYMBOL_MODEL_VERSION:
        return {"state": "unavailable", "reason": "CLASS_ACCEPTANCE_PREPROCESSING_UNAVAILABLE"}
    if report.get("temperature") != max(0.50, model.temperature):
        return unavailable
    auto = policy.get("autoAccept", {})
    if auto.get("enabled") is False:
        return {"state": "disabled", "reason": "CLASS_AUTO_ACCEPT_DISABLED", "threshold": None}
    threshold = auto.get("threshold")
    if (
        auto.get("enabled") is not True
        or type(threshold) not in (int, float)
        or not math.isfinite(threshold)
        or not 0 <= threshold <= 1
    ):
        return unavailable
    return {"state": "available", "threshold": threshold, "reason": None}


def human_class(
    cell: dict[str, Any],
    events: list[dict[str, Any]],
    board: dict[str, Any],
    active_codes: dict[str, str],
) -> dict[str, Any]:
    """No label derives from confidence, status alone, or a free-form last actor."""
    reason = "CLASS_CURRENT_APPROVAL_UNAVAILABLE"
    pairs = (
        ("crop_sample_id", "approved_crop_sample_id"),
        ("crop_checksum_sha256", "approved_crop_checksum_sha256"),
        ("geometry_revision", "approved_geometry_revision"),
        ("asset_mode", "approved_asset_mode"),
        ("source_geometry_revision_id", "approved_source_geometry_revision_id"),
        ("render_spec_checksum_sha256", "approved_render_spec_checksum_sha256"),
        ("rendered_pixel_checksum_sha256", "approved_rendered_pixel_checksum_sha256"),
    )
    code = active_codes.get(str(cell.get("assigned_symbol_id")))
    if (
        cell.get("review_state") != "approved"
        or cell.get("quality_issue") is not None
        or not code
        or cell.get("source_available") is not True
        or cell.get("source_visibility") not in (None, "full")
        or cell.get("asset_mode") != "virtual_source"
        or cell.get("geometry_revision") != board.get("geometry_revision")
        or cell.get("source_geometry_revision_id") != board.get("source_geometry_revision_id")
        or cell.get("sequence_number") != board.get("sequence_number")
        or any(cell.get(a) is None or cell.get(a) != cell.get(b) for a, b in pairs)
    ):
        return {"state": "unavailable", "reason": reason}
    matches = [
        e
        for e in events
        if e.get("cell_review_id") == cell.get("id")
        and (
            e.get("action") in ("approve", "reassign")
            or (
                e.get("action") == "board_synchronized"
                and cell.get("assignment_source") == "board_decision"
                and e.get("human_board_decision") is True
            )
        )
        and isinstance(e.get("actor"), str)
        and e["actor"].strip()
        and not e["actor"].strip().casefold().startswith(("system", "worker"))
        and e.get("review_state") == "approved"
        and e.get("quality_issue") is None
        and e.get("assigned_symbol_id") == cell.get("assigned_symbol_id")
        and e.get("cell_revision") == cell.get("revision")
        and all(e.get(a) == cell.get(a) and e.get(b) == cell.get(b) for a, b in pairs)
    ]
    if len(matches) != 1:
        return {"state": "unavailable", "reason": "CLASS_HUMAN_APPROVAL_UNAVAILABLE"}
    return {
        "state": "available",
        "code": code,
        "cellReviewId": cell["id"],
        "cellRevision": cell["revision"],
        "event": matches[0],
        "renderSpecSha256": cell["render_spec_checksum_sha256"],
        "renderedPixelSha256": cell["rendered_pixel_checksum_sha256"],
    }


class PinnedClassifier:
    def __init__(
        self,
        payload: dict[str, Any],
        *,
        repository_root: Path,
        artifact_root: Path,
        policy: dict[str, Any] | None = None,
    ) -> None:
        self.model = SymbolModelJobSnapshot.from_payload(payload)
        if self.model.inference_mode != "model":
            raise ValueError("CLASS_MODEL_UNAVAILABLE")
        root = repository_root if self.model.storage_root.value == "repository" else artifact_root
        self.adapter = LocalSymbolOnnxAdapter(
            safe_path(root, self.model.onnx_relative_path),
            expected_sha256=self.model.onnx_checksum_sha256,
            class_codes=self.model.class_codes,
            input_size=self.model.input_size,
            **symbol_onnx_variant_arguments(self.model.model_version),
        )
        self.policy = acceptance_policy(self.model, policy)

    def predict(self, rasters: list[Any]) -> list[dict[str, Any]]:
        if not rasters:
            return []
        values = self.adapter.infer(
            preprocess_rgb_batch(
                [r.rgb for r in rasters],
                input_size=self.model.input_size,
                model_version=self.model.model_version,
            )
        )
        predictions = build_symbol_predictions(
            values.logits,
            temperature=max(0.50, self.model.temperature),
            class_codes=self.model.class_codes,
        )
        return [
            {
                "code": p.symbol_code,
                "confidence": p.confidence,
                "accepted": p.confidence >= self.policy["threshold"]
                if self.policy["state"] == "available"
                else False
                if self.policy["state"] == "disabled"
                else None,
                "acceptanceState": self.policy["state"],
            }
            for p in predictions
        ]
