"""Actual disposable PG: legacy JSON bytes, private capability and B fences."""

import json
import os
import runpy
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from alembic import command
from game_predictor_api.storage.source_recording_permissions_v8 import recording_permission_errors
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_correction_registry_postgres import scope
from test_recording_migration_lifecycle_postgres import _config

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def test_legacy_json_bytes_survive_column_and_fresh_b_use_blocks_legacy_selection():
    with application_role_database(
        "t1158purpose", ("purpose",), revision="0180_screen_grid_corrections"
    ) as db:
        game = next(iter(db.games.values()))
        family, job, cohort = uuid4(), uuid4(), uuid4()
        ids = [uuid4(), uuid4(), uuid4()]
        with db.owner_engine.begin() as c:
            c.execute(text("UPDATE public.games SET shape_geometry_configuration='neural_grid_v3'"))
            c.execute(
                text(
                    "INSERT INTO public.grid_model_families(id,code,descriptor_json) "
                    "VALUES(:i,:c,'{}')"
                ),
                {"i": family, "c": family.hex},
            )
            c.execute(
                text(
                    "INSERT INTO public.jobs(id,game_id,job_type,status,input_payload,input_key) "
                    "VALUES(:i,:g,'import','completed','{}',:k)"
                ),
                {"i": job, "g": game, "k": job.hex},
            )
        with Session(db.owner_engine) as s, s.begin():
            scope(s, game)
            for source in ids:
                sha = source.hex * 2
                s.execute(
                    text(
                        "INSERT INTO public.image_file_executions(file_execution_key,"
                        "source_checksum_sha256,pipeline_fingerprint,checkpoint_payload,status) "
                        "VALUES(:s,:s,:s,'{}','completed')"
                    ),
                    {"s": sha},
                )
                s.execute(
                    text("""INSERT INTO source_images(game_id,id,import_job_id,file_execution_key,
                 relative_path,checksum_sha256,width,height,status,raw_width,raw_height,
                 oriented_width,oriented_height,coordinate_space,normalization_adapter_version,
                 normalized_pixel_checksum_sha256) VALUES(:g,:i,:j,:s,'fixture.jpg',:s,100,100,
                 'completed',100,100,100,100,'exif-normalized-rgb-pixels-v1','fixture-v1',:s)"""),
                    {"g": game, "i": source, "j": job, "s": sha},
                )
            for source in ids[:2]:
                s.execute(
                    text("""INSERT INTO public.recording_photo_uses(game_id,cohort_id,source_id,
                 family_id,import_id,source_sha256,pixel_sha256,role,group_ids,range_start,range_end,
                 used_in_cohort,split_sha256)
                 VALUES(:g,:c,:s,:f,:j,:sha,:sha,'VALIDATION','{}',1,9,false,:sha)"""),
                    {
                        "g": game,
                        "c": cohort,
                        "s": source,
                        "f": family,
                        "j": job,
                        "sha": source.hex * 2,
                    },
                )
            s.execute(
                text("""INSERT INTO public.recording_photo_reservation_releases
             (game_id,cohort_id,source_id,released_by_game,released_by_cohort,split_sha256,actor)
             VALUES(:g,:c,:s,:g,:c,:sha,'fixture')"""),
                {"g": game, "c": cohort, "s": ids[1], "sha": "a" * 64},
            )
            old = [
                s.scalar(
                    text(
                        f"SELECT public.recording_photo_context_v{v}(:g,CAST(:ids AS uuid[]))::text"
                    ),
                    {"g": game, "ids": ids},
                )
                for v in (1, 2)
            ]
        command.upgrade(_config(db), "0181_validation_purposes")
        with db.owner_engine.connect() as c:
            assert recording_permission_errors(c, db.role) == ()
        with Session(db.owner_engine) as s, s.begin():
            scope(s, game)
            new = [
                s.scalar(
                    text(
                        f"SELECT public.recording_photo_context_v{v}(:g,CAST(:ids AS uuid[]))::text"
                    ),
                    {"g": game, "ids": ids},
                )
                for v in (1, 2)
            ]
            assert [v.encode() for v in new] == [v.encode() for v in old]
            insert = text("""INSERT INTO public.recording_photo_uses(game_id,cohort_id,source_id,
             family_id,import_id,source_sha256,pixel_sha256,role,group_ids,used_in_cohort,split_sha256,
             validation_purpose) VALUES(:g,:c,:s,:f,:j,:sha,:sha,'VALIDATION','{}',true,:sha,:p)""")
            params = {
                "g": game,
                "c": uuid4(),
                "s": ids[2],
                "f": family,
                "j": job,
                "sha": ids[2].hex * 2,
                "p": "B",
            }
            s.execute(insert, params)
            with (
                pytest.raises(DBAPIError, match="GRID_VALIDATION_PURPOSE_CONFLICT"),
                s.begin_nested(),
            ):
                s.execute(insert, {**params, "c": uuid4(), "p": None})
            legacy = uuid4()
            s.execute(
                text(
                    "INSERT INTO grid_training_cohorts(game_id,id,status,document,created_by) "
                    "VALUES(:g,:c,'preparing','{}','fixture')"
                ),
                {"g": game, "c": legacy},
            )
            s.execute(
                text("""INSERT INTO grid_training_cohort_members(game_id,cohort_id,source_id,
             live_source_image_id,ordinal,role,frozen)
             VALUES(:g,:c,:s,:s,0,'VALIDATION',CAST(:f AS jsonb))"""),
                {"g": game, "c": legacy, "s": ids[2], "f": '{"used":true}'},
            )
            with (
                pytest.raises(DBAPIError, match="GRID_VALIDATION_B_SELECTION_FORBIDDEN"),
                s.begin_nested(),
            ):
                s.execute(
                    text("SELECT public.recording_training_scope_v1(:g,:c)"),
                    {"g": game, "c": legacy},
                )
        _diagnostic_registration(db, game, ids[2], family, job)


def _diagnostic_registration(db, game, source, family, job):
    from game_predictor_worker.geometry_core.diagnostic_registration import registration_request
    from game_predictor_worker.geometry_core.input_diagnostics import encode_record

    # Reuse the bounded T1 record fixture; no host/operator sidecars are read.
    sample = runpy.run_path(
        str(
            Path(__file__).resolve().parents[4]
            / "services/worker/tests/test_full_board_input_diagnostics.py"
        )
    )["sample"]
    record = sample.__wrapped__()[1]
    identity = {
        "source_id": str(source),
        "source_sha256": source.hex * 2,
        "normalized_pixel_sha256": source.hex * 2,
    }
    record = record.model_copy(
        update={
            "source": record.source.model_copy(update=identity),
            "diagnostic_use": record.diagnostic_use.model_copy(update=identity),
        }
    )
    request = registration_request(encode_record(record))
    statement = text("SELECT public.recording_diagnostic_use_v1(:g,CAST(:r AS jsonb),'fixture')")
    with Session(db.app_engine) as s, s.begin():
        scope(s, game)
        args = {"g": game, "r": json.dumps(request)}
        save = s.begin_nested()
        first = s.scalar(statement, args)
        save.rollback()
        assert (
            s.scalar(
                text("SELECT public.recording_photo_context_v3(:g,CAST(:ids AS uuid[]))"),
                {"g": game, "ids": [source]},
            )[0]["diagnosticExposed"]
            is False
        )
        assert s.scalar(statement, args) == first
        assert s.scalar(statement, args) == first
    with Session(db.app_engine) as s, s.begin():
        scope(s, game)
        facts = s.scalar(
            text("SELECT public.recording_photo_context_v3(:g,CAST(:ids AS uuid[]))"),
            {"g": game, "ids": [source]},
        )[0]
        assert facts["diagnosticExposed"] is True
        assert facts["validationPurposes"] == ["B"]  # immutable history remains honest
        assert s.scalar(statement, {"g": game, "r": json.dumps(request)}) == first
        forged = {**request, "idempotencyKey": str(uuid4()), "presetJson": "{}"}
        with pytest.raises(DBAPIError, match="GRID_DIAGNOSTIC_RECORD_INVALID"), s.begin_nested():
            s.scalar(statement, {"g": game, "r": json.dumps(forged)})
    with Session(db.owner_engine) as s, s.begin():
        scope(s, game)
        assert (
            s.scalar(
                text(
                    "SELECT count(*) FROM public.recording_evidence "
                    "WHERE payload->>'purpose'='diagnostic_comparison'"
                )
            )
            == 1
        )
        with (
            pytest.raises(DBAPIError, match="GRID_VALIDATION_DIAGNOSTIC_EXPOSED"),
            s.begin_nested(),
        ):
            s.execute(
                text("""INSERT INTO public.recording_photo_uses(game_id,cohort_id,source_id,
                family_id,import_id,source_sha256,pixel_sha256,role,group_ids,used_in_cohort,
                split_sha256,validation_purpose) VALUES(:g,:c,:s,:f,:j,:sha,:sha,
                'VALIDATION','{}',true,:sha,'B')"""),
                {
                    "g": game,
                    "c": uuid4(),
                    "s": source,
                    "f": family,
                    "j": job,
                    "sha": source.hex * 2,
                },
            )
