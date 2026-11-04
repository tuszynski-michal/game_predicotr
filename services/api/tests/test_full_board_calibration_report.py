from copy import deepcopy
from uuid import UUID

import pytest
from game_predictor_api.domain.full_board_calibration_report import (
    attach_calibration,
    require_report,
    unqualified,
)
from game_predictor_api.domain.grid_model_publication import require_evaluation_evidence
from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256
from game_predictor_api.schemas.grid_model_evaluations import GridCalibratedEvaluationReport
from test_grid_correction_evaluation import fixture


def test_raw_quality_pass_and_publication_are_independent_from_missing_b_minima():
    manifest, quality = fixture()
    report = attach_calibration(
        quality,
        [
            unqualified(game, "CALIBRATION_MINIMUM:baselineBadSources")
            for game in quality["requiredGameIds"]
        ],
    )
    encoded = canonical_json(report)
    assert report["verdict"] == "PASS"
    assert require_report(encoded, manifest=manifest, base_sha256="c" * 64) == report
    GridCalibratedEvaluationReport.model_validate(report)
    evidence = require_evaluation_evidence(
        report_id=UUID(int=22),
        report_json=encoded,
        report_sha256=descriptor_sha256(report),
        producer=report["producer"],
        invalidated=False,
        manifest=manifest,
        base_sha256="c" * 64,
        game_id=UUID(quality["trainingGameId"]),
    )
    assert evidence.scoped
    forged = deepcopy(report)
    forged["automaticCalibration"][0].update(state="qualified", reasonCodes=[])
    with pytest.raises(ValueError):
        require_report(canonical_json(forged), manifest=manifest, base_sha256="c" * 64)
