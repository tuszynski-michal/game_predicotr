"""Qualified cohort bindings and validation-only gates for independent inference."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .annotations import read_checked
from .catalog import Catalog
from .run_contracts import RunState
from .run_files import verify_artifact
from .snapshot import reject_links, sha
from .symbol_models import compare, evaluate_frozen_fusion, model_pair
from .symbol_training_manifest import SymbolTrainingAdapter, SymbolTrainingInputs


@dataclass
class BatchInputs:
    inputs: SymbolTrainingInputs
    live: dict[str, str]
    external_sources: dict[str, str]
    photo_pixels: list[str]
    protected: list[Path]


def batch_inputs(training: Path, generation: int) -> BatchInputs:
    if generation != 3:
        inputs = SymbolTrainingAdapter(training).validate()
        return BatchInputs(
            inputs,
            dict(inputs.payload["live_bindings"]),
            {},
            sorted(inputs.payload["photo_pixel_groups"]),
            [],
        )
    # Feedback qualification imports the batch renderer; dispatch only after module loading.
    from .symbol_feedback import SymbolFeedbackAdapter, resolve_source

    adapter = SymbolFeedbackAdapter(training)
    inputs = adapter.validate()
    original = Path(inputs.payload["qualification"]["recording_reference"])
    live = {
        str(resolve_source(Path(path), original, adapter.source_root)): checksum
        for path, checksum in inputs.payload["live_bindings"].items()
    }
    if adapter.location_path.exists():
        live[str(adapter.location_path)] = sha(adapter.location_path)
    external = {"feedback:" + row["sha256"]: row["sha256"] for row in inputs.payload["folder_rows"]}
    return BatchInputs(
        inputs,
        live,
        external,
        sorted(inputs.payload["photo_partitions"]),
        list(adapter.protected_paths()),
    )


def exclusion_hashes(context: BatchInputs, catalog: Catalog, excluded: set[str]) -> set[str]:
    if not excluded <= set(catalog.sources) | set(context.external_sources):
        raise ValueError("SYMBOL_BATCH_EXCLUSION_CATALOG_MISMATCH")
    return {
        catalog.sources[sid].sha256 if sid in catalog.sources else context.external_sources[sid]
        for sid in excluded
    }


def require_class_reference(candidate: dict[str, Any], baseline: dict[str, Any]) -> None:
    old = {row["class"]: row for row in baseline["per_class"]}
    rows = candidate["per_class"]
    if (
        candidate["samples"] != baseline["samples"]
        or candidate["samples"] != 84
        or not 83 <= candidate["correct"] <= 84
        or len(old) != 10
        or len(rows) != 10
        or {row["class"] for row in rows} != set(old)
        or any(
            row["samples"] != old[row["class"]]["samples"]
            or row["samples"] < 1
            or row["correct"] < old[row["class"]]["correct"]
            for row in rows
        )
    ):
        raise ValueError("SYMBOL_BATCH_FEEDBACK_CLASS_REGRESSION")


def feedback_qualification(
    evidence: Path,
    context: BatchInputs,
    reports: dict[str, dict[str, Any]],
    calibration: dict[str, Any],
    required_pins: dict[str, str],
) -> dict[str, str]:
    """Recompute the frozen V1 class gate from pinned real reports, never test labels."""
    if not evidence.is_absolute():
        raise ValueError("SYMBOL_BATCH_ABSOLUTE_PATH_REQUIRED")
    reject_links(evidence)
    proof = read_checked(evidence)
    pair = model_pair(3)
    candidate = evaluate_frozen_fusion(
        reports[pair[0]]["predictions"], reports[pair[1]]["predictions"], calibration
    )
    if (
        proof.get("format") != "mumie-symbol-feedback-iteration-v1"
        or proof["manifest_id"] != context.inputs.manifest_id
        or proof["calibration"] != calibration
        or proof["validation"] != candidate
        or proof["pair_qualified"] is not True
        or proof["qualification"] != dict.fromkeys(("rgb", "gray", "fusion"), True)
    ):
        raise ValueError("SYMBOL_BATCH_FEEDBACK_QUALIFICATION_INVALID")
    pins = proof["input_hashes"]
    if any(pins.get(path) != checksum for path, checksum in required_pins.items()):
        raise ValueError("SYMBOL_BATCH_FEEDBACK_REPORT_BINDING_INVALID")
    baselines = []
    base_manifest = Path(context.inputs.payload["base_manifest"]).stem
    for name, checksum in pins.items():
        path = Path(name)
        if not path.is_absolute():
            raise ValueError("SYMBOL_BATCH_ABSOLUTE_PATH_REQUIRED")
        reject_links(path)
        if sha(path) != checksum:
            raise ValueError("SYMBOL_BATCH_FEEDBACK_INPUT_DRIFT")
        if path.name != "state.json":
            continue
        state = read_checked(path)
        baseline: dict[str, dict[str, Any]] = {}
        for raw in state.get("runs", {}).values():
            run = RunState.model_validate(raw)
            if (
                run.request.model_version not in model_pair(1)
                or run.request.manifest_id != base_manifest
            ):
                continue
            if (
                run.status != "succeeded"
                or run.report is None
                or run.request.model_version in baseline
            ):
                raise ValueError("SYMBOL_BATCH_FEEDBACK_BASELINE_INVALID")
            report = verify_artifact(path.parent, run.report)
            if pins.get(str(report)) != run.report.sha256:
                raise ValueError("SYMBOL_BATCH_FEEDBACK_BASELINE_INVALID")
            baseline[run.request.model_version] = json.loads(report.read_bytes())["metrics"][
                "predictions"
            ]
        if baseline:
            if set(baseline) != set(model_pair(1)):
                raise ValueError("SYMBOL_BATCH_FEEDBACK_BASELINE_INVALID")
            baselines.append(baseline)
    if len(baselines) != 1:
        raise ValueError("SYMBOL_BATCH_FEEDBACK_BASELINE_INVALID")
    old_pair = model_pair(1)
    rgb, gray = [baselines[0][model] for model in old_pair]
    for current, old in [
        (reports[pair[0]]["predictions"], rgb),
        (reports[pair[1]]["predictions"], gray),
    ]:
        if any(current[key] != old[key] for key in ("classes", "labels", "sample_ids")):
            raise ValueError("SYMBOL_BATCH_FEEDBACK_BASELINE_INVALID")
    baseline = evaluate_frozen_fusion(rgb, gray, compare(rgb, gray))
    if baseline != proof["baseline_validation"]:
        raise ValueError("SYMBOL_BATCH_FEEDBACK_BASELINE_INVALID")
    for branch in ("rgb", "gray", "fusion"):
        require_class_reference(candidate[branch], baseline[branch])
    return {**pins, str(evidence): sha(evidence)}
