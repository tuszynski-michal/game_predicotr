"""Psycopg URL query overrides cannot redirect the isolated bootstrap endpoint."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "pilot_bootstrap", _ROOT / "scripts" / "prepare_v7_reviewed_pilot.py"
)
assert _SPEC is not None and _SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bootstrap)


@pytest.mark.parametrize("override", ["host=remote.invalid", "hostaddr=203.0.113.9"])
@pytest.mark.parametrize("target", ["owner", "runtime"])
def test_source_and_persisted_query_overrides_refuse_before_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: str, target: str
) -> None:
    owner = "postgresql+psycopg://owner:private@127.0.0.1:5432/game_predictor_v7_pilot"
    runtime = "postgresql+psycopg://game_predictor_v7_pilot_app:private@127.0.0.1:5432/game_predictor_v7_pilot"
    if target == "owner":
        owner += "?" + override
    else:
        runtime += "?" + override
    with pytest.raises(ValueError, match="without queries"):
        bootstrap._require_local_urls(make_url(owner), make_url(runtime))
    called = []
    monkeypatch.setattr(bootstrap, "create_engine", lambda *args, **kwargs: called.append(args))
    with pytest.raises(ValueError, match="query overrides"):
        bootstrap._engine(make_url(owner if target == "owner" else runtime))
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "task": "TASK-0853",
                "worktree": str(_ROOT),
                "ownerDatabaseUrl": owner,
                "databaseUrl": runtime,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bootstrap, "SETTINGS", settings)
    with pytest.raises(ValueError, match="without queries"):
        bootstrap._load()
    assert called == []


def test_matching_local_urls_have_no_query() -> None:
    url = make_url("postgresql+psycopg://owner:private@127.0.0.1:5432/game_predictor")
    bootstrap._require_local_urls(url, url.set(username="new_app"))
