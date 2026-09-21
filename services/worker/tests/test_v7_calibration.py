from __future__ import annotations

from dataclasses import replace

import pytest
from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7AcceptancePrediction,
    V7AcceptanceTruth,
    V7AutomaticOutcome,
    V7CalibrationError,
    V7EvaluationStatus,
    V7HoldoutAcceptanceTruth,
    V7LabelGeometryAnnotation,
    V7SourceReference,
    calibrate_v7_label_geometry,
    evaluate_v7_acceptance,
    evaluate_v7_holdout_acceptance,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7CorpusSplit

FINGERPRINT = "a" * 64
SOURCE = V7SourceReference(source_id="validation/source.jpg", source_checksum_sha256="c" * 64)


def _annotations(*, source_count: int = 5, spread: float = 0.002):
    result = []
    for source_index in range(source_count):
        for position_index in range(9):
            row, column = divmod(position_index, 3)
            offset = (source_index - source_count // 2) * spread
            result.append(
                V7LabelGeometryAnnotation(
                    source_id=f"source-{source_index}",
                    source_checksum_sha256=f"{source_index + 1:064x}",
                    split=V7CorpusSplit.CALIBRATION,
                    position_index=position_index,
                    center_x=0.2 + column * 0.25 + offset,
                    center_y=0.3 + row * 0.2 + offset,
                )
            )
    return tuple(result)


def test_geometry_calibration_requires_five_independent_calibration_sources_per_position() -> None:
    calibration = calibrate_v7_label_geometry(_annotations(), manifest_fingerprint=FINGERPRINT)

    assert calibration.status is V7EvaluationStatus.PASSED
    assert calibration.source_count_by_position == (5,) * 9
    assert calibration.locator_config.position_confidence == 0.95
    assert calibration.p95_center_residual <= calibration.maximum_p95_center_residual
    assert (
        calibration.input_fingerprint
        == calibrate_v7_label_geometry(
            tuple(reversed(_annotations())), manifest_fingerprint=FINGERPRINT
        ).input_fingerprint
    )

    with pytest.raises(V7CalibrationError, match="lacks independent"):
        calibrate_v7_label_geometry(_annotations(source_count=4), manifest_fingerprint=FINGERPRINT)


def test_geometry_calibration_rejects_mixed_split_duplicate_or_unstable_positions() -> None:
    mixed = list(_annotations())
    mixed[0] = replace(mixed[0], split=V7CorpusSplit.DEVELOPMENT)
    with pytest.raises(V7CalibrationError, match="calibration-split"):
        calibrate_v7_label_geometry(mixed, manifest_fingerprint=FINGERPRINT)

    duplicate = (*_annotations(), _annotations()[0])
    with pytest.raises(V7CalibrationError, match="more than once"):
        calibrate_v7_label_geometry(duplicate, manifest_fingerprint=FINGERPRINT)

    duplicate_checksum = (*_annotations(), replace(_annotations()[0], source_id="copy-source"))
    with pytest.raises(V7CalibrationError, match="byte-identical aliases"):
        calibrate_v7_label_geometry(duplicate_checksum, manifest_fingerprint=FINGERPRINT)

    unstable = list(_annotations())
    position_zero_indices = [
        index for index, item in enumerate(unstable) if item.position_index == 0
    ]
    for index, center_x in zip(position_zero_indices, (0.10, 0.20, 0.30, 0.40, 0.50), strict=True):
        unstable[index] = replace(unstable[index], center_x=center_x)
    assert (
        calibrate_v7_label_geometry(unstable, manifest_fingerprint=FINGERPRINT).status
        is V7EvaluationStatus.FAILED
    )


def _truth(
    case_id: str,
    *,
    start: int = 1,
    top: bool = False,
    bottom: bool = False,
) -> V7AcceptanceTruth:
    return V7AcceptanceTruth(
        case_id=case_id,
        corpus_case_id="validation",
        split=V7CorpusSplit.VALIDATION,
        expected_range_start=start,
        expected_range_end=start + 8,
        evidence_sources=(SOURCE,),
        automatically_recoverable=True,
        eligible_acceptable_representative=True,
        top_cropped=top,
        bottom_cropped=bottom,
    )


def _prediction(
    case_id: str,
    *,
    range_outcome: V7AutomaticOutcome = V7AutomaticOutcome.CORRECT,
    representative_outcome: V7AutomaticOutcome = V7AutomaticOutcome.CORRECT,
    top: bool = False,
    bottom: bool = False,
    manual_review: bool = False,
    selected_source: V7SourceReference | None = None,
) -> V7AcceptancePrediction:
    if selected_source is None and range_outcome is not V7AutomaticOutcome.NOT_SELECTED:
        selected_source = SOURCE
    return V7AcceptancePrediction(
        case_id=case_id,
        range_outcome=range_outcome,
        representative_outcome=representative_outcome,
        selected_source=selected_source,
        top_warning=top,
        bottom_warning=bottom,
        manual_review=manual_review,
    )


def test_acceptance_uses_separate_95_95_zero_and_100_percent_denominators() -> None:
    truths = tuple(
        _truth(f"case-{index}", start=index * 9 + 1, top=index == 0, bottom=index == 1)
        for index in range(20)
    )
    predictions = tuple(
        _prediction(
            truth.case_id,
            range_outcome=(
                V7AutomaticOutcome.NOT_SELECTED if index == 19 else V7AutomaticOutcome.CORRECT
            ),
            representative_outcome=(
                V7AutomaticOutcome.NOT_SELECTED if index == 19 else V7AutomaticOutcome.CORRECT
            ),
            top=truth.top_cropped,
            bottom=truth.bottom_cropped,
        )
        for index, truth in enumerate(truths)
    )

    evaluation = evaluate_v7_acceptance(truths, predictions)
    assert evaluation.status is V7EvaluationStatus.PASSED
    assert (evaluation.range_recovery.numerator, evaluation.range_recovery.denominator) == (19, 20)
    assert (
        evaluation.representative_selection.numerator,
        evaluation.representative_selection.denominator,
    ) == (
        19,
        20,
    )
    assert (
        evaluation.top_crop_recall.percentage == evaluation.bottom_crop_recall.percentage == 100.0
    )

    wrong = list(predictions)
    wrong[19] = _prediction(
        truths[19].case_id,
        range_outcome=V7AutomaticOutcome.INCORRECT,
        representative_outcome=V7AutomaticOutcome.NOT_SELECTED,
    )
    assert evaluate_v7_acceptance(truths, wrong).status is V7EvaluationStatus.FAILED


def test_acceptance_never_counts_manual_correction_or_empty_denominator_as_success() -> None:
    truth = V7AcceptanceTruth(
        case_id="manual",
        split=V7CorpusSplit.VALIDATION,
        corpus_case_id="validation",
        expected_range_start=1,
        expected_range_end=9,
        evidence_sources=(SOURCE,),
        automatically_recoverable=False,
        eligible_acceptable_representative=False,
        top_cropped=False,
        bottom_cropped=False,
    )
    evaluation = evaluate_v7_acceptance(
        (truth,),
        (
            _prediction(
                "manual",
                range_outcome=V7AutomaticOutcome.NOT_SELECTED,
                representative_outcome=V7AutomaticOutcome.NOT_SELECTED,
                top=True,
                manual_review=True,
            ),
        ),
    )

    assert evaluation.status is V7EvaluationStatus.NOT_EVALUABLE
    assert evaluation.range_recovery.status is V7EvaluationStatus.NOT_EVALUABLE
    assert evaluation.representative_selection.status is V7EvaluationStatus.NOT_EVALUABLE
    assert evaluation.top_crop_false_positive_count == 1
    assert evaluation.manual_review_count == 1


def test_acceptance_rejects_holdout_duplicate_and_mismatched_case_sets() -> None:
    with pytest.raises(V7CalibrationError, match="invalid for T05"):
        replace(_truth("holdout"), split=V7CorpusSplit.HOLDOUT)

    with pytest.raises(V7CalibrationError, match="holdout acceptance truth"):
        V7HoldoutAcceptanceTruth(
            case_id="validation",
            corpus_case_id="validation",
            split=V7CorpusSplit.VALIDATION,
            expected_range_start=1,
            expected_range_end=9,
            evidence_sources=(SOURCE,),
            acceptable_representative_sources=(),
            automatically_recoverable=True,
            eligible_acceptable_representative=True,
        )

    holdout_truth = V7HoldoutAcceptanceTruth(
        case_id="holdout",
        corpus_case_id="holdout",
        split=V7CorpusSplit.HOLDOUT,
        expected_range_start=1,
        expected_range_end=9,
        evidence_sources=(SOURCE,),
        acceptable_representative_sources=(SOURCE,),
        automatically_recoverable=True,
        eligible_acceptable_representative=True,
    )
    with pytest.raises(V7CalibrationError, match="requires T05 truth only"):
        evaluate_v7_acceptance((holdout_truth,), (_prediction("holdout"),))
    with pytest.raises(V7CalibrationError, match="requires holdout truth only"):
        evaluate_v7_holdout_acceptance((_truth("t05"),), (), ())

    truth = _truth("case")
    prediction = _prediction("case")
    with pytest.raises(V7CalibrationError, match="duplicated"):
        evaluate_v7_acceptance((truth, truth), (prediction,))
    same_range = _truth("same-range")
    with pytest.raises(V7CalibrationError, match="corpus range is duplicated"):
        evaluate_v7_acceptance(
            (truth, same_range),
            (prediction, _prediction("same-range")),
        )
    with pytest.raises(V7CalibrationError, match="cases differ"):
        evaluate_v7_acceptance((truth,), (_prediction("other"),))


def test_acceptance_rejects_representative_success_without_a_correct_range_write() -> None:
    with pytest.raises(V7CalibrationError, match="requires a correct automatic range"):
        _prediction(
            "no-range",
            range_outcome=V7AutomaticOutcome.NOT_SELECTED,
            representative_outcome=V7AutomaticOutcome.CORRECT,
        )
    with pytest.raises(V7CalibrationError, match="requires a correct automatic range"):
        _prediction(
            "wrong-range",
            range_outcome=V7AutomaticOutcome.INCORRECT,
            representative_outcome=V7AutomaticOutcome.CORRECT,
        )
