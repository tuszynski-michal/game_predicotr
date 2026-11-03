"""0178 is reversible only before any incremental history exists."""

import os
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from _grid_growth_replacement_fence import assert_replacement_fence
from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from game_predictor_api.storage.source_recording_permissions_v6 import recording_permission_errors
from sqlalchemy import text
from test_recording_migration_lifecycle_postgres import _config

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1", reason="Disposable PostgreSQL only"
)


def test_empty_downgrade_reupgrade_and_each_incremental_history_guard():
    with application_role_database("t1139down", ("correction",)) as db:
        config = _config(db)
        assert_replacement_fence(db)
        command.downgrade(config, "0177_source_replacement_purge")
        assert_replacement_fence(db)
        with db.owner_engine.connect() as c:
            assert (
                c.scalar(
                    text("SELECT to_regprocedure('public.recording_photo_context_v2(uuid,uuid[])')")
                )
                is None
            )
            assert (
                c.scalar(text("SELECT to_regclass('public.recording_photo_reservation_releases')"))
                is None
            )
            definition = c.scalar(
                text(
                    "SELECT pg_get_functiondef("
                    "'public.recording_photo_context_v1(uuid,uuid[])'::regprocedure)"
                )
            )
            assert "recording_photo_context_data_v2" not in definition
            assert "recording_photo_uses" in definition
        command.upgrade(config, "head")
        assert_replacement_fence(db)
        migration = (
            ScriptDirectory.from_config(config).get_revision("0178_grid_correction_growth").module
        )
        with db.owner_engine.begin() as c:
            assert recording_permission_errors(c, db.role) == ()
            game = next(iter(db.games.values()))
            family, cohort, source, job = (uuid4() for _ in range(4))
            c.execute(
                text(
                    "INSERT INTO public.grid_model_families(id,code,descriptor_json) "
                    "VALUES(:id,:code,'{}')"
                ),
                {"id": family, "code": "fixture_" + family.hex},
            )
            for history in ("reservation", "release"):
                with pytest.raises(RuntimeError, match="history prevents"), c.begin_nested():
                    c.execute(
                        text("""INSERT INTO public.recording_photo_uses
                     (game_id,cohort_id,source_id,family_id,import_id,source_sha256,pixel_sha256,
                      role,group_ids,split_sha256,used_in_cohort,reservation_policy)
                     VALUES(:g,:c,:s,:f,:j,:sha,:sha,'TRAIN','{}',:sha,false,:policy)"""),
                        {
                            "g": game,
                            "c": cohort,
                            "s": source,
                            "f": family,
                            "j": job,
                            "sha": "a" * 64,
                            "policy": "incremental-v2" if history == "reservation" else "legacy-v1",
                        },
                    )
                    if history == "release":
                        c.execute(
                            text("""INSERT INTO public.recording_photo_reservation_releases
                         (game_id,cohort_id,source_id,released_by_game,released_by_cohort,split_sha256,actor)
                         VALUES(:g,:c,:s,:g,:c,:sha,'fixture:1139')"""),
                            {"g": game, "c": cohort, "s": source, "sha": "a" * 64},
                        )
                    with Operations.context(MigrationContext.configure(c)):
                        migration.downgrade()
                assert c.scalar(text("SELECT count(*) FROM public.recording_photo_uses")) == 0
                assert (
                    c.scalar(
                        text("SELECT count(*) FROM public.recording_photo_reservation_releases")
                    )
                    == 0
                )
                assert (
                    c.scalar(text("SELECT version_num FROM public.alembic_version"))
                    == "0178_grid_correction_growth"
                )
