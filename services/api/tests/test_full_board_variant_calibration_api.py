"""Real response router/DTO dispatch; controlled observations are not physical proof."""

from copy import deepcopy
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_model_evaluations import create_grid_model_evaluations_router
from game_predictor_api.domain.full_board_calibration_report import attach_calibration
from game_predictor_api.domain.grid_model_registry import canonical_json
from game_predictor_api.domain.production_cell_evaluation import attach_content, require_report
from game_predictor_api.schemas.grid_model_evaluations import GridCalibratedEvaluationReport
from pydantic import ValidationError
from test_full_board_variant_calibration import qualify, variant_fixture
from test_grid_correction_learning_api import evaluation_value
from test_production_cell_evaluation import evidence, reports


def test_variant_dispatch_requires_existing_verified_bundle(tmp_path):
    from game_predictor_api.storage.full_board_variant_calibration_evidence import (
        variant_report_allowed,
    )

    document = {
        "schemaVersion": "grid-model-evaluation-read-v6",
        "automaticCalibration": [{"version": "full-board-calibration-qualification-v3"}],
    }
    with pytest.raises(ValueError, match="CONTENT_DISPATCH_REQUIRED"):
        variant_report_allowed(None, {}, document)
    # Physical bundle lookup cannot be replaced by the report's own version flag.
    with pytest.raises(ValueError, match="FROZEN_CONTEXT_UNAVAILABLE"):
        variant_report_allowed(tmp_path, {"managedDirectory": "missing-candidate"}, document)
    assert not variant_report_allowed(None, {}, {"automaticCalibration": []})


def test_get_and_list_preserve_variant_counts_and_reject_legacy_reinterpretation():
    manifest, raw, _ = reports()
    prepared, b, reg = variant_fixture(sources_per_variant=15)
    calibration = qualify(prepared, b, reg)
    calibrations = [{**deepcopy(calibration), "gameId": game} for game in raw["requiredGameIds"]]
    calibrated = attach_calibration(raw, calibrations, allow_variant_calibration=True)
    report = attach_content(calibrated, [evidence(game) for game in raw["requiredGameIds"]])
    assert (
        require_report(
            canonical_json(report),
            manifest=manifest,
            base_sha256="c" * 64,
            allow_variant_calibration=True,
        )
        == report
    )
    with pytest.raises(ValueError):
        require_report(canonical_json(report), manifest=manifest, base_sha256="c" * 64)
    with pytest.raises(ValidationError):
        GridCalibratedEvaluationReport.model_validate(calibrated)

    view = {**evaluation_value(), "status": "completed", "report": report}
    calls = []

    class Service:
        def get(self, value):
            calls.append(("get", value))
            return deepcopy(view)

        def list(self, value):
            calls.append(("list", value))
            return {"items": [deepcopy(view)]}

    service = Service()
    app = FastAPI()
    app.include_router(create_grid_model_evaluations_router(lambda: service))
    with TestClient(app) as client:
        response = client.get(f"/api/v1/admin/grid-model-evaluations/{view['evaluationId']}")
        assert response.status_code == 200
        received = response.json()["report"]
        assert received["automaticCalibration"] == calibrations
        assert received["rawQuality"]["automaticCalibration"] == calibrations
        assert all("b" not in item for item in received["automaticCalibration"])
        assert all(
            child["b"]["baselineBadSources"] == 15
            for item in received["automaticCalibration"]
            for child in item["variants"]
        )
        listed = client.get(
            "/api/v1/admin/grid-model-evaluations", params={"versionId": view["versionId"]}
        )
        assert listed.status_code == 200
        assert listed.json()["items"][0]["report"] == received
    assert calls == [("get", UUID(view["evaluationId"])), ("list", UUID(view["versionId"]))]
