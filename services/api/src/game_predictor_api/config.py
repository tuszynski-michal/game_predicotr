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
_DEFAULT_REVIEW_CROP_ROOT = Path(
    "artifacts/m5-reviewed-manual-merge-v16-full-preflight"
)
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
    review_crop_root: Path = field(
        default_factory=lambda: _DEFAULT_REVIEW_CROP_ROOT.resolve()
    )
    review_source_root: Path = field(
        default_factory=lambda: _DEFAULT_REVIEW_SOURCE_ROOT.resolve()
    )
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
        return cls(
            host=host,
            port=port,
            admin_origin=admin_origin,
            reviewer_origin=reviewer_origin,
            database_url=database_url,
            artifact_root=artifact_root,
            import_root=import_root,
            import_max_bytes=import_max_bytes,
            review_crop_root=review_crop_root,
            review_source_root=review_source_root,
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
