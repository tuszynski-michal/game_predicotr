"""CPU contracts for cohort schema, retention and the capability boundary."""

from pathlib import Path
from typing import Any, cast

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.storage import game_data_v2_manifest_v15 as previous
from game_predictor_api.storage import game_data_v2_manifest_v16 as current
from game_predictor_api.storage import source_recording_permissions_v3 as permissions
from game_predictor_api.storage import source_recording_sql_v3 as sql
from game_predictor_api.storage.cleanup_repository import (
    _GAME_ARTIFACTS_SQL,
    _GAME_RESET_STATEMENTS,
)
from game_predictor_api.storage.database_roles import DatabaseRoleError
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortMemberModel
from sqlalchemy.engine import Connection


def test_manifest_adds_exact_six_game_owned_tables() -> None:
    assert set(current.GAME_TABLES) - set(previous.GAME_TABLES) == set(current.ADDED_GAME_TABLES)
    assert len(current.ADDED_GAME_TABLES) == 6
    assert all(current.ownership(table) == "game" for table in current.ADDED_GAME_TABLES)
    assert current.CREATE_TABLES == current.DELETE_TABLES == current.PARTITIONED_TABLES
    assert current.PREVIOUS_VERSION == previous.VERSION


def test_retained_source_identity_has_no_live_foreign_key() -> None:
    table = GridTrainingCohortMemberModel.__table__
    assert not table.c.source_id.foreign_keys
    assert table.c.live_source_image_id.nullable
    assert table.c.role.nullable
    assert {column.name for column in table.primary_key} == {"game_id", "cohort_id", "source_id"}
    assert all(
        table.c[name].type.item_type.python_type.__name__ == "UUID"
        for name in ("board_ids", "review_ids", "cell_ids")
    )


def test_reset_preserves_cohort_receipts_and_files() -> None:
    statements = "\n".join(_GAME_RESET_STATEMENTS)
    assert not any(table in statements for table in current.ADDED_GAME_TABLES)
    assert "grid-training-cohorts" not in _GAME_ARTIFACTS_SQL
    assert "grid_training_cohort_pages" not in _GAME_ARTIFACTS_SQL


class _Result:
    def __init__(self, value: Any):
        self.value = value

    def scalar_one(self) -> Any:
        return self.value


class _Connection:
    def __init__(self):
        self.execute_allowed = True
        self.statements: list[str] = []

    def execute(self, statement: Any, params: Any) -> _Result:
        assert "has_function_privilege" in str(statement) or "has_column_privilege" in str(
            statement
        )
        return _Result(
            (self.execute_allowed and params["oid"] < 2)
            if "has_function_privilege" in str(statement)
            else True
        )

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)
        if statement.startswith("GRANT EXECUTE"):
            self.execute_allowed = True


@pytest.fixture
def boundary(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    functions = [
        {
            "signature": signature,
            "oid": index,
            "owner": "gp_rec_fixture",
            "prosecdef": True,
            "proconfig": ["search_path=pg_catalog"],
            "public_execute": False,
        }
        for index, signature in enumerate(
            (*permissions.SOURCE_RECORDING_V3_FUNCTIONS, *permissions.COHORT_HELPER_FUNCTIONS)
        )
    ]
    monkeypatch.setattr(permissions, "_functions", lambda connection: functions)
    monkeypatch.setattr(permissions.v1, "_exists", lambda *args: True)
    monkeypatch.setattr(
        permissions, "validate_recording_capability", lambda *args: "gp_rec_fixture"
    )
    monkeypatch.setattr(
        permissions.v2, "recording_permission_errors", lambda *args: ("v2:retained",)
    )
    return functions


def test_current_compliance_preserves_historical_findings(boundary: Any) -> None:
    assert permissions.recording_permission_errors(cast(Connection, _Connection()), "runtime") == (
        "v2:retained",
    )


@pytest.mark.parametrize(
    "field,value,suffix",
    (
        ("owner", "foreign_owner", "owner"),
        ("public_execute", True, "public_execute"),
        ("prosecdef", False, "security"),
        ("proconfig", ["search_path=public"], "security"),
    ),
)
def test_current_compliance_rejects_broadened_function(
    boundary: Any, field: str, value: Any, suffix: str
) -> None:
    boundary[0][field] = value
    assert f"{boundary[0]['signature']}:{suffix}" in permissions.recording_permission_errors(
        cast(Connection, _Connection()), "runtime"
    )


def test_reprovision_grants_only_exact_new_entries(
    boundary: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _Connection()
    monkeypatch.setattr(permissions.v2, "enforce_recording_permissions", lambda *args: None)
    monkeypatch.setattr(permissions, "grant_recording_capability_dependencies", lambda *args: None)
    permissions.enforce_recording_permissions(cast(Connection, connection), "runtime")
    assert len(connection.statements) == 6
    assert all(
        any(
            signature in statement
            for signature in (
                *permissions.SOURCE_RECORDING_V3_FUNCTIONS,
                *permissions.COHORT_HELPER_FUNCTIONS,
            )
        )
        for statement in connection.statements
    )
    assert not any("GRANT SELECT" in statement for statement in connection.statements)


def test_missing_current_function_fails_closed(boundary: Any) -> None:
    boundary.pop(1)
    assert f"{permissions.SOURCE_RECORDING_V3_FUNCTIONS[1]}:missing" in (
        permissions.recording_permission_errors(cast(Connection, _Connection()), "runtime")
    )


def test_capability_cannot_be_runtime(boundary: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions.v2, "enforce_recording_permissions", lambda *args: None)
    monkeypatch.setattr(permissions, "grant_recording_capability_dependencies", lambda *args: None)
    with pytest.raises(DatabaseRoleError, match="Runtime cannot use"):
        permissions.enforce_recording_permissions(cast(Connection, _Connection()), "gp_rec_fixture")


def test_forward_sql_has_no_foreign_partition_or_fake_report_writes() -> None:
    assert (
        "INSERT INTO public.grid_model_evaluation_reports"
        not in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    )
    assert "RECORDING_PROOF_CHANGED_BY_USE" in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    assert (
        "resolution.dependency_group_ids IS DISTINCT FROM component"
        in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    )
    assert "FROM game_data_v2.source_images" not in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    assert "grid-model-evaluation-read-v2" in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    assert "e.payload=use_payload" in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    assert "e.payload=payload" not in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    assert "application-grid-evaluation-v1" not in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    assert (
        "pg_catalog.octet_length(report.report_json)>1048576" in sql.INSTALL_SOURCE_RECORDING_V3_SQL
    )


def test_forward_sql_keeps_excluded_metadata_out_of_protection_and_minima() -> None:
    text = sql.INSTALL_SOURCE_RECORDING_V3_SQL
    assert "RECORDING_SELECTION_REQUIRED" in text
    assert "pg_catalog.jsonb_typeof(m.frozen->'used') IS DISTINCT FROM 'boolean'" in text
    assert "AND m.role=required.role AND m.frozen->'used'='true'::jsonb" in text
    member_loop = text[text.index("FOR member IN SELECT m.source_id,m.role,m.frozen") :]
    assert member_loop.index("AND m.frozen->'used'='true'::jsonb") < member_loop.index(
        "INSERT INTO public.recording_evidence"
    )
    assert "minimum.photos<10 OR minimum.boards<30" in text
    assert "minimum.photos<5 OR minimum.boards<15" in text
    assert "minimum.full_photos<5" in text


def test_validation_does_not_replay_receipts_and_returns_before_receipt_insert() -> None:
    text = sql.INSTALL_SOURCE_RECORDING_V3_SQL
    mutation_section = text[text.index("IF k<>'validate_cohort_use' THEN") :]
    assert mutation_section.index("IF k<>'validate_cohort_use' THEN") < mutation_section.index(
        "PERFORM pg_catalog.pg_advisory_xact_lock"
    )
    assert mutation_section.index("IF k<>'validate_cohort_use' THEN") < mutation_section.index(
        "RETURN previous.receipt"
    )
    validation_return = text[text.index("IF k='validate_cohort_use' THEN") :]
    assert validation_return.index(
        "RETURN pg_catalog.jsonb_build_object"
    ) < validation_return.index("INSERT INTO public.recording_commands")
    assert "'usedMemberCount',used_members" in validation_return
    assert "'proofSha256',public.recording_digest_v1(uses)" in validation_return


def test_all_new_actual_use_paths_reject_removed_used_source_before_writes() -> None:
    text = sql.INSTALL_SOURCE_RECORDING_V3_SQL
    loop = text[text.index("FOR member IN SELECT m.source_id,m.role,m.frozen") :]
    refusal = "'SOURCE_REMOVED_NEW_USE_BLOCKED' USING ERRCODE='22023'"
    assert "SOURCE_REMOVED_POLICY_UNRESOLVED" not in text
    assert loop.index("AND m.frozen->'used'='true'::jsonb") < loop.index(refusal)
    assert loop.index("IF member.live_source_image_id IS NULL") < loop.index(refusal)
    assert loop.index(refusal) < loop.index("INSERT INTO public.recording_evidence")
    assert loop.index(refusal) < loop.index("IF k='validate_cohort_use' THEN")


def _migration() -> Any:
    script = ScriptDirectory.from_config(
        Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    )
    return script.get_revision("0163_grid_training_cohorts").module


def test_generic_trigger_dispatches_before_planning_table_specific_fields() -> None:
    value = _migration().IMMUTABLE_SQL
    member, rest = value.split("ELSIF TG_ARGV[0]='page' THEN", 1)
    page, header = rest.split("ELSIF TG_ARGV[0]='header' THEN", 1)
    assert "IF TG_ARGV[0]='member' THEN\n  IF TG_OP='INSERT' THEN" in member
    assert "NEW.cohort_id" in member and "NEW.cohort_id" in page
    assert "NEW.cohort_id" not in header
    assert "NEW.document" in header and "NEW.document" not in member


def test_source_delete_trigger_uses_selected_blocked_policy_notice() -> None:
    value = _migration().NOTICE_SQL
    assert "SOURCE_REMOVED_POLICY_UNRESOLVED" not in value
    assert "AND TG_OP='DELETE' THEN 'SOURCE_REMOVED_NEW_USE_BLOCKED'" in value


def test_migration_installs_six_partitioned_rls_tables_without_cluster_role_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _migration()
    statements: list[str] = []

    class Connection:
        def execute(self, statement: Any) -> Any:
            class Result:
                def scalars(self) -> tuple[()]:
                    return ()

            return Result()

    monkeypatch.setattr(module.op, "execute", lambda statement: statements.append(str(statement)))
    monkeypatch.setattr(module.op, "get_bind", Connection)
    monkeypatch.setattr(
        module, "validate_recording_capability", lambda connection: "gp_rec_fixture"
    )
    monkeypatch.setattr(module, "grant_recording_capability_dependencies", lambda connection: None)
    module.upgrade()
    ddl = "\n".join(statements)
    assert ddl.count("PARTITION BY LIST(game_id)") == 6
    assert "ON DELETE SET NULL (live_source_image_id)" in ddl
    assert "FOREIGN KEY(game_id,source_id)" not in ddl
    assert "CREATE ROLE" not in ddl and "ALTER ROLE" not in ddl
    assert "r.rolname<>'gp_rec_fixture'" in ddl
    for table in current.ADDED_GAME_TABLES:
        assert f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY" in ddl
        assert f"PARTITION OF game_data_v2.{table}" in ddl
    for table in module.NOTICE_TABLES:
        assert f"ON game_data_v2.{table} FOR EACH ROW" in ddl
    assert "OLD.frozen='{}'::jsonb" in ddl


def test_migration_downgrade_guards_all_retained_and_private_history_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _migration()
    statements: list[str] = []
    monkeypatch.setattr(module.op, "get_bind", object)
    monkeypatch.setattr(
        module, "validate_recording_capability", lambda connection: "gp_rec_fixture"
    )
    monkeypatch.setattr(module.op, "execute", lambda statement: statements.append(str(statement)))
    module.downgrade()
    ddl = "\n".join(statements)
    assert ddl.count("GRID_COHORT_DOWNGRADE_HAS_HISTORY") == 7
    assert ddl.index("WHERE kind='use' AND payload ? 'cohortId'") < ddl.index("DROP FUNCTION")
    assert "DROP OWNED" not in ddl and "REASSIGN OWNED" not in ddl and "CASCADE" not in ddl
    assert ddl.index("DROP TABLE game_data_v2.grid_training_cohort_members") < ddl.index(
        "DROP TABLE game_data_v2.grid_training_cohorts"
    )
