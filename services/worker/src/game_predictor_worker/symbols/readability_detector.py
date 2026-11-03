"""Deterministic independent L2 heads; validation selection and held-out evidence."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch

from .readability_cohort import CohortSplit, QualitySample, assign_families, pilot_issues
from .readability_features import (
    FEATURE_COUNT,
    FEATURE_VERSION,
    PREPROCESSING,
    FloatArray,
    FrozenBase,
    ReadabilityError,
    fingerprint,
)

LAMBDAS = (0.01, 0.1, 1.0, 10.0)
SOLVER = {
    "algorithm": "LBFGS",
    "lineSearch": "strong_wolfe",
    "lr": 1,
    "maxIter": 1000,
    "toleranceGrad": 1e-6,
    "toleranceChange": 1e-9,
    "objective": "mean-BCE+lambda*sum(w*w)/2",
    "biasPenalty": False,
    "initialization": "zero",
    "device": "cpu",
    "dtype": "float64",
}


def _matrix(values: FloatArray) -> None:
    if values.ndim != 2 or not len(values) or not np.isfinite(values).all():
        raise ReadabilityError(
            "READABILITY_FEATURES_INVALID", "Finite nonempty feature matrix required."
        )


@dataclass(frozen=True)
class LinearHead:
    weights: tuple[float, ...]
    bias: float
    regularization: float
    threshold: float
    validation_precision: float
    validation_recall: float

    def scores(self, values: FloatArray) -> FloatArray:
        logits = values @ np.asarray(self.weights) + self.bias
        # Stable sigmoid without overflow; a score, not a calibrated probability.
        scores = np.exp(-np.logaddexp(0, -logits))
        return cast(FloatArray, scores)


def fit_linear(values: FloatArray, labels: Sequence[bool], regularization: float) -> LinearHead:
    """Exactly the accepted CPU solver, with an explicit convergence check."""
    _matrix(values)
    if regularization not in LAMBDAS or len(labels) != len(values) or set(labels) != {False, True}:
        raise ReadabilityError(
            "READABILITY_FIT_INVALID", "Both human classes and approved lambda required."
        )
    x = torch.tensor(values, dtype=torch.float64)
    y = torch.tensor(labels, dtype=torch.float64)
    parameters = torch.zeros(values.shape[1] + 1, dtype=torch.float64, requires_grad=True)
    optimizer = torch.optim.LBFGS(
        [parameters],
        lr=1,
        max_iter=1000,
        tolerance_grad=1e-6,
        tolerance_change=1e-9,
        line_search_fn="strong_wolfe",
    )
    old_threads = torch.get_num_threads()
    old_deterministic = torch.are_deterministic_algorithms_enabled()
    try:
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)

        def closure() -> torch.Tensor:
            optimizer.zero_grad()
            logits = x @ parameters[:-1] + parameters[-1]
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, y)
            loss = loss + regularization * parameters[:-1].square().sum() / 2
            loss.backward()  # type: ignore[no-untyped-call]
            return loss

        optimizer.step(closure)  # type: ignore[no-untyped-call]
        final_loss = float(closure().detach())
        state = optimizer.state[parameters]
        gradient = float(parameters.grad.abs().max()) if parameters.grad is not None else math.inf
        change = abs(final_loss - float(state.get("prev_loss", math.inf)))
        if (
            not math.isfinite(final_loss)
            or not torch.isfinite(parameters).all()
            or int(state.get("n_iter", 1000)) >= 1000
            or (gradient > 1e-6 and change > 1e-9)
        ):
            raise ReadabilityError("READABILITY_NONCONVERGENCE", "L2 head did not converge.")
    finally:
        torch.set_num_threads(old_threads)
        torch.use_deterministic_algorithms(old_deterministic)
    result = parameters.detach().numpy()
    return LinearHead(
        tuple(float(v) for v in result[:-1]), float(result[-1]), regularization, 0.5, 0, 0
    )


def select_threshold(scores: FloatArray, labels: Sequence[bool]) -> tuple[float, float, float]:
    if (
        scores.ndim != 1
        or len(scores) != len(labels)
        or not np.isfinite(scores).all()
        or not any(labels)
        or any(score < 0 or score > 1 for score in scores)
    ):
        raise ReadabilityError(
            "READABILITY_VALIDATION_INVALID", "Positive validation evidence required."
        )
    targets = np.asarray(labels, dtype=bool)
    # Candidates use strict score > threshold. nextafter includes the boundary
    # score while retaining the highest representable threshold for that recall.
    for score in sorted(set(float(s) for s in scores), reverse=True):
        threshold = float(np.nextafter(score, -math.inf))
        predicted = scores > threshold
        recall = float(np.sum(predicted & targets) / np.sum(targets))
        if recall >= 0.95:
            precision = float(np.sum(predicted & targets) / np.sum(predicted))
            return threshold, precision, recall
    raise ReadabilityError("READABILITY_VALIDATION_INVALID", "No admissible threshold.")


def select_head(
    train: FloatArray,
    train_labels: Sequence[bool],
    validation: FloatArray,
    validation_labels: Sequence[bool],
) -> LinearHead:
    candidates: list[LinearHead] = []
    for regularization in LAMBDAS:
        head = fit_linear(train, train_labels, regularization)
        threshold, precision, recall = select_threshold(head.scores(validation), validation_labels)
        candidates.append(
            LinearHead(head.weights, head.bias, regularization, threshold, precision, recall)
        )
    return max(candidates, key=lambda h: (h.validation_precision, h.regularization))


@dataclass(frozen=True)
class QualityArtifact:
    base: dict[str, Any]
    cohort_sha256: str
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    overlap: LinearHead
    unreadable: LinearHead

    def document(self) -> dict[str, Any]:
        body = {
            "schema": "symbol-quality-two-head-v1",
            "base": self.base,
            "cohortSha256": self.cohort_sha256,
            "featureVersion": FEATURE_VERSION,
            "preprocessing": PREPROCESSING,
            "solver": SOLVER,
            "lambdaGrid": LAMBDAS,
            "mean": self.mean,
            "scale": self.scale,
            "overlap": asdict(self.overlap),
            "unreadable": asdict(self.unreadable),
        }
        return {**body, "fingerprint": fingerprint(body)}

    def score(self, values: FloatArray) -> tuple[FloatArray, FloatArray]:
        _matrix(values)
        if values.shape[1] != len(self.mean):
            raise ReadabilityError("READABILITY_FEATURES_INVALID", "Feature dimension differs.")
        standardized = (values - np.asarray(self.mean)) / np.asarray(self.scale)
        return self.overlap.scores(standardized), self.unreadable.scores(standardized)


def train_detector(cohort: CohortSplit, features: FloatArray, base: FrozenBase) -> QualityArtifact:
    """One explicit pilot fit. TEST and natural audit never tune any component."""
    _matrix(features)
    if features.shape != (len(cohort.samples), FEATURE_COUNT):
        raise ReadabilityError("READABILITY_FEATURES_INVALID", "Cohort feature inventory differs.")
    if cohort.base_fingerprint != fingerprint(base.binding()):
        raise ReadabilityError("READABILITY_BASE_DRIFT", "Cohort uses a different base.")
    verified = assign_families(cohort.samples, base, assignments=cohort.assignments)
    if verified != cohort:
        raise ReadabilityError(
            "READABILITY_COHORT_DRIFT", "Cohort families differ from provenance."
        )
    issues = pilot_issues(cohort)
    if issues:
        raise ReadabilityError("READABILITY_PILOT_STOP", ", ".join(issues))
    train = np.asarray([split == "train" for split in cohort.assignments])
    mean = features[train].mean(axis=0)
    scale = features[train].std(axis=0)
    scale[scale == 0] = 1
    standardized = (features - mean) / scale
    heads: dict[str, LinearHead] = {}
    for name in ("overlap", "unreadable"):
        masks = [
            np.asarray(
                [
                    split == part and getattr(sample, name) is not None
                    for sample, split in zip(cohort.samples, cohort.assignments, strict=True)
                ]
            )
            for part in ("train", "validation")
        ]
        labels = [
            [
                bool(getattr(sample, name))
                for sample, used in zip(cohort.samples, mask, strict=True)
                if used
            ]
            for mask in masks
        ]
        heads[name] = select_head(
            standardized[masks[0]], labels[0], standardized[masks[1]], labels[1]
        )
    return QualityArtifact(
        base.binding(),
        fingerprint(cohort.binding()),
        tuple(mean),
        tuple(scale),
        heads["overlap"],
        heads["unreadable"],
    )


def load_artifact(path: Path, *, expected_fingerprint: str, base: FrozenBase) -> QualityArtifact:
    """Decode untrusted JSON with stable errors; bindings still fail closed."""
    try:
        return _load_artifact(path, expected_fingerprint=expected_fingerprint, base=base)
    except ReadabilityError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise ReadabilityError(
            "READABILITY_ARTIFACT_INVALID", "Malformed or unreadable quality artifact."
        ) from error


def _load_artifact(path: Path, *, expected_fingerprint: str, base: FrozenBase) -> QualityArtifact:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON constant: {value}")

    document = json.loads(path.read_bytes(), parse_constant=reject_constant)
    body = {key: value for key, value in document.items() if key != "fingerprint"}
    if (
        document.get("fingerprint") != expected_fingerprint
        or fingerprint(body) != expected_fingerprint
        or body.get("schema") != "symbol-quality-two-head-v1"
        or body.get("featureVersion") != FEATURE_VERSION
        or body.get("preprocessing") != PREPROCESSING
        or body.get("solver") != SOLVER
        or tuple(body.get("lambdaGrid", ())) != LAMBDAS
        or body.get("base") != base.binding()
    ):
        raise ReadabilityError("READABILITY_ARTIFACT_DRIFT", "Artifact binding differs.")
    try:
        heads = [LinearHead(**body[name]) for name in ("overlap", "unreadable")]
        mean, scale = tuple(body["mean"]), tuple(body["scale"])
        if (
            len(mean) != FEATURE_COUNT
            or len(scale) != FEATURE_COUNT
            or not np.isfinite(mean).all()
            or not np.isfinite(scale).all()
            or min(scale) <= 0
            or any(
                len(head.weights) != FEATURE_COUNT
                or not np.isfinite(head.weights).all()
                or not math.isfinite(head.bias)
                or head.regularization not in LAMBDAS
                or not -1e-12 <= head.threshold <= 1
                for head in heads
            )
        ):
            raise ValueError("Invalid artifact coefficients")
    except (KeyError, TypeError, ValueError) as error:
        raise ReadabilityError("READABILITY_ARTIFACT_INVALID", str(error)) from error
    return QualityArtifact(body["base"], body["cohortSha256"], mean, scale, heads[0], heads[1])


def rank_candidates(
    artifact: QualityArtifact,
    samples: Sequence[QualitySample],
    features: FloatArray,
) -> tuple[dict[str, object], ...]:
    overlap, unreadable = artifact.score(features)
    if len(samples) != len(features):
        raise ReadabilityError("READABILITY_FEATURES_INVALID", "Sample inventory differs.")
    entries: list[tuple[tuple[float, float, int, str], dict[str, object]]] = []
    for sample, first, second in zip(samples, overlap, unreadable, strict=True):
        margins = sorted(
            (
                float(first) - artifact.overlap.threshold,
                float(second) - artifact.unreadable.threshold,
            ),
            reverse=True,
        )
        if margins[0] <= 0:
            continue
        entries.append(
            (
                (-margins[0], -margins[1], sample.sequence_number, sample.cell_id),
                {
                    "cellId": sample.cell_id,
                    "identity": sample.identity(),
                    "sequenceNumber": sample.sequence_number,
                    "overlapScore": float(first),
                    "unreadableScore": float(second),
                    "margins": margins,
                },
            )
        )
    return tuple(entry for _, entry in sorted(entries, key=lambda item: item[0]))


def rate_metric(successes: int, count: int, families: int) -> dict[str, object]:
    if not 0 <= successes <= count or families < 0:
        raise ValueError("Invalid metric counts")
    if count == 0:
        return {"count": 0, "successes": 0, "families": families, "rate": None, "wilson95": None}
    z = 1.959963984540054
    rate = successes / count
    denominator = 1 + z * z / count
    center = (rate + z * z / (2 * count)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / count + z * z / (4 * count * count)) / denominator
    return {
        "count": count,
        "successes": successes,
        "families": families,
        "rate": rate,
        "wilson95": [max(0, center - radius), min(1, center + radius)],
    }


def evaluate_pilot(
    artifact: QualityArtifact,
    cohort: CohortSplit,
    features: FloatArray,
    *,
    natural_audit_receipt: Mapping[str, object] | None = None,
    operator_accepted: bool = False,
) -> dict[str, object]:
    """Report held-out strata; PASS alone never authorizes a full scan."""
    if fingerprint(cohort.binding()) != artifact.cohort_sha256:
        raise ReadabilityError("READABILITY_COHORT_DRIFT", "Evaluation cohort differs from fit.")
    first, second = artifact.score(features)
    if len(features) != len(cohort.samples):
        raise ReadabilityError("READABILITY_FEATURES_INVALID", "Evaluation inventory differs.")
    predicted = (first > artifact.overlap.threshold) | (second > artifact.unreadable.threshold)
    metrics: dict[str, dict[str, object]] = {}
    for name in (
        "overlap_unreadable",
        "all_unreadable",
        "sharp_overlap",
        "confident_overlap",
        "similar_readable_fpr",
    ):
        selected: list[int] = []
        for i, (sample, split) in enumerate(zip(cohort.samples, cohort.assignments, strict=True)):
            overlap = sample.overlap is True and sample.unreadable is True
            if (
                split == "test"
                and {
                    "overlap_unreadable": overlap,
                    "all_unreadable": sample.unreadable is True,
                    "sharp_overlap": overlap and sample.sharp,
                    "confident_overlap": overlap and (sample.top1 or 0) >= 0.95,
                    "similar_readable_fpr": sample.unreadable is False and sample.similar_readable,
                }[name]
            ):
                selected.append(i)
        metrics[name] = rate_metric(
            sum(bool(predicted[i]) for i in selected),
            len(selected),
            len({cohort.families[i] for i in selected}),
        )
    issues = list(pilot_issues(cohort))
    for name in ("overlap_unreadable", "all_unreadable"):
        rate = metrics[name]["rate"]
        if rate is None or cast(float, rate) < 0.9:
            issues.append(name + "_recall_below_90")
    audit_indices = [i for i, split in enumerate(cohort.assignments) if split == "audit"]
    receipt = dict(natural_audit_receipt or {})
    audit_valid = (
        len(audit_indices) == 200
        and all(
            cohort.samples[i].previously_unlabelled
            and cohort.samples[i].unreadable is not None
            and cohort.samples[i].overlap is not None
            for i in audit_indices
        )
        and receipt.get("selection") == "uniform-random-before-labels"
        and receipt.get("identitiesSha256")
        == fingerprint(sorted(cohort.samples[i].identity() for i in audit_indices))
        and isinstance(receipt.get("seed"), str)
        and bool(receipt.get("seed"))
    )
    if not audit_valid:
        issues.append("natural_audit_200_missing_or_invalid")
    natural: dict[str, object] = {"count": len(audit_indices), "receipt": receipt}
    natural_groups: tuple[tuple[str, list[int], Callable[[int], bool]], ...] = (
        (
            "candidate_noise",
            [i for i in audit_indices if predicted[i]],
            lambda i: cohort.samples[i].unreadable is False and cohort.samples[i].overlap is False,
        ),
        (
            "unreadable_missed",
            [i for i in audit_indices if cohort.samples[i].unreadable is True],
            lambda i: not bool(predicted[i]),
        ),
        (
            "overlap_missed",
            [i for i in audit_indices if cohort.samples[i].overlap is True],
            lambda i: not bool(predicted[i]),
        ),
    )
    for name, eligible, success in natural_groups:
        natural[name] = rate_metric(
            sum(success(i) for i in eligible),
            len(eligible),
            len({cohort.families[i] for i in eligible}),
        )
    return {
        "status": "STOP" if issues else "PASS",
        "issues": issues,
        "test": metrics,
        "naturalAudit": natural,
        "fullScanAllowed": not issues and operator_accepted,
        "operatorAccepted": operator_accepted,
        "artifactFingerprint": artifact.document()["fingerprint"],
    }
