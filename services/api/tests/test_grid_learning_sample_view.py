"""Public sample projection preserves the existing selection and its shortages."""

from copy import deepcopy
from uuid import UUID

from game_predictor_api.domain.grid_learning_sample_view import learning_test_sample
from game_predictor_api.schemas.grid_correction_learning import GridLearningTestSample


def test_sample_projection_does_not_select_or_hide_missing_reference():
    report = {
        "version": "stratified-fresh-content-regression-v2",
        "seed": 20261108,
        "state": "not_evaluable",
        "baseVersionId": None,
        "strata": {
            "ordinary": {"geometryFullPhotos": 5, "contentFullPhotos": 2},
            "hard": {"geometryFullPhotos": 3, "contentFullPhotos": 0},
        },
        "missingContentSourceIds": [str(UUID(int=index)) for index in range(1, 4)],
        "unknownReferencePhotos": 4,
        "categoryCounts": {"missing-row": 2},
        "unrepresentedCategories": ["perspective"],
        "reasonCounts": {"CONTENT_UNKNOWN_LIMIT": 1},
    }
    before = deepcopy(report)
    sample = GridLearningTestSample.model_validate(learning_test_sample(report))
    assert report == before
    assert sample.state == "not_evaluable"
    assert sample.ordinaryGeometryPhotos == 5 and sample.ordinaryContentPhotos == 2
    assert sample.hardGeometryPhotos == 3 and sample.hardContentPhotos == 0
    assert sample.missingContentSources == 3
    assert sample.unrepresentedCategories == ["perspective"]


def test_legacy_or_absent_evidence_cannot_claim_new_sample_coverage():
    assert learning_test_sample(None) is None
    assert learning_test_sample({"version": "fresh-content-regression-selection-v1"}) is None
