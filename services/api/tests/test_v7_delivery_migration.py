"""Compile the actual V7 delivery DDL without a connection or operator data writes."""

from __future__ import annotations

import importlib.util
import re
from io import StringIO
from pathlib import Path
from typing import Literal

import pytest
from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "services/api/alembic/versions/0144_v7_reviewed_delivery.py"
)
RANGES = "semi_automatic_image_selection_ranges"
RUNS = "semi_automatic_image_selection_runs"
GATE = "semi_automatic_selection_v7_activation_gate"
SOURCES = "semi_automatic_selection_v7_source_observations"
OPERATIONS = "semi_automatic_selection_v7_output_operations"
INHERITED_SEARCH_PATHS = ("pg_catalog, public", '"unrelated_schema", public')


def _ddl(direction: Literal["upgrade", "downgrade"], search_path: str) -> str:
    spec = importlib.util.spec_from_file_location("migration_0144", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0144_v7_reviewed_delivery"
    assert module.down_revision == "0143_merge_share_grid_shadow"

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        # Migration 0129 leaves this transaction-local setting for later revisions.
        # A second unrelated first schema also catches dependence on that exact path.
        op.execute(f"SET LOCAL search_path = {search_path}")
        getattr(module, direction)()
    return output.getvalue()


def _table_targets(sql: str) -> set[str]:
    return set(re.findall(r"(?:CREATE TABLE|ALTER TABLE|DROP TABLE|REFERENCES) ([\w.]+)", sql))


@pytest.mark.parametrize("search_path", INHERITED_SEARCH_PATHS)
def test_upgrade_uses_public_for_actual_table_fk_and_index_ddl(search_path: str) -> None:
    sql = _ddl("upgrade", search_path)

    assert sql.startswith(f"SET LOCAL search_path = {search_path};")
    assert _table_targets(sql) == {
        f"public.{name}" for name in (RANGES, RUNS, GATE, SOURCES, OPERATIONS)
    }
    assert re.findall(r"CREATE TABLE ([\w.]+)", sql) == [
        f"public.{SOURCES}",
        f"public.{OPERATIONS}",
    ]
    assert sql.count(f"REFERENCES public.{RUNS} (id) ON DELETE RESTRICT") == 2
    assert f"REFERENCES public.{RANGES} (id) ON DELETE RESTRICT" in sql
    assert re.findall(r"CREATE (?:UNIQUE )?INDEX \w+ ON ([\w.]+)", sql) == [
        f"public.{OPERATIONS}",
        f"public.{OPERATIONS}",
    ]
    assert "SET " not in sql.split(";", 1)[1]
    assert "pg_catalog.semi_automatic" not in sql


def test_upgrade_preserves_blocked_gate_history_and_pending_constraints() -> None:
    sql = " ".join(_ddl("upgrade", INHERITED_SEARCH_PATHS[0]).split())

    assert "pilot_status VARCHAR(16) DEFAULT 'blocked' NOT NULL" in sql
    assert "pilot_generation BIGINT DEFAULT '0' NOT NULL" in sql
    assert "pilot_mode VARCHAR(32) DEFAULT 'semi_automatic' NOT NULL" in sql
    assert "pilot_source_bindings JSONB DEFAULT '[]'::jsonb NOT NULL" in sql
    assert (
        "CHECK (status IN ('missing', 'proposed', 'auto_selected', 'output_synced', 'conflict'))"
        in sql
    )
    assert "PRIMARY KEY (run_id, source_index)" in sql
    assert "CONSTRAINT ck_v7_source_observation_index CHECK (source_index >= 0)" in sql
    assert (
        "CONSTRAINT ck_v7_output_operation_state CHECK "
        "(state IN ('reserved', 'recovery_required', 'committed', 'conflict', 'failed') "
        "AND decision_generation >= 0 AND reserved_revision >= 0)" in sql
    )
    assert (
        f"CREATE UNIQUE INDEX uq_v7_output_operation_pending_run ON public.{OPERATIONS} "
        "(run_id) WHERE state IN ('reserved', 'recovery_required')" in sql
    )
    assert (
        f"CREATE INDEX ix_v7_output_operation_range_created ON public.{OPERATIONS} "
        "(range_id, created_at)" in sql
    )
    assert "pilot_status <> 'active' OR (pilot_geometry_family_id IS NOT NULL" in sql
    assert "pilot_acceptance_receipt_fingerprint IS NOT NULL" in sql
    assert "jsonb_array_length(pilot_source_bindings) > 0" in sql
    assert "INSERT INTO" not in sql and "UPDATE " not in sql and "DELETE FROM" not in sql


@pytest.mark.parametrize("search_path", INHERITED_SEARCH_PATHS)
def test_downgrade_checks_public_history_before_public_ddl(search_path: str) -> None:
    sql = _ddl("downgrade", search_path)
    guard, drops = sql.split("DROP TABLE", 1)

    assert set(re.findall(r"SELECT 1 FROM ([\w.]+)", guard)) == {
        f"public.{name}" for name in (OPERATIONS, SOURCES, RANGES, GATE)
    }
    assert f"FROM public.{RANGES} WHERE v7_review IS NOT NULL" in guard
    assert f"FROM public.{GATE} WHERE pilot_generation <> 0" in guard
    assert "pilot_status <> 'blocked' OR pilot_acceptance_receipt_fingerprint IS NOT NULL" in guard
    assert "RAISE EXCEPTION 'Cannot discard V7 delivery history'" in guard
    assert _table_targets(sql) == {f"public.{name}" for name in (OPERATIONS, SOURCES, RANGES, GATE)}
    assert re.findall(r"DROP TABLE ([\w.]+)", sql) == [
        f"public.{OPERATIONS}",
        f"public.{SOURCES}",
    ]
    assert "CHECK (status IN ('missing', 'auto_selected', 'output_synced', 'conflict'))" in drops
    assert "SET " not in sql.split(";", 1)[1]
    assert "CASCADE" not in sql
