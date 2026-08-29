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
    assert settings.browser_layout_import_max_bytes == 20 * 1024 * 1024 * 1024
    assert settings.image_selection_max_bytes == 128 * 1024 * 1024 * 1024
    assert settings.storage_gc_observe_only is False
    assert settings.remote_manual_selection_host_mapping_enabled is True
    assert settings.remote_selection_deselect_enabled is True
    assert settings.remote_selection_max_file_bytes == 32 * 1024 * 1024
    assert settings.remote_selection_max_session_bytes == 20 * 1024 * 1024 * 1024
    assert settings.remote_selection_max_active_session_transfers == 4
    assert settings.remote_selection_max_active_global_transfers == 8
    assert settings.remote_selection_upload_timeout_seconds == 120
    assert settings.remote_selection_materialization_lease_seconds == 60
    assert settings.remote_selection_materialization_max_attempts == 5
    assert settings.remote_selection_materialization_max_actions_per_cycle == 4


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
        (
            {"GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES": "0"},
            "GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES",
        ),
        (
            {"GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES": "one"},
            "GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "yes"},
            "GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_DESELECT_ENABLED": "yes"},
            "GAME_PREDICTOR_REMOTE_SELECTION_DESELECT_ENABLED",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_ENABLED": "yes"},
            "GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_ENABLED",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_MAX_FILE_BYTES": "0"},
            "GAME_PREDICTOR_REMOTE_SELECTION_MAX_FILE_BYTES",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_MAX_SESSION_BYTES": "invalid"},
            "GAME_PREDICTOR_REMOTE_SELECTION_MAX_SESSION_BYTES",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_SESSION_TRANSFERS": "0"},
            "GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_SESSION_TRANSFERS",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_GLOBAL_TRANSFERS": "0"},
            "GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_GLOBAL_TRANSFERS",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_UPLOAD_TIMEOUT_SECONDS": "0"},
            "GAME_PREDICTOR_REMOTE_SELECTION_UPLOAD_TIMEOUT_SECONDS",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_LEASE_SECONDS": "0"},
            "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_LEASE_SECONDS",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ATTEMPTS": "0"},
            "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ATTEMPTS",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ACTIONS_PER_CYCLE": "0"},
            "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ACTIONS_PER_CYCLE",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_LIMIT": "0"},
            "GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_LIMIT",
        ),
        (
            {"GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_LIMIT": "1001"},
            "GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_LIMIT",
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
            "GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES": "4096",
        }
    )

    assert settings.import_root == import_root.resolve()
    assert settings.import_max_bytes == 2048
    assert settings.browser_layout_import_max_bytes == 4096


def test_storage_gc_requires_explicit_rollout_after_observe_only() -> None:
    settings = ApiSettings.from_environment({"GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY": "false"})

    assert settings.storage_gc_observe_only is False


def test_remote_host_mapping_can_be_disabled_for_rollback() -> None:
    settings = ApiSettings.from_environment(
        {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
    )

    assert settings.remote_manual_selection_host_mapping_enabled is False


def test_remote_deselect_can_be_disabled_for_rollback() -> None:
    settings = ApiSettings.from_environment(
        {"GAME_PREDICTOR_REMOTE_SELECTION_DESELECT_ENABLED": "false"}
    )

    assert settings.remote_selection_deselect_enabled is False


def test_remote_transfer_limits_are_configurable() -> None:
    settings = ApiSettings.from_environment(
        {
            "GAME_PREDICTOR_REMOTE_SELECTION_MAX_FILE_BYTES": "1000",
            "GAME_PREDICTOR_REMOTE_SELECTION_MAX_SESSION_BYTES": "2000",
            "GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_SESSION_TRANSFERS": "2",
            "GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_GLOBAL_TRANSFERS": "3",
            "GAME_PREDICTOR_REMOTE_SELECTION_UPLOAD_TIMEOUT_SECONDS": "45",
            "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_LEASE_SECONDS": "90",
            "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ATTEMPTS": "7",
            "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ACTIONS_PER_CYCLE": "6",
            "GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_ENABLED": "false",
            "GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_LIMIT": "25",
        }
    )

    assert settings.remote_selection_max_file_bytes == 1000
    assert settings.remote_selection_max_session_bytes == 2000
    assert settings.remote_selection_max_active_session_transfers == 2
    assert settings.remote_selection_max_active_global_transfers == 3
    assert settings.remote_selection_upload_timeout_seconds == 45
    assert settings.remote_selection_materialization_lease_seconds == 90
    assert settings.remote_selection_materialization_max_attempts == 7
    assert settings.remote_selection_materialization_max_actions_per_cycle == 6
    assert settings.remote_selection_recovery_enabled is False
    assert settings.remote_selection_recovery_limit == 25
