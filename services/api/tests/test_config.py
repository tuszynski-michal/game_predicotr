import pytest
from game_predictor_api.config import ApiSettings, ConfigurationError


def test_defaults_are_loopback_only() -> None:
    settings = ApiSettings.from_environment({})

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.admin_origin == "http://127.0.0.1:3000"
    assert settings.reviewer_origin == "http://127.0.0.1:3001"
    assert settings.database_url == (
        "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
    )
    assert settings.artifact_root.is_absolute()
    assert settings.artifact_root.name == "artifacts"
    assert settings.review_crop_root.is_absolute()
    assert settings.review_crop_root.name == ("m5-reviewed-manual-merge-v16-full-preflight")
    assert settings.review_source_root.is_absolute()
    assert settings.review_source_root.as_posix().endswith("examples/imgs")
    assert settings.import_root.is_absolute()
    assert settings.import_root.name == "imports"
    assert settings.import_max_bytes == 1024 * 1024 * 1024


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        (
            {"GAME_PREDICTOR_API_HOST": "0.0.0.0"},
            "GAME_PREDICTOR_API_HOST",
        ),
        (
            {"GAME_PREDICTOR_API_PORT": "70000"},
            "GAME_PREDICTOR_API_PORT",
        ),
        (
            {"GAME_PREDICTOR_ADMIN_ORIGIN": "https://admin.example.com"},
            "GAME_PREDICTOR_ADMIN_ORIGIN",
        ),
        (
            {"GAME_PREDICTOR_ADMIN_ORIGIN": "http://127.0.0.1:3000/path"},
            "GAME_PREDICTOR_ADMIN_ORIGIN",
        ),
        (
            {"GAME_PREDICTOR_REVIEWER_ORIGIN": "https://review.example.com"},
            "GAME_PREDICTOR_REVIEWER_ORIGIN",
        ),
        (
            {
                "GAME_PREDICTOR_DATABASE_URL": (
                    "postgresql+psycopg://user:password@database.example.com/game"
                )
            },
            "GAME_PREDICTOR_DATABASE_URL",
        ),
        (
            {"GAME_PREDICTOR_DATABASE_URL": "postgresql://user:password@localhost/game"},
            "GAME_PREDICTOR_DATABASE_URL",
        ),
        (
            {"GAME_PREDICTOR_DATABASE_URL": "postgresql+psycopg://localhost/game"},
            "GAME_PREDICTOR_DATABASE_URL",
        ),
        (
            {"GAME_PREDICTOR_DATABASE_URL": ("postgresql+psycopg://user:password@localhost/game")},
            "GAME_PREDICTOR_DATABASE_URL",
        ),
        (
            {"GAME_PREDICTOR_ARTIFACT_ROOT": "  "},
            "GAME_PREDICTOR_ARTIFACT_ROOT",
        ),
        (
            {"GAME_PREDICTOR_IMPORT_ROOT": "  "},
            "GAME_PREDICTOR_IMPORT_ROOT",
        ),
        (
            {"GAME_PREDICTOR_IMPORT_MAX_BYTES": "0"},
            "GAME_PREDICTOR_IMPORT_MAX_BYTES",
        ),
        (
            {"GAME_PREDICTOR_IMPORT_MAX_BYTES": "one"},
            "GAME_PREDICTOR_IMPORT_MAX_BYTES",
        ),
    ],
)
def test_rejects_non_local_or_invalid_configuration(
    environment: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        ApiSettings.from_environment(environment)


def test_normalizes_ipv6_loopback_origin() -> None:
    settings = ApiSettings.from_environment({"GAME_PREDICTOR_ADMIN_ORIGIN": "http://[::1]:3000/"})

    assert settings.admin_origin == "http://[::1]:3000"


def test_database_password_is_not_exposed_by_settings_repr() -> None:
    settings = ApiSettings.from_environment(
        {
            "GAME_PREDICTOR_DATABASE_URL": (
                "postgresql+psycopg://game_predictor:secret@localhost:5432/game_predictor"
            )
        }
    )

    assert "secret" not in repr(settings)


def test_import_root_and_limit_are_configurable(tmp_path) -> None:
    import_root = tmp_path / "incoming"
    settings = ApiSettings.from_environment(
        {
            "GAME_PREDICTOR_IMPORT_ROOT": str(import_root),
            "GAME_PREDICTOR_IMPORT_MAX_BYTES": "2048",
        }
    )

    assert settings.import_root == import_root.resolve()
    assert settings.import_max_bytes == 2048
