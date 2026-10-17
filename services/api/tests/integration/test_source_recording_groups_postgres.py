"""Real nonowner privilege, alias, restart and retained protection regressions."""

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.source_recording_groups import SourceRecordingGroupsService
from game_predictor_api.domain.source_recording_groups import RecordingError, recording_sha256
from game_predictor_api.schemas.source_recording_groups import SourceRecordingCommandRequest
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_storage_routing import GameStorageRoutingError
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.source_recording_groups import SqlAlchemySourceRecordingRepository
from game_predictor_api.storage.source_recording_permissions import recording_permission_errors
from game_predictor_api.storage.source_recording_providers import (
    TrustedRecordingProviders,
    install_recording_provider,
)
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from test_virtual_deferred_resolution_postgres import _factory, _seed


def seed_source(*args, **kwargs):
    import hashlib

    # Real imports can use different pipeline pins for identical input bytes.
    # The shared helper otherwise fixes one global source/pipeline unique key.
    with patch(
        "test_virtual_deferred_resolution_postgres._PIPELINE",
        hashlib.sha256(kwargs["label"].encode()).hexdigest(),
    ):
        return _seed(*args, **kwargs)


pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit owned disposable PostgreSQL only",
)


def _write_cleanup_evidence(outcome):
    """Keep evidence inside an explicit absolute owned artifact root.

    Teardown evidence I/O must never replace the original test failure. Cleanup
    assertions remain independent and still fail if database resources survive.
    """
    repository = Path(__file__).resolve().parents[4]
    artifact_root = repository / "artifacts"
    configured = os.environ.get(
        "GAME_PREDICTOR_RECORDING_TEST_EVIDENCE_ROOT",
        str(artifact_root / "audits" / "TASK-1002_R2_FIX"),
    )
    try:
        root = Path(configured)
        if (
            not root.is_absolute()
            or ".." in root.parts
            or not root.is_relative_to(artifact_root)
            or not root.resolve().is_relative_to(artifact_root.resolve())
        ):
            raise ValueError("Evidence root must be absolute and inside owned artifacts")
        current = root
        while current != artifact_root:
            if current.is_symlink() or current.is_junction():
                raise ValueError("Evidence root crosses a link")
            current = current.parent
        if artifact_root.is_symlink() or artifact_root.is_junction():
            raise ValueError("Owned artifact root crosses a link")
        root.mkdir(parents=True, exist_ok=True)
        destination = root / "TASK-1002_PG_CLEANUP.json"
        if destination == artifact_root / "audits" / "TASK-1002_PG_CLEANUP.json":
            raise ValueError("Original audit evidence is frozen")
        if destination.is_symlink():
            raise ValueError("Evidence file is a link")
        destination.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    except (OSError, ValueError) as error:
        message = f"Cleanup evidence not saved: {type(error).__name__}"
        try:
            warnings.warn(message, pytest.PytestWarning, stacklevel=2)
        except Warning:
            # A warnings-as-errors setting must not replace the test's failure.
            print(message, file=sys.stderr)


@pytest.fixture(scope="module")
def database():
    def sentinel(connection):
        connection.exec_driver_sql(
            "CREATE FUNCTION public.recording_custom() RETURNS integer LANGUAGE sql AS 'SELECT 7'"
        )
        connection.exec_driver_sql(
            """CREATE FUNCTION public.recording_command(text) RETURNS integer
            LANGUAGE sql AS 'SELECT 8'"""
        )

    retained = None
    try:
        with application_role_database("t1002", ("rec-a", "rec-b"), before_upgrade=sentinel) as db:
            retained = db
            with db.owner_engine.begin() as connection:
                connection.execute(
                    text(
                        """UPDATE public.games SET
                        shape_geometry_configuration='neural_grid_v3' WHERE
                        id=ANY(CAST(:ids AS uuid[]))"""
                    ),
                    {"ids": list(db.games.values())},
                )
            yield db
    finally:
        if retained:
            engine = create_engine(
                retained.owner_url.set(database="postgres"),
                poolclass=NullPool,
                connect_args={"connect_timeout": 5},
            )
            with engine.connect() as connection:
                name = retained.owner_url.database
                capability = retained.recording_capability
                outcome = {
                    "database": name,
                    "runtimeRole": retained.role,
                    "capabilityRole": capability.role,
                    "capabilityOid": capability.role_oid,
                    "databaseOid": capability.database_oid,
                    "databaseRemaining": connection.execute(
                        text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
                    ).scalar_one(),
                    "rolesRemaining": connection.execute(
                        text(
                            """SELECT count(*) FROM pg_roles WHERE
                            rolname=ANY(CAST(:roles AS text[]))"""
                        ),
                        {"roles": [retained.role, capability.role]},
                    ).scalar_one(),
                    "remainingPids": list(
                        connection.execute(
                            text("SELECT pid FROM pg_stat_activity WHERE datname=:name"),
                            {"name": name},
                        ).scalars()
                    ),
                }
            engine.dispose()
            _write_cleanup_evidence(outcome)
            assert (
                outcome["databaseRemaining"] == outcome["rolesRemaining"] == 0
                and outcome["remainingPids"] == []
            )


def execute(db, root, game, kind, providers=None, **values):
    command = SourceRecordingCommandRequest.model_validate(
        {"kind": kind, "idempotencyKey": str(uuid4()), **values}
    )
    with Session(db.app_engine) as session:
        result = SourceRecordingGroupsService(
            SqlAlchemySourceRecordingRepository(session), root, providers
        ).execute(game, command, "local-owner")
        session.commit()
        return result, command


def prepare_group(db, root, game, source_id):
    created, _ = execute(db, root, game, "prepare", selection={"sourceIds": [str(source_id)]})
    group = created["group"]
    attached, _ = execute(
        db,
        root,
        game,
        "attach",
        groupId=group["id"],
        manifestId=group["manifestId"],
        pageIndex=0,
        expectedRevision=group["revision"],
    )
    group = attached["group"]
    complete, _ = execute(
        db, root, game, "complete", groupId=group["id"], expectedRevision=group["revision"]
    )
    declared, _ = execute(
        db,
        root,
        game,
        "declare",
        groupId=group["id"],
        expectedRevision=complete["group"]["revision"],
        independenceConfirmed=True,
    )
    return declared["group"]


def test_actual_role_rls_reprovision_and_no_global_access(database, tmp_path):
    a, b = database.games.values()
    first = seed_source(_factory(database.owner_engine), a, tmp_path, label="rec-a", slot_count=1)
    second = seed_source(_factory(database.owner_engine), b, tmp_path, label="rec-b", slot_count=1)
    with Session(database.app_engine) as session:
        repo = SqlAlchemySourceRecordingRepository(session)
        assert repo.attest(a, [first.source_image_id])[0]["sourceId"] == str(first.source_image_id)
    with Session(database.app_engine) as session, pytest.raises(RecordingError, match="qualified"):
        SqlAlchemySourceRecordingRepository(session).attest(a, [second.source_image_id])
    with database.owner_engine.begin() as connection:
        provision_application_role(
            connection, ApplicationRoleSpec(database.role, database.app_url.password)
        )
        assert recording_permission_errors(connection, database.role) == ()
        for signature, _expected in (
            ("public.recording_custom()", 7),
            ("public.recording_command(text)", 8),
        ):
            row = connection.execute(
                text(
                    """SELECT p.proowner=(SELECT oid FROM pg_roles WHERE
                    rolname=:owner),has_function_privilege(:role,p.oid,'EXECUTE')
                    FROM pg_proc p WHERE p.oid=to_regprocedure(:signature)"""
                ),
                {"owner": database.owner_role, "role": database.role, "signature": signature},
            ).one()
            assert row == (True, True)
    with database.app_engine.begin() as connection:
        ordinary = uuid4()
        connection.execute(
            text("""INSERT INTO public.games
        (id,code,name,status,expected_layout_count)
        VALUES(:id,:code,'owned runtime CRUD','draft',10)"""),
            {"id": ordinary, "code": "owned-" + ordinary.hex[:12]},
        )
        assert (
            connection.execute(
                text("UPDATE public.games SET name='owned updated' WHERE id=:id"), {"id": ordinary}
            ).rowcount
            == 1
        )
        assert (
            connection.execute(
                text("DELETE FROM public.games WHERE id=:id"), {"id": ordinary}
            ).rowcount
            == 1
        )
    for query in (
        "SELECT * FROM public.recording_groups",
        "SELECT nextval('public.recording_evidence_ordinal_seq')",
        "SELECT public.recording_closure_v1('{}'::uuid[])",
        "SELECT public.recording_invalidate_dependents_v1(gen_random_uuid())",
    ):
        with database.app_engine.begin() as connection, pytest.raises(DBAPIError):
            connection.exec_driver_sql(query)
    with database.app_engine.begin() as connection:
        assert (
            connection.execute(
                text("SELECT name FROM public.games WHERE id=:id"), {"id": a}
            ).scalar_one()
            == "rec-a"
        )
    group = prepare_group(database, tmp_path, a, first.source_image_id)
    assert group["membershipComplete"] and group["declared"]
    assert group["qualification"] == "unresolved"
    assert "RECORDING_ROLE_REQUIRED" in group["reasonCodes"]


def test_cross_game_alias_role_and_fresh_process_replay(database, tmp_path):
    a, b = database.games.values()
    seed_a = seed_source(
        _factory(database.owner_engine),
        a,
        tmp_path,
        label="alias-aa",
        slot_count=1,
        sequence_base=300,
    )
    seed_b = seed_source(
        _factory(database.owner_engine),
        b,
        tmp_path,
        label="alias-bb",
        slot_count=1,
        sequence_base=300,
    )
    # Same length labels intentionally produce the same real JPEG bytes in the shared seed helper.
    group_a = prepare_group(database, tmp_path, a, seed_a.source_image_id)
    group_b = prepare_group(database, tmp_path, b, seed_b.source_image_id)
    with database.owner_engine.connect() as connection:
        family = connection.execute(
            text("SELECT id FROM public.grid_model_families ORDER BY id LIMIT 1")
        ).scalar_one()
    control, command = execute(
        database,
        tmp_path,
        a,
        "assign_role",
        groupId=group_a["id"],
        expectedRevision=group_a["revision"],
        familyId=str(family),
        role="VALIDATION",
    )
    assert control["statusCode"] == 200
    train, _ = execute(
        database,
        tmp_path,
        b,
        "assign_role",
        groupId=group_b["id"],
        expectedRevision=group_b["revision"],
        familyId=str(family),
        role="TRAIN",
    )
    assert train["statusCode"] == 409
    assert "RECORDING_PROTECTED" in train["group"]["reasonCodes"]
    serialized = json.dumps(train)
    assert group_a["id"] not in serialized and str(a) not in serialized
    script = """import json, sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from game_predictor_api.storage.source_recording_groups import SqlAlchemySourceRecordingRepository
from game_predictor_api.application.source_recording_groups import SourceRecordingGroupsService
from game_predictor_api.schemas.source_recording_groups import SourceRecordingCommandRequest
from pathlib import Path
from uuid import UUID
engine = create_engine(sys.argv[1])
with Session(engine) as session:
    result = SourceRecordingGroupsService(
        SqlAlchemySourceRecordingRepository(session), Path(sys.argv[2])
    ).execute(UUID(sys.argv[3]),SourceRecordingCommandRequest.model_validate_json(sys.argv[4]),
        'local-owner')
    print(json.dumps(result, sort_keys=True))
    session.commit()
engine.dispose()
"""
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(Path("services/api/src").resolve()), str(Path("services/worker/src").resolve()))
        ),
    }
    replay = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            database.app_url.render_as_string(hide_password=False),
            str(tmp_path),
            str(a),
            command.model_dump_json(by_alias=True),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
        env=environment,
    )
    assert json.loads(replay.stdout) == control


def test_membership_drift_and_missing_declaration_are_fail_closed(database, tmp_path):
    a = next(iter(database.games.values()))
    seed = seed_source(
        _factory(database.owner_engine),
        a,
        tmp_path,
        label="drift-unique",
        slot_count=1,
        sequence_base=600,
    )
    created, _ = execute(
        database, tmp_path, a, "prepare", selection={"sourceIds": [str(seed.source_image_id)]}
    )
    group = created["group"]
    with database.owner_engine.begin() as connection:
        connection.execute(
            text(
                """UPDATE game_data_v2.source_images SET checksum_sha256=:checksum
                WHERE game_id=:game AND id=:id"""
            ),
            {"checksum": "e" * 64, "game": a, "id": seed.source_image_id},
        )
    with pytest.raises(RecordingError):
        execute(
            database,
            tmp_path,
            a,
            "attach",
            groupId=group["id"],
            manifestId=group["manifestId"],
            pageIndex=0,
            expectedRevision=1,
        )
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM public.recording_occurrences WHERE group_id=:id"),
                {"id": group["id"]},
            ).scalar_one()
            == 0
        )


def base_and_providers(db, root, game, protected=(), *, install_proof=True):
    from game_predictor_api.storage.source_recording_lab_import import install_provider_proof

    with Session(db.app_engine) as session:
        registry = SqlAlchemyGridModelRegistryRepository(session)
        base = registry.versions()[0]
        lineage = registry.lineage(base.id)
        version, family = base.id, base.family_id
    index_sha = None
    for ancestor in lineage["ancestors"]:
        payload = {
            "schemaVersion": "recording-ancestor-provider-v1",
            "ancestor": ancestor,
            "complete": True,
            "recordingIdentityAvailable": True,
            "recordingGroups": list(protected),
        }
        source = root / "installed-provider-input.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(json.dumps(payload), encoding="utf-8")
        import hashlib

        if install_proof:
            with db.owner_engine.begin() as connection:
                install_provider_proof(connection, payload, recording_sha256(payload))
        index_sha = install_recording_provider(
            root, source, hashlib.sha256(source.read_bytes()).hexdigest(), index_sha
        )
    return version, family, TrustedRecordingProviders(root, index_sha)


def event(db, kind, groups, payload, *, dependencies=(), proof=None):
    identifier = uuid4()
    with db.owner_engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO public.recording_evidence
        (id,kind,group_ids,dependency_group_ids,payload,payload_sha256,proof_sha256,actor)
        VALUES(:id,:kind,CAST(:groups AS uuid[]),CAST(:deps AS uuid[]),
        CAST(:payload AS jsonb),:sha,:proof,'server:owned-fixture')"""),
            {
                "id": identifier,
                "kind": kind,
                "groups": [UUID(str(g)) for g in groups],
                "deps": list(dependencies),
                "payload": json.dumps(payload),
                "sha": recording_sha256(payload),
                "proof": proof,
            },
        )
    return identifier


def test_provisional_freeze_unrelated_change_and_dependent_invalidation(database, tmp_path):
    game = next(iter(database.games.values()))
    seed = seed_source(
        _factory(database.owner_engine),
        game,
        tmp_path,
        label="provisional-recording-unique",
        slot_count=1,
        sequence_base=900,
    )
    group = prepare_group(database, tmp_path, game, seed.source_image_id)
    version, family, providers = base_and_providers(database, tmp_path, game)
    role, _ = execute(
        database,
        tmp_path,
        game,
        "assign_role",
        groupId=group["id"],
        expectedRevision=group["revision"],
        familyId=str(family),
        role="VALIDATION",
    )
    _, _, untrusted = base_and_providers(
        database,
        tmp_path / "uninstalled-proof",
        game,
        [{"groupId": group["id"], "role": "VALIDATION"}],
        install_proof=False,
    )
    refused, _ = execute(
        database,
        tmp_path,
        game,
        "freeze",
        providers=untrusted,
        groupId=group["id"],
        expectedRevision=role["group"]["revision"],
        familyId=str(family),
        baseVersionId=str(version),
    )
    assert refused["reasonCode"] == "RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED"
    frozen, _ = execute(
        database,
        tmp_path,
        game,
        "freeze",
        providers=providers,
        groupId=group["id"],
        expectedRevision=role["group"]["revision"],
        familyId=str(family),
        baseVersionId=str(version),
    )
    assert frozen["statusCode"] == 200
    resolution_id = frozen["resolutionId"]
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    """SELECT count(*) FROM public.recording_evidence WHERE kind IN
                    ('use','holdout','ancestor') AND group_ids @> CAST(:ids AS
                    uuid[])"""
                ),
                {"ids": [UUID(group["id"])]},
            ).scalar_one()
            == 0
        )
    unrelated = seed_source(
        _factory(database.owner_engine),
        game,
        tmp_path,
        label="unrelated-longer-recording-unique",
        slot_count=1,
        sequence_base=1100,
    )
    unrelated_group = prepare_group(database, tmp_path, game, unrelated.source_image_id)
    with Session(database.app_engine) as session:
        view = SqlAlchemySourceRecordingRepository(session).list_groups(
            game, family, 1, None, [UUID(group["id"])]
        )["items"][0]
        assert view["resolutionId"] == resolution_id
    # Simulate only the future producer's durable binding, not a quality PASS.
    report = uuid4()
    with database.owner_engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO
                public.grid_model_evaluation_reports(id,version_id,producer,report_json,report_sha256)
                VALUES(:id,:version,'owned-future-producer-fixture','{}',:sha)"""
            ),
            {"id": report, "version": version, "sha": recording_sha256({})},
        )
    event(
        database,
        "use",
        [group["id"]],
        {"role": "VALIDATION", "resolutionId": resolution_id, "reportId": str(report)},
    )
    with Session(database.app_engine) as session:
        view = SqlAlchemySourceRecordingRepository(session).list_groups(
            game, family, 1, None, [UUID(group["id"])]
        )["items"][0]
        assert view["resolutionId"] == resolution_id
    # A failed catalog invalidation must roll back the complete private command.
    with database.owner_engine.begin() as connection:
        connection.exec_driver_sql("""CREATE FUNCTION public.t1002_reject_invalidation()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'owned-invalidation-failure'; END $$""")
        connection.exec_driver_sql("""CREATE TRIGGER t1002_reject BEFORE INSERT ON
        public.grid_model_evaluation_invalidations FOR EACH ROW
        EXECUTE FUNCTION public.t1002_reject_invalidation()""")
    try:
        with pytest.raises(DBAPIError, match="owned-invalidation-failure"):
            execute(
                database,
                tmp_path,
                game,
                "alias",
                groupId=group["id"],
                otherGroupId=unrelated_group["id"],
                expectedRevision=role["group"]["revision"],
            )
        with database.owner_engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        """SELECT count(*) FROM public.recording_evidence WHERE
                        kind='alias' AND group_ids @> CAST(:ids AS uuid[])"""
                    ),
                    {"ids": [UUID(group["id"])]},
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text(
                        """SELECT count(*) FROM
                        public.grid_model_evaluation_invalidations WHERE
                        report_id=:id"""
                    ),
                    {"id": report},
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT revision FROM public.recording_groups WHERE id=:id"),
                    {"id": group["id"]},
                ).scalar_one()
                == role["group"]["revision"]
            )
    finally:
        with database.owner_engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER t1002_reject ON public.grid_model_evaluation_invalidations"
            )
            connection.exec_driver_sql("DROP FUNCTION public.t1002_reject_invalidation()")
    aliased, _ = execute(
        database,
        tmp_path,
        game,
        "alias",
        groupId=group["id"],
        otherGroupId=unrelated_group["id"],
        expectedRevision=role["group"]["revision"],
    )
    assert aliased["statusCode"] == 200
    retracted, _ = execute(
        database,
        tmp_path,
        game,
        "retract",
        groupId=group["id"],
        expectedRevision=aliased["group"]["revision"],
    )
    assert retracted["statusCode"] == 200
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    """SELECT count(*) FROM
                    public.grid_model_evaluation_invalidations WHERE report_id=:id"""
                ),
                {"id": report},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    """SELECT count(*) FROM public.recording_evidence WHERE
                    kind='use' AND payload->>'reportId'=:id"""
                ),
                {"id": str(report)},
            ).scalar_one()
            == 1
        )
    blocked, _ = execute(
        database,
        tmp_path,
        game,
        "assign_role",
        groupId=group["id"],
        expectedRevision=retracted["group"]["revision"],
        familyId=str(family),
        role="TRAIN",
    )
    assert blocked["reasonCode"] == "RECORDING_PROTECTED"


def test_inherited_holdout_and_unknown_mapping_never_train(database, tmp_path):
    a, b = database.games.values()
    seed_a = seed_source(
        _factory(database.owner_engine),
        a,
        tmp_path,
        label="ancestor-control-aaaaaaaaaa",
        slot_count=1,
        sequence_base=1400,
    )
    seed_b = seed_source(
        _factory(database.owner_engine),
        b,
        tmp_path,
        label="ancestor-control-bbbbbbbbbb",
        slot_count=1,
        sequence_base=1400,
    )
    protected = prepare_group(database, tmp_path, a, seed_a.source_image_id)
    child = prepare_group(database, tmp_path, b, seed_b.source_image_id)
    with Session(database.app_engine) as session:
        base = SqlAlchemyGridModelRegistryRepository(session).versions()[0]
        version, family = base.id, base.family_id
    role, _ = execute(
        database,
        tmp_path,
        b,
        "assign_role",
        groupId=child["id"],
        expectedRevision=child["revision"],
        familyId=str(family),
        role="TRAIN",
    )
    _, _, providers = base_and_providers(
        database, tmp_path, b, [{"groupId": protected["id"], "role": "final_test"}]
    )
    frozen, _ = execute(
        database,
        tmp_path,
        b,
        "freeze",
        providers=providers,
        groupId=child["id"],
        expectedRevision=role["group"]["revision"],
        familyId=str(family),
        baseVersionId=str(version),
    )
    assert frozen["reasonCode"] == "RECORDING_PROTECTED"
    assert protected["id"] not in json.dumps(frozen) and str(a) not in json.dumps(frozen)
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    """SELECT count(*) FROM public.recording_evidence WHERE
                    kind='ancestor' AND group_ids=CAST(:ids AS uuid[]) AND
                    payload->>'role'='final_test'"""
                ),
                {"ids": [UUID(protected["id"])]},
            ).scalar_one()
            == 1
        )
    _, _, unknown = base_and_providers(
        database,
        tmp_path / "unknown",
        b,
        [{"groupId": str(uuid4()), "role": "Reels"}],
        install_proof=False,
    )
    result, _ = execute(
        database,
        tmp_path / "unknown",
        b,
        "freeze",
        providers=unknown,
        groupId=child["id"],
        expectedRevision=role["group"]["revision"],
        familyId=str(family),
        baseVersionId=str(version),
    )
    assert result["reasonCode"] == "RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED"


def test_between_attestation_and_commit_drift_rolls_back_and_receipt_cas(database, tmp_path):
    game = next(iter(database.games.values()))
    seed = seed_source(
        _factory(database.owner_engine),
        game,
        tmp_path,
        label="between-check-and-write-source-drift",
        slot_count=1,
        sequence_base=1700,
    )
    created, _ = execute(
        database, tmp_path, game, "prepare", selection={"sourceIds": [str(seed.source_image_id)]}
    )
    group = created["group"]
    command = SourceRecordingCommandRequest.model_validate(
        {
            "kind": "attach",
            "idempotencyKey": str(uuid4()),
            "groupId": group["id"],
            "manifestId": group["manifestId"],
            "pageIndex": 0,
            "expectedRevision": 1,
        }
    )
    with Session(database.app_engine) as session:
        repo = SqlAlchemySourceRecordingRepository(session)
        original = repo.command

        def drift_then_commit(wanted, envelope, actor):
            if not envelope.get("lookup"):
                with database.owner_engine.begin() as connection:
                    connection.execute(
                        text(
                            """UPDATE game_data_v2.source_images SET
                            normalized_pixel_checksum_sha256=:pixel WHERE
                            game_id=:game AND id=:id"""
                        ),
                        {"pixel": "f" * 64, "game": game, "id": seed.source_image_id},
                    )
                    connection.execute(
                        text(
                            """UPDATE game_data_v2.image_source_geometry_revisions
                            SET normalized_pixel_checksum_sha256=:pixel WHERE
                            game_id=:game AND source_image_id=:id"""
                        ),
                        {"pixel": "f" * 64, "game": game, "id": seed.source_image_id},
                    )
            return original(wanted, envelope, actor)

        repo.command = drift_then_commit
        with pytest.raises(RecordingError) as failure:
            SourceRecordingGroupsService(repo, tmp_path).execute(game, command, "local-owner")
        assert failure.value.code == "RECORDING_SOURCE_IDENTITY_DRIFT"
        session.rollback()
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM public.recording_occurrences WHERE group_id=:id"),
                {"id": group["id"]},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM public.recording_commands WHERE idempotency_key=:id"),
                {"id": command.idempotency_key},
            ).scalar_one()
            == 0
        )


def test_lab_photo_protection_resolves_only_with_real_recording_mapping(database, tmp_path):
    from game_predictor_api.domain.source_recording_groups import resolve_ancestor_references
    from game_predictor_api.storage.source_recording_lab_import import (
        finalize_lab_import,
        import_lab_page,
        lab_group_id,
        lab_photo_group_id,
        read_lab_import_manifest,
    )

    game = next(iter(database.games.values()))
    seed = seed_source(
        _factory(database.owner_engine),
        game,
        tmp_path,
        label="lab-real-owned-source-identity",
        slot_count=1,
        sequence_base=2100,
    )
    own = prepare_group(database, tmp_path, game, seed.source_image_id)
    with Session(database.app_engine) as session:
        repo = SqlAlchemySourceRecordingRepository(session)
        attested = repo.attest(game, [seed.source_image_id])[0]
        registry = SqlAlchemyGridModelRegistryRepository(session)
        base = registry.versions()[0]
        lineage = registry.lineage(base.id)
    identity, source_ref, recording_ref = (
        recording_sha256(value)
        for value in ("owned-lab-provider", "owned-lab-photo", "owned-lab-whole-film")
    )
    photo_id, film_id = (
        lab_photo_group_id(identity, source_ref),
        lab_group_id(identity, recording_ref),
    )

    def manifest_for(directory, *, mapped):
        directory.mkdir(parents=True)

        def pin(name, value):
            path = directory / name
            path.write_text(json.dumps(value), encoding="utf-8")
            import hashlib

            return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

        provider = {
            "schemaVersion": "recording-ancestor-provider-v1",
            "ancestor": lineage["ancestors"][0],
            "complete": mapped,
            "recordingIdentityAvailable": mapped,
            "recordingGroups": [{"groupId": str(film_id if mapped else photo_id), "role": "Reels"}],
        }
        payload = {
            "schemaVersion": "recording-lab-import-v1",
            "providerIdentitySha256": identity,
            "provider": pin("provider.json", provider),
            "descriptor": pin("descriptor.json", {"schemaVersion": "owned-descriptor-fixture-v1"}),
            "split": pin("split.json", {"schemaVersion": "owned-split-fixture-v1"}),
            "groups": [
                {
                    "recordingRefSha256": recording_ref,
                    "expectedSources": 1,
                    "role": "Reels",
                    "independenceConfirmed": True,
                }
            ]
            if mapped
            else [],
            "pages": [
                pin(
                    "page.json",
                    {
                        "schemaVersion": "recording-lab-import-page-v1",
                        "sources": [
                            {
                                "sourceRefSha256": source_ref,
                                "recordingRefSha256": recording_ref if mapped else None,
                                "byteSha256": attested["byteSha256"],
                                "pixelSha256": attested["pixelSha256"],
                                "pixelAlgorithm": attested["pixelAlgorithm"],
                                "width": attested["width"],
                                "height": attested["height"],
                            }
                        ],
                    },
                )
            ],
        }
        frozen = pin("manifest.json", payload)
        return read_lab_import_manifest(directory / frozen["path"], frozen["sha256"])

    partial = manifest_for(tmp_path / "photo-only", mapped=False)
    page_key, final_key = uuid4(), uuid4()
    with database.app_engine.begin() as connection, pytest.raises(RecordingError) as denied:
        import_lab_page(connection, partial, 0, page_key)
    assert denied.value.code == "RECORDING_DEPLOYMENT_OWNER_REQUIRED"
    with database.owner_engine.begin() as connection:
        page_receipt = import_lab_page(connection, partial, 0, page_key)
    with database.owner_engine.begin() as connection:
        assert import_lab_page(connection, partial, 0, page_key) == page_receipt
        finalize_lab_import(connection, partial, final_key)
    assert not resolve_ancestor_references(lineage, {str(base.id): partial.provider}).complete
    refused, _ = execute(
        database,
        tmp_path,
        game,
        "assign_role",
        groupId=own["id"],
        expectedRevision=own["revision"],
        familyId=str(base.family_id),
        role="TRAIN",
    )
    assert refused["reasonCode"] == "RECORDING_PROTECTED"
    assert str(photo_id) not in json.dumps(refused)
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT membership_complete FROM public.recording_groups WHERE id=:id"),
                {"id": photo_id},
            ).scalar_one()
            is False
        )
    mapped = manifest_for(tmp_path / "whole-film", mapped=True)
    with database.owner_engine.begin() as connection:
        import_lab_page(connection, mapped, 0, uuid4())
    final_key = uuid5(NAMESPACE_URL, f"recording-lab:{mapped.manifest_sha256}:finalize")
    with database.owner_engine.begin() as connection:
        complete = finalize_lab_import(connection, mapped, final_key)
        before = connection.execute(
            text("SELECT count(*) FROM public.recording_evidence")
        ).scalar_one()
    # DB complete / index absent: the exact retry produces no second proof/use.
    with database.owner_engine.begin() as connection:
        assert finalize_lab_import(connection, mapped, final_key) == complete
        assert (
            connection.execute(text("SELECT count(*) FROM public.recording_evidence")).scalar_one()
            == before
        )
    # The first insert of a page must disappear when a later source conflicts.
    invalid = manifest_for(tmp_path / "conflicting-page", mapped=True)
    page_path = invalid.pages[0].path
    page = json.loads(page_path.read_bytes())
    conflicting = page["sources"][0]
    added = {**conflicting, "sourceRefSha256": recording_sha256("rollback-only-source")}
    conflicting["pixelSha256"] = "d" * 64
    page["sources"] = [added, conflicting]
    page_path.write_text(json.dumps(page), encoding="utf-8")
    import hashlib

    manifest_path = page_path.parent / "manifest.json"
    payload = json.loads(manifest_path.read_bytes())
    payload["pages"][0]["sha256"] = hashlib.sha256(page_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    invalid = read_lab_import_manifest(
        manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    with (
        pytest.raises(RecordingError, match="identity changed"),
        database.owner_engine.begin() as connection,
    ):
        import_lab_page(connection, invalid, 0, uuid4())
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(
                text("""SELECT count(*) FROM public.recording_occurrences
        WHERE origin='LAB_DESCRIPTOR' AND external_ref_sha256=:ref"""),
                {"ref": added["sourceRefSha256"]},
            ).scalar_one()
            == 0
        )
    # A genuinely new process resumes the identical trusted deployment receipt
    # and publishes the previously absent index, using only this owned database.
    deployed = subprocess.run(
        [
            sys.executable,
            "scripts/import_recording_lab_provider.py",
            "--finalize-only",
            "--manifest",
            str(mapped.provider_pin.path.parent / "manifest.json"),
            "--sha256",
            mapped.manifest_sha256,
            "--artifact-root",
            str(tmp_path),
        ],
        env={
            **os.environ,
            "GAME_PREDICTOR_DATABASE_URL": database.app_url.render_as_string(hide_password=False),
            "GAME_PREDICTOR_OWNER_DATABASE_URL": database.owner_url.render_as_string(
                hide_password=False
            ),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    index_sha = next(
        line.split("=", 1)[1]
        for line in deployed.stdout.splitlines()
        if line.startswith("GAME_PREDICTOR_RECORDING_PROVIDER_INDEX_SHA256=")
    )
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM public.recording_evidence")).scalar_one()
            == before
        )
    providers = TrustedRecordingProviders(tmp_path, index_sha)
    assert resolve_ancestor_references(lineage, providers.read(lineage)).complete
    with database.owner_engine.connect() as connection:
        assert connection.execute(
            text(
                """SELECT bool_and(membership_complete AND declared AND independent)
                FROM public.recording_groups WHERE id=ANY(CAST(:ids AS uuid[]))"""
            ),
            {"ids": [photo_id, film_id]},
        ).scalar_one()
        assert (
            connection.execute(
                text(
                    """SELECT count(*) FROM public.recording_evidence WHERE
                    kind='holdout' AND group_ids=ARRAY[CAST(:id AS uuid)]"""
                ),
                {"id": photo_id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    """SELECT count(*) FROM public.recording_groups WHERE
                    origin='LAB_DESCRIPTOR' AND game_id IS NOT NULL"""
                )
            ).scalar_one()
            == 0
        )
    declared, _ = execute(
        database,
        tmp_path,
        game,
        "assign_role",
        groupId=own["id"],
        expectedRevision=own["revision"],
        familyId=str(base.family_id),
        role="VALIDATION",
    )
    frozen, _ = execute(
        database,
        tmp_path,
        game,
        "freeze",
        providers=providers,
        groupId=own["id"],
        expectedRevision=declared["group"]["revision"],
        familyId=str(base.family_id),
        baseVersionId=str(base.id),
    )
    assert frozen["statusCode"] == 200
    assert str(film_id) not in json.dumps(frozen) and str(photo_id) not in json.dumps(frozen)


def test_source_game_delete_retains_minimal_protection(database):
    from game_predictor_api.storage.game_partition_lifecycle import (
        GamePartitionLifecycleKind,
        GamePartitionLifecycleRepository,
    )

    game = list(database.games.values())[-1]
    with database.owner_engine.connect() as connection:
        ids = list(
            connection.execute(
                text("SELECT id FROM public.recording_groups WHERE game_id=:game"), {"game": game}
            ).scalars()
        )
        assert ids
        before = connection.execute(
            text("SELECT count(*) FROM public.recording_occurrences WHERE game_id=:game"),
            {"game": game},
        ).scalar_one()
    with Session(database.owner_engine) as session:
        receipt = GamePartitionLifecycleRepository(session).start_or_resume(
            game_id=game, kind=GamePartitionLifecycleKind.DELETE
        )
        session.commit()
        for _ in range(100):
            receipt = GamePartitionLifecycleRepository(session).run_next(receipt.operation_id)
            session.commit()
            if receipt.status == "done":
                break
        assert receipt.status == "done"
    with database.owner_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM public.games WHERE id=:game"), {"game": game}
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM public.recording_occurrences WHERE game_id=:game"),
                {"game": game},
            ).scalar_one()
            == before
        )
        assert connection.execute(
            text("SELECT count(*) FROM public.recording_groups WHERE id=ANY(CAST(:ids AS uuid[]))"),
            {"ids": ids},
        ).scalar_one() == len(ids)
    with Session(database.app_engine) as session, pytest.raises(GameStorageRoutingError):
        SqlAlchemySourceRecordingRepository(session).list_groups(game, None, 10, None)
