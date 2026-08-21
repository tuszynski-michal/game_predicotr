"""End-to-end M2 acceptance through the public Admin API and PostgreSQL."""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_m2_acceptance_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_m2_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    test_database_url = _database_url(TEST_DATABASE_NAME)
    identifier = f'"{TEST_DATABASE_NAME}"'

    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        command.upgrade(_migration_config(test_database_url), "head")
        yield test_database_url
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _json(response: Any, expected_status: int) -> Any:
    assert response.status_code == expected_status, response.text
    return response.json()


def test_complete_m2_admin_flow_uses_only_public_http_contracts(
    isolated_m2_database: URL,
) -> None:
    settings = ApiSettings.from_environment(
        {"GAME_PREDICTOR_DATABASE_URL": isolated_m2_database.render_as_string(hide_password=False)}
    )
    application = create_app(settings)

    try:
        with TestClient(application) as client:
            assert _json(client.get("/api/v1/admin/games"), 200) == []

            game = _json(
                client.post(
                    "/api/v1/admin/games",
                    json={
                        "code": "m2-game",
                        "name": "M2 Acceptance Game",
                        "status": "active",
                        "expectedLayoutCount": 1000,
                    },
                ),
                201,
            )
            game_id = game["id"]
            assert (
                _json(
                    client.get(f"/api/v1/admin/games/{game_id}/rules-versions"),
                    200,
                )
                == []
            )
            assert (
                _json(
                    client.get(f"/api/v1/admin/games/{game_id}/dataset-versions"),
                    200,
                )
                == []
            )

            symbols = []
            for number in range(1, 13):
                symbols.append(
                    _json(
                        client.post(
                            f"/api/v1/admin/games/{game_id}/symbols",
                            json={
                                "mobileCode": number,
                                "code": f"S{number}",
                                "name": ("Joker" if number == 12 else f"Symbol {number}"),
                                "imagePath": f"symbols/m2-game/s{number}.png",
                                "isWildcard": number == 12,
                                "displayOrder": number * 10,
                                "status": "active",
                            },
                        ),
                        201,
                    )
                )
            assert (
                len(
                    _json(
                        client.get(f"/api/v1/admin/games/{game_id}/symbols"),
                        200,
                    )
                )
                == 12
            )

            rules = _json(
                client.post(
                    f"/api/v1/admin/games/{game_id}/rules-versions",
                    json={"rows": 3, "columns": 5, "spinCost": 10},
                ),
                201,
            )
            rules_id = rules["id"]

            incomplete = _json(
                client.post(
                    f"/api/v1/admin/rules-versions/{rules_id}/paylines",
                    json={
                        "code": "incomplete",
                        "name": "Incomplete",
                        "rowPath": [0, 0, 0],
                        "displayOrder": 1,
                        "isActive": True,
                    },
                ),
                422,
            )
            assert incomplete["code"] == "INVALID_PAYLINE_LENGTH"

            for row_index, code in enumerate(("line-top", "line-middle", "line-bottom")):
                _json(
                    client.post(
                        f"/api/v1/admin/rules-versions/{rules_id}/paylines",
                        json={
                            "code": code,
                            "name": code,
                            "rowPath": [row_index] * 5,
                            "displayOrder": (row_index + 1) * 10,
                            "isActive": True,
                        },
                    ),
                    201,
                )

            duplicate = _json(
                client.post(
                    f"/api/v1/admin/rules-versions/{rules_id}/paylines",
                    json={
                        "code": "line-top-copy",
                        "name": "Duplicate top",
                        "rowPath": [0, 0, 0, 0, 0],
                        "displayOrder": 40,
                        "isActive": True,
                    },
                ),
                409,
            )
            assert duplicate["code"] == "DUPLICATE_PAYLINE"

            for index, symbol in enumerate(symbols):
                is_wildcard = symbol["isWildcard"]
                minimum = None if is_wildcard else (2 if index == 0 else 3)
                _json(
                    client.patch(
                        (f"/api/v1/admin/rules-versions/{rules_id}/symbols/{symbol['id']}"),
                        json={
                            "minimumMatchLength": minimum,
                            "isActive": True,
                        },
                    ),
                    200,
                )
                if is_wildcard:
                    continue
                assert minimum is not None
                for match_length in range(minimum, 6):
                    _json(
                        client.post(
                            (f"/api/v1/admin/rules-versions/{rules_id}/payout-rules"),
                            json={
                                "symbolId": symbol["id"],
                                "matchLength": match_length,
                                "payoutCredits": (match_length - minimum + 1) * 10,
                                "isActive": True,
                            },
                        ),
                        201,
                    )

            readiness = _json(
                client.get(f"/api/v1/admin/rules-versions/{rules_id}/publication-readiness"),
                200,
            )
            assert readiness == {
                "rulesVersionId": rules_id,
                "ready": True,
                "issues": [],
            }

            published_rules = _json(
                client.post(f"/api/v1/admin/rules-versions/{rules_id}/publish"),
                200,
            )
            assert published_rules["status"] == "published"
            assert published_rules["publishedAt"] is not None

            immutable = _json(
                client.patch(
                    f"/api/v1/admin/rules-versions/{rules_id}",
                    json={"spinCost": 20},
                ),
                409,
            )
            assert immutable["code"] == "RULES_VERSION_IMMUTABLE"

            dataset = _json(
                client.post(
                    f"/api/v1/admin/games/{game_id}/dataset-versions/mock",
                    json={"rulesVersionId": rules_id, "seed": 71401},
                ),
                201,
            )
            dataset_id = dataset["id"]
            assert dataset["layoutCount"] == 1000
            assert dataset["status"] == "staging"

            report = _json(
                client.get(f"/api/v1/admin/dataset-versions/{dataset_id}/validation-report"),
                200,
            )
            assert report["readyForPublication"] is True
            assert report["duplicateSignatureGroupCount"] == 6
            assert report["duplicateSignatureAffectedLayoutCount"] == 12

            preview = _json(
                client.get(
                    f"/api/v1/admin/dataset-versions/{dataset_id}/layouts",
                    params={"after_sequence_number": 0, "limit": 12},
                ),
                200,
            )
            assert preview["rows"] == 3
            assert preview["columns"] == 5
            assert len(preview["items"]) == 12
            assert preview["items"][0]["sequenceNumber"] == 1
            assert len(preview["items"][0]["cells"]) == 15
            assert preview["nextAfterSequenceNumber"] == 12

            published_dataset = _json(
                client.post(f"/api/v1/admin/dataset-versions/{dataset_id}/publish"),
                200,
            )
            assert published_dataset["status"] == "published"
            assert published_dataset["publishedAt"] is not None

            rules_history = _json(
                client.get(f"/api/v1/admin/games/{game_id}/rules-versions"),
                200,
            )
            dataset_history = _json(
                client.get(f"/api/v1/admin/games/{game_id}/dataset-versions"),
                200,
            )
            assert [item["status"] for item in rules_history] == ["published"]
            assert [item["status"] for item in dataset_history] == ["published"]
    finally:
        application.state.database_engine.dispose()
