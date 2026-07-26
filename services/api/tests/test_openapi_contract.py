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
