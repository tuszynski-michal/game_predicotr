"""Bounded real PostgreSQL DDL audit; never connect migrations to the user DB."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.game_data_v2_manifest_v1 import (
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
    SHARED,
    VERSION,
)
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


@pytest.fixture
def database() -> Iterator[tuple[Engine, Config]]:
    name = "game_predictor_task0518_" + uuid4().hex[:12]
    assert re.fullmatch(r"game_predictor_task0518_[0-9a-f]{12}", name)
    url = make_url(ApiSettings.from_environment().database_url)
    assert url.database != name
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        command.upgrade(config, "0105_partitioned_game_storage")
        print(f"TASK-0518 isolated schema ready: {name}", flush=True)
        yield engine, config
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            active = connection.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"), {"name": name}
            ).scalar_one()
            assert active == 0, "Refusing DROP while a test connection remains"
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


def test_catalog_partition_constraints_indexes_and_empty_downgrade(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    with engine.connect() as connection:
        parents = connection.execute(
            text(
                "SELECT c.relname, p.partstrat, pg_get_partkeydef(c.oid) "
                "FROM pg_partitioned_table p "
                "JOIN pg_class c ON c.oid=p.partrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='game_data_v2'"
            )
        ).all()
        assert {row[0] for row in parents} == set(GAME_TABLES)
        assert all(row[1:] == ("l", "LIST (game_id)") for row in parents)
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_inherits i "
                    "JOIN pg_class c ON c.oid=i.inhparent "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='game_data_v2'"
                )
            ).scalar_one()
            == 0
        )
        inspector = inspect(connection)
        assert set(inspector.get_table_names(schema="public")) == (
            CATALOG | SHARED | set(GAME_TABLES) | set(CONTROL_TABLES)
        )
        assert ["execution_slot"] in [
            constraint["column_names"]
            for constraint in inspector.get_unique_constraints("jobs", schema="public")
        ]
        target_schemas: dict[str, str] = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                text(
                    "SELECT f.conname,n.nspname FROM pg_constraint f "
                    "JOIN pg_class c ON c.oid=f.confrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE f.contype='f' AND f.connamespace='game_data_v2'::regnamespace"
                )
            ).all()
        }
        check_differences: list[str] = []
        for table in GAME_TABLES:
            columns = {
                column["name"]: column
                for column in inspector.get_columns(table, schema="game_data_v2")
            }
            assert columns["game_id"]["nullable"] is False
            legacy_columns = inspector.get_columns(table, schema="public")
            assert set(columns) == {column["name"] for column in legacy_columns} | {"game_id"}
            for column in legacy_columns:
                assert str(columns[column["name"]]["type"]) == str(column["type"])
                if column["name"] != "game_id":
                    assert columns[column["name"]]["nullable"] == column["nullable"]
            legacy_checks = {
                check["sqltext"]
                for check in inspector.get_check_constraints(table, schema="public")
                if check["name"] != "ck_image_symbol_review_events_render_provenance"
            }
            v2_checks = {
                check["sqltext"]
                for check in inspector.get_check_constraints(table, schema="game_data_v2")
                if check["name"] != "ck_image_symbol_review_events_render_provenance"
            }
            if legacy_checks != v2_checks:
                check_differences.append(
                    f"{table}: missing={legacy_checks - v2_checks!r}; "
                    f"extra={v2_checks - legacy_checks!r}"
                )
            primary = inspector.get_pk_constraint(table, schema="game_data_v2")[
                "constrained_columns"
            ]
            assert primary[0] == "game_id"
            indexes = [
                index
                for index in inspector.get_indexes(table, schema="game_data_v2")
                if not index.get("dialect_options", {}).get("postgresql_where")
            ]
            prefixes = [primary] + [index["column_names"] for index in indexes]
            for fk in inspector.get_foreign_keys(
                table, schema="game_data_v2", postgresql_ignore_search_path=True
            ):
                parent = fk["referred_table"]
                fk_name = fk["name"]
                assert fk_name is not None
                own = fk["constrained_columns"]
                target = fk["referred_columns"]
                assert any(prefix[: len(own)] == own for prefix in prefixes), (table, fk)
                if parent in GAME_TABLES:
                    assert target_schemas[fk_name] == "game_data_v2", (table, fk)
                    assert own[0] == target[0] == "game_id"
                else:
                    assert parent in CATALOG | SHARED
                    assert target_schemas[fk_name] == "public", (table, fk)
                    if parent in {"symbols", "rules_versions", "jobs"}:
                        assert own[0] == target[0] == "game_id"
        assert not check_differences, "\n".join(check_differences)
        # 0082's missing OR parentheses allowed a legacy previous asset to mask
        # invalid new virtual provenance. v2 deliberately preserves the stronger
        # ORM/domain rule: both sides must be valid, not just one OR branch.
        for schema, expected in (("public", True), ("game_data_v2", False)):
            expression = connection.execute(
                text(
                    "SELECT pg_get_expr(conbin, conrelid) FROM pg_constraint "
                    "WHERE conname='ck_image_symbol_review_events_render_provenance' "
                    "AND connamespace=CAST(:schema AS regnamespace)"
                ),
                {"schema": schema},
            ).scalar_one()
            valid = connection.exec_driver_sql(
                f"SELECT {expression} FROM (SELECT 'legacy_file'::text previous_asset_mode, "
                "'virtual_source'::text asset_mode, "
                "NULL::uuid previous_source_geometry_revision_id,"
                "NULL::uuid source_geometry_revision_id, "
                "NULL::text previous_render_spec_checksum_sha256,"
                "NULL::text previous_rendered_pixel_checksum_sha256, "
                "NULL::text render_spec_checksum_sha256,"
                "NULL::text rendered_pixel_checksum_sha256) asset"
            ).scalar_one()
            assert valid is expected
    engine.dispose()
    command.downgrade(config, "0104_game_deletion_access_paths")
    assert "game_data_v2" not in inspect(engine).get_schema_names()
    engine.dispose()
    command.upgrade(config, "0105_partitioned_game_storage")


def test_unprepared_game_and_cross_game_parent_fail_closed(database: tuple[Engine, Config]) -> None:
    engine, config = database
    first, second, job_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        for game in (first, second):
            connection.execute(
                text(
                    "INSERT INTO public.games (id,code,name,status,expected_layout_count) "
                    "VALUES (:id,:code,'Schema test','draft',1)"
                ),
                {"id": game, "code": game.hex},
            )
        connection.execute(
            text(
                "INSERT INTO public.jobs (id,game_id,job_type,status,input_payload,input_key,"
                "progress_current,success_count,failure_count,review_count,attempt_count) "
                "VALUES (:id,:game,'import','cancelled','{}',:key,0,0,0,0,0)"
            ),
            {"id": job_id, "game": first, "key": job_id.hex},
        )
    insert = text(
        "INSERT INTO game_data_v2.image_review_queue_states "
        "(game_id,import_job_id,queue_version,total_count,pending_count,accepted_count,"
        "corrected_count,rejected_count,superseded_count) VALUES (:game,:job,1,0,0,0,0,0,0)"
    )
    with pytest.raises(DBAPIError, match="no partition"), engine.begin() as connection:
        connection.execute(insert, {"game": first, "job": job_id})
    with engine.begin() as connection:
        for number, game in enumerate((first, second)):
            connection.exec_driver_sql(
                f"CREATE TABLE game_data_v2.queue_test_{number} "
                "PARTITION OF game_data_v2.image_review_queue_states "
                f"FOR VALUES IN ('{game}')"
            )
    with pytest.raises(DBAPIError, match="foreign key"), engine.begin() as connection:
        connection.execute(insert, {"game": second, "job": job_id})
    with engine.begin() as connection:
        connection.execute(insert, {"game": first, "job": job_id})
    with pytest.raises(DBAPIError, match="foreign key"), engine.begin() as connection:
        connection.execute(
            text("UPDATE game_data_v2.image_review_queue_states SET game_id=:game"),
            {"game": second},
        )
    engine.dispose()
    with pytest.raises(
        DBAPIError,
        match=r"GAME_STORAGE_DOWNGRADE_NOT_EMPTY: game_data_v2\.image_review_queue_states",
    ):
        command.downgrade(config, "0104_game_deletion_access_paths")


def test_registry_survives_connection_restart_and_downgrade_protects_it(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    game, migration = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.game_storage_migrations "
                "(id,game_id,manifest_version,source_schema,target_schema,"
                "source_generation,target_generation,status) "
                "VALUES (:id,:game,:version,'public','game_data_v2',1,2,'copying')"
            ),
            {"id": migration, "game": game, "version": VERSION},
        )
        connection.execute(
            text(
                "INSERT INTO public.game_storage_table_progress "
                "(game_id,migration_id,manifest_version,table_name,cursor,copied_rows,status) "
                "VALUES (:game,:id,:version,'cell_observations','[7]',7,'copying')"
            ),
            {"id": migration, "game": game, "version": VERSION},
        )
    engine.dispose()
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT cursor,copied_rows FROM public.game_storage_table_progress "
                "WHERE game_id=:game"
            ),
            {"game": game},
        ).one() == ([7], 7)
    with pytest.raises(DBAPIError, match="foreign key"), engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.game_storage_table_progress SET game_id=:other WHERE game_id=:game"
            ),
            {"game": game, "other": uuid4()},
        )
    with pytest.raises(DBAPIError, match="foreign key"), engine.begin() as connection:
        connection.execute(
            text("UPDATE public.game_storage_table_progress SET table_name='jobs'"),
        )
    engine.dispose()
    # A function-scoped database contains only this test's registry/checkpoint.
    # Assert the exact blocker so game data can never mask a missing registry guard.
    with pytest.raises(
        DBAPIError,
        match=r"GAME_STORAGE_DOWNGRADE_NOT_EMPTY: public\.game_storage_migrations",
    ):
        command.downgrade(config, "0104_game_deletion_access_paths")


def test_v2_child_cannot_reference_another_game_parent(database: tuple[Engine, Config]) -> None:
    engine, _ = database
    first, second, batch = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        for number, game in enumerate((first, second)):
            connection.execute(
                text(
                    "INSERT INTO public.games (id,code,name,status,expected_layout_count) "
                    "VALUES (:game,:code,'Schema child test','draft',1)"
                ),
                {"game": game, "code": game.hex},
            )
            for table in ("review_batches", "review_feedback_exports"):
                connection.exec_driver_sql(
                    f"CREATE TABLE game_data_v2.{table}_test_{number} "
                    f"PARTITION OF game_data_v2.{table} FOR VALUES IN ('{game}')"
                )
        connection.execute(
            text(
                "INSERT INTO game_data_v2.review_batches "
                "(id,game_id,source_report_sha256,active_learning_version,model_version,"
                "model_artifact_sha256,calibration_report_sha256,dataset_sha256,split_sha256,"
                "inventory_sha256,temperature,item_count,source_report) "
                "VALUES (:batch,:game,:sha,'test','test',:sha,:sha,:sha,:sha,:sha,1,1,'{}')"
            ),
            {"batch": batch, "game": first, "sha": "a" * 64},
        )
    insert = text(
        "INSERT INTO game_data_v2.review_feedback_exports "
        "(id,review_batch_id,game_id,version,source_state_sha256,payload_sha256,sample_count,"
        "rejected_item_count,payload,created_by) "
        "VALUES (:id,:batch,:game,1,:sha,:sha,0,0,'{}','test')"
    )
    params = {"id": uuid4(), "batch": batch, "game": second, "sha": "a" * 64}
    with pytest.raises(DBAPIError, match="foreign key"), engine.begin() as connection:
        connection.execute(insert, params)
    with engine.begin() as connection:
        connection.execute(insert, {**params, "game": first})
