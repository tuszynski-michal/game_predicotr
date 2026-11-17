"""Real single-row operator CAS and lost-response replay in an owned test database."""

import json
import os
from copy import deepcopy
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_worker.training_core.grid_training_admission import (
    SCREEN_GRID_CORRECTIONS_V1,
    RunBudget,
)
from game_predictor_worker.training_core.run_budget_extension import prepare_extension
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def test_operator_update_cas_and_idempotent_replay(tmp_path, monkeypatch):
    from scripts import extend_grid_training_run as cli

    with application_role_database("t1237", ("budget",)) as db:
        game = next(iter(db.games.values()))
        preset = SCREEN_GRID_CORRECTIONS_V1
        budget = replace(
            RunBudget.for_preset(preset, "train"),
            used_seconds=7200,
            reserved_steps=1200,
            attempts=2,
        )
        row = {
            "id": str(uuid4()),
            "game_id": str(game),
            "job_type": "grid_training",
            "status": "failed",
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "input_payload": {
                "training_kind": "grid-training-run-v1",
                "preset_id": preset.preset_id,
                "preset_fingerprint": preset.fingerprint,
                "planned_steps": 1200,
            },
            "checkpoint_payload": {
                "format": "grid-training-state-v1",
                "budget": budget.to_payload(),
                "chargedAt": None,
                "checkpoint": None,
                "history": [],
                "attempt": 2,
            },
        }
        recovery = {"path": "a" * 64 + ".pt", "sha256": "a" * 64, "step": 575}
        run = UUID(row["id"])
        row["game_id"] = str(game)
        with db.owner_engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO public.jobs(id,game_id,job_type,status,
              input_payload,input_key,checkpoint_payload,error_code)
              VALUES(:id,:g,'grid_training','failed',CAST(:i AS jsonb),:k,CAST(:s AS jsonb),
              'RUN_BUDGET_EXHAUSTED')"""),
                {
                    "id": run,
                    "g": game,
                    "i": json.dumps(row["input_payload"]),
                    "k": "budget_" + run.hex,
                    "s": json.dumps(row["checkpoint_payload"]),
                },
            )
        monkeypatch.setattr(cli, "checkpoint_pointer", lambda *_: recovery)
        change = prepare_extension(
            row,
            recovery,
            at="2026-11-17T00:45:00+00:00",
            reason="Operator approved four-hour limit",
        )
        with db.owner_engine.begin() as connection:
            drift = deepcopy(row["checkpoint_payload"])
            drift["concurrentMetadata"] = True

        def concurrent_validation(*_):
            # Another transaction changes state after the initial read, before FOR UPDATE.
            with db.owner_engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE public.jobs SET checkpoint_payload=CAST(:s AS jsonb) WHERE id=:id"
                    ),
                    {"s": json.dumps(drift), "id": run},
                )
            return recovery

        monkeypatch.setattr(cli, "checkpoint_pointer", concurrent_validation)
        with pytest.raises(ValueError, match="RUN_STATE_DRIFT"):
            cli.apply_preview(db.owner_engine, game, run, change, change["sha256"], tmp_path)
        with db.owner_engine.begin() as connection:
            assert cli.read_row(connection, run, game)["checkpoint_payload"] == drift
            connection.execute(
                text("UPDATE public.jobs SET checkpoint_payload=CAST(:s AS jsonb) WHERE id=:id"),
                {"s": json.dumps(row["checkpoint_payload"]), "id": run},
            )
        monkeypatch.setattr(cli, "checkpoint_pointer", lambda *_: recovery)
        result = cli.apply_preview(db.owner_engine, game, run, change, change["sha256"], tmp_path)
        assert result["applied"]
        with db.owner_engine.connect() as connection:
            saved = cli.read_row(connection, run, game)
            updated_at = connection.execute(
                text("SELECT updated_at FROM public.jobs WHERE id=:id"), {"id": run}
            ).scalar_one()
            assert saved["status"] == "failed"
            assert saved["input_payload"] == row["input_payload"]
            assert saved["checkpoint_payload"] == change["payload"]["afterState"]
        assert cli.apply_preview(db.owner_engine, game, run, change, change["sha256"], tmp_path)[
            "alreadyApplied"
        ]
        with db.owner_engine.connect() as connection:
            replayed = cli.read_row(connection, run, game)
            assert replayed == saved
            assert len(replayed["checkpoint_payload"]["history"]) == 1
            assert (
                connection.execute(
                    text("SELECT updated_at FROM public.jobs WHERE id=:id"), {"id": run}
                ).scalar_one()
                == updated_at
            )
