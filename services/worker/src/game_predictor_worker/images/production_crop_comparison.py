"""Paired real production crops, immutable per-instance denominators and game gates."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from game_predictor_api.application.grid_model_evaluation import bundle_sha256
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.symbol_model_snapshots import LAB_RGB_SYMBOL_MODEL_VERSION

from ..training_core.grid_correction_metrics import CorrectionControlPhoto, evaluate_photo
from ..training_core.grid_evaluation import predictions
from .grid_rescue_assessment import load_assessment_engine
from .production_cell_evaluation import ProductionContentObserver, reference_context, render_cells
from .production_cell_run import summarize_content
from .production_crop_artifacts import (
    checked,
    read_json,
    safe_path,
    save_raster,
    sealed,
    write_json,
)
from .production_crop_classification import PinnedClassifier
from .production_crop_inputs import analyse_with_inputs

REPORT_VERSION = "production-crop-comparison-v1"


def comparison_summary(photos: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_content(photos)
    summary["newMissingInstances"] = sum(
        cell["candidate"]["finalContentState"] == "missing"
        and cell["base"]["finalContentState"] != "missing"
        for photo in photos
        for board in photo["boards"]
        for cell in board["cells"]
        if cell["contentState"] == "visible"
    )
    return summary


def paired_gate(summary: dict[str, Any], classes: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = list(summary["reasonCodes"])
    if summary["visible"] == 0 or summary["unknown"] > 0.1 * summary["slots"]:
        reasons.append("CONTENT_REFERENCE_INSUFFICIENT")
    if not classes or any(c["state"] != "available" for c in classes):
        reasons.append("CLASS_REFERENCE_OR_MODEL_UNAVAILABLE")
    policies = {c.get("acceptanceState") for c in classes}
    if not policies or policies - {"available", "disabled"}:
        reasons.append("CLASS_ACCEPTANCE_POLICY_UNAVAILABLE")
    damage = sum(
        summary[k]
        for k in (
            "degradedInstances",
            "newWrongCells",
            "newTies",
            "newForeignSymbols",
            "newMatchAmbiguities",
        )
    )
    class_damage = sum(
        c.get("baseCorrect") is True and c.get("candidateCorrect") is False for c in classes
    )
    false_accept = sum(
        c.get("candidateFalseAccept") is True and c.get("baseFalseAccept") is not True
        for c in classes
    )
    base_missing = summary["base"].get("missing", 0)
    candidate_missing = summary["candidate"].get("missing", 0)
    new_missing = max(summary.get("newMissingInstances", 0), candidate_missing - base_missing)
    improved = (
        summary["candidate"]["clipped"] + candidate_missing
        < summary["base"]["clipped"] + base_missing
    )
    if damage or new_missing or class_damage or false_accept:
        state = "regression"
    elif reasons:
        state = "not_evaluable"
    elif not improved:
        state = "no_improvement"
    else:
        state = "candidate"
    return {
        "state": state,
        "reasonCodes": sorted(set(reasons)),
        "newContentDamage": damage,
        "newMissing": new_missing,
        "newClassificationErrors": class_damage,
        "newFalseAccepts": false_accept
        if policies
        and not policies - {"available", "disabled"}
        and all(c["state"] == "available" for c in classes)
        else None,
        "automaticAcceptance": "disabled"
        if policies == {"disabled"}
        else "evaluated"
        if policies == {"available"}
        else "mixed"
        if policies == {"available", "disabled"}
        else "unavailable",
        "fewerClipped": improved,
        "qualificationAllowed": False,
    }


class _SnapshotView:
    def __init__(self, snapshot: Any, source: dict[str, Any], frozen: dict[str, Any]) -> None:
        self.manifest, self.snapshot, self.source, self.frozen = (
            snapshot.manifest,
            snapshot,
            source,
            frozen,
        )

    def frame(self, *_args: Any, **_kwargs: Any) -> Any:
        return self.snapshot.frame(self.frozen, self.frozen["role"], validation_purpose="A")


def absolute_reference(summary: dict[str, Any], classes: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = list(summary["reasonCodes"])
    if not summary["visible"] or summary["unknown"] > 0.1 * summary["slots"]:
        reasons.append("CONTENT_REFERENCE_INSUFFICIENT")
    known = [c for c in classes if c["state"] == "available"]
    if len(known) != len(classes) or not classes:
        reasons.append("CLASS_REFERENCE_OR_MODEL_UNAVAILABLE")
    accepts_known = (
        bool(classes)
        and len(known) == len(classes)
        and all(c.get("acceptanceState") in ("available", "disabled") for c in known)
    )
    if not accepts_known:
        reasons.append("CLASS_ACCEPTANCE_POLICY_UNAVAILABLE")
    return {
        "state": "not_evaluable" if reasons else "reference",
        "purpose": "absolute-reference",
        "qualificationAllowed": False,
        "reasonCodes": sorted(set(reasons)),
        "slots": summary["slots"],
        "visible": summary["visible"],
        "unknown": summary["unknown"],
        "content": summary["base"],
        "classification": {
            "available": len(known),
            "correct": sum(c.get("baseCorrect") is True for c in known),
            "falseAccepts": sum(c.get("baseFalseAccept") is True for c in known)
            if accepts_known
            else None,
        },
    }


def _labels(targets: list[dict[str, Any]]) -> list[Any]:
    return [np.asarray([[p["x"], p["y"]] for p in t["nodes"]], dtype=np.float32) for t in targets]


def _verify_class_pixels(photo: dict[str, Any], frame: Any) -> dict[str, Any]:
    verified = deepcopy(photo)
    for target, nodes in zip(verified["targets"], _labels(verified["targets"]), strict=True):
        if "classSourceNodes" in target:
            nodes = _labels([{"nodes": target["classSourceNodes"]}])[0]
        context = reference_context(target)
        if context is None or not any(t["state"] == "available" for t in target["classes"]):
            continue
        rasters = render_cells(frame, nodes, target, context)
        for truth, raster in zip(target["classes"], rasters, strict=True):
            if truth["state"] == "available":
                if truth.get("renderedPixelSha256") != raster.get("renderedPixelSha256"):
                    truth.update(state="unavailable", reason="CLASS_APPROVED_RASTER_CHANGED")
                else:
                    truth["pixelVerification"] = "current-human-geometry-production-render"
    return verified


def _pair(
    snapshot: Any,
    photo: dict[str, Any],
    frame: Any,
    found: list[Any],
    engine: Any,
    *,
    kind: str,
    u: float | None,
    root: Path,
    repository_root: Path,
    artifact_root: Path,
    lab_model: dict[str, Any] | None = None,
    lab_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    targets = photo["targets"]
    source = {**photo["frozenSource"], "targets": targets}
    labels = _labels(targets)
    control = CorrectionControlPhoto(
        photo["sourceId"],
        photo["sourceId"],
        frame.source.source_checksum_sha256,
        tuple(labels),
        lambda: frame.rgb,
        full_geometry=len(targets) == 9,
    )
    measured = evaluate_photo(
        control.source_id,
        control.group_id,
        labels,
        predictions(found),
        full_geometry=control.full_geometry,
    )
    contexts = [reference_context(t) for t in targets]
    valid_contexts = [c for c in contexts if c is not None]
    if len(valid_contexts) != len(targets) or len({digest(c) for c in valid_contexts}) != 1:
        return {"state": "unavailable", "reasonCodes": ["CROP_CONTEXT_NOT_UNIQUE"]}
    context = valid_contexts[0]
    classifier_payload = lab_model or context["classifier"]
    if lab_model is None and classifier_payload["modelVersion"] == LAB_RGB_SYMBOL_MODEL_VERSION:
        return {"state": "unavailable", "reasonCodes": ["CROP_LEGACY_CLASSIFIER_REQUIRED"]}
    original = context["renderConfiguration"]
    configurations = {
        "base": {**original, "paddingFraction": 0.08},
        "candidate": {**original, "paddingFraction": 0.0},
    }
    if lab_model is not None:
        configurations = {
            name: {**original, "paddingFraction": 0.0, "outputWidth": 96, "outputHeight": 96}
            for name in ("base", "candidate")
        }
    retained: dict[tuple[str, int, int], Any] = {}
    observer = ProductionContentObserver(
        _SnapshotView(snapshot, source, photo["frozenSource"]),
        photo["frozenSource"]["role"],
        u=u,
        sources={photo["sourceId"]: source},
        render_configurations=configurations,
        raster_sink=lambda name, p, r: retained.__setitem__((name, p, r.cell_index), r),
        physical_slots={t["positionIndex"]: i for i, t in enumerate(targets)}
        if kind == "human"
        else None,
        input_reader=(lambda *_args: None) if kind == "human" else None,
    )
    observed = observer(
        control, frame.rgb, {name: (found, measured, engine) for name in ("base", "candidate")}
    )
    classifier, classifier_reason = None, None
    try:
        classifier = PinnedClassifier(
            classifier_payload,
            repository_root=repository_root,
            artifact_root=artifact_root,
            policy=lab_policy if lab_model else targets[0].get("classificationPolicy"),
        )
    except (OSError, ValueError) as error:
        classifier_reason = getattr(error, "code", "CLASS_MODEL_UNAVAILABLE")
    inference: dict[tuple[str, int, int], Any] = {}
    rasters = []
    # Small batches, stable ordering; A never exports visual hints or raster paths.
    keys = sorted(retained)
    for start in range(0, len(keys), 150):
        batch_keys = keys[start : start + 150]
        results = classifier.predict([retained[k] for k in batch_keys]) if classifier else []
        inference.update(zip(batch_keys, results, strict=bool(classifier)))
    for key in keys:
        name, p, cell = key
        raster = retained[key]
        item = {
            "variant": name,
            "predictionIndex": p,
            "cellIndex": cell,
            "pixelSha256": raster.rendered_pixel_checksum_sha256,
            "renderSpecSha256": raster.render_spec_checksum_sha256,
        }
        if photo["role"] == "TRAIN":
            prefix = f"rasters/{photo['sourceId']}/{kind}/{'lab' if lab_model else 'legacy'}"
            item.update(
                save_raster(
                    root,
                    f"{prefix}/{name}-{p}-{cell}.png",
                    raster,
                )
            )
        rasters.append(item)
    classes = []
    for target, board in zip(targets, observed["boards"], strict=True):
        for j, truth in enumerate(target["classes"]):
            item = {
                "positionIndex": target["positionIndex"],
                "sequenceNumber": target["sequenceNumber"],
                "cellIndex": j,
                "classReference": truth,
                "state": "unavailable",
                "reason": classifier_reason or truth.get("reason"),
                "acceptanceState": "unavailable",
            }
            pair = {}
            for name in ("base", "candidate"):
                match = board[name]["matchedPrediction"]
                pred = (
                    None
                    if match is None or board[name]["matchAmbiguous"]
                    else inference.get((name, match, j))
                )
                item[name] = pred
                if truth["state"] == "available" and classifier:
                    item[name + "Correct"] = pred is not None and pred["code"] == truth["code"]
                    item[name + "FalseAccept"] = (
                        None
                        if classifier.policy["state"] == "unavailable"
                        else bool(
                            pred is not None and pred["accepted"] and pred["code"] != truth["code"]
                        )
                    )
                    pair[name] = pred
            if len(pair) == 2 and classifier is not None:
                item.update(
                    state="available", reason=None, acceptanceState=classifier.policy["state"]
                )
            classes.append(item)
    summary = comparison_summary([observed])
    return {
        "state": "available",
        "kind": kind,
        "comparisonKind": "lab-rgb-reference" if lab_model else "legacy-margin-pair",
        "configurations": configurations,
        "classifier": classifier_payload,
        "classifierState": "available" if classifier is not None else "unavailable",
        "acceptancePolicy": classifier.policy if classifier is not None else None,
        "observation": observed,
        "geometryMetrics": measured.as_dict(),
        "rasters": rasters,
        "classification": classes,
        "summary": summary,
        **(
            {"reference": absolute_reference(summary, classes)}
            if lab_model
            else {"gate": paired_gate(summary, classes)}
        ),
        "footprintSemantics": "zero:exact-cell-quad;positive:outer-board-homography-inset",
    }


def _verify_saved(root: Path, value: Any) -> None:
    if isinstance(value, dict):
        if {"path", "sha256", "bytes", "pixelSha256"} <= value.keys():
            path = safe_path(root, value["path"])
            if (
                path.stat().st_size != value["bytes"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != value["sha256"]
            ):
                raise ValueError("CROP_RASTER_CHANGED")
        for item in value.values():
            _verify_saved(root, item)
    elif isinstance(value, list):
        for item in value:
            _verify_saved(root, item)


def _verify_classifier_files(repository: Path, artifacts: Path, report: Any) -> None:
    from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot

    seen = set()
    for photo in report["photos"]:
        for evaluation in photo["geometry"].values():
            for pair in (evaluation, evaluation.get("labRgb", {})):
                payload = pair.get("classifier")
                if payload is None or pair.get("classifierState") != "available":
                    continue
                model = SymbolModelJobSnapshot.from_payload(payload)
                if model.inference_mode != "model" or model.inference_fingerprint in seen:
                    continue
                seen.add(model.inference_fingerprint)
                root = repository if model.storage_root.value == "repository" else artifacts
                path = safe_path(root, model.onnx_relative_path)
                with path.open("rb") as stream:
                    if (
                        hashlib.file_digest(stream, "sha256").hexdigest()
                        != model.onnx_checksum_sha256
                    ):
                        raise ValueError("CROP_CLASSIFIER_CHANGED")


def run_comparison(
    snapshot: Any,
    capture: dict[str, Any],
    *,
    root: Path,
    repository_root: Path,
    artifact_root: Path,
    engine: Any = None,
) -> dict[str, Any]:
    checked(capture, "production-crop-capture-v1")
    if capture["manifestSha256"] != snapshot.manifest_sha256:
        raise ValueError("CROP_COHORT_CHANGED")
    write_json(root, "capture.json", capture)
    grid = capture["gridModel"]
    grid_error = "CROP_GRID_MODEL_UNAVAILABLE"
    if engine is None and grid is not None:
        manifest = grid["manifest"]
        directory = safe_path(artifact_root, manifest["managedDirectory"])
        try:
            engine = load_assessment_engine(directory, bundle_sha256(manifest), 1)
        except (OSError, ValueError):
            if safe_path(root, "report.json").exists():
                raise
            grid_error = "CROP_GRID_MODEL_OR_ARTIFACT_UNAVAILABLE"
    if safe_path(root, "report.json").exists():
        previous = read_json(root, "report.json")
        checked(previous, REPORT_VERSION)
        if previous["captureSha256"] != capture["sha256"]:
            raise ValueError("CROP_CAPTURE_CHANGED")
        for photo in capture["photos"]:
            if photo["state"] == "available":
                snapshot.frame(
                    photo["frozenSource"], photo["frozenSource"]["role"], validation_purpose="A"
                )
        _verify_classifier_files(repository_root, artifact_root, previous)
        _verify_saved(root, previous)
        return previous
    measurement = capture["measurement"]
    u = None if measurement is None else measurement["games"][capture["gameId"]]["u"]
    results = []
    for photo in capture["photos"]:
        photo_measurement = photo.get("measurement", measurement)
        u = (
            None
            if photo_measurement is None
            else photo_measurement["games"][capture["gameId"]]["u"]
        )
        result = {
            "sourceId": photo["sourceId"],
            "role": photo["role"],
            "state": photo["state"],
            "reasonCodes": photo["reasonCodes"],
            "instanceCount": photo["instanceCount"],
            "geometry": {},
            "measurementSha256": None
            if photo_measurement is None
            else photo_measurement.get("sha256"),
            "measurementQualificationState": None
            if photo_measurement is None
            else photo_measurement.get("qualificationState"),
            "measurementUse": "repeatability-only-render-blocked"
            if photo_measurement is not None
            and photo_measurement.get("qualificationState") == "render_contract_blocked"
            else "qualified-or-unavailable",
            "visualExportAllowed": photo["role"] == "TRAIN" and photo["state"] == "available",
        }
        results.append(result)
        if photo["state"] != "available":
            continue
        frame = snapshot.frame(
            photo["frozenSource"], photo["frozenSource"]["role"], validation_purpose="A"
        )
        photo = _verify_class_pixels(photo, frame)
        human = [
            SimpleNamespace(nodes=n, screen_quad=n[[0, 5, 23, 18]])
            for n in _labels(photo["targets"])
        ]
        found_by_kind = {"human": human}
        # Exactly one actual model call per source; both margins share its outputs/routing.
        if engine is not None:
            found_by_kind["model"], result["neuralInput"] = analyse_with_inputs(
                engine, frame, photo, grid, root
            )
            result["modelPredictions"] = [
                {
                    "predictionIndex": i,
                    "nodes": None if d.nodes is None else np.asarray(d.nodes).tolist(),
                    "rawNodes": None
                    if getattr(d, "raw_nodes", None) is None
                    else np.asarray(d.raw_nodes).tolist(),
                    "screenQuad": np.asarray(d.screen_quad).tolist(),
                    "reasonCodes": list(getattr(d, "reasons", [])),
                }
                for i, d in enumerate(found_by_kind["model"])
            ]
        else:
            result["geometry"]["model"] = {
                "state": "unavailable",
                "reasonCodes": [grid_error],
            }
        for kind, found in found_by_kind.items():
            result["geometry"][kind] = _pair(
                snapshot,
                photo,
                frame,
                found,
                engine,
                kind=kind,
                u=u,
                root=root,
                repository_root=repository_root,
                artifact_root=artifact_root,
            )
            result["geometry"][kind]["labRgb"] = (
                {"state": "unavailable", "reasonCodes": ["CROP_LAB_MODEL_UNAVAILABLE"]}
                if capture["labModel"] is None
                else _pair(
                    snapshot,
                    photo,
                    frame,
                    found,
                    engine,
                    kind=kind,
                    u=u,
                    root=root,
                    repository_root=repository_root,
                    artifact_root=artifact_root,
                    lab_model=capture["labModel"],
                    lab_policy=capture.get("labClassificationPolicy"),
                )
            )
    games = []
    lab_games = []
    for role, kind in (
        (role, kind) for role in sorted({p["role"] for p in results}) for kind in ("human", "model")
    ):
        observations, classes = [], []
        missing = False
        for result in results:
            if result["role"] != role:
                continue
            evaluation = result["geometry"].get(kind, {})
            if evaluation.get("state") != "available":
                missing = True
                continue
            observations.append(evaluation["observation"])
            classes.extend(evaluation["classification"])
        summary = comparison_summary(observations)
        if missing:
            summary["reasonCodes"].append("CROP_SELECTED_SOURCE_UNAVAILABLE")
        games.append(
            {
                "gameId": capture["gameId"],
                "geometry": kind,
                "role": role,
                "selectedInstances": sum(p["instanceCount"] for p in results if p["role"] == role),
                "evaluatedInstances": summary["slots"],
                "summary": summary,
                "gate": paired_gate(summary, classes),
            }
        )
        lab_observations, lab_classes = [], []
        lab_missing = False
        for result in results:
            if result["role"] != role:
                continue
            lab = result["geometry"].get(kind, {}).get("labRgb", {})
            if lab.get("state") != "available":
                lab_missing = True
                continue
            lab_observations.append(lab["observation"])
            lab_classes.extend(lab["classification"])
        lab_summary = comparison_summary(lab_observations)
        if lab_missing:
            lab_summary["reasonCodes"].append("CROP_LAB_REFERENCE_UNAVAILABLE")
        lab_games.append(
            {
                "gameId": capture["gameId"],
                "role": role,
                "geometry": kind,
                "selectedInstances": sum(p["instanceCount"] for p in results if p["role"] == role),
                "evaluatedInstances": lab_summary["slots"],
                "reference": absolute_reference(lab_summary, lab_classes),
            }
        )
    states = [g["gate"]["state"] for g in games]
    state = (
        "regression"
        if "regression" in states
        else "not_evaluable"
        if "not_evaluable" in states
        else ("candidate" if states and all(s == "candidate" for s in states) else "no_improvement")
    )
    report = sealed(
        {
            "schemaVersion": REPORT_VERSION,
            "diagnosticOnly": True,
            "qualificationAllowed": False,
            "captureSha256": capture["sha256"],
            "state": state,
            "variantNames": {"base": "legacy08", "candidate": "legacy00"},
            "games": games,
            "labGames": lab_games,
            "accessScope": "internal-diagnostic-metadata",
            "visualExportRule": "TRAIN-and-visualExportAllowed-only",
            "photos": results,
        }
    )
    write_json(root, "report.json", report)
    return report
