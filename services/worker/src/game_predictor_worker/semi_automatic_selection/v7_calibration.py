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

V7_CALIBRATION_VERSION = "v7-calibration-v2"
V7_CALIBRATION_MINIMUM_SOURCES_PER_POSITION = 5
V7_CALIBRATION_MINIMUM_CAPTURE_GROUPS_PER_POSITION = 2
V7_CALIBRATION_MAXIMUM_P95_CENTER_RESIDUAL = 0.04
V7_CALIBRATION_POSITION_CONFIDENCE = 0.95
V7_ACCEPTANCE_MINIMUM_PERCENT = 95
V7_STANDARD_GEOMETRY_FAMILY_ID = "standard_3x3_numeric_labels_v1"


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


class V7ValidationQualityStatus(StrEnum):
    """Quality gate for an automatically selected T05 representative."""

    ACCEPTABLE = "acceptable"
    UNACCEPTABLE = "unacceptable"
    UNKNOWN = "unknown"


class V7CropAssessment(StrEnum):
    """Operator's visible verification of a crop derived from an annotated centre."""

    CONTAINED = "contained"
    CLIPPED = "clipped"
    UNCERTAIN = "uncertain"


class V7AnnotationState(StrEnum):
    """One reviewed state for a source/slot in an annotation session."""

    UNREVIEWED = "unreviewed"
    ANNOTATED = "annotated"
    UNAVAILABLE = "unavailable"


class V7SourceExposureStatus(StrEnum):
    KNOWN = "known"
    RESERVED_HOLDOUT = "reserved_holdout"


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
    geometry_family_id: str | None = None
    capture_group_id: str | None = None
    crop_assessment: V7CropAssessment = V7CropAssessment.UNCERTAIN

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
            "captureGroupId": self.capture_group_id,
            "cropAssessment": self.crop_assessment.value,
            "geometryFamilyId": self.geometry_family_id,
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
    geometry_family_id: str
    locator_config: V7GridLabelLocatorConfig
    source_count_by_position: tuple[int, ...]
    capture_group_count_by_position: tuple[int, ...]
    p95_center_residual_by_position: tuple[float, ...]
    p95_center_residual: float
    maximum_p95_center_residual: float
    minimum_sources_per_position: int
    minimum_capture_groups_per_position: int

    def __post_init__(self) -> None:
        if (
            not self.geometry_family_id
            or len(self.source_count_by_position) != 9
            or len(self.capture_group_count_by_position) != 9
            or len(self.p95_center_residual_by_position) != 9
            or any(
                count < self.minimum_capture_groups_per_position
                for count in self.capture_group_count_by_position
            )
            or any(
                count < self.minimum_sources_per_position for count in self.source_count_by_position
            )
            or self.minimum_sources_per_position < 1
            or self.minimum_capture_groups_per_position < 1
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
            "captureGroupCountByPosition": list(self.capture_group_count_by_position),
            "geometryFamilyId": self.geometry_family_id,
            "locatorConfig": self.locator_config.as_dict(),
            "manifestFingerprint": self.manifest_fingerprint,
            "maximumP95CenterResidual": self.maximum_p95_center_residual,
            "minimumCaptureGroupsPerPosition": self.minimum_capture_groups_per_position,
            "minimumSourcesPerPosition": self.minimum_sources_per_position,
            "p95CenterResidual": self.p95_center_residual,
            "p95CenterResidualByPosition": list(self.p95_center_residual_by_position),
            "sourceCountByPosition": list(self.source_count_by_position),
            "status": self.status.value,
            "version": V7_CALIBRATION_VERSION,
        }


@dataclass(frozen=True, slots=True)
class V7GeometryProfile:
    """An immutable exported calibration profile, never an activation by itself."""

    profile_fingerprint: str
    calibration: V7GeometryCalibration
    revision: int

    def __post_init__(self) -> None:
        if self.revision < 0:
            raise V7CalibrationError("V7 geometry profile revision is invalid.")
        try:
            validate_sha256(self.profile_fingerprint, field="profileFingerprint")
        except ValueError as error:
            raise V7CalibrationError("V7 geometry profile fingerprint is invalid.") from error

    def as_dict(self) -> dict[str, object]:
        return {
            "calibration": self.calibration.as_dict(),
            "profileFingerprint": self.profile_fingerprint,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class V7GeometryAdoption:
    """A separate approval that one source-game corpus may use one profile."""

    adoption_key: str
    source_game_ref: str
    geometry_family_id: str
    profile_fingerprint: str
    validation_report_fingerprint: str

    def __post_init__(self) -> None:
        if not self.adoption_key or not self.source_game_ref or not self.geometry_family_id:
            raise V7CalibrationError("V7 geometry adoption identity is invalid.")
        for field, value in (
            ("profileFingerprint", self.profile_fingerprint),
            ("validationReportFingerprint", self.validation_report_fingerprint),
        ):
            try:
                validate_sha256(value, field=field)
            except ValueError as error:
                raise V7CalibrationError("V7 geometry adoption fingerprint is invalid.") from error

    def as_dict(self) -> dict[str, object]:
        return {
            "adoptionKey": self.adoption_key,
            "geometryFamilyId": self.geometry_family_id,
            "profileFingerprint": self.profile_fingerprint,
            "sourceGameRef": self.source_game_ref,
            "validationReportFingerprint": self.validation_report_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class V7SourceExposureRecord:
    """Checksum-bound history used to keep the final holdout independent."""

    source: V7SourceReference
    status: V7SourceExposureStatus

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source.as_dict(),
            "status": self.status.value,
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
class V7HoldoutSourceObservation:
    """Independent human truth for one JPEG that may be selected by V7."""

    source: V7SourceReference
    represented_range_start: int
    represented_range_end: int
    top_cropped: bool
    bottom_cropped: bool

    def __post_init__(self) -> None:
        if (
            self.represented_range_start < 1
            or self.represented_range_end < self.represented_range_start
        ):
            raise V7CalibrationError("V7 holdout source observation range is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "bottomCropped": self.bottom_cropped,
            "representedRangeEnd": self.represented_range_end,
            "representedRangeStart": self.represented_range_start,
            "sourceChecksumSha256": self.source.source_checksum_sha256,
            "sourceId": self.source.source_id,
            "topCropped": self.top_cropped,
        }


@dataclass(frozen=True, slots=True)
class V7HoldoutAcceptanceTruth:
    """Independent human ground truth exclusively for the final T12 holdout."""

    case_id: str
    corpus_case_id: str
    split: V7CorpusSplit
    expected_range_start: int
    expected_range_end: int
    evidence_sources: tuple[V7SourceReference, ...]
    acceptable_representative_sources: tuple[V7SourceReference, ...]
    automatically_recoverable: bool
    eligible_acceptable_representative: bool

    def __post_init__(self) -> None:
        if (
            not self.case_id
            or not self.corpus_case_id
            or self.expected_range_start < 1
            or self.expected_range_end < self.expected_range_start
            or not self.evidence_sources
            or len({item.source_id for item in self.evidence_sources}) != len(self.evidence_sources)
            or len({item.source_id for item in self.acceptable_representative_sources})
            != len(self.acceptable_representative_sources)
            or self.eligible_acceptable_representative
            != bool(self.acceptable_representative_sources)
            or self.split is not V7CorpusSplit.HOLDOUT
        ):
            raise V7CalibrationError("V7 holdout acceptance truth split or case ID is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "automaticallyRecoverable": self.automatically_recoverable,
            "acceptableRepresentativeSources": [
                item.as_dict() for item in self.acceptable_representative_sources
            ],
            "caseId": self.case_id,
            "corpusCaseId": self.corpus_case_id,
            "evidenceSources": [item.as_dict() for item in self.evidence_sources],
            "eligibleAcceptableRepresentative": self.eligible_acceptable_representative,
            "expectedRangeEnd": self.expected_range_end,
            "expectedRangeStart": self.expected_range_start,
            "split": self.split.value,
        }


@dataclass(frozen=True, slots=True)
class V7ValidationSourceObservation:
    """Independent source truth used only by non-holdout T05 validation."""

    source: V7SourceReference
    represented_range_start: int
    represented_range_end: int
    top_cropped: bool
    bottom_cropped: bool

    def __post_init__(self) -> None:
        if (
            self.represented_range_start < 1
            or self.represented_range_end < self.represented_range_start
        ):
            raise V7CalibrationError("V7 validation source observation range is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "bottomCropped": self.bottom_cropped,
            "representedRangeEnd": self.represented_range_end,
            "representedRangeStart": self.represented_range_start,
            "sourceChecksumSha256": self.source.source_checksum_sha256,
            "sourceId": self.source.source_id,
            "topCropped": self.top_cropped,
        }


@dataclass(frozen=True, slots=True)
class V7ValidationAcceptanceTruth:
    """Human truth for T05; deliberately disjoint from the sealed holdout."""

    case_id: str
    corpus_case_id: str
    split: V7CorpusSplit
    expected_range_start: int
    expected_range_end: int
    evidence_sources: tuple[V7SourceReference, ...]
    acceptable_representative_sources: tuple[V7SourceReference, ...]
    automatically_recoverable: bool
    eligible_acceptable_representative: bool

    def __post_init__(self) -> None:
        if (
            not self.case_id
            or not self.corpus_case_id
            or self.expected_range_start < 1
            or self.expected_range_end < self.expected_range_start
            or not self.evidence_sources
            or len({item.source_id for item in self.evidence_sources}) != len(self.evidence_sources)
            or len({item.source_id for item in self.acceptable_representative_sources})
            != len(self.acceptable_representative_sources)
            or self.eligible_acceptable_representative
            != bool(self.acceptable_representative_sources)
            or self.split in {V7CorpusSplit.HOLDOUT, V7CorpusSplit.REFERENCE_ONLY}
        ):
            raise V7CalibrationError("V7 validation truth split or case ID is invalid for T05.")

    def as_dict(self) -> dict[str, object]:
        return {
            "acceptableRepresentativeSources": [
                item.as_dict() for item in self.acceptable_representative_sources
            ],
            "automaticallyRecoverable": self.automatically_recoverable,
            "caseId": self.case_id,
            "corpusCaseId": self.corpus_case_id,
            "evidenceSources": [item.as_dict() for item in self.evidence_sources],
            "eligibleAcceptableRepresentative": self.eligible_acceptable_representative,
            "expectedRangeEnd": self.expected_range_end,
            "expectedRangeStart": self.expected_range_start,
            "split": self.split.value,
        }


@dataclass(frozen=True, slots=True)
class V7ValidationPredictionSnapshot:
    """Raw automatic observation frozen before manual correction for T05."""

    case_id: str
    predicted_range_start: int | None
    predicted_range_end: int | None
    selected_source: V7SourceReference | None
    quality_status: V7ValidationQualityStatus
    top_warning: bool
    bottom_warning: bool
    manual_review: bool

    def __post_init__(self) -> None:
        has_range = self.predicted_range_start is not None or self.predicted_range_end is not None
        if (
            not self.case_id
            or has_range
            and (
                self.predicted_range_start is None
                or self.predicted_range_end is None
                or self.predicted_range_start < 1
                or self.predicted_range_end < self.predicted_range_start
            )
            or has_range != (self.selected_source is not None)
            or not has_range
            and (
                self.top_warning
                or self.bottom_warning
                or self.quality_status is not V7ValidationQualityStatus.UNKNOWN
            )
        ):
            raise V7CalibrationError("V7 validation prediction snapshot is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "bottomWarning": self.bottom_warning,
            "caseId": self.case_id,
            "manualReview": self.manual_review,
            "predictedRangeEnd": self.predicted_range_end,
            "predictedRangeStart": self.predicted_range_start,
            "qualityStatus": self.quality_status.value,
            "selectedSource": (
                None if self.selected_source is None else self.selected_source.as_dict()
            ),
            "topWarning": self.top_warning,
        }


@dataclass(frozen=True, slots=True)
class V7HoldoutPredictionSnapshot:
    """Frozen raw automatic observation evaluated against independent holdout truth."""

    case_id: str
    predicted_range_start: int | None
    predicted_range_end: int | None
    selected_source: V7SourceReference | None
    top_warning: bool
    bottom_warning: bool
    manual_review: bool

    def __post_init__(self) -> None:
        has_range = self.predicted_range_start is not None or self.predicted_range_end is not None
        if (
            not self.case_id
            or has_range
            and (
                self.predicted_range_start is None
                or self.predicted_range_end is None
                or self.predicted_range_start < 1
                or self.predicted_range_end < self.predicted_range_start
            )
            or has_range != (self.selected_source is not None)
            or not has_range
            and (self.top_warning or self.bottom_warning)
        ):
            raise V7CalibrationError("V7 holdout prediction snapshot is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "bottomWarning": self.bottom_warning,
            "caseId": self.case_id,
            "manualReview": self.manual_review,
            "predictedRangeEnd": self.predicted_range_end,
            "predictedRangeStart": self.predicted_range_start,
            "selectedSource": (
                None if self.selected_source is None else self.selected_source.as_dict()
            ),
            "topWarning": self.top_warning,
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
    geometry_family_id: str,
    minimum_sources_per_position: int = V7_CALIBRATION_MINIMUM_SOURCES_PER_POSITION,
    minimum_capture_groups_per_position: int = (V7_CALIBRATION_MINIMUM_CAPTURE_GROUPS_PER_POSITION),
    maximum_p95_center_residual: float = V7_CALIBRATION_MAXIMUM_P95_CENTER_RESIDUAL,
) -> V7GeometryCalibration:
    """Build a locator only from independently annotated calibration sources."""

    if (
        minimum_sources_per_position < 1
        or minimum_capture_groups_per_position < 1
        or not 0 < maximum_p95_center_residual < 1
    ):
        raise V7CalibrationError("V7 geometry calibration policy is invalid.")
    if not geometry_family_id:
        raise V7CalibrationError("V7 geometry family is required for calibration.")
    values = tuple(annotations)
    if not values or any(item.split is not V7CorpusSplit.CALIBRATION for item in values):
        raise V7CalibrationError(
            "V7 geometry calibration requires calibration-split annotations only."
        )
    _validate_geometry_source_identity(values)
    if any(not item.capture_group_id for item in values):
        raise V7CalibrationError("V7 geometry calibration requires capture groups.")
    if any(item.crop_assessment is not V7CropAssessment.CONTAINED for item in values):
        raise V7CalibrationError("V7 geometry calibration requires contained label crops.")
    if any(item.geometry_family_id != geometry_family_id for item in values):
        raise V7CalibrationError("V7 geometry calibration mixes incompatible families.")
    positions = tuple(
        tuple(item for item in values if item.position_index == position) for position in range(9)
    )
    source_counts = tuple(len({item.source_id for item in position}) for position in positions)
    if any(count < minimum_sources_per_position for count in source_counts):
        raise V7CalibrationError(
            "V7 geometry calibration lacks independent sources for a position."
        )
    capture_group_counts = tuple(
        len({item.capture_group_id for item in position}) for position in positions
    )
    if any(count < minimum_capture_groups_per_position for count in capture_group_counts):
        raise V7CalibrationError(
            "V7 geometry calibration lacks independent capture groups for a position."
        )
    centers = tuple(
        (median(item.center_x for item in position), median(item.center_y for item in position))
        for position in positions
    )
    residual_values = tuple(
        math.hypot(
            item.center_x - centers[item.position_index][0],
            item.center_y - centers[item.position_index][1],
        )
        for item in values
    )
    residuals = sorted(residual_values)
    p95 = residuals[math.ceil(len(residuals) * 0.95) - 1]
    p95_by_position = tuple(
        sorted(
            math.hypot(
                item.center_x - centers[position][0],
                item.center_y - centers[position][1],
            )
            for item in values
            if item.position_index == position
        )[math.ceil(len(position_values) * 0.95) - 1]
        for position, position_values in enumerate(positions)
    )
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
        geometry_family_id=geometry_family_id,
        input_fingerprint=_fingerprint(
            {
                "annotations": [item.as_dict() for item in sorted(values, key=_geometry_sort_key)],
                "geometryFamilyId": geometry_family_id,
                "maximumP95CenterResidual": maximum_p95_center_residual,
                "minimumCaptureGroupsPerPosition": minimum_capture_groups_per_position,
                "minimumSourcesPerPosition": minimum_sources_per_position,
            }
        ),
        locator_config=config,
        source_count_by_position=source_counts,
        capture_group_count_by_position=capture_group_counts,
        p95_center_residual_by_position=p95_by_position,
        p95_center_residual=p95,
        maximum_p95_center_residual=maximum_p95_center_residual,
        minimum_sources_per_position=minimum_sources_per_position,
        minimum_capture_groups_per_position=minimum_capture_groups_per_position,
    )


def evaluate_v7_acceptance(
    truths: Iterable[V7AcceptanceTruth],
    predictions: Iterable[V7AcceptancePrediction],
) -> V7AcceptanceEvaluation:
    """Account for V7 automatic performance without absorbing manual corrections."""

    truth_values = tuple(truths)
    if any(type(value) is not V7AcceptanceTruth for value in truth_values):
        raise V7CalibrationError("V7 T05 acceptance requires T05 truth only.")
    return _evaluate_v7_acceptance(truth_values, predictions)


def evaluate_v7_holdout_acceptance(
    truths: Iterable[V7HoldoutAcceptanceTruth],
    snapshots: Iterable[V7HoldoutPredictionSnapshot],
    source_observations: Iterable[V7HoldoutSourceObservation],
) -> V7AcceptanceEvaluation:
    """Account for the final holdout without permitting it in T05 calibration."""

    truth_values = tuple(truths)
    snapshot_values = tuple(snapshots)
    source_values = tuple(source_observations)
    if any(type(value) is not V7HoldoutAcceptanceTruth for value in truth_values):
        raise V7CalibrationError("V7 holdout acceptance requires holdout truth only.")
    if any(type(value) is not V7HoldoutPredictionSnapshot for value in snapshot_values):
        raise V7CalibrationError("V7 holdout acceptance requires raw prediction snapshots only.")
    if any(type(value) is not V7HoldoutSourceObservation for value in source_values):
        raise V7CalibrationError("V7 holdout acceptance requires source observations only.")
    truth_by_case = _unique_holdout_truth_by_case_id(truth_values)
    snapshot_by_case = _unique_holdout_snapshot_by_case_id(snapshot_values)
    if set(truth_by_case) != set(snapshot_by_case):
        raise V7CalibrationError("V7 holdout truth and prediction snapshot cases differ.")
    source_by_id = _unique_holdout_source_observations(source_values)
    _validate_holdout_truth_source_references(truth_values, source_by_id)
    resolved = tuple(
        _holdout_snapshot_as_prediction(
            truth,
            snapshot_by_case[truth.case_id],
            source_by_id=source_by_id,
        )
        for truth in truth_by_case.values()
    )
    return _evaluate_v7_holdout(truth_by_case.values(), resolved, source_values)


def evaluate_v7_validation_acceptance(
    truths: Iterable[V7ValidationAcceptanceTruth],
    snapshots: Iterable[V7ValidationPredictionSnapshot],
    source_observations: Iterable[V7ValidationSourceObservation],
) -> V7AcceptanceEvaluation:
    """Evaluate non-holdout T05 from raw snapshots, never caller outcomes."""

    truth_values = tuple(truths)
    snapshot_values = tuple(snapshots)
    source_values = tuple(source_observations)
    if any(type(value) is not V7ValidationAcceptanceTruth for value in truth_values):
        raise V7CalibrationError("V7 validation acceptance requires T05 truth only.")
    if any(type(value) is not V7ValidationPredictionSnapshot for value in snapshot_values):
        raise V7CalibrationError("V7 validation acceptance requires raw prediction snapshots only.")
    if any(type(value) is not V7ValidationSourceObservation for value in source_values):
        raise V7CalibrationError("V7 validation acceptance requires source observations only.")
    truth_by_case = _unique_validation_truth_by_case_id(truth_values)
    snapshot_by_case = _unique_validation_snapshot_by_case_id(snapshot_values)
    if set(truth_by_case) != set(snapshot_by_case):
        raise V7CalibrationError("V7 validation truth and prediction snapshot cases differ.")
    source_by_id = _unique_validation_source_observations(source_values)
    _validate_validation_truth_source_references(truth_values, source_by_id)
    resolved = tuple(
        _validation_snapshot_as_prediction(
            truth,
            snapshot_by_case[truth.case_id],
            source_by_id=source_by_id,
        )
        for truth in truth_by_case.values()
    )
    return _evaluate_v7_validation(truth_by_case.values(), resolved, source_values)


def _evaluate_v7_acceptance(
    truths: Iterable[V7AcceptanceTruth],
    predictions: Iterable[V7AcceptancePrediction],
) -> V7AcceptanceEvaluation:
    """Compute shared metrics after the caller selected the permitted truth type."""

    truth_by_case = _unique_truth_by_case_id(truths)
    prediction_by_case = _unique_prediction_by_case_id(predictions)
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


def _unique_truth_by_case_id(
    values: Iterable[V7AcceptanceTruth],
) -> dict[str, V7AcceptanceTruth]:
    result: dict[str, V7AcceptanceTruth] = {}
    for value in values:
        if value.case_id in result:
            raise V7CalibrationError("V7 acceptance truth case ID is duplicated.")
        result[value.case_id] = value
    return result


def _unique_prediction_by_case_id(
    values: Iterable[V7AcceptancePrediction],
) -> dict[str, V7AcceptancePrediction]:
    result: dict[str, V7AcceptancePrediction] = {}
    for value in values:
        if value.case_id in result:
            raise V7CalibrationError("V7 acceptance prediction case ID is duplicated.")
        result[value.case_id] = value
    return result


def _unique_holdout_truth_by_case_id(
    values: Iterable[V7HoldoutAcceptanceTruth],
) -> dict[str, V7HoldoutAcceptanceTruth]:
    result: dict[str, V7HoldoutAcceptanceTruth] = {}
    for value in values:
        if value.case_id in result:
            raise V7CalibrationError("V7 holdout acceptance truth case ID is duplicated.")
        result[value.case_id] = value
    return result


def _unique_validation_truth_by_case_id(
    values: Iterable[V7ValidationAcceptanceTruth],
) -> dict[str, V7ValidationAcceptanceTruth]:
    result: dict[str, V7ValidationAcceptanceTruth] = {}
    for value in values:
        if value.case_id in result:
            raise V7CalibrationError("V7 validation truth case ID is duplicated.")
        result[value.case_id] = value
    return result


def _unique_holdout_snapshot_by_case_id(
    values: Iterable[V7HoldoutPredictionSnapshot],
) -> dict[str, V7HoldoutPredictionSnapshot]:
    result: dict[str, V7HoldoutPredictionSnapshot] = {}
    for value in values:
        if value.case_id in result:
            raise V7CalibrationError("V7 holdout prediction snapshot case ID is duplicated.")
        result[value.case_id] = value
    return result


def _unique_validation_snapshot_by_case_id(
    values: Iterable[V7ValidationPredictionSnapshot],
) -> dict[str, V7ValidationPredictionSnapshot]:
    result: dict[str, V7ValidationPredictionSnapshot] = {}
    for value in values:
        if value.case_id in result:
            raise V7CalibrationError("V7 validation prediction snapshot case ID is duplicated.")
        result[value.case_id] = value
    return result


def _unique_holdout_source_observations(
    values: Iterable[V7HoldoutSourceObservation],
) -> dict[str, V7HoldoutSourceObservation]:
    result: dict[str, V7HoldoutSourceObservation] = {}
    source_ids_by_checksum: dict[str, str] = {}
    for value in values:
        if value.source.source_id in result:
            raise V7CalibrationError("V7 holdout source observation ID is duplicated.")
        other_source_id = source_ids_by_checksum.setdefault(
            value.source.source_checksum_sha256,
            value.source.source_id,
        )
        if other_source_id != value.source.source_id:
            raise V7CalibrationError("V7 holdout source observations are byte-identical aliases.")
        result[value.source.source_id] = value
    return result


def _unique_validation_source_observations(
    values: Iterable[V7ValidationSourceObservation],
) -> dict[str, V7ValidationSourceObservation]:
    result: dict[str, V7ValidationSourceObservation] = {}
    source_ids_by_checksum: dict[str, str] = {}
    for value in values:
        if value.source.source_id in result:
            raise V7CalibrationError("V7 validation source observation ID is duplicated.")
        other_source_id = source_ids_by_checksum.setdefault(
            value.source.source_checksum_sha256,
            value.source.source_id,
        )
        if other_source_id != value.source.source_id:
            raise V7CalibrationError(
                "V7 validation source observations are byte-identical aliases."
            )
        result[value.source.source_id] = value
    return result


def _validate_holdout_truth_source_references(
    truths: Iterable[V7HoldoutAcceptanceTruth],
    source_by_id: Mapping[str, V7HoldoutSourceObservation],
) -> None:
    for truth in truths:
        for source in (*truth.evidence_sources, *truth.acceptable_representative_sources):
            observation = source_by_id.get(source.source_id)
            if observation is None or observation.source != source:
                raise V7CalibrationError("V7 holdout truth source lacks an exact observation.")
            if (
                observation.represented_range_start,
                observation.represented_range_end,
            ) != (truth.expected_range_start, truth.expected_range_end):
                raise V7CalibrationError("V7 holdout truth source range differs from its case.")


def _validate_validation_truth_source_references(
    truths: Iterable[V7ValidationAcceptanceTruth],
    source_by_id: Mapping[str, V7ValidationSourceObservation],
) -> None:
    for truth in truths:
        for source in (*truth.evidence_sources, *truth.acceptable_representative_sources):
            observation = source_by_id.get(source.source_id)
            if observation is None or observation.source != source:
                raise V7CalibrationError("V7 validation truth source lacks an exact observation.")
            if (
                observation.represented_range_start,
                observation.represented_range_end,
            ) != (truth.expected_range_start, truth.expected_range_end):
                raise V7CalibrationError("V7 validation truth source range differs from its case.")


def _holdout_snapshot_as_prediction(
    truth: V7HoldoutAcceptanceTruth,
    snapshot: V7HoldoutPredictionSnapshot,
    *,
    source_by_id: Mapping[str, V7HoldoutSourceObservation],
) -> tuple[V7AcceptancePrediction, V7HoldoutSourceObservation | None]:
    selected_observation: V7HoldoutSourceObservation | None = None
    if snapshot.selected_source is not None:
        selected_observation = source_by_id.get(snapshot.selected_source.source_id)
        if selected_observation is None or selected_observation.source != snapshot.selected_source:
            raise V7CalibrationError("V7 holdout selected source lacks an exact observation.")
    if snapshot.predicted_range_start is None:
        range_outcome = V7AutomaticOutcome.NOT_SELECTED
    elif selected_observation is not None and (
        snapshot.predicted_range_start,
        snapshot.predicted_range_end,
        selected_observation.represented_range_start,
        selected_observation.represented_range_end,
    ) == (
        truth.expected_range_start,
        truth.expected_range_end,
        truth.expected_range_start,
        truth.expected_range_end,
    ):
        range_outcome = V7AutomaticOutcome.CORRECT
    else:
        range_outcome = V7AutomaticOutcome.INCORRECT
    acceptable_sources = {
        (item.source_id, item.source_checksum_sha256)
        for item in truth.acceptable_representative_sources
    }
    selected_source = snapshot.selected_source
    if (
        range_outcome is not V7AutomaticOutcome.CORRECT
        or not truth.eligible_acceptable_representative
    ):
        representative_outcome = V7AutomaticOutcome.NOT_SELECTED
    elif (
        selected_source is not None
        and (
            selected_source.source_id,
            selected_source.source_checksum_sha256,
        )
        in acceptable_sources
    ):
        representative_outcome = V7AutomaticOutcome.CORRECT
    else:
        representative_outcome = V7AutomaticOutcome.INCORRECT
    return (
        V7AcceptancePrediction(
            case_id=snapshot.case_id,
            range_outcome=range_outcome,
            representative_outcome=representative_outcome,
            selected_source=selected_source,
            top_warning=snapshot.top_warning,
            bottom_warning=snapshot.bottom_warning,
            manual_review=snapshot.manual_review,
        ),
        selected_observation,
    )


def _validation_snapshot_as_prediction(
    truth: V7ValidationAcceptanceTruth,
    snapshot: V7ValidationPredictionSnapshot,
    *,
    source_by_id: Mapping[str, V7ValidationSourceObservation],
) -> tuple[V7AcceptancePrediction, V7ValidationSourceObservation | None]:
    selected_observation: V7ValidationSourceObservation | None = None
    if snapshot.selected_source is not None:
        selected_observation = source_by_id.get(snapshot.selected_source.source_id)
        if selected_observation is None or selected_observation.source != snapshot.selected_source:
            raise V7CalibrationError("V7 validation selected source lacks an exact observation.")
    if snapshot.predicted_range_start is None:
        range_outcome = V7AutomaticOutcome.NOT_SELECTED
    elif selected_observation is not None and (
        snapshot.predicted_range_start,
        snapshot.predicted_range_end,
        selected_observation.represented_range_start,
        selected_observation.represented_range_end,
    ) == (
        truth.expected_range_start,
        truth.expected_range_end,
        truth.expected_range_start,
        truth.expected_range_end,
    ):
        range_outcome = V7AutomaticOutcome.CORRECT
    else:
        range_outcome = V7AutomaticOutcome.INCORRECT
    acceptable_sources = {
        (item.source_id, item.source_checksum_sha256)
        for item in truth.acceptable_representative_sources
    }
    selected_source = snapshot.selected_source
    if (
        range_outcome is not V7AutomaticOutcome.CORRECT
        or not truth.eligible_acceptable_representative
        or snapshot.quality_status is not V7ValidationQualityStatus.ACCEPTABLE
    ):
        representative_outcome = V7AutomaticOutcome.NOT_SELECTED
    elif (
        selected_source is not None
        and (selected_source.source_id, selected_source.source_checksum_sha256)
        in acceptable_sources
    ):
        representative_outcome = V7AutomaticOutcome.CORRECT
    else:
        representative_outcome = V7AutomaticOutcome.INCORRECT
    return (
        V7AcceptancePrediction(
            case_id=snapshot.case_id,
            range_outcome=range_outcome,
            representative_outcome=representative_outcome,
            selected_source=selected_source,
            top_warning=snapshot.top_warning,
            bottom_warning=snapshot.bottom_warning,
            manual_review=snapshot.manual_review,
        ),
        selected_observation,
    )


def _evaluate_v7_holdout(
    truths: Iterable[V7HoldoutAcceptanceTruth],
    resolved: Iterable[tuple[V7AcceptancePrediction, V7HoldoutSourceObservation | None]],
    source_observations: Iterable[V7HoldoutSourceObservation],
) -> V7AcceptanceEvaluation:
    truth_values = tuple(truths)
    resolved_values = tuple(resolved)
    prediction_values = tuple(item[0] for item in resolved_values)
    selected_observations = tuple(item[1] for item in resolved_values)
    _validate_unique_holdout_range_cases(truth_values)
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
        and prediction.representative_outcome is V7AutomaticOutcome.CORRECT
        for truth, prediction in zip(truth_values, prediction_values, strict=True)
    )
    top_denominator = sum(
        observation is not None and observation.top_cropped for observation in selected_observations
    )
    top_numerator = sum(
        observation is not None and observation.top_cropped and prediction.top_warning
        for observation, prediction in zip(selected_observations, prediction_values, strict=True)
    )
    bottom_denominator = sum(
        observation is not None and observation.bottom_cropped
        for observation in selected_observations
    )
    bottom_numerator = sum(
        observation is not None and observation.bottom_cropped and prediction.bottom_warning
        for observation, prediction in zip(selected_observations, prediction_values, strict=True)
    )
    return V7AcceptanceEvaluation(
        input_fingerprint=_fingerprint(
            {
                "predictions": [item.as_dict() for item in prediction_values],
                "sourceObservations": [item.as_dict() for item in source_observations],
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
            observation is not None and prediction.top_warning and not observation.top_cropped
            for observation, prediction in zip(
                selected_observations, prediction_values, strict=True
            )
        ),
        bottom_crop_false_positive_count=sum(
            observation is not None and prediction.bottom_warning and not observation.bottom_cropped
            for observation, prediction in zip(
                selected_observations, prediction_values, strict=True
            )
        ),
        manual_review_count=sum(item.manual_review for item in prediction_values),
        total_case_count=len(truth_values),
    )


def _evaluate_v7_validation(
    truths: Iterable[V7ValidationAcceptanceTruth],
    resolved: Iterable[tuple[V7AcceptancePrediction, V7ValidationSourceObservation | None]],
    source_observations: Iterable[V7ValidationSourceObservation],
) -> V7AcceptanceEvaluation:
    truth_values = tuple(truths)
    resolved_values = tuple(resolved)
    prediction_values = tuple(item[0] for item in resolved_values)
    selected_observations = tuple(item[1] for item in resolved_values)
    _validate_unique_validation_range_cases(truth_values)
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
    top_denominator = sum(
        observation is not None and observation.top_cropped for observation in selected_observations
    )
    top_numerator = sum(
        observation is not None and observation.top_cropped and prediction.top_warning
        for observation, prediction in zip(selected_observations, prediction_values, strict=True)
    )
    bottom_denominator = sum(
        observation is not None and observation.bottom_cropped
        for observation in selected_observations
    )
    bottom_numerator = sum(
        observation is not None and observation.bottom_cropped and prediction.bottom_warning
        for observation, prediction in zip(selected_observations, prediction_values, strict=True)
    )
    return V7AcceptanceEvaluation(
        input_fingerprint=_fingerprint(
            {
                "predictions": [item.as_dict() for item in prediction_values],
                "sourceObservations": [item.as_dict() for item in source_observations],
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
            observation is not None and prediction.top_warning and not observation.top_cropped
            for observation, prediction in zip(
                selected_observations, prediction_values, strict=True
            )
        ),
        bottom_crop_false_positive_count=sum(
            observation is not None and prediction.bottom_warning and not observation.bottom_cropped
            for observation, prediction in zip(
                selected_observations, prediction_values, strict=True
            )
        ),
        manual_review_count=sum(item.manual_review for item in prediction_values),
        total_case_count=len(truth_values),
    )


def _validate_unique_range_cases(
    values: Iterable[V7AcceptanceTruth],
) -> None:
    seen: set[tuple[str, int, int]] = set()
    for value in values:
        key = (value.corpus_case_id, value.expected_range_start, value.expected_range_end)
        if key in seen:
            raise V7CalibrationError("V7 acceptance corpus range is duplicated.")
        seen.add(key)


def _validate_unique_holdout_range_cases(values: Iterable[V7HoldoutAcceptanceTruth]) -> None:
    seen: set[tuple[str, int, int]] = set()
    for value in values:
        key = (value.corpus_case_id, value.expected_range_start, value.expected_range_end)
        if key in seen:
            raise V7CalibrationError("V7 holdout acceptance corpus range is duplicated.")
        seen.add(key)


def _validate_unique_validation_range_cases(values: Iterable[V7ValidationAcceptanceTruth]) -> None:
    seen: set[tuple[str, int, int]] = set()
    for value in values:
        key = (value.corpus_case_id, value.expected_range_start, value.expected_range_end)
        if key in seen:
            raise V7CalibrationError("V7 validation corpus range is duplicated.")
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
    "V7HoldoutAcceptanceTruth",
    "V7HoldoutPredictionSnapshot",
    "V7HoldoutSourceObservation",
    "V7ValidationAcceptanceTruth",
    "V7ValidationPredictionSnapshot",
    "V7ValidationQualityStatus",
    "V7ValidationSourceObservation",
    "V7AutomaticOutcome",
    "V7AnnotationState",
    "V7CalibrationError",
    "V7_CALIBRATION_VERSION",
    "V7CropAssessment",
    "V7EvaluationStatus",
    "V7GeometryCalibration",
    "V7GeometryAdoption",
    "V7GeometryProfile",
    "V7LabelGeometryAnnotation",
    "V7SourceReference",
    "V7SourceExposureRecord",
    "V7SourceExposureStatus",
    "V7_STANDARD_GEOMETRY_FAMILY_ID",
    "calibrate_v7_label_geometry",
    "evaluate_v7_acceptance",
    "evaluate_v7_holdout_acceptance",
    "evaluate_v7_validation_acceptance",
]
