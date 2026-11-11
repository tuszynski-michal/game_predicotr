"""Disposable metadata fixture, not human GT: new capability and immutable history."""

import json
import os
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256
from game_predictor_api.storage.source_recording_permissions_v10 import recording_permission_errors
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_correction_registry_postgres import scope
from test_recording_migration_lifecycle_postgres import _config

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)


def test_material_migration_partial_train_full_minima_exclusion_and_cold_validation():
    with application_role_database(
        "t1183", ("material",), revision="0183_production_cell_evaluation"
    ) as db:
        game = next(iter(db.games.values()))
        with db.owner_engine.connect() as c:
            old = c.scalar(
                text(
                    "SELECT pg_get_functiondef("
                    "'public.recording_photo_cohort_v3(uuid,jsonb,text)'::regprocedure)"
                )
            )
        print("T1183 disposable database ready", flush=True)
        command.upgrade(_config(db), "head")
        command.downgrade(_config(db), "0183_production_cell_evaluation")
        command.upgrade(_config(db), "head")
        migration = (
            ScriptDirectory.from_config(_config(db))
            .get_revision("0184_effective_grid_material")
            .module
        )
        with db.owner_engine.connect() as c:
            assert (
                c.scalar(
                    text(
                        "SELECT pg_get_functiondef("
                        "'public.recording_photo_cohort_v3(uuid,jsonb,text)'::regprocedure)"
                    )
                )
                == old
            )
            assert recording_permission_errors(c, db.role) == ()
        family, cohort, job, base, candidate = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
        ids = [uuid4() for _ in range(24)]
        roles = (
            ["TRAIN"] * 10 + ["VALIDATION"] * 5 + ["REGRESSION"] * 5 + ["TRAIN", None, None, None]
        )
        with db.owner_engine.begin() as c:
            c.execute(text("UPDATE public.games SET shape_geometry_configuration='neural_grid_v3'"))
            c.execute(
                text(
                    "INSERT INTO public.grid_model_families(id,code,descriptor_json) "
                    "VALUES(:i,:c,'{}')"
                ),
                {"i": family, "c": "material_" + family.hex},
            )
            for version, ancestor in ((base, None), (candidate, base)):
                c.execute(
                    text(
                        "INSERT INTO public.grid_model_versions"
                        "(id,family_id,version,base_version_id,manifest_json,manifest_sha256) "
                        "VALUES(:i,:f,:v,:b,'{}',:h)"
                    ),
                    {"i": version, "f": family, "v": version.hex, "b": ancestor, "h": "c" * 64},
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
            for identifier in ids:
                sha = identifier.hex * 2
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
                    {"g": game, "i": identifier, "j": job, "s": sha},
                )
            for identifier, role, used in zip(
                ids[-3:], ["TRAIN", "REGRESSION", "TRAIN"], [True, True, False], strict=True
            ):
                s.execute(
                    text("""INSERT INTO public.recording_photo_uses(game_id,cohort_id,source_id,
                 family_id,import_id,source_sha256,pixel_sha256,role,group_ids,used_in_cohort,split_sha256)
                 VALUES(:g,:c,:i,:f,:j,:sha,:sha,:r,'{}',:used,:sha)"""),
                    {
                        "g": game,
                        "c": uuid4(),
                        "i": identifier,
                        "f": family,
                        "j": job,
                        "sha": identifier.hex * 2,
                        "r": role,
                        "used": used,
                    },
                )
            history = s.scalar(
                text(
                    "SELECT jsonb_agg(to_jsonb(u) ORDER BY source_id)::text "
                    "FROM public.recording_photo_uses u"
                )
            )
            facts = {
                r["sourceId"]: r
                for r in s.scalar(
                    text("SELECT public.recording_photo_context_v3(:g,CAST(:ids AS uuid[]))"),
                    {"g": game, "ids": ids},
                )
            }
            pins = [
                {
                    "sourceId": str(i),
                    "importId": str(job),
                    "sourceSha256": i.hex * 2,
                    "pixelSha256": i.hex * 2,
                    "role": roles[n],
                    "buffer": False,
                    "validationPurpose": "A" if roles[n] == "VALIDATION" else None,
                    "registryProofSha256": facts[str(i)]["proofSha256"],
                    **({"geometryOnlyTraining": True} if n == 20 else {}),
                    **({"newUseExcluded": True} if n >= 21 else {}),
                }
                for n, i in enumerate(ids)
            ]
            doc = {
                "policyVersion": "application-grid-corrections-v4",
                "mode": "screen+grid",
                "familyId": str(family),
                "baseVersionId": str(base),
                "photoSplit": {
                    "sha256": "b" * 64,
                    "sources": pins,
                    "contentSampling": {"policy": "full-symbol-content-sampling-v1"},
                    "learningMaterial": {"version": "effective-grid-learning-material-v1"},
                },
            }
            s.execute(
                text(
                    "INSERT INTO grid_training_cohorts(game_id,id,status,document,created_by) "
                    "VALUES(:g,:c,'preparing',CAST(:d AS jsonb),'fixture')"
                ),
                {"g": game, "c": cohort, "d": json.dumps(doc)},
            )
            for n, identifier in enumerate(ids):
                count = 9 if n < 20 else 3 if n == 20 else 0
                frozen = {
                    "used": count > 0,
                    "boardEligibleCount": count,
                    "screenEligible": count == 9,
                    "positions": [{"label": {} if k < count else None} for k in range(9)],
                    "recording": {
                        "qualification": "eligible",
                        "evidenceLevel": "photo-only",
                        "validationPurpose": pins[n]["validationPurpose"],
                        "assessmentPolicy": "human-labeled-targets-v1",
                        **(
                            {
                                "geometryOnlyTraining": True,
                                "contentSamplingPolicy": "full-symbol-content-sampling-v1",
                            }
                            if n == 20
                            else {}
                        ),
                    },
                }
                s.execute(
                    text("""INSERT INTO grid_training_cohort_members(game_id,cohort_id,source_id,
                 live_source_image_id,ordinal,role,frozen)
                 VALUES(:g,:c,:i,:i,:o,:r,CAST(:f AS jsonb))"""),
                    {
                        "g": game,
                        "c": cohort,
                        "i": identifier,
                        "o": n,
                        "r": roles[n],
                        "f": json.dumps(frozen),
                    },
                )
            for revision, status in enumerate(
                ("preview_ready", "materializing", "ready_to_freeze"), 2
            ):
                s.execute(
                    text(
                        "UPDATE grid_training_cohorts SET status=:s,revision=:r,manifest_sha256=:h,"
                        "manifest_path='fixture.json' WHERE game_id=:g AND id=:c"
                    ),
                    {"g": game, "c": cohort, "s": status, "r": revision, "h": "a" * 64},
                )
            with (
                pytest.raises(RuntimeError, match="history prevents downgrade"),
                s.begin_nested(),
                Operations.context(MigrationContext.configure(s.connection())),
            ):
                migration.downgrade()

        def execute(s, kind, revision, function="recording_cohort_command_v7", **extra):
            request = {
                "kind": kind,
                "cohortId": str(cohort),
                "expectedRevision": revision,
                "idempotencyKey": str(uuid4()),
                "manifestSha256": "a" * 64,
                **extra,
            }
            return s.scalar(
                text(f"SELECT public.{function}(:g,CAST(:q AS jsonb),'fixture')"),
                {"g": game, "q": json.dumps(request)},
            )

        def report(schema, policy, rule="production-cell-content-evaluation-v1"):
            identifier = uuid4()
            document = {
                "producer": "server:grid-model-evaluator-v1",
                "versionId": str(candidate),
                "manifestSha256": "c" * 64,
                "baseVersionId": str(base),
                "familyId": str(family),
                "evidenceLevel": "photo-only",
                "cohorts": [
                    {"gameId": str(game), "cohortId": str(cohort), "manifestSha256": "a" * 64}
                ],
                "schemaVersion": "grid-model-evaluation-read-" + schema,
                "policyVersion": policy,
                "ruleVersion": rule,
            }
            with db.owner_engine.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO public.grid_model_evaluation_reports"
                        "(id,version_id,producer,report_json,report_sha256) "
                        "VALUES(:i,:v,:p,:j,:s)"
                    ),
                    {
                        "i": identifier,
                        "v": candidate,
                        "p": document["producer"],
                        "j": canonical_json(document),
                        "s": descriptor_sha256(document),
                    },
                )
            return str(identifier), descriptor_sha256(document)

        print("T1183 metadata fixture ready", flush=True)
        with Session(db.app_engine) as s, s.begin():
            scope(s, game)
            # Historical capability keeps its old rejection; opt-in alone grants no direct access.
            with (
                pytest.raises(DBAPIError, match="GRID_COHORT_FULL_PHOTO_REQUIRED"),
                s.begin_nested(),
            ):
                execute(s, "register_cohort_use", 4, "recording_cohort_command_v5")
            with pytest.raises(DBAPIError, match="permission denied"), s.begin_nested():
                execute(s, "register_cohort_use", 4, "recording_photo_cohort_v4")
            savepoint = s.begin_nested()
            execute(s, "register_cohort_use", 4)
            savepoint.rollback()
            register_key = str(uuid4())
            registered = execute(s, "register_cohort_use", 4, idempotencyKey=register_key)
        assert registered["splitSha256"] == "b" * 64
        # Lost reply: exact replay is the freeze command receipt (repo.replay runs
        # before SQL, as for v3). Re-executing the committed SQL key fails closed
        # without a second use or release.
        with Session(db.app_engine) as s, s.begin():
            scope(s, game)
            with pytest.raises(DBAPIError, match="GRID_CORRECTION_REGISTRY_CHANGED"):
                execute(s, "register_cohort_use", 4, idempotencyKey=register_key)
        with Session(db.app_engine) as s, s.begin():
            scope(s, game)
            s.execute(
                text(
                    "UPDATE grid_training_cohorts SET status='frozen',revision=5 "
                    "WHERE game_id=:g AND id=:c"
                ),
                {"g": game, "c": cohort},
            )
        with Session(db.app_engine) as s, s.begin():
            s.execute(text("SET TRANSACTION READ ONLY"))
            scope(s, game)
            execute(s, "validate_cohort_use", 5)
        # P1-2: binding a report validates partial TRAIN through the v4 cohort
        # function. The historical v6 path still rejects it unchanged.
        pairs = [
            ("v6", "production-cell-per-game-gate-v1", None, True),
            ("v5", "grid-model-per-game-gate-v3", None, True),
            ("v6", "production-cell-per-game-gate-v1", "other-rule-v1", False),
            ("v6", "grid-model-per-game-gate-v2", None, False),
            ("v4", "grid-model-per-game-gate-v3", None, False),
            ("v5", "production-cell-per-game-gate-v1", None, False),
        ]
        bound = None
        for schema, policy, rule, allowed in pairs:
            report_id, report_sha = report(schema, policy, rule) if rule else report(schema, policy)
            key = str(uuid4())
            with Session(db.app_engine) as s, s.begin():
                scope(s, game)
                if allowed:
                    receipt = execute(
                        s, "bind_existing_report", 5, reportId=report_id, idempotencyKey=key
                    )
                    assert receipt["reportSha256"] == report_sha
                    bound = bound or (key, report_id, receipt)
                else:
                    with pytest.raises(DBAPIError, match="RECORDING_BINDING_INVALID"):
                        execute(s, "bind_existing_report", 5, reportId=report_id)
        assert bound is not None
        key, report_id, receipt = bound
        with Session(db.app_engine) as s, s.begin():
            scope(s, game)
            replayed = execute(s, "bind_existing_report", 5, reportId=report_id, idempotencyKey=key)
            assert replayed == receipt
            with (
                pytest.raises(DBAPIError, match="GRID_COHORT_FULL_PHOTO_REQUIRED"),
                s.begin_nested(),
            ):
                execute(
                    s, "bind_existing_report", 5, "recording_cohort_command_v6", reportId=report_id
                )
            with pytest.raises(DBAPIError, match="permission denied"), s.begin_nested():
                execute(
                    s,
                    "bind_existing_report",
                    5,
                    "recording_correction_report_bind_v5",
                    reportId=report_id,
                )
        with db.owner_engine.connect() as c:
            assert (
                c.scalar(
                    text("SELECT count(*) FROM public.recording_photo_uses WHERE cohort_id=:c"),
                    {"c": cohort},
                )
                == 21
            )
            assert (
                c.scalar(
                    text(
                        "SELECT jsonb_agg(to_jsonb(u) ORDER BY source_id)::text "
                        "FROM public.recording_photo_uses u WHERE cohort_id<>:c"
                    ),
                    {"c": cohort},
                )
                == history
            )
            assert (
                c.scalar(text("SELECT count(*) FROM public.recording_photo_reservation_releases"))
                == 0
            )
        # A new use of an excluded source changes its registry proof; binding must
        # re-check exclusions too, not only the used members.
        with Session(db.owner_engine) as s, s.begin():
            scope(s, game)
            s.execute(
                text("""INSERT INTO public.recording_photo_uses(game_id,cohort_id,source_id,
             family_id,import_id,source_sha256,pixel_sha256,role,group_ids,used_in_cohort,
             split_sha256) VALUES(:g,:c,:i,:f,:j,:sha,:sha,'VALIDATION','{}',true,:sha)"""),
                {
                    "g": game,
                    "c": uuid4(),
                    "i": ids[22],
                    "f": family,
                    "j": job,
                    "sha": ids[22].hex * 2,
                },
            )
        report_id, _ = report("v6", "production-cell-per-game-gate-v1")
        with Session(db.app_engine) as s, s.begin():
            scope(s, game)
            with pytest.raises(DBAPIError, match="GRID_CORRECTION_REGISTRY_CHANGED"):
                execute(s, "bind_existing_report", 5, reportId=report_id)
        print("T1183 durable partial and excluded history verified", flush=True)
