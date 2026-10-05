"""The actual Admin composition includes the disabled shadow API without DB work."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_shadow import GridShadowError
from game_predictor_api.main import create_app


class DisabledShadow:
    def start(self, **_kwargs: Any) -> None:
        raise GridShadowError("GRID_SHADOW_DISABLED", "Shadow is disabled.", status_code=503)


def test_shadow_routes_are_composed_and_domain_error_is_explicit() -> None:
    settings = ApiSettings.from_environment({})
    assert settings.grid_shadow_enabled is False
    app = create_app(settings, grid_shadow_service_dependency=lambda: DisabledShadow())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/games/11111111-1111-4111-8111-111111111111/grid-shadow-jobs",
            json={
                "requestId": "22222222-2222-4222-8222-222222222222",
                "sourceImageIds": ["33333333-3333-4333-8333-333333333333"],
            },
        )
    assert response.status_code == 503
    assert response.json() == {
        "code": "GRID_SHADOW_DISABLED",
        "message": "Shadow is disabled.",
        "details": {},
    }
    operations = app.openapi()["paths"]
    assert (
        operations["/api/v1/admin/games/{game_id}/grid-shadow-jobs"]["post"]["operationId"]
        == "startGridShadowJob"
    )
    assert (
        operations["/api/v1/admin/games/{game_id}/grid-shadow-results"]["get"]["operationId"]
        == "listGridShadowResults"
    )
    assert (
        operations["/api/v1/admin/games/{game_id}/grid-shadow-results/{result_id}"]["get"][
            "operationId"
        ]
        == "getGridShadowResult"
    )


def test_shadow_http_cannot_supply_a_model_or_managed_path() -> None:
    app = create_app(
        ApiSettings.from_environment({}), grid_shadow_service_dependency=lambda: DisabledShadow()
    )
    schema = app.openapi()["components"]["schemas"]["GridShadowJobCreate"]
    assert set(schema["properties"]) == {"requestId", "sourceImageIds"}
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/games/11111111-1111-4111-8111-111111111111/grid-shadow-jobs",
            json={
                "requestId": "22222222-2222-4222-8222-222222222222",
                "sourceImageIds": ["33333333-3333-4333-8333-333333333333"],
                "sourceRelativePath": "other.jpg",
            },
        )
    assert response.status_code == 422
