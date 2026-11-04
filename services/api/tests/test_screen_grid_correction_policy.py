from dataclasses import replace

import pytest
from game_predictor_api.domain.grid_correction_incremental_split import solve_incremental_split
from game_predictor_api.domain.grid_detector_readiness import detector_readiness
from game_predictor_api.domain.grid_training_cohorts import role_summary
from game_predictor_api.schemas.grid_correction_learning import GridCorrectionLearningPreviewCommand
from game_predictor_api.storage.source_recording_sql_v7 import PHOTO_SQL, WRAPPER_SQL
from game_predictor_worker.training_core.grid_training_admission import (
    GRID_CORRECTIONS_V1,
    SCREEN_GRID_CORRECTIONS_V1,
    SCREEN_GRID_V1,
    preset_for_mode,
)
from pydantic import ValidationError
from test_grid_correction_split import source


def test_screen_split_retains_partial_regression_and_complete_population():
    values = [
        replace(source(i, import_id="train", boards=9), frozen_role="TRAIN") for i in range(10)
    ]
    values += [
        replace(source(i + 100, import_id="selection", boards=9), frozen_role="VALIDATION")
        for i in range(5)
    ]
    values += [
        replace(source(i + 200, import_id="regression", boards=3), frozen_role="REGRESSION")
        for i in range(5)
    ]
    # Partial sibling remains in TRAIN's indivisible import, but never becomes detector background.
    values += [source(99, import_id="train", boards=3)]
    result = solve_incremental_split(values, full_training=True)
    assert len(result.assignments) == len(values)
    assert [(r.photos, r.boards) for r in result.role_counts] == [(10, 90), (5, 45), (5, 15)]
    assert result.schema_version == "grid-correction-split-v3"
    assert result == solve_incremental_split(reversed(values), full_training=True)


def test_partial_controls_do_not_qualify_screen_selection():
    values = [
        replace(source(i, import_id=role, boards=3), frozen_role=role)
        for index, role in enumerate(("TRAIN", "VALIDATION", "REGRESSION"))
        for i in range(index * 100, index * 100 + 10)
    ]
    assert solve_incremental_split(values).schema_version == "grid-correction-split-v2"
    with pytest.raises(ValueError):
        solve_incremental_split(values, full_training=True)


def test_regression_minimum_is_not_changed_for_legacy_screen():
    new = role_summary("screen+grid", [], policy="application-grid-corrections-v3")
    old = role_summary("screen+grid", [])
    assert [r["requiredFullPhotos"] for r in new["roles"]] == [10, 5, 0]
    assert [r["requiredFullPhotos"] for r in old["roles"]] == [10, 5, 5]


def test_readiness_counts_measured_zero_without_inventing_role_allocation():
    ready = detector_readiness([3] * 134)
    assert ready["fullPhotos"] == 0
    assert ready["partialExcludedFromDetector"] == 134
    assert ready["reasonCodes"] == ["SCREEN_FULL_PHOTOS_REQUIRED"]
    assert all(r["eligibleFullPhotos"] is None for r in ready["roles"])
    assert ready["roles"][2]["requiredFullPhotos"] == 0


def test_policy_mode_dispatch_keeps_old_fingerprints_and_rejects_cross_pairs():
    assert preset_for_mode("screen+grid") is SCREEN_GRID_V1
    assert (
        preset_for_mode("grid-only", policy="application-grid-corrections-v2")
        is GRID_CORRECTIONS_V1
    )
    assert (
        preset_for_mode("screen+grid", policy="application-grid-corrections-v3")
        is SCREEN_GRID_CORRECTIONS_V1
    )
    assert preset_for_mode("grid-only", policy="application-grid-corrections-v3") is None
    assert preset_for_mode("screen+grid", policy="application-grid-corrections-v2") is None


def test_additive_mode_and_typed_variant_contract():
    assert GridCorrectionLearningPreviewCommand().trainingMode == "grid-only"
    with pytest.raises(ValidationError):
        GridCorrectionLearningPreviewCommand(rescueVariant={"board": {"margin": 0.2}})
    parsed = GridCorrectionLearningPreviewCommand(
        trainingMode="screen+grid",
        rescueVariant={"screen": {"longSide": 1024, "trainCanvas": [1024, 768]}},
    )
    assert parsed.rescueVariant.screen.longSide == 1024
    with pytest.raises(ValidationError):
        GridCorrectionLearningPreviewCommand(
            trainingMode="screen+grid",
            rescueVariant={"screen": {"longSide": 1025, "trainCanvas": [1024, 768]}},
        )


def test_new_sql_has_separate_names_and_role_specific_guards():
    assert "CREATE FUNCTION public.recording_photo_cohort_v2(" in PHOTO_SQL
    assert "CREATE OR REPLACE" not in PHOTO_SQL
    assert "desired IN ('TRAIN','VALIDATION')" in PHOTO_SQL
    assert "human-labeled-targets-v1" in PHOTO_SQL
    assert "RETURN public.recording_cohort_command_v3(wanted,req,actor)" in WRAPPER_SQL
