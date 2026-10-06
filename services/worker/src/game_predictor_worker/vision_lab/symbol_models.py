"""Pure, validation-only metrics and calibration for the first fresh symbol models."""

from typing import Any, cast

import numpy as np

MODELS = ("mumie-symbol-rgb-v1", "mumie-symbol-gray-v1")
ROBUST_MODELS = ("mumie-symbol-rgb-v2", "mumie-symbol-gray-v2")
FEEDBACK_MODELS = ("mumie-symbol-rgb-v3", "mumie-symbol-gray-v3")
AI_MODELS = ("mumie-symbol-rgb-v4-ai", "mumie-symbol-gray-v4-ai")
PREPROCESSING = {
    MODELS[0]: "rgb-resize64-normalize-half-v1",
    MODELS[1]: "rgb-resize64-normalize-half-gray3-v1",
    ROBUST_MODELS[0]: "rgb-resize64-normalize-half-v1",
    ROBUST_MODELS[1]: "rgb-resize64-normalize-half-gray3-v1",
    FEEDBACK_MODELS[0]: "rgb-resize64-normalize-half-v1",
    FEEDBACK_MODELS[1]: "rgb-resize64-normalize-half-gray3-v1",
    AI_MODELS[0]: "rgb-resize64-normalize-half-v1",
    AI_MODELS[1]: "rgb-resize64-normalize-half-gray3-v1",
}


def model_pair(generation: int = 1) -> tuple[str, str]:
    if generation not in (1, 2, 3, 4):
        raise ValueError("SYMBOL_GENERATION_INVALID")
    return (MODELS, ROBUST_MODELS, FEEDBACK_MODELS, AI_MODELS)[generation - 1]


def require_robust_qualification(measured: dict[str, Any]) -> None:
    validation, onnx = measured["validation"], measured["onnx"]
    if (
        validation["samples"] != 84
        or not 83 <= validation["correct"] <= 84
        or onnx.get("status") != "passed"
        or onnx.get("samples") != 84
        or not 0 <= onnx.get("max_absolute_error", float("inf")) <= 1e-4
    ):
        raise ValueError("SYMBOL_ROBUST_QUALIFICATION_FAILED")


def probabilities(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    value = np.asarray(logits, dtype=np.float64) / temperature
    value -= value.max(axis=1, keepdims=True)
    exp = np.exp(value)
    return cast(np.ndarray, exp / exp.sum(axis=1, keepdims=True))


def metrics(probs: np.ndarray, labels: list[int], classes: list[str]) -> dict[str, Any]:
    values = np.asarray(probs, dtype=np.float64)
    targets = np.asarray(labels)
    if values.shape != (len(labels), len(classes)) or not len(labels):
        raise ValueError("SYMBOL_METRICS_SHAPE_INVALID")
    if not np.isfinite(values).all() or (values < 0).any() or not np.allclose(values.sum(1), 1):
        raise ValueError("SYMBOL_METRICS_PROBABILITY_INVALID")
    predictions = values.argmax(1)
    confusion = np.zeros((len(classes), len(classes)), dtype=np.int64)
    for expected, predicted in zip(targets, predictions, strict=True):
        confusion[expected, predicted] += 1
    per_class = [
        {
            "class": name,
            "samples": int(confusion[i].sum()),
            "correct": int(confusion[i, i]),
            "accuracy": float(confusion[i, i] / confusion[i].sum()) if confusion[i].sum() else None,
        }
        for i, name in enumerate(classes)
    ]
    return {
        "samples": len(labels),
        "correct": int((predictions == targets).sum()),
        "accuracy": float((predictions == targets).mean()),
        "macro_accuracy": float(
            np.mean([c["accuracy"] for c in per_class if c["accuracy"] is not None])
        ),
        "log_loss": float(
            -np.log(np.maximum(values[np.arange(len(targets)), targets], 1e-12)).mean()
        ),
        "per_class": per_class,
        "confusion": confusion.tolist(),
    }


def calibrate(logits: np.ndarray, labels: list[int], classes: list[str]) -> dict[str, Any]:
    options = []
    for temperature in np.linspace(0.5, 3.0, 51):
        measured = metrics(probabilities(logits, float(temperature)), labels, classes)
        options.append((measured["log_loss"], abs(temperature - 1), float(temperature), measured))
    _, _, temperature, measured = min(options, key=lambda row: row[:3])
    return {
        "temperature": temperature,
        "metrics": measured,
        "selected_on": "validation",
        "independent_final_test": False,
    }


def compare(rgb: dict[str, Any], gray: dict[str, Any]) -> dict[str, Any]:
    for key in ("manifest_id", "classes", "labels", "sample_ids"):
        if rgb[key] != gray[key]:
            raise ValueError("SYMBOL_FUSION_BINDING_MISMATCH")
    classes, labels = rgb["classes"], rgb["labels"]
    rgb_logits = np.asarray(rgb["logits"])
    gray_logits = np.asarray(gray["logits"])
    rgb_cal = calibrate(rgb_logits, labels, classes)
    gray_cal = calibrate(gray_logits, labels, classes)
    rp = probabilities(rgb_logits, rgb_cal["temperature"])
    gp = probabilities(gray_logits, gray_cal["temperature"])
    candidates: list[dict[str, Any]] = []
    for weight in (0.0, 0.1, 0.2, 0.3):
        measured = metrics(weight * rp + (1 - weight) * gp, labels, classes)
        candidates.append({"rgb_weight": weight, "metrics": measured})
    best = min(
        candidates,
        key=lambda c: (-c["metrics"]["macro_accuracy"], c["metrics"]["log_loss"], c["rgb_weight"]),
    )
    fused = best["rgb_weight"] * rp + (1 - best["rgb_weight"]) * gp
    predictions = fused.argmax(1)
    agree = rp.argmax(1) == gp.argmax(1)
    accepted = agree & (fused.max(1) >= 0.9)
    rows = [
        {
            "sample_id": sid,
            "expected": classes[target],
            "predicted": classes[int(pred)],
            "confidence": float(fused[i].max()),
            "disagreement": not bool(agree[i]),
            "model_requires_review": not bool(accepted[i]),
            "reference_conflict": int(pred) != target,
            "requires_review": not bool(accepted[i]) or int(pred) != target,
            "correct": int(pred) == target,
        }
        for i, (sid, target, pred) in enumerate(
            zip(rgb["sample_ids"], labels, predictions, strict=True)
        )
    ]
    return {
        "manifest_id": rgb["manifest_id"],
        "rgb": rgb_cal,
        "gray": gray_cal,
        "fusion_candidates": candidates,
        "selected_fusion": best,
        "review_policy": "both models agree and fused probability >=0.9",
        "evaluation_review_policy": (
            "Also flag disagreement with the existing human reference; do not rewrite labels."
        ),
        "coverage": float(accepted.mean()),
        "accepted": int(accepted.sum()),
        "accepted_correct": int(((predictions == labels) & accepted).sum()),
        "disagreements": int((~agree).sum()),
        "rows": rows,
        "limitation": (
            "Selection and calibration reuse small validation; no independent final test."
        ),
    }


def evaluate_frozen_fusion(
    rgb: dict[str, Any], gray: dict[str, Any], calibration: dict[str, Any]
) -> dict[str, Any]:
    """Apply validation-selected parameters without fitting held-out or training labels."""
    for key in ("manifest_id", "classes", "labels", "sample_ids"):
        if rgb[key] != gray[key]:
            raise ValueError("SYMBOL_FUSION_BINDING_MISMATCH")
    if calibration["manifest_id"] != rgb["manifest_id"]:
        raise ValueError("SYMBOL_FUSION_BINDING_MISMATCH")
    weight = calibration["selected_fusion"]["rgb_weight"]
    temperatures = [calibration[branch]["temperature"] for branch in ["rgb", "gray"]]
    if weight not in (0.0, 0.1, 0.2, 0.3) or any(not 0.5 <= t <= 3 for t in temperatures):
        raise ValueError("SYMBOL_FROZEN_CALIBRATION_INVALID")
    rp = probabilities(np.asarray(rgb["logits"]), temperatures[0])
    gp = probabilities(np.asarray(gray["logits"]), temperatures[1])
    fused = weight * rp + (1 - weight) * gp
    classes, labels = rgb["classes"], rgb["labels"]
    return {
        "rgb": metrics(rp, labels, classes),
        "gray": metrics(gp, labels, classes),
        "fusion": metrics(fused, labels, classes),
        "calibration_selected_on": "validation",
        "rows": [
            {
                "sample_id": sid,
                "expected": classes[target],
                "rgb": classes[int(rp[i].argmax())],
                "gray": classes[int(gp[i].argmax())],
                "predicted": classes[int(fused[i].argmax())],
                "confidence": float(fused[i].max()),
                "disagreement": int(rp[i].argmax()) != int(gp[i].argmax()),
                "correct": int(fused[i].argmax()) == target,
            }
            for i, (sid, target) in enumerate(zip(rgb["sample_ids"], labels, strict=True))
        ],
    }
