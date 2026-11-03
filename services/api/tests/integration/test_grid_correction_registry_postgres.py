"""Disposable metadata-only registry proofs; these fixtures are not human labels."""

import json
import os
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.source_recording_permissions_v4 import recording_permission_errors
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def scope(session, game):
    GameStorageRouter().bind(session, game, intent=GameStorageIntent.READ)


def context(session, game, ids):
    return session.scalar(
        text("SELECT public.recording_photo_context_v1(:g,CAST(:ids AS uuid[]))"),
        {"g": game, "ids": ids},
    )


def command(session, game, cohort, kind, revision):
    return session.scalar(
        text("SELECT public.recording_cohort_command_v3(:g,CAST(:q AS jsonb),'fixture:1120')"),
        {
            "g": game,
            "q": json.dumps(
                {
                    "kind": kind,
                    "cohortId": str(cohort),
                    "idempotencyKey": str(uuid4()),
                    "expectedRevision": revision,
                    "manifestSha256": "a" * 64,
                }
            ),
        },
    )


def test_photo_roles_buffers_atomic_freeze_restart_alias_and_private_permissions(
    monkeypatch, tmp_path
):
    with application_role_database("t1120", ("correction-a", "correction-b")) as db:
        game, other = db.games.values()
        family, cohort, job = uuid4(), uuid4(), uuid4()
        source_ids = [uuid4() for _ in range(41)]
        roles = (
            ["TRAIN"] * 10 + ["VALIDATION"] * 5 + ["REGRESSION"] * 5 + [None] * 20 + ["VALIDATION"]
        )
        with db.owner_engine.begin() as c:
            c.execute(text("UPDATE public.games SET shape_geometry_configuration='neural_grid_v3'"))
            c.execute(
                text(
                    "INSERT INTO public.grid_model_families(id,code,descriptor_json) "
                    "VALUES(:i,:c,'{}')"
                ),
                {"i": family, "c": "test_" + family.hex},
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
            for identifier in source_ids:
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
            contexts = {r["sourceId"]: r for r in context(s, game, source_ids)}
            pins = [
                {
                    "sourceId": str(identifier),
                    "importId": str(job),
                    "sourceSha256": identifier.hex * 2,
                    "pixelSha256": identifier.hex * 2,
                    "role": roles[i],
                    "buffer": roles[i] is None,
                    "rangeStart": i * 9 + 1,
                    "rangeEnd": i * 9 + 9,
                    "registryProofSha256": contexts[str(identifier)]["proofSha256"],
                }
                for i, identifier in enumerate(source_ids)
            ]
            doc = {
                "policyVersion": "application-grid-corrections-v1",
                "mode": "grid-only",
                "familyId": str(family),
                "photoSplit": {"sources": pins, "sha256": "b" * 64},
            }
            s.execute(
                text(
                    "INSERT INTO grid_training_cohorts(game_id,id,status,document,created_by) "
                    "VALUES(:g,:c,'preparing',CAST(:d AS jsonb),'fixture:1120')"
                ),
                {"g": game, "c": cohort, "d": json.dumps(doc)},
            )
            for i, identifier in enumerate(source_ids):
                frozen = {
                    "used": i < 20,
                    "boardEligibleCount": 3 if i < 20 else 0,
                    "screenEligible": False,
                    "recording": {"qualification": "eligible", "evidenceLevel": "photo-only"},
                    "positions": [{"label": {} if i < 20 and j < 3 else None} for j in range(9)],
                }
                s.execute(
                    text("""INSERT INTO grid_training_cohort_members(game_id,cohort_id,source_id,
                  live_source_image_id,ordinal,role,frozen)
                  VALUES(:g,:c,:i,:i,:o,:r,CAST(:f AS jsonb))"""),
                    {
                        "g": game,
                        "c": cohort,
                        "i": identifier,
                        "o": i,
                        "r": roles[i],
                        "f": json.dumps(frozen),
                    },
                )
            for revision, status in enumerate(
                ("preview_ready", "materializing", "ready_to_freeze"), 2
            ):
                s.execute(
                    text(
                        "UPDATE grid_training_cohorts SET status=:s,revision=:r,"
                        "manifest_sha256=:h,manifest_path='fixture.json' "
                        "WHERE game_id=:g AND id=:c"
                    ),
                    {"g": game, "c": cohort, "s": status, "r": revision, "h": "a" * 64},
                )
        with db.owner_engine.connect() as c:
            assert recording_permission_errors(c, db.role) == ()
            assert c.scalar(text("SELECT count(*) FROM public.recording_photo_uses")) == 0
        # A concurrent same-role reservation changes the proof without changing
        # eligibility. Registration must reject drift before inserting any rows.
        with Session(db.owner_engine) as s, s.begin():
            scope(s, game)
            staged = s.begin_nested()
            s.execute(
                text(
                    "INSERT INTO public.recording_photo_uses"
                    "(game_id,cohort_id,source_id,family_id,import_id,source_sha256,"
                    "pixel_sha256,role,group_ids,split_sha256,used_in_cohort) "
                    "VALUES(:g,:c,:i,:f,:j,:sha,:sha,'TRAIN','{}',:h,false)"
                ),
                {
                    "g": game,
                    "c": uuid4(),
                    "i": source_ids[0],
                    "f": family,
                    "j": job,
                    "sha": source_ids[0].hex * 2,
                    "h": "c" * 64,
                },
            )
            with (
                pytest.raises(DBAPIError, match="GRID_CORRECTION_REGISTRY_CHANGED"),
                s.begin_nested(),
            ):
                command(s, game, cohort, "register_cohort_use", 4)
            assert s.scalar(text("SELECT count(*) FROM public.recording_photo_uses")) == 1
            staged.rollback()
        with Session(db.app_engine) as s, s.begin():
            scope(s, game)
            with pytest.raises(DBAPIError), s.begin_nested():
                s.execute(text("SELECT * FROM public.recording_photo_uses"))
            with pytest.raises(DBAPIError), s.begin_nested():
                context(s, other, source_ids[:1])
            # Rolled-back closure leaves neither partial roles nor buffers.
            savepoint = s.begin_nested()
            command(s, game, cohort, "register_cohort_use", 4)
            savepoint.rollback()
            assert context(s, game, source_ids[:1])[0]["priorRoles"] == []
            result = command(s, game, cohort, "register_cohort_use", 4)
            assert result["evidenceLevel"] == "photo-only"
            s.execute(
                text(
                    "UPDATE grid_training_cohorts SET status='frozen',revision=5 "
                    "WHERE game_id=:g AND id=:c"
                ),
                {"g": game, "c": cohort},
            )
        # New connection and READ ONLY validation prove durable state, no replay write.
        with Session(db.app_engine) as s, s.begin():
            s.execute(text("SET TRANSACTION READ ONLY"))
            scope(s, game)
            command(s, game, cohort, "validate_cohort_use", 5)
            facts = {r["sourceId"]: r for r in context(s, game, source_ids)}
            assert facts[str(source_ids[0])]["allowedRoles"] == ["TRAIN"]
            assert facts[str(source_ids[10])]["allowedRoles"] == ["VALIDATION"]
            assert facts[str(source_ids[-2])]["priorRoles"] == ["BUFFER"]
            assert facts[str(source_ids[-2])]["allowedRoles"] == []
            assert facts[str(source_ids[-1])]["allowedRoles"] == ["VALIDATION"]
        with db.owner_engine.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM public.recording_photo_uses")) == 41
            assert (
                c.scalar(
                    text("SELECT count(*) FROM public.recording_photo_uses WHERE used_in_cohort")
                )
                == 20
            )
        # Identical bytes in another game's own RLS scope inherit the frozen buffer.
        alias, other_job = uuid4(), uuid4()
        with db.owner_engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO public.jobs(id,game_id,job_type,status,input_payload,input_key) "
                    "VALUES(:i,:g,'import','completed','{}',:k)"
                ),
                {"i": other_job, "g": other, "k": other_job.hex},
            )
        with Session(db.owner_engine) as s, s.begin():
            scope(s, other)
            s.execute(
                text(
                    "INSERT INTO source_images(game_id,id,import_job_id,file_execution_key,"
                    "relative_path,checksum_sha256,width,height,status) "
                    "VALUES(:g,:i,:j,:sha,'alias.jpg',:sha,100,100,'completed')"
                ),
                {"g": other, "i": alias, "j": other_job, "sha": source_ids[-2].hex * 2},
            )
        with Session(db.app_engine) as s, s.begin():
            scope(s, other)
            assert context(s, other, [alias])[0]["priorRoles"] == ["BUFFER"]

        # A legacy TRAIN cohort cannot consume any newly reserved control,
        # buffer, or unlabelled photo. The legacy function would reject these
        # minimal metadata fixtures for readiness; the photo guard must run first.
        for identifier in (source_ids[10], source_ids[-2], source_ids[-1]):
            legacy = uuid4()
            with Session(db.owner_engine) as s, s.begin():
                scope(s, game)
                s.execute(
                    text(
                        "INSERT INTO grid_training_cohorts"
                        "(game_id,id,status,document,created_by) "
                        "VALUES(:g,:c,'preparing',CAST(:d AS jsonb),'fixture:1120')"
                    ),
                    {
                        "g": game,
                        "c": legacy,
                        "d": json.dumps({"policyVersion": "application-grid-cohort-v1"}),
                    },
                )
                s.execute(
                    text(
                        "INSERT INTO grid_training_cohort_members"
                        "(game_id,cohort_id,source_id,live_source_image_id,ordinal,role,frozen) "
                        "VALUES(:g,:c,:i,:i,0,'TRAIN',CAST(:f AS jsonb))"
                    ),
                    {"g": game, "c": legacy, "i": identifier, "f": json.dumps({"used": True})},
                )
            with Session(db.app_engine) as s, s.begin():
                scope(s, game)
                with pytest.raises(DBAPIError, match="RECORDING_ROLE_CONFLICT"), s.begin_nested():
                    command(s, game, legacy, "register_cohort_use", 1)

        _assert_command_lifecycle(db, tmp_path, game, job, pins, monkeypatch)


def _assert_command_lifecycle(db, root, game, job, original_pins, monkeypatch):
    """Actual service/SQL/files/CAS with explicit substitutes only at proof/image boundaries.

    These metadata fixtures do not prove human approvals; the separate genuine-label
    reader/e2e suites own that assertion. No training consumer is invoked.
    """
    from copy import deepcopy
    from types import SimpleNamespace
    from uuid import UUID

    from game_predictor_api.application import grid_training_cohort_commands as commands
    from game_predictor_api.application import grid_training_cohort_freeze as finalizer
    from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
    from game_predictor_api.domain.grid_training_cohorts import GridCohortError
    from game_predictor_api.storage import grid_correction_split as adapter
    from game_predictor_api.storage import grid_training_cohort_currentness as currentness
    from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
    from game_predictor_api.storage.grid_training_cohort_repository import (
        SqlAlchemyGridTrainingCohortRepository,
    )
    from test_grid_training_cohort_e2e_postgres import _install_base

    version, family = _install_base(db, game)
    pins = deepcopy(original_pins)
    for index, pin in enumerate(pins):
        pin.update(eligibleBoards=3 if index < 20 else 0, representative=True)

    def split(repo, game, imports, deadline):
        facts = adapter.contexts(repo, game, [p["sourceId"] for p in pins])
        return {
            "sha256": "b" * 64,
            "sources": [
                {**p, "registryProofSha256": facts[p["sourceId"]]["proofSha256"]} for p in pins
            ],
            "importIds": imports,
            "evidenceLevel": "photo-only",
        }

    by_source = {p["sourceId"]: p for p in pins}

    def capture(game, source, ordinal, proof, mode):
        pin = by_source[str(source)]
        count = pin["eligibleBoards"]
        return {
            "sourceId": str(source),
            "ordinal": ordinal,
            "role": pin["role"],
            "used": count > 0,
            "boardEligibleCount": count,
            "screenEligible": False,
            "recording": proof,
            "reasons": [],
            "metadataMissing": False,
            "source": {"checksum_sha256": pin["sourceSha256"]},
            "dependencyCellIds": [],
            "positions": [
                {
                    "label": {"boardId": str(uuid4()), "reviewItemId": str(uuid4())}
                    if index < count
                    else None
                }
                for index in range(9)
            ],
        }

    copied = []

    def copy_source(store, game, cohort, source):
        copied.append(source["checksum_sha256"])
        return store.publish_json(game, cohort, {"fixtureOriginal": source["checksum_sha256"]})

    monkeypatch.setattr(commands, "prepare_split", split)
    monkeypatch.setattr(commands, "validate_population", lambda *args: None)
    monkeypatch.setattr(adapter, "validate_population", lambda *args: None)
    monkeypatch.setattr(
        commands, "GridCohortEvidenceReader", lambda *args: SimpleNamespace(capture=capture)
    )
    monkeypatch.setattr(currentness, "check_member", lambda *args: None)
    monkeypatch.setattr(finalizer, "check_member", lambda *args: None)
    monkeypatch.setattr(GridCohortArtifactStore, "copy_source", copy_source)

    def service(session):
        return GridTrainingCohortService(
            SqlAlchemyGridTrainingCohortRepository(session, root), root
        )

    request = {
        "idempotencyKey": str(uuid4()),
        "mode": "grid-only",
        "familyId": str(family),
        "baseVersionId": str(version),
        "selector": {"importJobId": str(job)},
        "recordings": [],
        "policyVersion": adapter.CORRECTIONS_POLICY,
    }
    with Session(db.app_engine) as session:
        prepared = service(session).prepare(game, request, "fixture:1120-workflow")
        session.commit()
    cohort = UUID(prepared["cohort"]["id"])
    # A fresh service/session retries an already committed response.
    with Session(db.app_engine) as session:
        assert service(session).prepare(game, request, "fixture:1120-workflow") == prepared
    state = prepared["cohort"]
    for kind, cursor in (
        ("prepare-page", "nextCaptureCursor"),
        ("materialize-page", "nextMaterializationCursor"),
    ):
        while state[cursor] is not None:
            body = {
                "idempotencyKey": str(uuid4()),
                "expectedRevision": state["revision"],
                "cursor": state[cursor],
            }
            with Session(db.app_engine) as session:
                response = service(session).command(
                    game, cohort, kind, body, "fixture:1120-workflow"
                )
                session.commit()
            with Session(db.app_engine) as session:
                assert (
                    service(session).command(game, cohort, kind, body, "fixture:1120-workflow")
                    == response
                )
            state = response["cohort"]
    assert state["status"] == "ready_to_freeze"
    assert len(copied) == 20  # Neither buffers nor assigned unlabelled sources copy bytes.
    body = {
        "idempotencyKey": str(uuid4()),
        "expectedRevision": state["revision"],
        "expectedManifestSha256": state["manifestSha256"],
        "expectedPreviewSha256": state["previewSha256"],
    }
    with Session(db.app_engine) as session:
        with pytest.raises(GridCohortError, match="Reload") as conflict:
            service(session).command(
                game,
                cohort,
                "freeze",
                {**body, "idempotencyKey": str(uuid4()), "expectedRevision": state["revision"] - 1},
                "fixture:1120-workflow",
            )
        assert conflict.value.code == "GRID_COHORT_REVISION_CONFLICT"
    with Session(db.app_engine) as session:
        frozen = service(session).command(game, cohort, "freeze", body, "fixture:1120-workflow")
        session.commit()
    with Session(db.app_engine) as session:
        assert (
            service(session).command(game, cohort, "freeze", body, "fixture:1120-workflow")
            == frozen
        )
    assert frozen["cohort"]["status"] == "frozen"
    _assert_scoped_report_binding(db, game, cohort, version, family, frozen["cohort"])
    with db.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM public.recording_photo_uses WHERE cohort_id=:c"),
                {"c": cohort},
            )
            == 41
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM game_data_v2.grid_training_cohort_commands "
                    "WHERE cohort_id=:c AND kind='freeze'"
                ),
                {"c": cohort},
            )
            == 1
        )


def _assert_scoped_report_binding(db, game, cohort, base, family, header):
    """T2 SQL binding only; synthetic server report is not a domain PASS claim."""
    from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256

    candidate, report_id, key = uuid4(), uuid4(), uuid4()
    report = {
        "schemaVersion": "grid-model-evaluation-read-v3",
        "policyVersion": "grid-model-per-game-gate-v2",
        "producer": "server:grid-model-evaluator-v1",
        "versionId": str(candidate),
        "manifestSha256": "c" * 64,
        "baseVersionId": str(base),
        "familyId": str(family),
        "evidenceLevel": "photo-only",
        "cohorts": [
            {
                "gameId": str(game),
                "cohortId": str(cohort),
                "manifestSha256": header["manifestSha256"],
            }
        ],
    }
    with db.owner_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.grid_model_versions"
                "(id,family_id,version,base_version_id,manifest_json,manifest_sha256) "
                "VALUES(:i,:f,'fixture-scoped',:b,'{}',:sha)"
            ),
            {"i": candidate, "f": family, "b": base, "sha": "c" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO public.grid_model_evaluation_reports"
                "(id,version_id,producer,report_json,report_sha256) VALUES(:i,:v,:p,:j,:s)"
            ),
            {
                "i": report_id,
                "v": candidate,
                "p": report["producer"],
                "j": canonical_json(report),
                "s": descriptor_sha256(report),
            },
        )
    body = {
        "kind": "bind_existing_report",
        "cohortId": str(cohort),
        "idempotencyKey": str(key),
        "expectedRevision": header["revision"],
        "manifestSha256": header["manifestSha256"],
        "reportId": str(report_id),
    }

    def invoke(session, payload):
        scope(session, game)
        return session.scalar(
            text("SELECT public.recording_cohort_command_v3(:g,CAST(:q AS jsonb),'fixture:1121')"),
            {"g": game, "q": json.dumps(payload)},
        )

    with Session(db.app_engine) as session, session.begin():
        receipt = invoke(session, body)
    with Session(db.app_engine) as session, session.begin():
        assert invoke(session, body) == receipt
        assert receipt["reportSha256"] == descriptor_sha256(report)
    with (
        Session(db.app_engine) as session,
        session.begin(),
        pytest.raises(DBAPIError, match="RECORDING_COMMAND_CONFLICT"),
        session.begin_nested(),
    ):
        invoke(session, {**body, "manifestSha256": "d" * 64})
    with (
        Session(db.app_engine) as session,
        session.begin(),
        pytest.raises(DBAPIError, match="RECORDING_BINDING_INVALID"),
        session.begin_nested(),
    ):
        invoke(session, {**body, "idempotencyKey": str(uuid4()), "manifestSha256": "d" * 64})
