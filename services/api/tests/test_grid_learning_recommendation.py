"""Read-only opt-in chooses a prepared mode without dropping partial TRAIN labels."""

from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.application.grid_correction_learning import GridCorrectionLearningService
from test_grid_correction_learning_api import preview_value


@pytest.mark.parametrize("case", ["legacy", "partial", "missing_full", "screen", "blocked_screen"])
def test_recommendation_preserves_the_exact_chosen_preview_and_legacy_default(case):
    points = preview_value()
    points["detectorReadiness"] = {"reasonCodes": []}
    if case == "partial":
        points["partialTrainingPhotos"] = 10
    if case == "missing_full":
        points["detectorReadiness"]["reasonCodes"] = ["SCREEN_FULL_VALIDATION_REQUIRED"]
    screen = {**deepcopy(points), "trainingMode": "screen+grid", "previewSha256": "d" * 64}
    if case == "blocked_screen":
        screen.update(canStart=False, blockers=["SCREEN_HISTORY_COHORT_REQUIRED"])
    service = object.__new__(GridCorrectionLearningService)
    service.preview = Mock(side_effect=[deepcopy(points), screen])
    result = service.ready(uuid4(), recommend_training_mode=case != "legacy")
    expected = screen if case == "screen" else points
    assert result["trainingMode"] == expected["trainingMode"]
    assert result["previewSha256"] == expected["previewSha256"]
    assert result["canStart"] == expected["canStart"]
    assert service.preview.call_count == (2 if case in ("screen", "blocked_screen") else 1)
    if case == "legacy":
        assert result == points and "trainingRecommendation" not in result
    else:
        assert result["trainingRecommendation"]["mode"] == expected["trainingMode"]
        if case == "partial":
            assert (
                "GRID_LEARNING_PARTIAL_TRAIN_PRESENT"
                in result["trainingRecommendation"]["reasonCodes"]
            )
        if case == "blocked_screen":
            assert (
                "SCREEN_HISTORY_COHORT_REQUIRED" in result["trainingRecommendation"]["reasonCodes"]
            )
