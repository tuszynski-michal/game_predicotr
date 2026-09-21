"""Versioned V7 geometry calibration and independent acceptance accounting."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from statistics import median

from .contracts import validate_sha256
from .v7_configuration import V7CorpusSplit
from .v7_label_locator import V7GridLabelLocatorConfig

V7_CALIBRATION_VERSION = "v7-calibration-v1"
V7_CALIBRATION_MINIMUM_SOURCES_PER_POSITION = 5
V7_CALIBRATION_MAXIMUM_P95_CENTER_RESIDUAL = 0.04
V7_CALIBRATION_POSITION_CONFIDENCE = 0.95
V7_ACCEPTANCE_MINIMUM_PERCENT = 95


class V7CalibrationError(ValueError):
    """The supplied evidence cannot safely calibrate or accept V7."""


class V7AutomaticOutcome(StrEnum):
    """The frozen automatic outcome before any operator remediation."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    NOT_SELECTED = "not_selected"


class V7EvaluationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class V7SourceReference:
    """Immutable source identity used by manually verified V7 evidence."""

    source_id: str
    source_checksum_sha256: str

    def __post_init__(self) -> None:
        if not self.source_id:
            raise V7CalibrationError("V7 source reference ID is required.")
        try:
            validate_sha256(self.source_checksum_sha256, field="sourceChecksumSha256")
        except ValueError as error:
            raise V7CalibrationError("V7 source reference checksum is invalid.") from error

    def as_dict(self) -> dict[str, object]:
        return {
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class V7LabelGeometryAnnotation:
    """A manually verified normalized label centre for one source and grid slot."""

    source_id: str
    source_checksum_sha256: str
    split: V7CorpusSplit
    position_index: int
    center_x: float
    center_y: float

    def __post_init__(self) -> None:
        if (
            not self.source_id
            or not 0 <= self.position_index < 9
            or not 0 < self.center_x < 1
            or not 0 < self.center_y < 1
        ):
            raise V7CalibrationError("V7 label geometry annotation is invalid.")
        try:
            validate_sha256(self.source_checksum_sha256, field="sourceChecksumSha256")
        except ValueError as error:
            raise V7CalibrationError("V7 label geometry checksum is invalid.") from error

    def as_dict(self) -> dict[str, object]:
        return {
            "centerX": self.center_x,
            "centerY": self.center_y,
            "positionIndex": self.position_index,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
            "split": self.split.value,
        }


@dataclass(frozen=True, slots=True)
class V7GeometryCalibration:
    """A measured locator configuration, never a production activation signal by itself."""

    manifest_fingerprint: str
    input_fingerprint: str
    locator_config: V7GridLabelLocatorConfig
    source_count_by_position: tuple[int, ...]
    p95_center_residual: float
    maximum_p95_center_residual: float
    minimum_sources_per_position: int

    def __post_init__(self) -> None:
        if (
            len(self.source_count_by_position) != 9
            or any(
                count < self.minimum_sources_per_position for count in self.source_count_by_position
            )
            or self.minimum_sources_per_position < 1
            or not 0 < self.maximum_p95_center_residual < 1
            or not 0 <= self.p95_center_residual < 1
            or self.locator_config.position_confidence != V7_CALIBRATION_POSITION_CONFIDENCE
        ):
            raise V7CalibrationError("V7 geometry calibration is invalid.")
        try:
            validate_sha256(self.manifest_fingerprint, field="manifestFingerprint")
            validate_sha256(self.input_fingerprint, field="inputFingerprint")
        except ValueError as error:
            raise V7CalibrationError("V7 geometry calibration fingerprint is invalid.") from error

    @property
    def status(self) -> V7EvaluationStatus:
        return (
            V7EvaluationStatus.PASSED
            if self.p95_center_residual <= self.maximum_p95_center_residual
            else V7EvaluationStatus.FAILED
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "inputFingerprint": self.input_fingerprint,
            "locatorConfig": {
                "centers": [list(center) for center in self.locator_config.centers],
                "heightRatio": self.locator_config.height_ratio,
                "positionConfidence": self.locator_config.position_confidence,
                "widthRatios": list(self.locator_config.width_ratios),
            },
            "manifestFingerprint": self.manifest_fingerprint,
            "maximumP95CenterResidual": self.maximum_p95_center_residual,
            "minimumSourcesPerPosition": self.minimum_sources_per_position,
            "p95CenterResidual": self.p95_center_residual,
            "sourceCountByPosition": list(self.source_count_by_position),
            "status": self.status.value,
            "version": V7_CALIBRATION_VERSION,
        }


@dataclass(frozen=True, slots=True)
class V7AcceptanceTruth:
    """Independent human ground truth for one expected range, not model output."""

    case_id: str
    corpus_case_id: str
    split: V7CorpusSplit
    expected_range_start: int
    expected_range_end: int
    evidence_sources: tuple[V7SourceReference, ...]
    automatically_recoverable: bool
    eligible_acceptable_representative: bool
    top_cropped: bool
    bottom_cropped: bool

    def __post_init__(self) -> None:
        if (
            not self.case_id
            or not self.corpus_case_id
            or self.expected_range_start < 1
            or self.expected_range_end < self.expected_range_start
            or not self.evidence_sources
            or len({item.source_id for item in self.evidence_sources}) != len(self.evidence_sources)
            or self.split in {V7CorpusSplit.HOLDOUT, V7CorpusSplit.REFERENCE_ONLY}
        ):
            raise V7CalibrationError("V7 acceptance truth split or case ID is invalid for T05.")

    def as_dict(self) -> dict[str, object]:
        return {
            "automaticallyRecoverable": self.automatically_recoverable,
            "bottomCropped": self.bottom_cropped,
            "caseId": self.case_id,
            "corpusCaseId": self.corpus_case_id,
            "evidenceSources": [item.as_dict() for item in self.evidence_sources],
            "eligibleAcceptableRepresentative": self.eligible_acceptable_representative,
            "expectedRangeEnd": self.expected_range_end,
            "expectedRangeStart": self.expected_range_start,
            "split": self.split.value,
            "topCropped": self.top_cropped,
        }


@dataclass(frozen=True, slots=True)
class V7AcceptancePrediction:
    """Frozen automatic output before a user can correct it."""

    case_id: str
    range_outcome: V7AutomaticOutcome
    representative_outcome: V7AutomaticOutcome
    selected_source: V7SourceReference | None
    top_warning: bool
    bottom_warning: bool
    manual_review: bool

    def __post_init__(self) -> None:
        if not self.case_id:
            raise V7CalibrationError("V7 acceptance prediction case ID is required.")
        if (
            self.range_outcome is not V7AutomaticOutcome.CORRECT
            and self.representative_outcome is not V7AutomaticOutcome.NOT_SELECTED
        ):
            raise V7CalibrationError(
                "V7 representative success requires a correct automatic range output."
            )
        if (
            self.range_outcome is V7AutomaticOutcome.NOT_SELECTED
            and self.selected_source is not None
        ) or (
            self.range_outcome is not V7AutomaticOutcome.NOT_SELECTED
            and self.selected_source is None
        ):
            raise V7CalibrationError("V7 automatic output source is inconsistent.")

    def as_dict(self) -> dict[str, object]:
        return {
            "bottomWarning": self.bottom_warning,
            "caseId": self.case_id,
            "manualReview": self.manual_review,
            "rangeOutcome": self.range_outcome.value,
            "representativeOutcome": self.representative_outcome.value,
            "selectedSource": (
                None if self.selected_source is None else self.selected_source.as_dict()
            ),
            "topWarning": self.top_warning,
        }


@dataclass(frozen=True, slots=True)
class V7AcceptanceMetric:
    numerator: int
    denominator: int
    minimum_percent: int | None = None

    def __post_init__(self) -> None:
        if self.numerator < 0 or self.denominator < 0 or self.numerator > self.denominator:
            raise V7CalibrationError("V7 acceptance metric counts are invalid.")
        if self.minimum_percent is not None and not 0 <= self.minimum_percent <= 100:
            raise V7CalibrationError("V7 acceptance threshold is invalid.")

    @property
    def status(self) -> V7EvaluationStatus:
        if self.denominator == 0:
            return V7EvaluationStatus.NOT_EVALUABLE
        if self.minimum_percent is None:
            return V7EvaluationStatus.PASSED
        return (
            V7EvaluationStatus.PASSED
            if self.numerator * 100 >= self.denominator * self.minimum_percent
            else V7EvaluationStatus.FAILED
        )

    @property
    def percentage(self) -> float | None:
        return None if self.denominator == 0 else self.numerator * 100 / self.denominator

    def as_dict(self) -> dict[str, object]:
        return {
            "denominator": self.denominator,
            "minimumPercent": self.minimum_percent,
            "numerator": self.numerator,
            "percentage": self.percentage,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class V7AcceptanceEvaluation:
    """Separate acceptance metrics. Manual remediation never changes automatic scores."""

    input_fingerprint: str
    range_recovery: V7AcceptanceMetric
    representative_selection: V7AcceptanceMetric
    top_crop_recall: V7AcceptanceMetric
    bottom_crop_recall: V7AcceptanceMetric
    incorrect_automatic_range_count: int
    top_crop_false_positive_count: int
    bottom_crop_false_positive_count: int
    manual_review_count: int
    total_case_count: int

    def __post_init__(self) -> None:
        if any(
            count < 0
            for count in (
                self.incorrect_automatic_range_count,
                self.top_crop_false_positive_count,
                self.bottom_crop_false_positive_count,
                self.manual_review_count,
                self.total_case_count,
            )
        ):
            raise V7CalibrationError("V7 acceptance evaluation counts are invalid.")
        try:
            validate_sha256(self.input_fingerprint, field="inputFingerprint")
        except ValueError as error:
            raise V7CalibrationError("V7 acceptance evaluation fingerprint is invalid.") from error

    @property
    def status(self) -> V7EvaluationStatus:
        required = (
            self.range_recovery,
            self.representative_selection,
            self.top_crop_recall,
            self.bottom_crop_recall,
        )
        if any(metric.status is V7EvaluationStatus.NOT_EVALUABLE for metric in required):
            return V7EvaluationStatus.NOT_EVALUABLE
        if self.incorrect_automatic_range_count == 0 and all(
            metric.status is V7EvaluationStatus.PASSED for metric in required
        ):
            return V7EvaluationStatus.PASSED
        return V7EvaluationStatus.FAILED

    def as_dict(self) -> dict[str, object]:
        return {
            "bottomCropFalsePositiveCount": self.bottom_crop_false_positive_count,
            "bottomCropRecall": self.bottom_crop_recall.as_dict(),
            "incorrectAutomaticRangeCount": self.incorrect_automatic_range_count,
            "inputFingerprint": self.input_fingerprint,
            "manualReviewCount": self.manual_review_count,
            "rangeRecovery": self.range_recovery.as_dict(),
            "representativeSelection": self.representative_selection.as_dict(),
            "status": self.status.value,
            "topCropFalsePositiveCount": self.top_crop_false_positive_count,
            "topCropRecall": self.top_crop_recall.as_dict(),
            "totalCaseCount": self.total_case_count,
            "version": V7_CALIBRATION_VERSION,
        }


def calibrate_v7_label_geometry(
    annotations: Iterable[V7LabelGeometryAnnotation],
    *,
    manifest_fingerprint: str,
    minimum_sources_per_position: int = V7_CALIBRATION_MINIMUM_SOURCES_PER_POSITION,
    maximum_p95_center_residual: float = V7_CALIBRATION_MAXIMUM_P95_CENTER_RESIDUAL,
) -> V7GeometryCalibration:
    """Build a locator only from independently annotated calibration sources."""

    if minimum_sources_per_position < 1 or not 0 < maximum_p95_center_residual < 1:
        raise V7CalibrationError("V7 geometry calibration policy is invalid.")
    values = tuple(annotations)
    if not values or any(item.split is not V7CorpusSplit.CALIBRATION for item in values):
        raise V7CalibrationError(
            "V7 geometry calibration requires calibration-split annotations only."
        )
    _validate_geometry_source_identity(values)
    positions = tuple(
        tuple(item for item in values if item.position_index == position) for position in range(9)
    )
    source_counts = tuple(len({item.source_id for item in position}) for position in positions)
    if any(count < minimum_sources_per_position for count in source_counts):
        raise V7CalibrationError(
            "V7 geometry calibration lacks independent sources for a position."
        )
    centers = tuple(
        (median(item.center_x for item in position), median(item.center_y for item in position))
        for position in positions
    )
    residuals = sorted(
        math.hypot(
            item.center_x - centers[item.position_index][0],
            item.center_y - centers[item.position_index][1],
        )
        for item in values
    )
    p95 = residuals[math.ceil(len(residuals) * 0.95) - 1]
    try:
        validate_sha256(manifest_fingerprint, field="manifestFingerprint")
    except ValueError as error:
        raise V7CalibrationError("V7 geometry manifest fingerprint is invalid.") from error
    config = V7GridLabelLocatorConfig(
        centers=centers,
        position_confidence=V7_CALIBRATION_POSITION_CONFIDENCE,
    )
    return V7GeometryCalibration(
        manifest_fingerprint=manifest_fingerprint,
        input_fingerprint=_fingerprint(
            {
                "annotations": [item.as_dict() for item in sorted(values, key=_geometry_sort_key)],
                "maximumP95CenterResidual": maximum_p95_center_residual,
                "minimumSourcesPerPosition": minimum_sources_per_position,
            }
        ),
        locator_config=config,
        source_count_by_position=source_counts,
        p95_center_residual=p95,
        maximum_p95_center_residual=maximum_p95_center_residual,
        minimum_sources_per_position=minimum_sources_per_position,
    )


def evaluate_v7_acceptance(
    truths: Iterable[V7AcceptanceTruth],
    predictions: Iterable[V7AcceptancePrediction],
) -> V7AcceptanceEvaluation:
    """Account for V7 automatic performance without absorbing manual corrections."""

    truth_by_case = _unique_by_case_id(truths, "truth")
    prediction_by_case = _unique_by_case_id(predictions, "prediction")
    if set(truth_by_case) != set(prediction_by_case):
        raise V7CalibrationError("V7 acceptance truth and prediction cases differ.")
    truth_values = tuple(truth_by_case.values())
    _validate_unique_range_cases(truth_values)
    prediction_values = tuple(prediction_by_case[item.case_id] for item in truth_values)
    range_denominator = sum(item.automatically_recoverable for item in truth_values)
    range_numerator = sum(
        truth.automatically_recoverable and prediction.range_outcome is V7AutomaticOutcome.CORRECT
        for truth, prediction in zip(truth_values, prediction_values, strict=True)
    )
    representative_denominator = sum(
        item.eligible_acceptable_representative for item in truth_values
    )
    representative_numerator = sum(
        truth.eligible_acceptable_representative
        and prediction.range_outcome is V7AutomaticOutcome.CORRECT
        and prediction.representative_outcome is V7AutomaticOutcome.CORRECT
        for truth, prediction in zip(truth_values, prediction_values, strict=True)
    )
    top_denominator = sum(item.top_cropped for item in truth_values)
    top_numerator = sum(
        truth.top_cropped and prediction.top_warning
        for truth, prediction in zip(truth_values, prediction_values, strict=True)
    )
    bottom_denominator = sum(item.bottom_cropped for item in truth_values)
    bottom_numerator = sum(
        truth.bottom_cropped and prediction.bottom_warning
        for truth, prediction in zip(truth_values, prediction_values, strict=True)
    )
    return V7AcceptanceEvaluation(
        input_fingerprint=_fingerprint(
            {
                "predictions": [item.as_dict() for item in prediction_values],
                "truth": [item.as_dict() for item in truth_values],
            }
        ),
        range_recovery=V7AcceptanceMetric(
            range_numerator, range_denominator, V7_ACCEPTANCE_MINIMUM_PERCENT
        ),
        representative_selection=V7AcceptanceMetric(
            representative_numerator,
            representative_denominator,
            V7_ACCEPTANCE_MINIMUM_PERCENT,
        ),
        top_crop_recall=V7AcceptanceMetric(top_numerator, top_denominator, 100),
        bottom_crop_recall=V7AcceptanceMetric(bottom_numerator, bottom_denominator, 100),
        incorrect_automatic_range_count=sum(
            item.range_outcome is V7AutomaticOutcome.INCORRECT for item in prediction_values
        ),
        top_crop_false_positive_count=sum(
            prediction.top_warning and not truth.top_cropped
            for truth, prediction in zip(truth_values, prediction_values, strict=True)
        ),
        bottom_crop_false_positive_count=sum(
            prediction.bottom_warning and not truth.bottom_cropped
            for truth, prediction in zip(truth_values, prediction_values, strict=True)
        ),
        manual_review_count=sum(item.manual_review for item in prediction_values),
        total_case_count=len(truth_values),
    )


def _validate_geometry_source_identity(values: tuple[V7LabelGeometryAnnotation, ...]) -> None:
    checksums_by_source: dict[str, str] = {}
    sources_by_checksum: dict[str, str] = {}
    positions_by_source: set[tuple[str, int]] = set()
    for item in values:
        prior_checksum = checksums_by_source.setdefault(item.source_id, item.source_checksum_sha256)
        if prior_checksum != item.source_checksum_sha256:
            raise V7CalibrationError("V7 geometry source ID has conflicting checksums.")
        prior_source = sources_by_checksum.setdefault(item.source_checksum_sha256, item.source_id)
        if prior_source != item.source_id:
            raise V7CalibrationError("V7 geometry sources are byte-identical aliases.")
        key = (item.source_id, item.position_index)
        if key in positions_by_source:
            raise V7CalibrationError("V7 geometry source position is annotated more than once.")
        positions_by_source.add(key)


def _unique_by_case_id[AcceptanceItem: V7AcceptanceTruth | V7AcceptancePrediction](
    values: Iterable[AcceptanceItem],
    kind: str,
) -> dict[str, AcceptanceItem]:
    result: dict[str, AcceptanceItem] = {}
    for value in values:
        if value.case_id in result:
            raise V7CalibrationError(f"V7 acceptance {kind} case ID is duplicated.")
        result[value.case_id] = value
    return result


def _validate_unique_range_cases(values: Iterable[V7AcceptanceTruth]) -> None:
    seen: set[tuple[str, int, int]] = set()
    for value in values:
        key = (value.corpus_case_id, value.expected_range_start, value.expected_range_end)
        if key in seen:
            raise V7CalibrationError("V7 acceptance corpus range is duplicated.")
        seen.add(key)


def _geometry_sort_key(item: V7LabelGeometryAnnotation) -> tuple[int, str, str]:
    return (item.position_index, item.source_id, item.source_checksum_sha256)


def _fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "V7AcceptanceEvaluation",
    "V7AcceptanceMetric",
    "V7AcceptancePrediction",
    "V7AcceptanceTruth",
    "V7AutomaticOutcome",
    "V7CalibrationError",
    "V7EvaluationStatus",
    "V7GeometryCalibration",
    "V7LabelGeometryAnnotation",
    "V7SourceReference",
    "calibrate_v7_label_geometry",
    "evaluate_v7_acceptance",
]
