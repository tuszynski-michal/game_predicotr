"""Only disposable PostgreSQL databases; no operator migration or model execution."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from alembic.config import Config
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    historical_catalogue,
)
from game_predictor_api.domain.image_import_engine_policy import (
    DEFAULT_CELL_ASSET_MODE,
    DEFAULT_GEOMETRY_MODE,
)
from game_predictor_api.storage.database import assign_session_game
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_data_v2_manifest_v8 import GAME_TABLES as V8_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v9 import GAME_TABLES as V9_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v9 import ownership
from game_predictor_api.storage.game_partition_lifecycle import (
    DELETE_TABLES as CURRENT_DELETE_TABLES,
)
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from services.api.tests.test_grid_model_registry import candidate

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


@pytest.fixture
def database() -> Iterator[tuple]:
    token = uuid4().hex[:12]
    name, role = f"game_predictor_task0994_{token}_test", f"task0994_{token}"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    engine = create_engine(
        url.set(database=name),
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    receipt = {"database": name, "role": role, "phase": "created", "operatorDatabaseChanged": False}
    destination = Path("artifacts/audits/TASK-0998_REGISTRY_REGRESSION_PG_RECEIPT.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    owned = OwnedRecordingCapability.for_engine(engine)
    with maintenance.connect() as connection:
        receipt["owner"] = connection.scalar(text("SELECT current_user"))
        receipt["maintenancePid"] = connection.scalar(text("SELECT pg_backend_pid()"))
        owned.create_database(connection)
    destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    try:
        yield engine, config, role, receipt
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            owner = connection.scalar(
                text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=:name"),
                {"name": name},
            )
            pids = list(
                connection.scalars(
                    text("SELECT pid FROM pg_stat_activity WHERE datname=:name"), {"name": name}
                )
            )
            receipt.update(ownerBeforeCleanup=owner, pidsBeforeCleanup=pids)
            assert owner == receipt["owner"] and not pids, (
                "Refuse cleanup with wrong owner or remaining sessions"
            )
            owned.drop_database(connection)
            receipt["databaseRemaining"] = connection.scalar(
                text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
            )
            receipt["roleRemaining"] = connection.scalar(
                text("SELECT count(*) FROM pg_roles WHERE rolname=:role"), {"role": role}
            )
            receipt["phase"] = "cleaned"
        destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        maintenance.dispose()


def definition_sha256(connection) -> str:
    queries = (
        """SELECT c.relname,c.relkind,c.relispartition,c.relrowsecurity,c.relforcerowsecurity,
            pg_get_partkeydef(c.oid),pg_get_expr(c.relpartbound,c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='game_data_v2' ORDER BY c.relname""",
        """SELECT c.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),
            a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid)
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname='game_data_v2' AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY c.relname,a.attnum""",
        """SELECT c.relname,k.conname,pg_get_constraintdef(k.oid,true)
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='game_data_v2' ORDER BY c.relname,k.conname""",
        """SELECT tablename,indexname,indexdef FROM pg_indexes
            WHERE schemaname='game_data_v2' ORDER BY tablename,indexname""",
        """SELECT tablename,policyname,permissive,roles::text,cmd,qual,with_check
            FROM pg_policies WHERE schemaname='game_data_v2' ORDER BY tablename,policyname""",
    )
    snapshot = [[tuple(row) for row in connection.execute(text(query))] for query in queries]
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()


def test_upgrade_keeps_games_partitions_and_pins_historical_models(database, tmp_path):
    engine, config, role, receipt = database
    command.upgrade(config, "0155_historical_grid_acceptance")
    codes = {
        "7": "grid_profile_777_v2",
        "777a2": "grid_profile_777_v2",
        "mumie": "grid_profile_mumie_v1",
        "legacy": None,
        "framed": "framed_full_page_v2",
        "unclear": "requires_clarification",
    }
    games = {code: uuid4() for code in codes}
    with engine.begin() as connection:
        for code, configuration in codes.items():
            connection.execute(
                text(
                    "INSERT INTO "
                    "public.games(id,code,name,status,shape_geometry_configuration) "
                    "VALUES(:id,:code,:code,'draft',:configuration)"
                ),
                {"id": games[code], "code": code, "configuration": configuration},
            )
        # Representative existing v8 registry, without creating new game partitions.
        connection.execute(
            text(
                "INSERT INTO "
                "public.game_storage_locations(game_id,store_schema,generation,status,manifest_version)"
                " VALUES(:id,'game_data_v2',2,'active','game-data-v2-manifest-v8')"
            ),
            {"id": games["777a2"]},
        )
        connection.exec_driver_sql(
            "CREATE TABLE game_data_v2.task0994_rollout PARTITION OF "
            f"game_data_v2.image_geometry_rollout_states FOR VALUES IN ('{games['777a2']}')"
        )
        connection.execute(
            text(
                "INSERT INTO "
                "game_data_v2.image_geometry_rollout_states(game_id,geometry_mode,cell_asset_mode,revision,backfill_status,updated_by)"
                " VALUES(:id,:geometry,:asset,0,'not_started','task0994-fixture')"
            ),
            {
                "id": games["777a2"],
                "geometry": DEFAULT_GEOMETRY_MODE,
                "asset": DEFAULT_CELL_ASSET_MODE,
            },
        )
        definitions_before = definition_sha256(connection)
        row_before = connection.execute(
            text("SELECT * FROM game_data_v2.image_geometry_rollout_states")
        ).all()
        before = connection.execute(
            text(
                "SELECT c.oid,c.relname,pg_get_partkeydef(c.oid),c.relkind FROM "
                "pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
                "n.nspname='game_data_v2' ORDER BY c.oid"
            )
        ).all()
    command.upgrade(config, "0156_grid_model_registry")
    with engine.begin() as connection:
        after = connection.execute(
            text(
                "SELECT c.oid,c.relname,pg_get_partkeydef(c.oid),c.relkind FROM "
                "pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
                "n.nspname='game_data_v2' ORDER BY c.oid"
            )
        ).all()
        assert before == after
        definitions_after = definition_sha256(connection)
        assert definitions_before == definitions_after
        receipt["gameDataDefinitionsBeforeSha256"] = definitions_before
        receipt["gameDataDefinitionsAfterSha256"] = definitions_after
        assert (
            row_before
            == connection.execute(
                text("SELECT * FROM game_data_v2.image_geometry_rollout_states")
            ).all()
        )
        assert (
            dict(
                connection.execute(
                    text("SELECT code,shape_geometry_configuration FROM public.games")
                ).all()
            )
            == codes
        )
        assert (
            connection.scalar(text("SELECT manifest_version FROM public.game_storage_locations"))
            == "game-data-v2-manifest-v9"
        )
        assert len(list(connection.execute(text("SELECT * FROM public.grid_model_versions")))) == 2
        mappings = dict(
            connection.execute(
                text(
                    "SELECT g.code,a.version_id FROM public.game_grid_model_assignments"
                    " a JOIN public.games g ON g.id=a.game_id"
                )
            ).all()
        )
        assert mappings == {
            "777a2": UUID(historical_catalogue()[0]["versionId"]),
            "mumie": UUID(historical_catalogue()[1]["versionId"]),
        }
        assert V8_TABLES == V9_TABLES
        assert ownership("grid_model_versions") == "shared"
        assert ownership("game_grid_model_assignments") == "catalog"
        connection.execute(
            text(
                "INSERT INTO "
                "public.games(id,code,name,status,shape_geometry_configuration) "
                "VALUES(:id,'neutral','neutral','draft','neural_grid_v3')"
            ),
            {"id": uuid4()},
        )
        connection.execute(
            text(
                "INSERT INTO "
                "public.game_storage_locations(game_id,store_schema,generation,status,manifest_version)"
                " VALUES(:id,'game_data_v2',2,'active','game-data-v2-manifest-v9')"
            ),
            {"id": games["mumie"]},
        )
        OwnedRecordingCapability.for_engine(engine).create_runtime_role(connection, role)
        provision_application_role(
            connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
        )
    # Runtime controls require the current head; the frozen0156 assertions above remain.
    command.upgrade(config, "0157_grid_model_publication")
    with pytest.raises(RuntimeError, match="GRID_MODEL_PUBLICATION_DOWNGRADE_REFUSED"):
        command.downgrade(config, "0156_grid_model_registry")
    OwnedRecordingCapability.for_engine(engine).provision()
    command.upgrade(config, "head")
    with engine.begin() as connection:
        provision_application_role(
            connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
        )
    factory = sessionmaker(engine)

    def assume_role(session, transaction, connection):
        connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')

    event.listen(factory, "after_begin", assume_role)
    with factory() as session:
        flags = session.execute(
            text("SELECT rolname,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
        ).one()
        assert flags == (role, False, False)
        service = GridModelRegistryService(
            SqlAlchemyGridModelRegistryRepository(session), GridModelArtifactInspector(tmp_path)
        )
        mumie = service.game_assignment(games["mumie"])
        assert mumie["version"]["manifest"]["familyCode"] == "grid_profile_mumie_v1"
        assert mumie["eventCount"] == 1 and mumie["version"]["available"] is False
        assert service.game_assignment(games["7"])["version"] is None
        assign_session_game(session, games["mumie"])
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_GAME_SCOPE_CONFLICT"):
            service.game_assignment(games["777a2"])
    payload = candidate(tmp_path / "candidate")
    key = uuid4()
    with factory() as session:
        service = GridModelRegistryService(
            SqlAlchemyGridModelRegistryRepository(session),
            GridModelArtifactInspector(tmp_path / "candidate"),
        )
        first = service.register(key, payload)
        session.commit()
    with factory() as session:
        service = GridModelRegistryService(
            SqlAlchemyGridModelRegistryRepository(session),
            GridModelArtifactInspector(tmp_path / "candidate"),
        )
        assert service.register(key, payload) == first
        assert service.register(uuid4(), payload) == first
        session.commit()
        changed = copy.deepcopy(payload)
        changed["familyLabel"] = "Conflicting label"
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_IDEMPOTENCY_CONFLICT"):
            service.register(key, changed)
        session.rollback()
    failed = candidate(tmp_path / "rollback")
    failed["familyCode"] = "fourth_geometry"

    def fail_receipt(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO public.grid_model_registration_receipts"):
            raise RuntimeError("injected PG receipt failure")

    event.listen(engine, "before_cursor_execute", fail_receipt)
    try:
        with factory() as session:
            service = GridModelRegistryService(
                SqlAlchemyGridModelRegistryRepository(session),
                GridModelArtifactInspector(tmp_path / "rollback"),
            )
            with pytest.raises(RuntimeError, match="injected PG receipt failure"):
                service.register(uuid4(), failed)
            session.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", fail_receipt)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.grid_model_families")) == 3
        assert connection.scalar(text("SELECT count(*) FROM public.grid_model_versions")) == 3
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.grid_model_version_events WHERE kind='registered'"
                )
            )
            == 1
        )
    for sql in (
        "UPDATE public.grid_model_versions SET version='tampered'",
        "DELETE FROM public.grid_model_versions",
        "DELETE FROM public.game_grid_model_assignment_events WHERE game_id=:id",
    ):
        with pytest.raises(DBAPIError, match="GRID_MODEL_IMMUTABLE"), engine.begin() as connection:
            connection.execute(text(sql), {"id": games["mumie"]})
    # Deletion compatibility: run the existing lifecycle for an empty game. Its catalogue
    # assignment/events cascade; other game and shared immutable model history survive.
    with Session(engine) as session:
        repository = GamePartitionLifecycleRepository(session)
        delete = repository.start_or_resume(
            game_id=games["mumie"], kind=GamePartitionLifecycleKind.DELETE
        )
        session.commit()
        for _ in range(len(CURRENT_DELETE_TABLES) + 1):
            delete = repository.run_next(delete.operation_id)
            session.commit()
            if delete.status == "done":
                break
        assert delete.status == "done"
    with engine.begin() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM public.games WHERE id=:id"), {"id": games["mumie"]}
            )
            == 0
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM public.game_grid_model_assignments")) == 1
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM public.game_grid_model_assignment_events"))
            == 1
        )
        assert connection.scalar(text("SELECT count(*) FROM public.grid_model_versions")) == 3
        assert (
            row_before
            == connection.execute(
                text("SELECT * FROM game_data_v2.image_geometry_rollout_states")
            ).all()
        )
    receipt["verified"] = [
        "0155_to_0156",
        "v8_partition_definitions_unchanged",
        "all_game_data_columns_constraints_indexes_RLS_definitions_unchanged",
        "all_old_formats_unchanged",
        "neutral_additive",
        "both_static_assignments",
        "old7_unassigned",
        "NOBYPASSRLS_role",
        "explicit_game_scope",
        "immutable_update_delete",
        "lifecycle_game_delete_cascade",
        "existing_game_partition_data_unchanged",
        "shared_history_retained",
        "downgrade_refused",
        "PG_new_session_idempotency",
        "PG_changed_command_conflict",
        "PG_receipt_failure_atomic_rollback",
        "third_family_registration",
    ]
