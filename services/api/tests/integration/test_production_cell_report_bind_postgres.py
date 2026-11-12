"""Real SQL capability/grants/restart; metadata fixtures do not claim content PASS."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256
from game_predictor_api.storage.source_recording_permissions_v9 import recording_permission_errors
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_correction_registry_postgres import context, scope
from test_grid_model_evaluation_bridge_postgres import _config

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)


REPLAY_SCRIPT = """
import json, os
from sqlalchemy import create_engine,text
from sqlalchemy.pool import NullPool
database_url=os.environ['TEST_DATABASE_URL']
expected_database=os.environ['TEST_DATABASE_NAME']
assert expected_database.startswith('game_predictor_t1166bind_')
engine=create_engine(database_url,poolclass=NullPool)
with engine.begin() as c:
 assert c.scalar(text('SELECT current_database()'))==expected_database
 c.execute(text("SELECT set_config('game_predictor.game_id',:g,true)"),
           {'g':os.environ['TEST_GAME']})
 result=c.scalar(text("SELECT public.recording_cohort_command_v6("
                     "CAST(:g AS uuid),CAST(:q AS jsonb),'fixture:1166')"),
                 {'g':os.environ['TEST_GAME'],'q':os.environ['TEST_REQUEST']})
 assert result==json.loads(os.environ['TEST_RECEIPT'])
engine.dispose()
print('fresh process exact receipt PASS')
"""


def seed(db, game, *, screen=False):
    """Minimum 10/5/5 frozen metadata sources, no pixels or training."""
    family, base, candidate, cohort, job = (uuid4() for _ in range(5))
    sources = [uuid4() for _ in range(20)]
    with db.owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' "
                "WHERE id=:game"
            ),
            {"game": game},
        )
        connection.execute(
            text(
                "INSERT INTO public.grid_model_families(id,code,descriptor_json) "
                "VALUES(:id,:code,'{}')"
            ),
            {"id": family, "code": "test_" + family.hex},
        )
        for version, ancestor in ((base, None), (candidate, base)):
            connection.execute(
                text(
                    "INSERT INTO public.grid_model_versions"
                    "(id,family_id,version,base_version_id,manifest_json,manifest_sha256) "
                    "VALUES(:id,:family,:version,:base,'{}',:sha)"
                ),
                {
                    "id": version,
                    "family": family,
                    "version": version.hex,
                    "base": ancestor,
                    "sha": "c" * 64,
                },
            )
        connection.execute(
            text(
                "INSERT INTO public.jobs"
                "(id,game_id,job_type,status,input_payload,input_key) "
                "VALUES(:id,:game,'import','completed','{}',:key)"
            ),
            {"id": job, "game": game, "key": job.hex},
        )
    with Session(db.owner_engine) as session, session.begin():
        scope(session, game)
        for identifier in sources:
            sha = identifier.hex * 2
            session.execute(
                text(
                    "INSERT INTO public.image_file_executions"
                    "(file_execution_key,source_checksum_sha256,pipeline_fingerprint,"
                    "checkpoint_payload,status) "
                    "VALUES(:sha,:sha,:sha,'{}','completed')"
                ),
                {"sha": sha},
            )
            session.execute(
                text("""INSERT INTO source_images(game_id,id,import_job_id,
              file_execution_key,relative_path,checksum_sha256,width,height,status,
              raw_width,raw_height,oriented_width,oriented_height,coordinate_space,
              normalization_adapter_version,normalized_pixel_checksum_sha256)
              VALUES(:g,:i,:j,:s,'metadata.jpg',:s,100,100,'completed',100,100,100,100,
              'exif-normalized-rgb-pixels-v1','fixture-v1',:s)"""),
                {"g": game, "i": identifier, "j": job, "s": sha},
            )
        proofs = {row["sourceId"]: row for row in context(session, game, sources)}
        pins = [
            dict(
                sourceId=str(identifier),
                importId=str(job),
                sourceSha256=identifier.hex * 2,
                pixelSha256=identifier.hex * 2,
                role="TRAIN" if index < 10 else "VALIDATION" if index < 15 else "REGRESSION",
                buffer=False,
                rangeStart=index * 9 + 1,
                rangeEnd=index * 9 + 9,
                registryProofSha256=proofs[str(identifier)]["proofSha256"],
            )
            for index, identifier in enumerate(sources)
        ]
        document = dict(
            policyVersion="application-grid-corrections-v3"
            if screen
            else "application-grid-corrections-v1",
            mode="screen+grid" if screen else "grid-only",
            familyId=str(family),
            baseVersionId=str(base),
            photoSplit={"sources": pins, "sha256": "b" * 64},
        )
        session.execute(
            text(
                "INSERT INTO grid_training_cohorts(game_id,id,status,document,created_by) "
                "VALUES(:g,:c,'preparing',CAST(:d AS jsonb),'fixture:1166')"
            ),
            {"g": game, "c": cohort, "d": json.dumps(document)},
        )
        frozen = dict(
            used=True,
            boardEligibleCount=3,
            screenEligible=False,
            recording={"qualification": "eligible", "evidenceLevel": "photo-only"},
            positions=[{"label": {} if index < 3 else None} for index in range(9)],
        )
        for index, pin in enumerate(pins):
            if screen:
                count = 9 if index < 15 else 3
                frozen = {
                    **frozen,
                    "boardEligibleCount": count,
                    "screenEligible": count == 9,
                    "recording": {
                        **frozen["recording"],
                        "assessmentPolicy": "human-labeled-targets-v1",
                    },
                    "positions": [{"label": {} if i < count else None} for i in range(9)],
                }
            session.execute(
                text(
                    "INSERT INTO grid_training_cohort_members"
                    "(game_id,cohort_id,source_id,live_source_image_id,ordinal,role,frozen) "
                    "VALUES(:g,:c,:i,:i,:o,:r,CAST(:f AS jsonb))"
                ),
                {
                    "g": game,
                    "c": cohort,
                    "i": pin["sourceId"],
                    "o": index,
                    "r": pin["role"],
                    "f": json.dumps(frozen),
                },
            )
        for revision, state in enumerate(("preview_ready", "materializing", "ready_to_freeze"), 2):
            session.execute(
                text(
                    "UPDATE grid_training_cohorts SET status=:s,revision=:r,"
                    "manifest_sha256=:h,manifest_path='fixture.json' WHERE game_id=:g AND id=:c"
                ),
                {"g": game, "c": cohort, "s": state, "r": revision, "h": "a" * 64},
            )
    request = dict(
        kind="register_cohort_use",
        cohortId=str(cohort),
        idempotencyKey=str(uuid4()),
        expectedRevision=4,
        manifestSha256="a" * 64,
    )
    invoke(db, game, request)
    with Session(db.owner_engine) as session, session.begin():
        scope(session, game)
        session.execute(
            text(
                "UPDATE grid_training_cohorts SET status='frozen',revision=5 "
                "WHERE game_id=:g AND id=:c"
            ),
            {"g": game, "c": cohort},
        )
    report = dict(
        producer="server:grid-model-evaluator-v1",
        versionId=str(candidate),
        manifestSha256="c" * 64,
        baseVersionId=str(base),
        familyId=str(family),
        evidenceLevel="photo-only",
        cohorts=[dict(gameId=str(game), cohortId=str(cohort), manifestSha256="a" * 64)],
    )
    return report, {**request, "kind": "bind_existing_report", "expectedRevision": 5}


def invoke(db, game, request):
    with Session(db.app_engine) as session, session.begin():
        scope(session, game)
        return session.scalar(
            text("SELECT public.recording_cohort_command_v6(:g,CAST(:q AS jsonb),'fixture:1166')"),
            {"g": game, "q": json.dumps(request)},
        )


def test_v6_binding_exact_pairs_permissions_and_fresh_process_replay():
    from alembic import command

    with application_role_database(
        "t1166bind", ("content-bind",), revision="0183_production_cell_evaluation"
    ) as db:
        Path("artifacts/TASK-1166-bind-owned.json").write_text(
            json.dumps({"database": db.owner_url.database, "role": db.role}), encoding="utf-8"
        )
        print("Owned binding database migrated", flush=True)
        config = _config(db)
        # Empty downgrade is reversible; roles retain only the public wrapper grant.
        command.downgrade(config, "0182_cell_content_references")
        command.upgrade(config, "0183_production_cell_evaluation")
        # TASK-1190: the runtime router expects the head manifest (v23+).
        command.upgrade(config, "head")
        with db.owner_engine.connect() as connection:
            assert recording_permission_errors(connection, db.role) == ()
        game = next(iter(db.games.values()))
        grid_original, grid_request = seed(db, game)
        screen_original, screen_request = seed(db, game, screen=True)
        print("Frozen metadata fixture ready", flush=True)
        pairs = [
            ("v3", "grid-model-per-game-gate-v2", True),
            ("v4", "grid-model-per-game-gate-v3", True),
            ("v5", "grid-model-per-game-gate-v2", True),
            ("v5", "grid-model-per-game-gate-v3", True),
            ("v6", "production-cell-per-game-gate-v1", True),
            ("v6", "grid-model-per-game-gate-v2", False),
            ("v6", "grid-model-per-game-gate-v3", False),
            ("v3", "production-cell-per-game-gate-v1", False),
            ("v4", "production-cell-per-game-gate-v1", False),
            ("v5", "production-cell-per-game-gate-v1", False),
        ]
        for schema, policy, allowed in pairs:
            original, request = (
                (screen_original, screen_request)
                if schema == "v4"
                else (grid_original, grid_request)
            )
            # v4 specifically requires its historical screen cohort dispatch.
            print(f"Checking {schema}/{policy}", flush=True)
            identifier = uuid4()
            document = {
                **original,
                "schemaVersion": "grid-model-evaluation-read-" + schema,
                "policyVersion": policy,
                "ruleVersion": "production-cell-content-evaluation-v1",
            }
            with db.owner_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO public.grid_model_evaluation_reports"
                        "(id,version_id,producer,report_json,report_sha256) VALUES(:i,:v,:p,:j,:s)"
                    ),
                    {
                        "i": identifier,
                        "v": original["versionId"],
                        "p": document["producer"],
                        "j": canonical_json(document),
                        "s": descriptor_sha256(document),
                    },
                )
            payload = {**request, "reportId": str(identifier), "idempotencyKey": str(uuid4())}
            if allowed:
                receipt = invoke(db, game, payload)
                assert receipt["reportSha256"] == descriptor_sha256(document)
                if schema == "v6":
                    process = subprocess.run(
                        [sys.executable, "-c", REPLAY_SCRIPT],
                        env=db.subprocess_environment(
                            TEST_DATABASE_URL=db.app_url.render_as_string(hide_password=False),
                            TEST_DATABASE_NAME=db.app_url.database,
                            TEST_GAME=str(game),
                            TEST_REQUEST=json.dumps(payload),
                            TEST_RECEIPT=json.dumps(receipt),
                        ),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    assert process.returncode == 0, process.stdout + process.stderr
            else:
                with pytest.raises(DBAPIError, match="RECORDING_BINDING_INVALID"):
                    invoke(db, game, payload)
        with pytest.raises(RuntimeError, match="history prevents downgrade"):
            command.downgrade(config, "0182_cell_content_references")


def test_replay_requires_explicit_owned_database_before_connecting():
    for missing in ("TEST_DATABASE_URL", "TEST_DATABASE_NAME"):
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"TEST_DATABASE_URL", "TEST_DATABASE_NAME"}
        }
        if missing == "TEST_DATABASE_NAME":
            # This is not a URL: reaching create_engine would fail differently.
            environment["TEST_DATABASE_URL"] = "MUST_NOT_REACH_ENGINE"
        process = subprocess.run(
            [sys.executable, "-c", REPLAY_SCRIPT],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert process.returncode != 0
        assert "KeyError: '" + missing + "'" in process.stderr
