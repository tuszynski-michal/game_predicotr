"""Validated local-only configuration for the Admin API."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)
_DEFAULT_IMPORT_MAX_BYTES = 1024 * 1024 * 1024
_DEFAULT_BROWSER_LAYOUT_IMPORT_MAX_BYTES = 20 * 1024 * 1024 * 1024
_DEFAULT_IMAGE_SELECTION_MAX_BYTES = 128 * 1024 * 1024 * 1024
_DEFAULT_REMOTE_SELECTION_MAX_FILE_BYTES = 32 * 1024 * 1024
_DEFAULT_REMOTE_SELECTION_MAX_SESSION_BYTES = 20 * 1024 * 1024 * 1024
_DEFAULT_REVIEW_CROP_ROOT = Path("artifacts/m5-reviewed-manual-merge-v16-full-preflight")
_DEFAULT_REVIEW_SOURCE_ROOT = Path("examples/imgs")


class ConfigurationError(ValueError):
    """Raised when local API configuration would expose a non-local service."""


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """Runtime settings constrained to the local machine."""

    host: str
    port: int
    admin_origin: str
    reviewer_origin: str = "http://127.0.0.1:3001"
    database_url: str = field(default=_DEFAULT_DATABASE_URL, repr=False)
    artifact_root: Path = field(default_factory=lambda: Path("artifacts").resolve())
    import_root: Path = field(default_factory=lambda: Path("imports").resolve())
    import_max_bytes: int = _DEFAULT_IMPORT_MAX_BYTES
    browser_layout_import_max_bytes: int = _DEFAULT_BROWSER_LAYOUT_IMPORT_MAX_BYTES
    image_selection_max_bytes: int = _DEFAULT_IMAGE_SELECTION_MAX_BYTES
    semi_automatic_image_selection_enabled: bool = False
    storage_warning_gib: int = 80
    storage_automatic_gc_gib: int = 60
    storage_target_gib: int = 80
    storage_hard_reserve_gib: int = 30
    storage_gc_observe_only: bool = False
    review_crop_root: Path = field(default_factory=lambda: _DEFAULT_REVIEW_CROP_ROOT.resolve())
    review_source_root: Path = field(default_factory=lambda: _DEFAULT_REVIEW_SOURCE_ROOT.resolve())
    remote_manual_selection_host_mapping_enabled: bool = True
    remote_selection_deselect_enabled: bool = True
    remote_selection_max_file_bytes: int = _DEFAULT_REMOTE_SELECTION_MAX_FILE_BYTES
    remote_selection_max_session_bytes: int = _DEFAULT_REMOTE_SELECTION_MAX_SESSION_BYTES
    remote_selection_max_active_session_transfers: int = 4
    remote_selection_max_active_global_transfers: int = 8
    remote_selection_upload_timeout_seconds: int = 120
    remote_selection_materialization_lease_seconds: int = 60
    remote_selection_materialization_max_attempts: int = 5
    remote_selection_materialization_max_actions_per_cycle: int = 4
    remote_selection_recovery_enabled: bool = True
    remote_selection_recovery_limit: int = 100
    application_name: str = "Game Predictor Admin API"
    version: str = "0.1.0"

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "ApiSettings":
        source = os.environ if environment is None else environment
        host = source.get("GAME_PREDICTOR_API_HOST", "127.0.0.1").strip()
        if host not in _LOOPBACK_HOSTS:
            raise ConfigurationError(
                "GAME_PREDICTOR_API_HOST must be localhost or a loopback address."
            )

        port = _parse_port(source.get("GAME_PREDICTOR_API_PORT", "8000"))
        admin_origin = _parse_loopback_origin(
            source.get("GAME_PREDICTOR_ADMIN_ORIGIN", "http://127.0.0.1:3000")
        )
        reviewer_origin = _parse_loopback_origin(
            source.get("GAME_PREDICTOR_REVIEWER_ORIGIN", "http://127.0.0.1:3001"),
            variable_name="GAME_PREDICTOR_REVIEWER_ORIGIN",
        )
        database_url = _parse_local_database_url(
            source.get("GAME_PREDICTOR_DATABASE_URL", _DEFAULT_DATABASE_URL)
        )
        artifact_root_value = source.get("GAME_PREDICTOR_ARTIFACT_ROOT", "artifacts").strip()
        if not artifact_root_value:
            raise ConfigurationError("GAME_PREDICTOR_ARTIFACT_ROOT cannot be empty.")
        artifact_root = Path(artifact_root_value).resolve()
        import_root_value = source.get("GAME_PREDICTOR_IMPORT_ROOT", "imports").strip()
        if not import_root_value:
            raise ConfigurationError("GAME_PREDICTOR_IMPORT_ROOT cannot be empty.")
        import_root = Path(import_root_value).resolve()
        import_max_bytes = _parse_positive_integer(
            source.get(
                "GAME_PREDICTOR_IMPORT_MAX_BYTES",
                str(_DEFAULT_IMPORT_MAX_BYTES),
            ),
            variable_name="GAME_PREDICTOR_IMPORT_MAX_BYTES",
        )
        browser_layout_import_max_bytes = _parse_positive_integer(
            source.get(
                "GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES",
                str(_DEFAULT_BROWSER_LAYOUT_IMPORT_MAX_BYTES),
            ),
            variable_name="GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES",
        )
        image_selection_max_bytes = _parse_positive_integer(
            source.get(
                "GAME_PREDICTOR_IMAGE_SELECTION_MAX_BYTES",
                str(_DEFAULT_IMAGE_SELECTION_MAX_BYTES),
            ),
            variable_name="GAME_PREDICTOR_IMAGE_SELECTION_MAX_BYTES",
        )
        semi_automatic_image_selection_enabled = _parse_boolean(
            source.get("GAME_PREDICTOR_ENABLE_SEMI_AUTOMATIC_IMAGE_SELECTION", "false"),
            variable_name="GAME_PREDICTOR_ENABLE_SEMI_AUTOMATIC_IMAGE_SELECTION",
        )
        storage_warning_gib = _parse_positive_integer(
            source.get("GAME_PREDICTOR_STORAGE_WARNING_GIB", "80"),
            variable_name="GAME_PREDICTOR_STORAGE_WARNING_GIB",
        )
        storage_automatic_gc_gib = _parse_positive_integer(
            source.get("GAME_PREDICTOR_STORAGE_AUTOMATIC_GC_GIB", "60"),
            variable_name="GAME_PREDICTOR_STORAGE_AUTOMATIC_GC_GIB",
        )
        storage_target_gib = _parse_positive_integer(
            source.get("GAME_PREDICTOR_STORAGE_TARGET_GIB", "80"),
            variable_name="GAME_PREDICTOR_STORAGE_TARGET_GIB",
        )
        storage_hard_reserve_gib = _parse_positive_integer(
            source.get("GAME_PREDICTOR_STORAGE_HARD_RESERVE_GIB", "30"),
            variable_name="GAME_PREDICTOR_STORAGE_HARD_RESERVE_GIB",
        )
        storage_gc_observe_only = _parse_boolean(
            source.get("GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY", "false"),
            variable_name="GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY",
        )
        review_crop_root = _parse_local_root(
            source.get(
                "GAME_PREDICTOR_REVIEW_CROP_ROOT",
                str(_DEFAULT_REVIEW_CROP_ROOT),
            ),
            variable_name="GAME_PREDICTOR_REVIEW_CROP_ROOT",
        )
        review_source_root = _parse_local_root(
            source.get(
                "GAME_PREDICTOR_REVIEW_SOURCE_ROOT",
                str(_DEFAULT_REVIEW_SOURCE_ROOT),
            ),
            variable_name="GAME_PREDICTOR_REVIEW_SOURCE_ROOT",
        )
        remote_manual_selection_host_mapping_enabled = _parse_boolean(
            source.get("GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED", "true"),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED",
        )
        remote_selection_deselect_enabled = _parse_boolean(
            source.get("GAME_PREDICTOR_REMOTE_SELECTION_DESELECT_ENABLED", "true"),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_DESELECT_ENABLED",
        )
        remote_selection_max_file_bytes = _parse_positive_integer(
            source.get(
                "GAME_PREDICTOR_REMOTE_SELECTION_MAX_FILE_BYTES",
                str(_DEFAULT_REMOTE_SELECTION_MAX_FILE_BYTES),
            ),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_MAX_FILE_BYTES",
        )
        remote_selection_max_session_bytes = _parse_positive_integer(
            source.get(
                "GAME_PREDICTOR_REMOTE_SELECTION_MAX_SESSION_BYTES",
                str(_DEFAULT_REMOTE_SELECTION_MAX_SESSION_BYTES),
            ),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_MAX_SESSION_BYTES",
        )
        remote_selection_max_active_session_transfers = _parse_positive_integer(
            source.get("GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_SESSION_TRANSFERS", "4"),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_SESSION_TRANSFERS",
        )
        remote_selection_max_active_global_transfers = _parse_positive_integer(
            source.get("GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_GLOBAL_TRANSFERS", "8"),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_GLOBAL_TRANSFERS",
        )
        remote_selection_upload_timeout_seconds = _parse_positive_integer(
            source.get("GAME_PREDICTOR_REMOTE_SELECTION_UPLOAD_TIMEOUT_SECONDS", "120"),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_UPLOAD_TIMEOUT_SECONDS",
        )
        remote_selection_materialization_lease_seconds = _parse_positive_integer(
            source.get(
                "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_LEASE_SECONDS",
                "60",
            ),
            variable_name=("GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_LEASE_SECONDS"),
        )
        remote_selection_materialization_max_attempts = _parse_positive_integer(
            source.get(
                "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ATTEMPTS",
                "5",
            ),
            variable_name=("GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ATTEMPTS"),
        )
        remote_selection_materialization_max_actions_per_cycle = _parse_positive_integer(
            source.get(
                "GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ACTIONS_PER_CYCLE",
                "4",
            ),
            variable_name=("GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ACTIONS_PER_CYCLE"),
        )
        remote_selection_recovery_enabled = _parse_boolean(
            source.get("GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_ENABLED", "true"),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_ENABLED",
        )
        remote_selection_recovery_limit = _parse_positive_integer(
            source.get("GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_LIMIT", "100"),
            variable_name="GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_LIMIT",
        )
        if remote_selection_recovery_limit > 1_000:
            raise ConfigurationError(
                "GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_LIMIT cannot exceed 1000."
            )
        return cls(
            host=host,
            port=port,
            admin_origin=admin_origin,
            reviewer_origin=reviewer_origin,
            database_url=database_url,
            artifact_root=artifact_root,
            import_root=import_root,
            import_max_bytes=import_max_bytes,
            browser_layout_import_max_bytes=browser_layout_import_max_bytes,
            image_selection_max_bytes=image_selection_max_bytes,
            semi_automatic_image_selection_enabled=(
                semi_automatic_image_selection_enabled
            ),
            storage_warning_gib=storage_warning_gib,
            storage_automatic_gc_gib=storage_automatic_gc_gib,
            storage_target_gib=storage_target_gib,
            storage_hard_reserve_gib=storage_hard_reserve_gib,
            storage_gc_observe_only=storage_gc_observe_only,
            review_crop_root=review_crop_root,
            review_source_root=review_source_root,
            remote_manual_selection_host_mapping_enabled=(
                remote_manual_selection_host_mapping_enabled
            ),
            remote_selection_deselect_enabled=remote_selection_deselect_enabled,
            remote_selection_max_file_bytes=remote_selection_max_file_bytes,
            remote_selection_max_session_bytes=remote_selection_max_session_bytes,
            remote_selection_max_active_session_transfers=(
                remote_selection_max_active_session_transfers
            ),
            remote_selection_max_active_global_transfers=(
                remote_selection_max_active_global_transfers
            ),
            remote_selection_upload_timeout_seconds=remote_selection_upload_timeout_seconds,
            remote_selection_materialization_lease_seconds=(
                remote_selection_materialization_lease_seconds
            ),
            remote_selection_materialization_max_attempts=(
                remote_selection_materialization_max_attempts
            ),
            remote_selection_materialization_max_actions_per_cycle=(
                remote_selection_materialization_max_actions_per_cycle
            ),
            remote_selection_recovery_enabled=remote_selection_recovery_enabled,
            remote_selection_recovery_limit=remote_selection_recovery_limit,
        )


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise ConfigurationError("GAME_PREDICTOR_API_PORT must be an integer.") from error

    if not 1 <= port <= 65535:
        raise ConfigurationError("GAME_PREDICTOR_API_PORT must be between 1 and 65535.")
    return port


def _parse_positive_integer(value: str, *, variable_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ConfigurationError(f"{variable_name} must be an integer.") from error
    if parsed < 1:
        raise ConfigurationError(f"{variable_name} must be positive.")
    return parsed


def _parse_boolean(value: str, *, variable_name: str) -> bool:
    candidate = value.strip().lower()
    if candidate == "true":
        return True
    if candidate == "false":
        return False
    raise ConfigurationError(f"{variable_name} must be true or false.")


def _parse_local_root(value: str, *, variable_name: str) -> Path:
    candidate = value.strip()
    if not candidate:
        raise ConfigurationError(f"{variable_name} cannot be empty.")
    return Path(candidate).resolve()


def _parse_loopback_origin(
    value: str,
    *,
    variable_name: str = "GAME_PREDICTOR_ADMIN_ORIGIN",
) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS:
        raise ConfigurationError(f"{variable_name} must be an http loopback origin.")
    if (
        parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            f"{variable_name} cannot contain credentials, a path, query, or fragment."
        )

    try:
        port = parsed.port
    except ValueError as error:
        raise ConfigurationError(f"{variable_name} contains an invalid port.") from error

    default_port = 80
    port_suffix = "" if port in {None, default_port} else f":{port}"
    hostname = f"[{parsed.hostname}]" if parsed.hostname == "::1" else parsed.hostname
    return f"http://{hostname}{port_suffix}"


def _parse_local_database_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme != "postgresql+psycopg":
        raise ConfigurationError(
            "GAME_PREDICTOR_DATABASE_URL must use the postgresql+psycopg driver."
        )
    if parsed.hostname not in _LOOPBACK_HOSTS:
        raise ConfigurationError("GAME_PREDICTOR_DATABASE_URL must use a loopback host.")
    if parsed.username is None or parsed.password is None:
        raise ConfigurationError(
            "GAME_PREDICTOR_DATABASE_URL must contain a username and password."
        )

    database_name = parsed.path.removeprefix("/")
    if not database_name or "/" in database_name:
        raise ConfigurationError(
            "GAME_PREDICTOR_DATABASE_URL must contain exactly one database name."
        )
    if parsed.query or parsed.fragment:
        raise ConfigurationError("GAME_PREDICTOR_DATABASE_URL cannot contain a query or fragment.")

    try:
        database_port = parsed.port
    except ValueError as error:
        raise ConfigurationError("GAME_PREDICTOR_DATABASE_URL contains an invalid port.") from error

    if database_port is None:
        raise ConfigurationError("GAME_PREDICTOR_DATABASE_URL must contain an explicit port.")

    return candidate


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    """Return the validated process configuration."""

    return ApiSettings.from_environment()
