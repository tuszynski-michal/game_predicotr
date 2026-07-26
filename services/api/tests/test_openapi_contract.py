from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app


def test_health_openapi_contract_is_stable_and_complete() -> None:
    schema = create_app(ApiSettings.from_environment({})).openapi()

    assert schema["openapi"] == "3.1.0"
    assert schema["info"] == {
        "title": "Game Predictor Admin API",
        "version": "0.1.0",
    }
    assert schema["servers"] == [
        {
            "url": "http://127.0.0.1:8000",
            "description": "Local Admin API",
        }
    ]

    operation = schema["paths"]["/api/v1/health"]["get"]
    assert operation["operationId"] == "getHealth"
    assert operation["tags"] == ["health"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }

    health_response = schema["components"]["schemas"]["HealthResponse"]
    assert health_response["additionalProperties"] is False
    assert health_response["required"] == ["status", "version"]
    assert health_response["properties"]["status"] == {
        "type": "string",
        "const": "ok",
        "title": "Status",
    }


def test_catalog_openapi_exposes_stable_operations_and_error_schema() -> None:
    schema = create_app(ApiSettings.from_environment({})).openapi()

    expected_operations = {
        ("/api/v1/admin/games", "get"): "listGames",
        ("/api/v1/admin/games", "post"): "createGame",
        ("/api/v1/admin/games/{game_id}", "get"): "getGame",
        ("/api/v1/admin/games/{game_id}", "patch"): "updateGame",
        ("/api/v1/admin/games/{game_id}", "delete"): "archiveGame",
        ("/api/v1/admin/games/{game_id}/symbols", "get"): "listSymbols",
        ("/api/v1/admin/games/{game_id}/symbols", "post"): "createSymbol",
        (
            "/api/v1/admin/games/{game_id}/symbols/{symbol_id}",
            "get",
        ): "getSymbol",
        (
            "/api/v1/admin/games/{game_id}/symbols/{symbol_id}",
            "patch",
        ): "updateSymbol",
        (
            "/api/v1/admin/games/{game_id}/symbols/{symbol_id}",
            "delete",
        ): "archiveSymbol",
    }

    for (path, method), operation_id in expected_operations.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["catalog"]

    error_schema = schema["components"]["schemas"]["ErrorResponse"]
    assert error_schema["additionalProperties"] is False
    assert error_schema["required"] == ["code", "message", "details"]
    assert (
        schema["paths"]["/api/v1/admin/games"]["post"]["responses"]["409"][
            "content"
        ]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/ErrorResponse"}
    )
