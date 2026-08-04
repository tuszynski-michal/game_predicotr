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
