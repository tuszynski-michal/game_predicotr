"""One exact-owned PostgreSQL proof; metadata fixtures are not human-label evidence."""

import json
import os
from contextlib import nullcontext
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database
from alembic import command
from alembic.config import Config
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_model_registry import (
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
    validate_manifest,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_data_v2_manifest_v16 import ADDED_GAME_TABLES
from game_predictor_api.storage.game_partition_lifecycle import partition_name
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.source_recording_permissions_v3 import (
    CAPABILITY_COLUMNS,
    COHORT_HELPER_FUNCTIONS,
    SOURCE_RECORDING_V3_FUNCTIONS,
    recording_permission_errors,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit exact-owned disposable PostgreSQL fixture only",
)


def _scope(session, db, game, *, read=False):
    GameStorageRouter().bind(
        session, game, intent=GameStorageIntent.READ if read else GameStorageIntent.WRITE
    )


def _command(session, game, cohort, kind, revision, root):
    body = {
        "kind": kind,
        "cohortId": str(cohort),
        "expectedRevision": revision,
        "manifestSha256": root,
    }
    if kind != "validate_cohort_use":
        body["idempotencyKey"] = str(uuid4())
    return session.scalar(
        text(
            "SELECT public.recording_cohort_command_v3(:game,CAST(:body AS jsonb),'fixture:0995')"
        ),
        {"game": game, "body": json.dumps(body)},
    )


def test_exact_owned_v3_migration_privileges_use_and_read_only_validation(monkeypatch):
    root = Path(__file__).resolve().parents[4]
    evidence = root / "artifacts/audits" / ("TASK-0995_PG_" + uuid4().hex)
    evidence.mkdir()
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))
    stages = []

    def stage(value):
        stages.append(value)
        (evidence / "progress.json").write_text(json.dumps(stages), encoding="utf-8")
        print("0995 PG " + value, flush=True)

    stage("starting_owned_fixture")
    try:
        with application_role_database("t0995", ("cohort-a", "cohort-b")) as db:
            stage("fixture_ready")
            config = Config(str(ALEMBIC_INI))
            config.set_main_option(
                "sqlalchemy.url",
                db.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
            )
            command.downgrade(config, "0162_grid_quality_measurements")
            command.upgrade(config, "0163_grid_training_cohorts")
            with db.owner_engine.begin() as connection:
                provision_application_role(
                    connection, ApplicationRoleSpec(db.role, db.app_url.password)
                )
                assert recording_permission_errors(connection, db.role) == ()
                # Below the merge revision 0164 main's board-search head stays applied too.
                assert set(
                    connection.scalars(text("SELECT version_num FROM public.alembic_version"))
                ) == {"0163_grid_training_cohorts", "0155_board_search_panels"}
                for table, columns in CAPABILITY_COLUMNS.items():
                    assert not connection.scalar(
                        text("SELECT has_table_privilege(:r,:t,'SELECT')"),
                        {"r": db.recording_capability.role, "t": table},
                    )
                    for column in columns:
                        assert connection.scalar(
                            text("SELECT has_column_privilege(:r,:t,:c,'SELECT')"),
                            {"r": db.recording_capability.role, "t": table, "c": column},
                        )
                    selected = set(
                        connection.scalars(
                            text(
                                "SELECT a.attname FROM pg_attribute a "
                                "WHERE a.attrelid=to_regclass(:t) "
                                "AND a.attnum>0 AND NOT a.attisdropped "
                                "AND has_column_privilege(:r,:t,a.attname,'SELECT')"
                            ),
                            {"r": db.recording_capability.role, "t": table},
                        )
                    )
                    assert selected == set(columns)
                connection.exec_driver_sql(
                    f'GRANT ALL ON ALL TABLES IN SCHEMA public,game_data_v2 TO "{db.role}"'
                )
                connection.exec_driver_sql(
                    f'GRANT ALL ON ALL FUNCTIONS IN SCHEMA public,game_data_v2 TO "{db.role}"'
                )
                provision_application_role(
                    connection, ApplicationRoleSpec(db.role, db.app_url.password)
                )
                assert recording_permission_errors(connection, db.role) == ()
                for signature in COHORT_HELPER_FUNCTIONS:
                    assert not connection.scalar(
                        text("SELECT has_function_privilege(:r,:f,'EXECUTE')"),
                        {"r": db.role, "f": signature},
                    )
                for signature in SOURCE_RECORDING_V3_FUNCTIONS:
                    assert connection.scalar(
                        text("SELECT has_function_privilege(:r,:f,'EXECUTE')"),
                        {"r": db.role, "f": signature},
                    )
            # 0163 is no longer head: the use checks below run on the current schema.
            command.upgrade(config, "heads")
            with db.owner_engine.begin() as connection:
                provision_application_role(
                    connection, ApplicationRoleSpec(db.role, db.app_url.password)
                )
            stage("empty_down_up_and_reprovision_passed")
            game, foreign = db.games.values()
            cohort, family, version, job = (uuid4() for _ in range(4))
            root_sha = "d" * 64
            roles = [("TRAIN", 10, 3), ("VALIDATION", 5, 9), ("REGRESSION", 5, 9)]
            groups = {role: uuid4() for role, _, _ in roles}
            document = {
                "policyVersion": "application-grid-cohort-v1",
                "mode": "grid-only",
                "familyId": str(family),
                "baseVersionId": str(version),
                "baseManifestSha256": "b" * 64,
                "recordings": [{"groupId": str(gid), "role": role} for role, gid in groups.items()],
            }
            with db.owner_engine.begin() as c:
                c.execute(
                    text(
                        "UPDATE public.games SET shape_geometry_configurati"
                        "on='neural_grid_v3' WHERE id=ANY(CAST(:ids AS uuid"
                        "[]))"
                    ),
                    {"ids": [game, foreign]},
                )
                c.execute(
                    text(
                        "INSERT INTO public.grid_model_families(id,code,des"
                        "criptor_json) VALUES(:id,:code,'{}')"
                    ),
                    {"id": family, "code": "fixture_" + family.hex},
                )
                c.execute(
                    text(
                        "INSERT INTO public.grid_model_versions(id,family_i"
                        "d,version,manifest_json,manifest_sha256) VALUES(:i"
                        "d,:family,'fixture','{}',:sha)"
                    ),
                    {"id": version, "family": family, "sha": "b" * 64},
                )
                c.execute(
                    text(
                        "INSERT INTO public.jobs(id,game_id,job_type,status"
                        ",input_payload,input_key) VALUES(:id,:g,'import','"
                        "completed','{}',:key)"
                    ),
                    {"id": job, "g": game, "key": uuid4().hex},
                )
            with Session(db.owner_engine) as s, s.begin():
                _scope(s, db, game)
                s.execute(
                    text(
                        "INSERT INTO grid_training_cohorts(game_id,id,statu"
                        "s,document,created_by) VALUES(:g,:id,'preparing',C"
                        "AST(:doc AS jsonb),'fixture:0995')"
                    ),
                    {"g": game, "id": cohort, "doc": json.dumps(document)},
                )
                ordinal = 0
                for role, photos, labels in roles:
                    gid, event = groups[role], uuid4()
                    s.execute(
                        text(
                            "INSERT INTO public.recording_groups(id,game_id,rev"
                            "ision,manifest_id,manifest_sha256,expected_sources"
                            ",page_count,membership_complete,declared,independe"
                            "nt) VALUES(:id,:g,1,:id,:sha,:n,1,true,true,true)"
                        ),
                        {"id": gid, "g": game, "sha": "a" * 64, "n": photos},
                    )
                    s.execute(
                        text(
                            "INSERT INTO public.recording_evidence(id,kind,grou"
                            "p_ids,payload,payload_sha256,actor) VALUES(:id,'de"
                            "claration',ARRAY[:gid]::uuid[],'{}',:sha,'fixture:"
                            "0995')"
                        ),
                        {"id": event, "gid": gid, "sha": "a" * 64},
                    )
                    s.execute(
                        text(
                            "INSERT INTO public.recording_role_heads(family_id,"
                            "group_id,revision,role,event_id) VALUES(:f,:g,1,:r"
                            "ole,:e)"
                        ),
                        {"f": family, "g": gid, "role": role, "e": event},
                    )
                    sources = []
                    for _ in range(photos):
                        source = uuid4()
                        sources.append(source)
                        checksum = source.hex * 2
                        s.execute(
                            text(
                                "INSERT INTO public.image_file_executions(file_exec"
                                "ution_key,source_checksum_sha256,pipeline_fingerpr"
                                "int,checkpoint_payload,status) VALUES(:sha,:sha,:s"
                                "ha,'{}','completed')"
                            ),
                            {"sha": checksum},
                        )
                        s.execute(
                            text(
                                "INSERT INTO source_images(game_id,id,import_job_id"
                                ",file_execution_key,relative_path,checksum_sha256,"
                                "width,height,status) VALUES(:g,:id,:j,:sha,'metada"
                                "ta-fixture-only.jpg',:sha,100,100,'completed')"
                            ),
                            {"g": game, "id": source, "j": job, "sha": checksum},
                        )
                        s.execute(
                            text(
                                "INSERT INTO public.recording_occurrences(id,group_"
                                "id,game_id,source_id,source_sha256,pixel_sha256,pi"
                                "xel_algorithm,width,height,attestation) VALUES(:id"
                                ",:group,:g,:s,:sha,:sha,'rgb-uint8-v1',100,100,'{}"
                                "')"
                            ),
                            {"id": uuid4(), "group": gid, "g": game, "s": source, "sha": checksum},
                        )
                    proof = s.scalar(
                        text("SELECT public.recording_proof_v1(ARRAY[:id]::uuid[])"), {"id": gid}
                    )
                    resolution = uuid4()
                    payload = {"familyId": str(family), "baseVersionId": str(version)}
                    s.execute(
                        text(
                            "INSERT INTO public.recording_evidence(id,kind,grou"
                            "p_ids,dependency_group_ids,payload,payload_sha256,"
                            "proof_sha256,actor) VALUES(:id,'resolution',ARRAY["
                            ":gid]::uuid[],ARRAY[:gid]::uuid[],CAST(:p AS jsonb"
                            "),:sha,:proof,'fixture:0995')"
                        ),
                        {
                            "id": resolution,
                            "gid": gid,
                            "p": json.dumps(payload),
                            "sha": "a" * 64,
                            "proof": proof,
                        },
                    )
                    for source in sources:
                        positions = [
                            {
                                "positionIndex": i,
                                "label": {
                                    "sequenceNumber": ordinal * 9 + i + 1,
                                    "nodes": [
                                        {"x": float(n % 6), "y": float(n // 6)} for n in range(24)
                                    ],
                                }
                                if i < labels
                                else None,
                            }
                            for i in range(9)
                        ]
                        frozen = {
                            "used": True,
                            "role": role,
                            "boardEligibleCount": labels,
                            "screenEligible": labels == 9,
                            "positions": positions,
                            "recording": {
                                "groupId": str(gid),
                                "role": role,
                                "qualification": "eligible",
                                "resolutionId": str(resolution),
                                "proofSha256": proof,
                            },
                        }
                        s.execute(
                            text(
                                "INSERT INTO grid_training_cohort_members(game_id,c"
                                "ohort_id,source_id,live_source_image_id,ordinal,ro"
                                "le,frozen) VALUES(:g,:c,:id,:id,:o,:role,CAST(:f A"
                                "S jsonb))"
                            ),
                            {
                                "g": game,
                                "c": cohort,
                                "id": source,
                                "o": ordinal,
                                "role": role,
                                "f": json.dumps(frozen),
                            },
                        )
                        ordinal += 1
                s.execute(
                    text(
                        "INSERT INTO grid_training_cohort_members(game_id,c"
                        "ohort_id,source_id,ordinal,frozen) "
                        "VALUES(:g,:c,:id,:o,jsonb_build_object('used',false,'reasons',"
                        "jsonb_build_array('RECORDING_SELECTION_REQUIRED')))"
                    ),
                    {"g": game, "c": cohort, "id": uuid4(), "o": ordinal},
                )
                for revision, status in enumerate(
                    ("preview_ready", "materializing", "ready_to_freeze"), 2
                ):
                    s.execute(
                        text(
                            "UPDATE grid_training_cohorts SET status=:status,re"
                            "vision=:revision,manifest_path=:p,manifest_sha256="
                            ":sha WHERE game_id=:g AND id=:id"
                        ),
                        {
                            "status": status,
                            "revision": revision,
                            "p": "data/grid-training-cohorts/fixture/root.json"
                            if revision == 4
                            else None,
                            "sha": root_sha if revision == 4 else None,
                            "g": game,
                            "id": cohort,
                        },
                    )
            stage("metadata_only_20_used_1_excluded_ready")
            with Session(db.app_engine) as s, s.begin():
                _scope(s, db, game)
                result = _command(s, game, cohort, "register_cohort_use", 4, root_sha)
                assert len(result["uses"]) == 3
                s.execute(
                    text(
                        "UPDATE grid_training_cohorts SET status='frozen',r"
                        "evision=5 WHERE game_id=:g AND id=:c"
                    ),
                    {"g": game, "c": cohort},
                )
            with db.owner_engine.connect() as c:
                saved_command = c.scalar(
                    text(
                        "SELECT command_json FROM public.recording_commands "
                        "WHERE kind='register_cohort_use'"
                    )
                )
                before = tuple(
                    c.execute(
                        text(
                            "SELECT (SELECT count(*) FROM public.recording_comm"
                            "ands),(SELECT count(*) FROM public.recording_evide"
                            "nce WHERE kind='use')"
                        )
                    ).one()
                )
                assert before == (1, 3)
            with Session(db.app_engine) as s, s.begin():
                _scope(s, db, game)
                replay = s.scalar(
                    text(
                        "SELECT public.recording_cohort_command_v3(:game,CAST(:body AS jsonb),"
                        "'fixture:0995')"
                    ),
                    {"game": game, "body": json.dumps(saved_command)},
                )
                assert replay == result
            with Session(db.app_engine) as s, s.begin():
                s.execute(text("SET TRANSACTION READ ONLY"))
                _scope(s, db, game, read=True)
                validation = _command(s, game, cohort, "validate_cohort_use", 5, root_sha)
                assert validation["valid"] and validation["usedMemberCount"] == 20
                assert len(validation["proofSha256"]) == 64
            with db.owner_engine.connect() as c:
                assert (
                    tuple(
                        c.execute(
                            text(
                                "SELECT (SELECT count(*) FROM public.recording_comm"
                                "ands),(SELECT count(*) FROM public.recording_evide"
                                "nce WHERE kind='use')"
                            )
                        ).one()
                    )
                    == before
                )
                assert (
                    c.scalar(
                        text(
                            "SELECT count(*) FROM public.recording_evidence WHE"
                            "RE kind='use' AND payload ? 'reportId'"
                        )
                    )
                    == 0
                )
            with Session(db.app_engine) as s, s.begin():
                _scope(s, db, foreign)
                for table in ADDED_GAME_TABLES:
                    assert (
                        s.scalar(
                            text(f"SELECT count(*) FROM game_data_v2.{table} WHERE game_id=:g"),
                            {"g": game},
                        )
                        == 0
                    )
                    assert (
                        s.scalar(
                            text(f"SELECT count(*) FROM game_data_v2.{partition_name(game, table)}")
                        )
                        == 0
                    )
            for forbidden in (
                "SELECT id FROM public.recording_evidence",
                "SELECT last_value FROM public.recording_evidence_ordinal_seq",
            ):
                with db.app_engine.begin() as c, pytest.raises(DBAPIError):
                    c.exec_driver_sql(forbidden)
            with pytest.raises(DBAPIError, match="GRID_COHORT_DOWNGRADE_HAS_HISTORY"):
                command.downgrade(config, "0162_grid_quality_measurements")
            stage("actual_use_read_only_rls_nonempty_downgrade_passed")
    finally:
        base = make_url(ApiSettings.from_environment().owner_database_url).set(database="postgres")
        engine = create_engine(
            base,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
        )
        checks = []
        journals = list((evidence / "resources").glob("*.json"))
        try:
            with engine.connect() if journals else nullcontext() as c:
                for path in journals:
                    receipt = json.loads(path.read_text(encoding="utf-8"))
                    assert receipt["databaseCreatedHere"] and receipt["databaseName"].startswith(
                        "game_predictor_t0995_"
                    )
                    name = receipt["databaseName"]
                    roles = [
                        receipt[key]["name"]
                        for key in ("capabilityRole", "runtimeRole")
                        if receipt.get(key) and receipt[key]["createdHere"]
                    ]
                    check = {
                        "database": name,
                        "databaseOid": receipt["databaseOid"],
                        "databaseRemaining": c.scalar(
                            text("SELECT count(*) FROM pg_database WHERE datname=:n"), {"n": name}
                        ),
                        "rolesRemaining": c.scalar(
                            text(
                                "SELECT count(*) FROM pg_roles WHERE rolname=ANY(CA"
                                "ST(:roles AS text[]))"
                            ),
                            {"roles": roles},
                        ),
                        "pids": list(
                            c.scalars(
                                text("SELECT pid FROM pg_stat_activity WHERE datname=:n"),
                                {"n": name},
                            )
                        ),
                    }
                    checks.append(check)
                    assert (
                        check["databaseRemaining"] == check["rolesRemaining"] == 0
                        and not check["pids"]
                    )
        finally:
            engine.dispose()
            (evidence / "cleanup.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
            stage("cleanup_checked")


def test_exact_owned_application_prepare_page_restart_and_minimum_rejection(monkeypatch):
    evidence = (
        Path(__file__).resolve().parents[4]
        / "artifacts/audits"
        / ("TASK-0995_APP_PG_" + uuid4().hex)
    )
    evidence.mkdir()
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))

    def no_pixels(*args, **kwargs):
        pytest.fail("The excluded metadata smoke must not copy or decode pixels")

    monkeypatch.setattr(GridCohortArtifactStore, "decode_source", no_pixels)
    monkeypatch.setattr(GridCohortArtifactStore, "copy_source", no_pixels)
    monkeypatch.setattr(
        "game_predictor_api.storage.grid_training_cohort_artifacts.decode_canonical_source_bytes",
        no_pixels,
    )

    def service(session):
        return GridTrainingCohortService(
            SqlAlchemyGridTrainingCohortRepository(session, evidence), evidence
        )

    try:
        with application_role_database("t0995a", ("cohort-app",)) as db:
            game = next(iter(db.games.values()))
            family, version, job = (uuid4() for _ in range(3))
            sources = [uuid4(), uuid4()]
            base = json.loads(json.dumps(historical_catalogue()[0]))
            base.update(
                familyId=str(family), versionId=str(version), familyCode="fixture_app_" + family.hex
            )
            descriptor = validate_manifest(base)
            sha = descriptor_sha256(base)
            with db.owner_engine.begin() as c:
                c.execute(
                    text(
                        "UPDATE public.games SET shape_geometry_configurati"
                        "on='neural_grid_v3' WHERE id=:g"
                    ),
                    {"g": game},
                )
                c.execute(
                    text(
                        "INSERT INTO public.grid_model_families(id,code,des"
                        "criptor_json) VALUES(:id,:code,:doc)"
                    ),
                    {
                        "id": family,
                        "code": base["familyCode"],
                        "doc": canonical_json(
                            {
                                "id": str(family),
                                "code": base["familyCode"],
                                "label": base["familyLabel"],
                            }
                        ),
                    },
                )
                c.execute(
                    text(
                        "INSERT INTO public.grid_model_versions(id,family_i"
                        "d,version,manifest_json,manifest_sha256) VALUES(:i"
                        "d,:f,:v,:doc,:sha)"
                    ),
                    {
                        "id": version,
                        "f": family,
                        "v": base["version"],
                        "doc": descriptor,
                        "sha": sha,
                    },
                )
                c.execute(
                    text(
                        "INSERT INTO public.jobs(id,game_id,job_type,status"
                        ",input_payload,input_key) VALUES(:id,:g,'import','"
                        "completed','{}',:key)"
                    ),
                    {"id": job, "g": game, "key": uuid4().hex},
                )
                for source in sources:
                    checksum = source.hex * 2
                    c.execute(
                        text(
                            "INSERT INTO public.image_file_executions(file_exec"
                            "ution_key,source_checksum_sha256,pipeline_fingerpr"
                            "int,checkpoint_payload,status) VALUES(:sha,:sha,:s"
                            "ha,'{}','completed')"
                        ),
                        {"sha": checksum},
                    )
                    c.execute(
                        text(
                            "INSERT INTO game_data_v2.source_images(game_id,id,"
                            "import_job_id,file_execution_key,relative_path,che"
                            "cksum_sha256,width,height,status) VALUES(:g,:id,:j"
                            ",:sha,'metadata-only-never-open.jpg',:sha,100,100,"
                            "'completed')"
                        ),
                        {"g": game, "id": source, "j": job, "sha": checksum},
                    )
            body = {
                "idempotencyKey": str(uuid4()),
                "mode": "grid-only",
                "familyId": str(family),
                "baseVersionId": str(version),
                "selector": {"sourceIds": [str(value) for value in sources]},
                "recordings": [],
            }
            with Session(db.app_engine) as s, s.begin():
                prepared = service(s).prepare(game, body, "fixture:0995")
                cohort = UUID(prepared["cohort"]["id"])
                assert prepared["cohort"]["status"] == "preparing"
            page = {"idempotencyKey": str(uuid4()), "expectedRevision": 1, "cursor": 0}
            with Session(db.app_engine) as s, s.begin():
                captured = service(s).command(game, cohort, "prepare-page", page, "fixture:0995")
                assert (
                    captured["cohort"]["status"] == "preview_ready"
                    and captured["cohort"]["revision"] == 2
                )
            with Session(db.app_engine) as s, s.begin():
                current = service(s).get(game, cohort)
                assert current == captured["cohort"]
                assert service(s).prepare(game, body, "fixture:0995") == prepared
                assert (
                    service(s).command(game, cohort, "prepare-page", page, "fixture:0995")
                    == captured
                )
                members = service(s).members(game, cohort, None, 200)["items"]
                assert len(members) == 2
                assert all(
                    member["role"] is None
                    and member["boardEligibleCount"] == 0
                    and "RECORDING_SELECTION_REQUIRED" in member["reasons"]
                    for member in members
                )
            for changed, expected in (
                ({**body, "mode": "screen+grid"}, "GRID_COHORT_IDEMPOTENCY_CONFLICT"),
            ):
                with (
                    pytest.raises(GridCohortError) as failure,
                    Session(db.app_engine) as s,
                    s.begin(),
                ):
                    service(s).prepare(game, changed, "fixture:0995")
                assert failure.value.code == expected
            with pytest.raises(GridCohortError) as failure, Session(db.app_engine) as s, s.begin():
                service(s).command(
                    game,
                    cohort,
                    "prepare-page",
                    {**page, "idempotencyKey": str(uuid4())},
                    "fixture:0995",
                )
            assert failure.value.code == "GRID_COHORT_REVISION_CONFLICT"
            with pytest.raises(GridCohortError) as failure, Session(db.app_engine) as s, s.begin():
                service(s).command(
                    game,
                    cohort,
                    "materialize-page",
                    {"idempotencyKey": str(uuid4()), "expectedRevision": 2, "cursor": 0},
                    "fixture:0995",
                )
            assert failure.value.code == "GRID_COHORT_MINIMUM_NOT_MET"
            with Session(db.app_engine) as s, s.begin():
                assert service(s).get(game, cohort) == current
                assert (
                    s.scalar(
                        text(
                            "SELECT count(*) FROM grid_training_cohort_pages WH"
                            "ERE kind='materialization'"
                        )
                    )
                    == 0
                )
                frozen = list(s.scalars(text("SELECT frozen FROM grid_training_cohort_members")))
                assert len(frozen) == 2 and all(member["used"] is False for member in frozen)
            # TASK-1000: recordings of different roles come from different imports.
            second, extra = uuid4(), uuid4()
            with db.owner_engine.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO public.jobs(id,game_id,job_type,status"
                        ",input_payload,input_key) VALUES(:id,:g,'import','"
                        "completed','{}',:key)"
                    ),
                    {"id": second, "g": game, "key": uuid4().hex},
                )
                checksum = extra.hex * 2
                c.execute(
                    text(
                        "INSERT INTO public.image_file_executions(file_exec"
                        "ution_key,source_checksum_sha256,pipeline_fingerpr"
                        "int,checkpoint_payload,status) VALUES(:sha,:sha,:s"
                        "ha,'{}','completed')"
                    ),
                    {"sha": checksum},
                )
                c.execute(
                    text(
                        "INSERT INTO game_data_v2.source_images(game_id,id,"
                        "import_job_id,file_execution_key,relative_path,che"
                        "cksum_sha256,width,height,status) VALUES(:g,:id,:j"
                        ",:sha,'metadata-only-never-open.jpg',:sha,100,100,"
                        "'completed')"
                    ),
                    {"g": game, "id": extra, "j": second, "sha": checksum},
                )
            several = {
                **body,
                "idempotencyKey": str(uuid4()),
                "selector": {"importJobIds": [str(job), str(second)]},
            }
            with Session(db.app_engine) as s, s.begin():
                joined = service(s).prepare(game, several, "fixture:1000")
            with Session(db.app_engine) as s, s.begin():
                assert service(s).prepare(game, several, "fixture:1000") == joined
                rows = s.execute(
                    text("SELECT source_id FROM grid_training_cohort_members WHERE cohort_id=:c"),
                    {"c": UUID(joined["cohort"]["id"])},
                ).scalars()
                assert set(rows) == {*sources, extra}
            for selector in (
                {"importJobIds": [str(job), str(uuid4())]},
                {"importJobIds": [str(second), str(uuid4())]},
            ):
                with (
                    pytest.raises(GridCohortError) as failure,
                    Session(db.app_engine) as s,
                    s.begin(),
                ):
                    service(s).prepare(
                        game,
                        {**body, "idempotencyKey": str(uuid4()), "selector": selector},
                        "fixture:1000",
                    )
                assert failure.value.code == "GRID_COHORT_SELECTION_UNAVAILABLE"
            assert not list(evidence.rglob("*.jpg"))
    finally:
        receipts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (evidence / "resources").glob("*.json")
        ]
        result = []
        if receipts:
            engine = create_engine(
                make_url(ApiSettings.from_environment().owner_database_url).set(
                    database="postgres"
                ),
                isolation_level="AUTOCOMMIT",
                poolclass=NullPool,
                connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
            )
            try:
                with engine.connect() as c:
                    for receipt in receipts:
                        name = receipt["databaseName"]
                        assert (
                            name.startswith("game_predictor_t0995a_")
                            and receipt["databaseCreatedHere"]
                        )
                        roles = [
                            receipt[k]["name"]
                            for k in ("capabilityRole", "runtimeRole")
                            if receipt.get(k) and receipt[k]["createdHere"]
                        ]
                        row = {
                            "database": name,
                            "databaseOid": receipt["databaseOid"],
                            "databaseRemaining": c.scalar(
                                text("SELECT count(*) FROM pg_database WHERE datname=:n"),
                                {"n": name},
                            ),
                            "rolesRemaining": c.scalar(
                                text(
                                    "SELECT count(*) FROM pg_roles WHERE rolname=ANY(CA"
                                    "ST(:r AS text[]))"
                                ),
                                {"r": roles},
                            ),
                            "pids": list(
                                c.scalars(
                                    text("SELECT pid FROM pg_stat_activity WHERE datname=:n"),
                                    {"n": name},
                                )
                            ),
                        }
                        result.append(row)
                        assert (
                            row["databaseRemaining"] == row["rolesRemaining"] == 0
                            and not row["pids"]
                        )
            finally:
                engine.dispose()
        (evidence / "cleanup.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
