from __future__ import annotations

from dataclasses import replace

import pytest
from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7_DYNAMIC_GEOMETRY_FAMILY_ID,
    V7_STANDARD_GEOMETRY_FAMILY_ID,
    V7AcceptancePrediction,
    V7AcceptanceTruth,
    V7AutomaticOutcome,
    V7CalibrationError,
    V7CropAssessment,
    V7EvaluationStatus,
    V7GeometryAdoption,
    V7GeometryProfile,
    V7HoldoutAcceptanceTruth,
    V7LabelGeometryAnnotation,
    V7SourceExposureRecord,
    V7SourceExposureStatus,
    V7SourceReference,
    V7ValidationAcceptanceTruth,
    V7ValidationPredictionSnapshot,
    V7ValidationQualityStatus,
    V7ValidationSourceObservation,
    calibrate_v7_label_geometry,
    evaluate_v7_acceptance,
    evaluate_v7_holdout_acceptance,
    evaluate_v7_validation_acceptance,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7CorpusSplit

FINGERPRINT = "a" * 64
FAMILY = V7_STANDARD_GEOMETRY_FAMILY_ID
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
                    capture_group_id=f"capture-{source_index % 2}",
                    crop_assessment=V7CropAssessment.CONTAINED,
                    geometry_family_id=FAMILY,
                )
            )
    return tuple(result)


def test_geometry_calibration_requires_five_independent_calibration_sources_per_position() -> None:
    calibration = calibrate_v7_label_geometry(
        _annotations(), manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
    )

    assert calibration.status is V7EvaluationStatus.PASSED
    assert calibration.source_count_by_position == (5,) * 9
    assert calibration.capture_group_count_by_position == (2,) * 9
    assert calibration.locator_config.position_confidence == 0.95
    assert calibration.p95_center_residual <= calibration.maximum_p95_center_residual
    assert (
        calibration.input_fingerprint
        == calibrate_v7_label_geometry(
            tuple(reversed(_annotations())),
            manifest_fingerprint=FINGERPRINT,
            geometry_family_id=FAMILY,
        ).input_fingerprint
    )

    with pytest.raises(V7CalibrationError, match="lacks independent"):
        calibrate_v7_label_geometry(
            _annotations(source_count=4),
            manifest_fingerprint=FINGERPRINT,
            geometry_family_id=FAMILY,
        )


def test_geometry_calibration_rejects_mixed_split_duplicate_or_unstable_positions() -> None:
    mixed = list(_annotations())
    mixed[0] = replace(mixed[0], split=V7CorpusSplit.DEVELOPMENT)
    with pytest.raises(V7CalibrationError, match="calibration-split"):
        calibrate_v7_label_geometry(
            mixed, manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
        )

    duplicate = (*_annotations(), _annotations()[0])
    with pytest.raises(V7CalibrationError, match="more than once"):
        calibrate_v7_label_geometry(
            duplicate, manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
        )

    duplicate_checksum = (*_annotations(), replace(_annotations()[0], source_id="copy-source"))
    with pytest.raises(V7CalibrationError, match="byte-identical aliases"):
        calibrate_v7_label_geometry(
            duplicate_checksum, manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
        )

    unstable = list(_annotations())
    position_zero_indices = [
        index for index, item in enumerate(unstable) if item.position_index == 0
    ]
    for index, center_x in zip(position_zero_indices, (0.10, 0.20, 0.30, 0.40, 0.50), strict=True):
        unstable[index] = replace(unstable[index], center_x=center_x)
    assert (
        calibrate_v7_label_geometry(
            unstable, manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
        ).status
        is V7EvaluationStatus.FAILED
    )


def test_geometry_calibration_requires_capture_diversity_and_contained_crops() -> None:
    same_capture = tuple(replace(item, capture_group_id="single") for item in _annotations())
    with pytest.raises(V7CalibrationError, match="capture groups"):
        calibrate_v7_label_geometry(
            same_capture, manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
        )

    clipped = (
        *_annotations()[:-1],
        replace(_annotations()[-1], crop_assessment=V7CropAssessment.CLIPPED),
    )
    with pytest.raises(V7CalibrationError, match="contained label crops"):
        calibrate_v7_label_geometry(
            clipped, manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
        )

    uncertain = (
        *_annotations()[:-1],
        replace(_annotations()[-1], crop_assessment=V7CropAssessment.UNCERTAIN),
    )
    with pytest.raises(V7CalibrationError, match="contained label crops"):
        calibrate_v7_label_geometry(
            uncertain,
            manifest_fingerprint=FINGERPRINT,
            geometry_family_id=FAMILY,
        )

    incompatible = (*_annotations()[:-1], replace(_annotations()[-1], geometry_family_id="other"))
    with pytest.raises(V7CalibrationError, match="incompatible families"):
        calibrate_v7_label_geometry(
            incompatible,
            manifest_fingerprint=FINGERPRINT,
            geometry_family_id=FAMILY,
        )


def test_geometry_calibration_uses_nearest_rank_p95_and_serializes_all_crop_parameters() -> None:
    values = list(_annotations())
    # 45 residuals: two largest values must not affect nearest-rank p95 at rank 43.
    values[-1] = replace(values[-1], center_x=0.99)
    values[-2] = replace(values[-2], center_x=0.99)
    calibration = calibrate_v7_label_geometry(
        values, manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
    )

    assert calibration.p95_center_residual <= calibration.maximum_p95_center_residual
    locator = calibration.as_dict()["locatorConfig"]
    assert locator["minimumAspectRatio"] == 1.0
    assert locator["maximumAspectRatio"] == 1.8

    assert (
        replace(
            calibration,
            p95_center_residual=0.0399,
            maximum_p95_center_residual=0.04,
        ).status
        is V7EvaluationStatus.PASSED
    )
    assert (
        replace(
            calibration,
            p95_center_residual=0.04,
            maximum_p95_center_residual=0.04,
        ).status
        is V7EvaluationStatus.PASSED
    )
    assert (
        replace(
            calibration,
            p95_center_residual=0.0401,
            maximum_p95_center_residual=0.04,
        ).status
        is V7EvaluationStatus.FAILED
    )


def test_dynamic_geometry_calibration_normalizes_each_source_local_grid() -> None:
    annotations = []
    for source_index in range(6):
        for position_index in range(9):
            row, column = divmod(position_index, 3)
            # Every source has a different whole-image viewport.  The local
            # grid itself remains consistent and is the only V2 calibration
            # coordinate system.
            annotations.append(
                V7LabelGeometryAnnotation(
                    source_id=f"dynamic-{source_index}",
                    source_checksum_sha256=f"{source_index + 50:064x}",
                    split=V7CorpusSplit.CALIBRATION,
                    position_index=position_index,
                    center_x=0.12 + source_index * 0.035 + column * (0.19 + source_index * 0.003),
                    center_y=0.20 + source_index * 0.021 + row * (0.16 + source_index * 0.002),
                    capture_group_id=f"capture-{source_index % 2}",
                    crop_assessment=V7CropAssessment.CONTAINED,
                    geometry_family_id=V7_DYNAMIC_GEOMETRY_FAMILY_ID,
                )
            )

    calibration = calibrate_v7_label_geometry(
        annotations,
        manifest_fingerprint=FINGERPRINT,
        geometry_family_id=V7_DYNAMIC_GEOMETRY_FAMILY_ID,
    )

    assert calibration.status is V7EvaluationStatus.PASSED
    assert calibration.locator_config.as_dict()["kind"] == "dynamic_lattice_v2"
    assert calibration.p95_center_residual <= calibration.maximum_p95_center_residual

    incomplete_source = tuple(
        item for item in annotations if item.source_id != "dynamic-0" or item.position_index < 4
    )
    with pytest.raises(V7CalibrationError, match="five source-local points"):
        calibrate_v7_label_geometry(
            incomplete_source,
            manifest_fingerprint=FINGERPRINT,
            geometry_family_id=V7_DYNAMIC_GEOMETRY_FAMILY_ID,
        )

    mirrored = tuple(
        replace(
            item,
            center_x=0.8 - (item.position_index % 3) * 0.2,
            center_y=0.2 + (item.position_index // 3) * 0.2,
        )
        for item in annotations
    )
    with pytest.raises(V7CalibrationError, match="mirrored or folded"):
        calibrate_v7_label_geometry(
            mirrored,
            manifest_fingerprint=FINGERPRINT,
            geometry_family_id=V7_DYNAMIC_GEOMETRY_FAMILY_ID,
        )


def test_api_profile_reader_reconstructs_the_dynamic_locator_payload() -> None:
    annotations = []
    for source_index in range(5):
        for position_index in range(9):
            row, column = divmod(position_index, 3)
            annotations.append(
                V7LabelGeometryAnnotation(
                    source_id=f"reader-{source_index}",
                    source_checksum_sha256=f"{source_index + 90:064x}",
                    split=V7CorpusSplit.CALIBRATION,
                    position_index=position_index,
                    center_x=0.15 + source_index * 0.02 + column * 0.2,
                    center_y=0.2 + source_index * 0.01 + row * 0.18,
                    capture_group_id=f"capture-{source_index % 2}",
                    crop_assessment=V7CropAssessment.CONTAINED,
                    geometry_family_id=V7_DYNAMIC_GEOMETRY_FAMILY_ID,
                )
            )
    calibration = calibrate_v7_label_geometry(
        annotations,
        manifest_fingerprint=FINGERPRINT,
        geometry_family_id=V7_DYNAMIC_GEOMETRY_FAMILY_ID,
    )
    from game_predictor_api.application.v7_label_geometry_calibration import (
        _profile_from_payload,
    )

    restored = _profile_from_payload(
        {
            "calibration": calibration.as_dict(),
            "profileFingerprint": "b" * 64,
            "revision": 0,
        }
    )

    assert restored.calibration.locator_config.as_dict() == calibration.locator_config.as_dict()


def test_profile_adoption_and_exposure_contracts_are_explicit_and_serializable() -> None:
    calibration = calibrate_v7_label_geometry(
        _annotations(), manifest_fingerprint=FINGERPRINT, geometry_family_id=FAMILY
    )
    profile = V7GeometryProfile(
        profile_fingerprint="b" * 64,
        calibration=calibration,
        revision=0,
    )
    adoption = V7GeometryAdoption(
        adoption_key="777-standard-v1",
        source_game_ref="777",
        geometry_family_id=FAMILY,
        profile_fingerprint=profile.profile_fingerprint,
        validation_report_fingerprint="c" * 64,
    )
    exposure = V7SourceExposureRecord(
        source=SOURCE,
        status=V7SourceExposureStatus.RESERVED_HOLDOUT,
    )

    assert profile.as_dict()["calibration"]["geometryFamilyId"] == FAMILY
    assert adoption.as_dict()["sourceGameRef"] == "777"
    assert exposure.as_dict()["status"] == "reserved_holdout"


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


def test_non_holdout_validation_derives_outcomes_from_raw_snapshot_and_never_uses_holdout() -> None:
    truth = V7ValidationAcceptanceTruth(
        case_id="validation-range",
        corpus_case_id="validation",
        split=V7CorpusSplit.VALIDATION,
        expected_range_start=1,
        expected_range_end=9,
        evidence_sources=(SOURCE,),
        acceptable_representative_sources=(SOURCE,),
        automatically_recoverable=True,
        eligible_acceptable_representative=True,
    )
    observation = V7ValidationSourceObservation(
        source=SOURCE,
        represented_range_start=1,
        represented_range_end=9,
        top_cropped=True,
        bottom_cropped=True,
    )
    correct = V7ValidationPredictionSnapshot(
        case_id="validation-range",
        predicted_range_start=1,
        predicted_range_end=9,
        selected_source=SOURCE,
        quality_status=V7ValidationQualityStatus.ACCEPTABLE,
        top_warning=True,
        bottom_warning=True,
        manual_review=False,
    )
    evaluation = evaluate_v7_validation_acceptance((truth,), (correct,), (observation,))
    assert evaluation.status is V7EvaluationStatus.PASSED

    assert (
        evaluate_v7_validation_acceptance(
            (truth,),
            (replace(correct, quality_status=V7ValidationQualityStatus.UNKNOWN),),
            (observation,),
        ).status
        is V7EvaluationStatus.FAILED
    )

    incorrect = replace(correct, predicted_range_start=10, predicted_range_end=18)
    failed = evaluate_v7_validation_acceptance((truth,), (incorrect,), (observation,))
    assert failed.incorrect_automatic_range_count == 1
    assert failed.status is V7EvaluationStatus.FAILED

    not_evaluable_truth = replace(
        truth,
        automatically_recoverable=False,
        acceptable_representative_sources=(),
        eligible_acceptable_representative=False,
    )
    no_output = V7ValidationPredictionSnapshot(
        case_id="validation-range",
        predicted_range_start=None,
        predicted_range_end=None,
        selected_source=None,
        quality_status=V7ValidationQualityStatus.UNKNOWN,
        top_warning=False,
        bottom_warning=False,
        manual_review=True,
    )
    not_evaluable = evaluate_v7_validation_acceptance(
        (not_evaluable_truth,),
        (no_output,),
        (observation,),
    )
    assert not_evaluable.status is V7EvaluationStatus.NOT_EVALUABLE


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
