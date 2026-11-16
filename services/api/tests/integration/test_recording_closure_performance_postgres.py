"""Owned metadata-only parity/closure tests; these fixtures are not human GT."""

import json
import os
from copy import deepcopy
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from alembic import command
from game_predictor_api.storage.source_recording_closure_performance import COHORT, CONTEXT
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_correction_registry_postgres import scope
from test_recording_migration_lifecycle_postgres import _config

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)


def _sources(session, game, job, ids, pixels):
    for index, identifier in enumerate(ids):
        sha = identifier.hex * 2
        session.execute(
            text("""INSERT INTO public.image_file_executions(file_execution_key,
             source_checksum_sha256,pipeline_fingerprint,checkpoint_payload,status)
             VALUES(:sha,:sha,:sha,'{}','completed')"""),
            {"sha": sha},
        )
        if pixels[index] is None:
            session.execute(
                text("""INSERT INTO source_images(game_id,id,import_job_id,file_execution_key,
                 relative_path,checksum_sha256,width,height,status)
                 VALUES(:g,:i,:j,:sha,'legacy.jpg',:sha,100,100,'completed')"""),
                {"g": game, "i": identifier, "j": job, "sha": sha},
            )
        else:
            session.execute(
                text("""INSERT INTO source_images(game_id,id,import_job_id,file_execution_key,
                 relative_path,checksum_sha256,width,height,status,raw_width,raw_height,
                 oriented_width,oriented_height,coordinate_space,normalization_adapter_version,
                 normalized_pixel_checksum_sha256)
                 VALUES(:g,:i,:j,:sha,'fixture.jpg',:sha,100,100,'completed',100,100,100,100,
                 'exif-normalized-rgb-pixels-v1','fixture-v1',:pixel)"""),
                {"g": game, "i": identifier, "j": job, "sha": sha, "pixel": pixels[index]},
            )


def _contexts(session, game, ids, preview):
    result = []
    for start in range(0, len(ids), 200):
        result.extend(
            session.scalar(
                text("SELECT public.recording_photo_context_data_v3(:g,CAST(:ids AS uuid[]),:p)"),
                {"g": game, "ids": ids[start : start + 200], "p": preview},
            )
        )
    return sorted(result, key=lambda row: row["sourceId"])


def _function_metadata(connection):
    return {
        signature: tuple(
            connection.execute(
                text("""SELECT oid,proowner,proacl,prosecdef,provolatile,proconfig FROM pg_proc
                 WHERE oid=to_regprocedure(:s)"""),
                {"s": signature},
            ).one()
        )
        for signature in (CONTEXT, COHORT)
    }


def _cohort(session, game, family, pins, *, stale=False, conflict=False, diagnostic=False):
    identifier = uuid4()
    values = deepcopy(pins)
    if stale:
        values[201]["registryProofSha256"] = "0" * 64
    if conflict:
        values[200]["role"] = "REGRESSION"  # Pixel alias of TRAIN source 0, on page two.
    if diagnostic:
        values[30]["role"] = "REGRESSION"
    document = {
        "policyVersion": "application-grid-corrections-v4",
        "mode": "grid-only",
        "familyId": str(family),
        "photoSplit": {
            "sha256": "b" * 64,
            "sources": values,
            "learningMaterial": {"version": "effective-grid-learning-material-v1"},
        },
    }
    session.execute(
        text("""INSERT INTO grid_training_cohorts(game_id,id,status,document,created_by)
         VALUES(:g,:c,'preparing',CAST(:d AS jsonb),'fixture:1235')"""),
        {"g": game, "c": identifier, "d": json.dumps(document)},
    )
    for index, pin in enumerate(values):
        used = index < 20
        frozen = {
            "used": used,
            "boardEligibleCount": 3 if used else 0,
            "screenEligible": False,
            "recording": {
                "qualification": "eligible",
                "evidenceLevel": "photo-only",
                "validationPurpose": pin["validationPurpose"],
                "assessmentPolicy": "human-labeled-targets-v1",
            },
            "positions": [{"label": {} if used and n < 3 else None} for n in range(9)],
        }
        session.execute(
            text("""INSERT INTO grid_training_cohort_members(game_id,cohort_id,source_id,
             live_source_image_id,ordinal,role,frozen)
             VALUES(:g,:c,:i,:i,:n,:r,CAST(:f AS jsonb))"""),
            {
                "g": game,
                "c": identifier,
                "i": pin["sourceId"],
                "n": index,
                "r": pin["role"],
                "f": json.dumps(frozen),
            },
        )
    for revision, status in enumerate(("preview_ready", "materializing", "ready_to_freeze"), 2):
        session.execute(
            text("""UPDATE grid_training_cohorts SET status=:s,revision=:r,
             manifest_sha256=:h,manifest_path='fixture.json' WHERE game_id=:g AND id=:c"""),
            {"g": game, "c": identifier, "s": status, "r": revision, "h": "a" * 64},
        )
    return identifier


def _command(session, game, cohort, kind, revision):
    return session.scalar(
        text("SELECT public.recording_cohort_command_v10(:g,CAST(:q AS jsonb),'fixture:1235')"),
        {
            "g": game,
            "q": json.dumps(
                {
                    "kind": kind,
                    "cohortId": str(cohort),
                    "expectedRevision": revision,
                    "idempotencyKey": str(uuid4()),
                    "manifestSha256": "a" * 64,
                }
            ),
        },
    )


def test_context_parity_migration_security_and_two_page_registration():
    with application_role_database(
        "t1235", ("closure", "closure-other"), revision="0190_grid_gate_improvement"
    ) as db:
        game, foreign = db.games.values()
        family, job, group = uuid4(), uuid4(), uuid4()
        ids = [uuid4() for _ in range(205)]
        pixels = [identifier.hex * 2 for identifier in ids]
        pixels[200], pixels[204] = pixels[0], None
        with db.owner_engine.begin() as connection:
            connection.execute(
                text("UPDATE public.games SET shape_geometry_configuration='neural_grid_v3'")
            )
            connection.execute(
                text(
                    "INSERT INTO public.grid_model_families(id,code,descriptor_json) "
                    "VALUES(:i,:c,'{}')"
                ),
                {"i": family, "c": "closure_" + family.hex},
            )
            connection.execute(
                text("""INSERT INTO public.jobs(id,game_id,job_type,status,input_payload,input_key)
                 VALUES(:j,:g,'import','completed','{}',:k)"""),
                {"j": job, "g": game, "k": job.hex},
            )
        with Session(db.owner_engine) as session, session.begin():
            scope(session, game)
            _sources(session, game, job, ids, pixels)
            for index, role, used, purpose in (
                (21, "TRAIN", True, None),
                (22, "BUFFER", False, None),
                (23, "VALIDATION", False, "A"),
                (24, "VALIDATION", False, "B"),
            ):
                historical = uuid4()
                if used:
                    session.execute(
                        text("""INSERT INTO grid_training_cohorts(game_id,id,status,document,
                         created_by) VALUES(:g,:c,'preparing','{}','fixture:1235')"""),
                        {"g": game, "c": historical},
                    )
                    session.execute(
                        text("""INSERT INTO grid_training_cohort_members(game_id,cohort_id,
                         source_id,live_source_image_id,ordinal,role,frozen)
                         VALUES(:g,:c,:i,:i,0,'TRAIN',CAST(:f AS jsonb))"""),
                        {
                            "g": game,
                            "c": historical,
                            "i": ids[index],
                            "f": json.dumps(
                                {
                                    "used": True,
                                    "positions": [
                                        {"label": {"positionIndex": 0, "nodes": [[0, 0]]}}
                                    ],
                                }
                            ),
                        },
                    )
                session.execute(
                    text("""INSERT INTO public.recording_photo_uses(game_id,cohort_id,source_id,
                     family_id,import_id,source_sha256,pixel_sha256,role,group_ids,
                     used_in_cohort,split_sha256,validation_purpose)
                     VALUES(:g,:c,:s,:f,:j,:sha,:sha,:r,'{}',:used,:sha,:purpose)"""),
                    {
                        "g": game,
                        "c": historical,
                        "s": ids[index],
                        "f": family,
                        "j": job,
                        "sha": ids[index].hex * 2,
                        "r": role,
                        "used": used,
                        "purpose": purpose,
                    },
                )
            session.execute(
                text("""INSERT INTO public.recording_evidence(id,kind,group_ids,payload,
                 payload_sha256,actor)
                 VALUES(:id,'use','{}',CAST(:p AS jsonb),:h,'fixture:1235')"""),
                {
                    "id": uuid4(),
                    "h": "d" * 64,
                    "p": json.dumps(
                        {"purpose": "diagnostic_comparison", "sourceSha256": ids[30].hex * 2}
                    ),
                },
            )
            session.execute(
                text("""INSERT INTO public.recording_groups(id,origin,game_id,revision,manifest_id,
                 manifest_sha256,expected_sources,page_count)
                 VALUES(:id,'MAIN',:g,1,:m,:h,1,1)"""),
                {"id": group, "g": game, "m": uuid4(), "h": "e" * 64},
            )
            session.execute(
                text("""INSERT INTO public.recording_occurrences(id,group_id,origin,game_id,
                 source_id,source_sha256,pixel_sha256,pixel_algorithm,width,height,attestation)
                 VALUES(:i,:group,'MAIN',:g,:s,:sha,:sha,'rgb-uint8-v1',100,100,'{}')"""),
                {"i": uuid4(), "group": group, "g": game, "s": ids[40], "sha": ids[40].hex * 2},
            )
        with Session(db.owner_engine) as session, session.begin():
            scope(session, foreign)
            foreign_job, foreign_source = uuid4(), uuid4()
            session.execute(
                text("""INSERT INTO public.jobs(id,game_id,job_type,status,input_payload,input_key)
                 VALUES(:j,:g,'import','completed','{}',:k)"""),
                {"j": foreign_job, "g": foreign, "k": foreign_job.hex},
            )
            _sources(session, foreign, foreign_job, [foreign_source], [pixels[50]])
            session.execute(
                text("""INSERT INTO public.recording_photo_uses(game_id,cohort_id,source_id,
                 family_id,import_id,source_sha256,pixel_sha256,role,group_ids,
                 used_in_cohort,split_sha256)
                 VALUES(:g,:c,:s,:f,:j,:sha,:pixel,'TRAIN','{}',true,:sha)"""),
                {
                    "g": foreign,
                    "c": uuid4(),
                    "s": foreign_source,
                    "f": family,
                    "j": foreign_job,
                    "sha": foreign_source.hex * 2,
                    "pixel": pixels[50],
                },
            )
        with Session(db.owner_engine) as session, session.begin():
            scope(session, game)
            baseline = {
                preview: _contexts(session, game, ids, preview) for preview in (False, True)
            }
            metadata = _function_metadata(session.connection())
        print("1235 original contexts captured", flush=True)
        command.upgrade(_config(db), "head")
        with Session(db.owner_engine) as session, session.begin():
            scope(session, game)
            assert _function_metadata(session.connection()) == metadata
            for preview in (False, True):
                assert _contexts(session, game, ids, preview) == baseline[preview]
            facts = {row["sourceId"]: row for row in baseline[True]}
            assert facts[str(ids[30])]["diagnosticExposed"]
            assert facts[str(ids[40])]["componentIds"] == [str(group)]
            assert facts[str(ids[21])]["usedTrainLabels"]
            assert facts[str(ids[23])]["selectionExposed"]
            assert facts[str(ids[24])]["validationPurposes"] == ["B"]
            assert facts[str(ids[50])]["priorRoles"] == ["TRAIN"]
            roles = ["TRAIN"] * 10 + ["VALIDATION"] * 5 + ["REGRESSION"] * 5
            roles += [None] * (len(ids) - len(roles))
            pins = [
                {
                    "sourceId": str(identifier),
                    "importId": str(job),
                    "sourceSha256": identifier.hex * 2,
                    "pixelSha256": pixels[index],
                    "role": roles[index],
                    "buffer": index == 22,
                    "validationPurpose": "A" if roles[index] == "VALIDATION" else None,
                    "registryProofSha256": facts[str(identifier)]["proofSha256"],
                    **({"newUseExcluded": True} if index == 21 else {}),
                }
                for index, identifier in enumerate(ids)
            ]
            bad_role = _cohort(session, game, family, pins, conflict=True)
            stale = _cohort(session, game, family, pins, stale=True)
            bad_diagnostic = _cohort(session, game, family, pins, diagnostic=True)
            ready = _cohort(session, game, family, pins)
        with Session(db.app_engine) as session, session.begin():
            scope(session, game)
            with pytest.raises(DBAPIError, match="permission denied"), session.begin_nested():
                _contexts(session, game, ids[:1], True)
            for identifier, error in (
                (bad_role, "RECORDING_ROLE_CONFLICT"),
                (stale, "GRID_CORRECTION_REGISTRY_CHANGED"),
                (bad_diagnostic, "GRID_VALIDATION_DIAGNOSTIC_EXPOSED"),
            ):
                with pytest.raises(DBAPIError, match=error), session.begin_nested():
                    _command(session, game, identifier, "register_cohort_use", 4)
            registered = _command(session, game, ready, "register_cohort_use", 4)
        with Session(db.owner_engine) as session, session.begin():
            scope(session, game)
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM public.recording_photo_uses "
                        "WHERE cohort_id IN (:a,:b)"
                    ),
                    {"a": bad_role, "b": stale},
                )
                == 0
            )
            session.execute(
                text(
                    "UPDATE grid_training_cohorts SET status='frozen',revision=5 "
                    "WHERE game_id=:g AND id=:c"
                ),
                {"g": game, "c": ready},
            )
        with Session(db.app_engine) as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            scope(session, game)
            validated = _command(session, game, ready, "validate_cohort_use", 5)
            assert validated["splitSha256"] == registered["splitSha256"]
        print("1235 role/stale guards and fresh-connection validation passed", flush=True)
        command.downgrade(_config(db), "0190_grid_gate_improvement")
        with Session(db.app_engine) as session, session.begin():
            scope(session, game)
            assert _command(session, game, ready, "validate_cohort_use", 5) == validated
        command.upgrade(_config(db), "head")
        with db.owner_engine.connect() as connection:
            assert _function_metadata(connection) == metadata
