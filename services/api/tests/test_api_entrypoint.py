from __future__ import annotations

from pathlib import Path
from typing import Any

import uvicorn
from game_predictor_api import __main__ as api_entrypoint
from game_predictor_api.config import ApiSettings


def test_development_entrypoint_watches_only_api_source(
    monkeypatch: Any,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    settings = ApiSettings.from_environment()
    monkeypatch.setattr(api_entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(api_entrypoint, "require_database_schema", lambda _settings: None)
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **options: calls.append((app, options)),
    )

    api_entrypoint.main(["--reload"])

    assert calls == [
        (
            "game_predictor_api.main:app",
            {
                "host": settings.host,
                "port": settings.port,
                "reload": True,
                "reload_dirs": [str(Path(api_entrypoint.__file__).resolve().parents[1])],
            },
        )
    ]


def test_default_entrypoint_keeps_reload_disabled(monkeypatch: Any) -> None:
    calls: list[dict[str, object]] = []
    settings = ApiSettings.from_environment()
    monkeypatch.setattr(api_entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(api_entrypoint, "require_database_schema", lambda _settings: None)
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda _app, **options: calls.append(options),
    )

    api_entrypoint.main([])

    assert calls == [
        {
            "host": settings.host,
            "port": settings.port,
            "reload": False,
            "reload_dirs": None,
        }
    ]


def test_entrypoint_refuses_a_database_behind_the_code_head(monkeypatch: Any) -> None:
    import pytest
    from game_predictor_api.storage import schema_readiness

    calls: list[object] = []
    settings = ApiSettings.from_environment()
    monkeypatch.setattr(api_entrypoint, "get_settings", lambda: settings)

    class _Engine:
        disposed = False

        def dispose(self) -> None:
            _Engine.disposed = True

    monkeypatch.setattr(api_entrypoint, "create_database_engine", lambda _settings: _Engine())
    monkeypatch.setattr(
        schema_readiness, "database_alembic_revision", lambda _engine: "0130_previous"
    )
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(schema_readiness.AlembicHeadMismatchError) as error:
        api_entrypoint.main([])

    assert error.value.code == "ALEMBIC_HEAD_MISMATCH"
    assert error.value.found == "0130_previous"
    assert calls == [] and _Engine.disposed
