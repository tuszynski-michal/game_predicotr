"""Fresh real CLI on disposable PG and a provisioned application LOGIN role."""

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_worker.geometry_core.diagnostic_registration import stage_registration
from game_predictor_worker.geometry_core.input_diagnostics import encode_record
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_grid_correction_registry_postgres import scope

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)
ROOT = Path(__file__).resolve().parents[4]


def test_real_cli_routes_write_replays_and_respects_storage_fences(tmp_path):
    with application_role_database("t1162cli", ("diagnostic",)) as db:
        game = next(iter(db.games.values()))
        source, job = uuid4(), uuid4()
        sha = source.hex * 2
        with db.owner_engine.begin() as c:
            c.execute(text("UPDATE public.games SET shape_geometry_configuration='neural_grid_v3'"))
            c.execute(
                text("""INSERT INTO public.jobs
                (id,game_id,job_type,status,input_payload,input_key)
                VALUES(:j,:g,'import','completed','{}',:k)"""),
                {"j": job, "g": game, "k": job.hex},
            )
        with Session(db.owner_engine) as s, s.begin():
            scope(s, game)
            s.execute(
                text("""INSERT INTO public.image_file_executions
                (file_execution_key,source_checksum_sha256,pipeline_fingerprint,
                checkpoint_payload,status) VALUES(:sha,:sha,:sha,'{}','completed')"""),
                {"sha": sha},
            )
            s.execute(
                text("""INSERT INTO source_images
                (game_id,id,import_job_id,file_execution_key,relative_path,checksum_sha256,
                width,height,status,raw_width,raw_height,oriented_width,oriented_height,
                coordinate_space,normalization_adapter_version,normalized_pixel_checksum_sha256)
                VALUES(:g,:s,:j,:sha,'synthetic.jpg',:sha,153,97,'completed',153,97,153,97,
                'exif-normalized-rgb-pixels-v1','fixture-v1',:sha)"""),
                {"g": game, "s": source, "j": job, "sha": sha},
            )
        sample = runpy.run_path(
            str(ROOT / "services/worker/tests/test_full_board_input_diagnostics.py")
        )["sample"]
        record = sample.__wrapped__()[1]
        identity = {
            "source_id": str(source),
            "source_sha256": sha,
            "normalized_pixel_sha256": sha,
        }
        record = record.model_copy(
            update={
                "source": record.source.model_copy(update=identity),
                "diagnostic_use": record.diagnostic_use.model_copy(update=identity),
            }
        )
        manifest = tmp_path / "synthetic-registration.json"
        manifest.write_text(json.dumps(stage_registration(game, [encode_record(record)])), "utf-8")
        env = db.subprocess_environment(
            GAME_PREDICTOR_DATABASE_URL=db.app_url.render_as_string(hide_password=False),
            GAME_PREDICTOR_OWNER_DATABASE_URL=db.owner_url.render_as_string(hide_password=False),
            GAME_PREDICTOR_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
            GAME_PREDICTOR_IMPORT_ROOT=str(tmp_path / "imports"),
        )
        # Prove the CLI's own timeout order, independent of inherited PostgreSQL options.
        env.pop("PGOPTIONS", None)

        def execute():
            # Run the checked-out script directly: no monkeypatch of settings, engine or SQL.
            return subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/register_grid_diagnostics.py"),
                    "execute",
                    "--manifest",
                    str(manifest),
                    "--actor",
                    "fixture:1162",
                    "--approved-deployment",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )

        def evidence():
            # The private ledger is owner-readable; runtime exposes only its public context.
            with Session(db.owner_engine) as s, s.begin():
                scope(s, game)
                return s.execute(
                    text("""SELECT id, payload::text, payload_sha256, actor
                    FROM public.recording_evidence
                    WHERE payload->>'purpose'='diagnostic_comparison' ORDER BY id""")
                ).all()

        assert evidence() == []
        # Maintenance rejects even a correctly scoped, otherwise valid new request.
        with db.owner_engine.begin() as c:
            c.execute(
                text(
                    "UPDATE public.game_storage_locations SET status='migrating' WHERE game_id=:g"
                ),
                {"g": game},
            )
        blocked = execute()
        assert blocked.returncode != 0
        assert "temporarily read-only during storage maintenance" in blocked.stderr
        assert evidence() == []
        with db.owner_engine.begin() as c:
            c.execute(
                text("UPDATE public.game_storage_locations SET status='active' WHERE game_id=:g"),
                {"g": game},
            )
        # An exclusive cutover fence must exclude the CLI's shared WRITE lock.
        with db.owner_engine.begin() as c:
            c.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:g,519))"),
                {"g": str(game)},
            )
            blocked = execute()
            assert blocked.returncode != 0
            assert "lock timeout" in blocked.stderr
            assert evidence() == []
        first = execute()
        assert first.returncode == 0, first.stderr
        assert "Registered 1 record bindings atomically." in first.stdout
        saved = evidence()
        assert len(saved) == 1
        assert saved[0].actor == "fixture:1162"
        # A separate process and connection reproduce the receipt after lost response.
        replay = execute()
        assert replay.returncode == 0, replay.stderr
        assert evidence() == saved
        with Session(db.app_engine) as s, s.begin():
            scope(s, game)
            facts = s.scalar(
                text("SELECT public.recording_photo_context_v3(:g,CAST(:ids AS uuid[]))"),
                {"g": game, "ids": [source]},
            )[0]
            assert facts["diagnosticExposed"] is True
