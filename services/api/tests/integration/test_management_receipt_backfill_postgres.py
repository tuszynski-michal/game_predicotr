"""Populated0151 preview/backfill: deterministic scope, exceptional redaction."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database
from alembic import command
from alembic.config import Config
from game_predictor_api.storage.database_roles import describe_application_role
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires disposable PostgreSQL migration test.",
)


@pytest.mark.parametrize("revision", ["0151_super_game_roles", "0152_super_game_series"])
def test_populated_receipt_preview_and_owner_backfill_preserve_retry_identity(revision):
    with application_role_database("t0940backfill", ("legacy",), revision=revision) as db:
        point, machine = uuid4(), uuid4()
        operation_ids = [uuid4() for _ in range(4)]
        timestamp = datetime.now(UTC)
        with db.owner_engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO public.management_points
                  (id,name,city,street,archived,revision,created_at,updated_at)
                VALUES (:id,'Point','City','Street',false,1,:time,:time)
            """),
                {"id": point, "time": timestamp},
            )
            conn.execute(
                text("""
                INSERT INTO public.management_machines
                  (id,point_id,name,archived,revision,created_at,updated_at)
                VALUES (:id,:point,'Machine',false,1,:time,:time)
            """),
                {"id": machine, "point": point, "time": timestamp},
            )
            conn.execute(
                text("""
                INSERT INTO public.management_assignments(machine_id,game_id,attached,updated_at)
                VALUES (:machine,:game,true,:time)
            """),
                {"machine": machine, "game": db.games["legacy"], "time": timestamp},
            )
            responses = [
                {"id": str(point), "city": "City", "street": "Street"},
                {"id": str(machine), "pointId": str(point)},
                {"searchContextId": str(operation_ids[2]), "search": {}},
                {"changed": False},  # An unchanged legacy correction has no journal.
            ]
            for operation, body in zip(operation_ids, responses, strict=True):
                conn.execute(
                    text("""
                    INSERT INTO public.management_operations
                      (operation_id,actor,request_checksum,response,created_at)
                    VALUES (:id,'local-owner',:checksum,CAST(:body AS json),:time)
                """),
                    {
                        "id": operation,
                        "checksum": "c" * 64,
                        "body": json.dumps(body),
                        "time": timestamp,
                    },
                )
            conn.execute(
                text("""
                INSERT INTO public.management_journal
                  (id,operation_id,actor,action,point_id,before,after,created_at)
                VALUES (:id,:operation,'local-owner','point.write',:point,'{}','{}',:time)
            """),
                {"id": uuid4(), "operation": operation_ids[0], "point": point, "time": timestamp},
            )
            conn.execute(
                text("""
                INSERT INTO public.management_search_contexts
                  (id,machine_id,game_id,stake_grosze,actor,query,sequence_numbers,created_at)
                VALUES (:id,:machine,:game,2000,'local-owner','{}','[]',:time)
            """),
                {
                    "id": operation_ids[2],
                    "machine": machine,
                    "game": db.games["legacy"],
                    "time": timestamp,
                },
            )
        preview = subprocess.run(
            [sys.executable, "scripts/preview_management_receipt_migration.py"],
            env=db.subprocess_environment(
                GAME_PREDICTOR_OWNER_DATABASE_URL=db.owner_url.render_as_string(
                    hide_password=False
                ),
                GAME_PREDICTOR_DATABASE_URL=db.app_url.render_as_string(hide_password=False),
            ),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert preview.returncode == 0, preview.stderr
        report = json.loads(preview.stdout)
        assert report["readOnly"] and report["totalReceipts"] == 4
        assert report["currentRevision"] == revision
        assert report["receiptCategories"] == {
            "journal": 1,
            "context": 1,
            "response": 1,
            "legacy_redacted": 1,
        }
        with db.owner_engine.connect() as conn:
            assert conn.execute(
                text("SELECT response FROM public.management_operations WHERE operation_id=:id"),
                {"id": operation_ids[3]},
            ).scalar_one() == {"changed": False}
        config = Config(str(ALEMBIC_INI))
        config.set_main_option(
            "sqlalchemy.url", db.owner_url.render_as_string(hide_password=False).replace("%", "%%")
        )
        command.upgrade(config, "head")
        with db.owner_engine.begin() as conn:
            # Owner default privileges already grant the new function to the
            # existing app role; this read-only check never changes its login.
            assert describe_application_role(conn, db.role).compliant
            rows = (
                conn.execute(
                    text("""
                SELECT operation_id,actor,request_checksum,created_at,point_id,machine_id,
                       game_id,response FROM public.management_operations
            """)
                )
                .mappings()
                .all()
            )
            by_id = {row["operation_id"]: row for row in rows}
            for operation in operation_ids:
                row = by_id[operation]
                assert row["actor"] == "local-owner" and row["request_checksum"] == "c" * 64
                assert row["created_at"] == timestamp
            assert by_id[operation_ids[0]]["point_id"] == point
            assert by_id[operation_ids[1]]["machine_id"] == machine
            assert by_id[operation_ids[1]]["point_id"] == point
            assert by_id[operation_ids[2]]["game_id"] == db.games["legacy"]
            assert by_id[operation_ids[3]]["response"] == {
                "managementReceiptState": "legacy_redacted",
            }
