"""Upgrade the already-installed compact branch without rewriting its parent."""

import os

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database
from alembic import command
from alembic.config import Config
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    describe_application_role,
    provision_application_role,
)
from game_predictor_api.storage.schema_readiness import EXPECTED_ALEMBIC_HEAD
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires disposable PostgreSQL migration test.",
)


@pytest.mark.parametrize(
    "revision",
    [
        "0143_merge_share_grid_shadow",
        "0145_neural_page_geometry_binding",
        "0152_management_compact_panel",
    ],
)
def test_existing_compact_branch_upgrades_to_combined_head(revision):
    with application_role_database("t0945merge", ("merge",), revision=revision) as db:
        config = Config(str(ALEMBIC_INI))
        config.set_main_option(
            "sqlalchemy.url", db.owner_url.render_as_string(hide_password=False).replace("%", "%%")
        )
        command.upgrade(config, "head")
        with db.owner_engine.begin() as connection:
            # Match the documented rollout: V7 predecessors added after an old
            # fixture's role provisioning require the normal post-upgrade grants.
            assert db.app_url.password is not None
            provision_application_role(
                connection, ApplicationRoleSpec(role_name=db.role, password=db.app_url.password)
            )
            assert connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalars().all() == [EXPECTED_ALEMBIC_HEAD]
            assert describe_application_role(connection, db.role).compliant
            assert (
                connection.execute(
                    text(
                        "SELECT manifest_version FROM public.game_storage_locations "
                        "WHERE game_id=:game"
                    ),
                    {"game": db.games["merge"]},
                ).scalar_one()
                == "game-data-v2-manifest-v6"
            )
            protected = set(
                connection.execute(
                    text("""
                SELECT c.relname FROM pg_trigger t
                JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND NOT t.tgisinternal AND t.tgenabled<>'D'
                  AND t.tgfoid='public.management_history_immutable()'::regprocedure
            """)
                )
                .scalars()
                .all()
            )
            assert {
                "management_result_versions",
                "management_search_contexts",
                "management_session_audit",
            } <= protected
