from __future__ import annotations

import os

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL

from services.api.tests.integration.test_v09_schema_migration import (
    _migration_config,
)

pytest_plugins = ("services.api.tests.integration.test_v09_schema_migration",)

PREVIOUS_REVISION = "0074_unknown_layout_cells"
CLEANUP_REVISION = "0075_remove_obsolete_board_search_storage"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def test_storage_cleanup_upgrade_downgrade_upgrade_cycle(
    isolated_v09_database: URL,
) -> None:
    config = _migration_config(isolated_v09_database)
    engine = create_engine(isolated_v09_database, pool_pre_ping=True)
    try:
        command.upgrade(config, PREVIOUS_REVISION)
        before = inspect(engine)
        assert "image_board_search_documents" in before.get_table_names()
        assert "primary_match_tokens" in {
            column["name"] for column in before.get_columns("image_board_search_candidates")
        }
        assert "has_grid_issue" in {
            column["name"] for column in before.get_columns("image_symbol_review_cells")
        }

        engine.dispose()
        command.upgrade(config, CLEANUP_REVISION)
        after = inspect(engine)
        assert "image_board_search_documents" not in after.get_table_names()
        assert "primary_match_tokens" not in {
            column["name"] for column in after.get_columns("image_board_search_candidates")
        }
        assert "has_grid_issue" not in {
            column["name"] for column in after.get_columns("image_symbol_review_cells")
        }
        assert "image_board_search_fast_documents" in after.get_table_names()

        engine.dispose()
        command.downgrade(config, PREVIOUS_REVISION)
        downgraded = inspect(engine)
        assert "image_board_search_documents" in downgraded.get_table_names()
        assert "primary_match_tokens" in {
            column["name"] for column in downgraded.get_columns("image_board_search_candidates")
        }
        assert "has_grid_issue" in {
            column["name"] for column in downgraded.get_columns("image_symbol_review_cells")
        }

        engine.dispose()
        command.upgrade(config, CLEANUP_REVISION)
        assert "image_board_search_documents" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
