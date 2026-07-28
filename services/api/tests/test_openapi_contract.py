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
    assert schema["paths"]["/api/v1/admin/games"]["post"]["responses"]["409"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}


def test_rules_openapi_exposes_server_versioned_draft_operations() -> None:
    schema = create_app(ApiSettings.from_environment({})).openapi()
    expected_operations = {
        (
            "/api/v1/admin/games/{game_id}/rules-versions",
            "get",
        ): "listRulesVersions",
        (
            "/api/v1/admin/games/{game_id}/rules-versions",
            "post",
        ): "createRulesVersion",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}",
            "get",
        ): "getRulesVersion",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}",
            "patch",
        ): "updateRulesVersion",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/paylines",
            "get",
        ): "listPaylines",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/paylines",
            "post",
        ): "createPayline",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/paylines/{payline_id}",
            "get",
        ): "getPayline",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/paylines/{payline_id}",
            "patch",
        ): "updatePayline",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/paylines/{payline_id}",
            "delete",
        ): "archivePayline",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/symbols",
            "get",
        ): "listRulesVersionSymbols",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/symbols/{symbol_id}",
            "patch",
        ): "updateRulesVersionSymbol",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/payout-rules",
            "get",
        ): "listPayoutRules",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/payout-rules",
            "post",
        ): "createPayoutRule",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/payout-rules/{payout_rule_id}",
            "get",
        ): "getPayoutRule",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/payout-rules/{payout_rule_id}",
            "patch",
        ): "updatePayoutRule",
        (
            "/api/v1/admin/rules-versions/{rules_version_id}/payout-rules/{payout_rule_id}",
            "delete",
        ): "archivePayoutRule",
    }

    for (path, method), operation_id in expected_operations.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["rules"]

    create_schema = schema["components"]["schemas"]["RulesVersionCreate"]
    assert create_schema["required"] == ["rows", "columns", "spinCost"]
    assert "version" not in create_schema["properties"]
    assert "status" not in create_schema["properties"]

    payline_create = schema["components"]["schemas"]["PaylineCreate"]
    assert payline_create["required"] == [
        "code",
        "name",
        "rowPath",
        "displayOrder",
    ]
    assert payline_create["properties"]["rowPath"]["items"]["type"] == "integer"

    symbol_update = schema["components"]["schemas"]["RulesVersionSymbolUpdate"]
    assert symbol_update["required"] == ["minimumMatchLength"]
    payout_create = schema["components"]["schemas"]["PayoutRuleCreate"]
    assert payout_create["required"] == [
        "symbolId",
        "matchLength",
        "payoutCredits",
    ]


def test_datasets_openapi_exposes_preview_and_publication_operations() -> None:
    schema = create_app(ApiSettings.from_environment({})).openapi()
    expected_operations = {
        (
            "/api/v1/admin/games/{game_id}/dataset-versions",
            "get",
        ): "listDatasetVersions",
        (
            "/api/v1/admin/games/{game_id}/dataset-versions/mock",
            "post",
        ): "generateMockDataset",
        (
            "/api/v1/admin/dataset-versions/{dataset_version_id}",
            "get",
        ): "getDatasetVersion",
        (
            "/api/v1/admin/dataset-versions/{dataset_version_id}",
            "delete",
        ): "archiveDatasetVersion",
        (
            "/api/v1/admin/dataset-versions/{dataset_version_id}/layouts",
            "get",
        ): "listDatasetLayouts",
        (
            "/api/v1/admin/dataset-versions/{dataset_version_id}/publish",
            "post",
        ): "publishDatasetVersion",
        (
            "/api/v1/admin/dataset-versions/{dataset_version_id}/validation-report",
            "get",
        ): "getDatasetValidationReport",
    }

    for (path, method), operation_id in expected_operations.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["datasets"]

    create_schema = schema["components"]["schemas"]["MockDatasetCreate"]
    assert create_schema["required"] == ["rulesVersionId", "seed"]
    assert create_schema["properties"]["seed"]["minimum"] == 0
    report_schema = schema["components"]["schemas"]["DatasetValidationReportResponse"]
    assert "readyForPublication" in report_schema["required"]
    assert "duplicateSignatures" in report_schema["required"]
    page_schema = schema["components"]["schemas"]["DatasetLayoutPageResponse"]
    assert page_schema["required"] == [
        "datasetVersionId",
        "datasetVersion",
        "rows",
        "columns",
        "items",
        "nextAfterSequenceNumber",
    ]
    layout_operation = schema["paths"][
        "/api/v1/admin/dataset-versions/{dataset_version_id}/layouts"
    ]["get"]
    parameters = {parameter["name"]: parameter for parameter in layout_operation["parameters"]}
    assert parameters["after_sequence_number"]["schema"]["minimum"] == 0
    assert parameters["limit"]["schema"]["maximum"] == 100


def test_jobs_openapi_exposes_retry_and_public_lease_observability() -> None:
    schema = create_app(ApiSettings.from_environment({})).openapi()
    expected_operations = {
        ("/api/v1/admin/jobs", "get"): "listJobs",
        ("/api/v1/admin/jobs", "post"): "createJob",
        ("/api/v1/admin/jobs/{job_id}", "get"): "getJob",
        ("/api/v1/admin/jobs/{job_id}/cancel", "post"): "cancelJob",
        ("/api/v1/admin/jobs/{job_id}/retry", "post"): "retryJob",
    }

    for (path, method), operation_id in expected_operations.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["jobs"]

    response_schema = schema["components"]["schemas"]["JobResponse"]
    assert {
        "attemptCount",
        "heartbeatAt",
        "leaseExpiresAt",
    }.issubset(response_schema["required"])
    assert "leaseToken" not in response_schema["properties"]
    assert "leaseOwner" not in response_schema["properties"]
    assert "checkpointPayload" not in response_schema["properties"]

    import_create = schema["components"]["schemas"]["ImportJobCreatePayload"]
    assert import_create["required"] == ["sourcePath"]
    assert set(import_create["properties"]) == {
        "schemaVersion",
        "sourcePath",
        "contractVersion",
    }
    import_response = schema["components"]["schemas"]["ImportJobPayload"]
    assert {
        "importKind",
        "sourceChecksum",
        "sourceSizeBytes",
        "fileFormat",
        "contractVersion",
    }.issubset(import_response["required"])


def test_layout_import_reports_openapi_exposes_bounded_diagnostics() -> None:
    schema = create_app(ApiSettings.from_environment({})).openapi()
    report_path = "/api/v1/admin/layout-import-validations/{validation_job_id}/integrity-report"
    rows_path = "/api/v1/admin/layout-import-validations/{validation_job_id}/rows"
    publication_path = "/api/v1/admin/layout-import-validations/{validation_job_id}/publish"
    rejection_path = "/api/v1/admin/layout-import-validations/{validation_job_id}/staging"

    assert schema["paths"][report_path]["get"]["operationId"] == ("getLayoutImportIntegrityReport")
    assert schema["paths"][rows_path]["get"]["operationId"] == ("listLayoutImportNormalizedRows")
    assert schema["paths"][publication_path]["post"]["operationId"] == (
        "publishLayoutImportDataset"
    )
    assert schema["paths"][rejection_path]["delete"]["operationId"] == ("rejectLayoutImportStaging")
    assert schema["paths"][report_path]["get"]["tags"] == ["layout-imports"]
    response_schema = schema["components"]["schemas"]["LayoutImportIntegrityReportResponse"]
    assert {
        "readyForPublication",
        "expectedRowCount",
        "actualRowCount",
        "missingSequenceCount",
        "duplicateSequences",
        "duplicateSignatures",
        "errorCodeCounts",
    }.issubset(response_schema["required"])
    parameters = {
        parameter["name"]: parameter
        for parameter in schema["paths"][rows_path]["get"]["parameters"]
    }
    assert parameters["after_line_number"]["schema"]["minimum"] == 0
    assert parameters["limit"]["schema"]["maximum"] == 100
    assert parameters["status"]["schema"]["$ref"].endswith("LayoutImportRowStatus")
