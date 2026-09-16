from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.storage.game_data_v2_manifest_v1 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleError,
    _receipt_from_row,
    partition_name,
)

ROOT = Path(__file__).resolve().parents[3]
REVISION = "0110_game_partition_lifecycle"
PREVIOUS = "0109_exact_symbol_review_counts"


def _config(output: StringIO) -> Config:
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    return result


def test_lifecycle_migration_is_linear_bounded_and_non_destructive() -> None:
    script = ScriptDirectory.from_config(_config(StringIO()))
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS

    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "CREATE TABLE public.game_storage_lifecycle_operations" in sql
    assert "SET LOCAL lock_timeout = '2s'" in sql
    assert "SET LOCAL statement_timeout = '30s'" in sql
    assert "DELETE FROM" not in sql
    assert "CASCADE" not in sql


def test_partition_names_are_manifest_bound_stable_and_short() -> None:
    game_id = UUID("11111111-2222-3333-4444-555555555555")

    names = {partition_name(game_id, table) for table in CREATE_TABLES}

    assert len(names) == len(CREATE_TABLES)
    assert max(map(len, names)) <= 63
    assert partition_name(game_id, CREATE_TABLES[0]) == partition_name(game_id, CREATE_TABLES[0])
    with pytest.raises(GamePartitionLifecycleError) as raised:
        partition_name(game_id, "unreviewed_table")
    assert raised.value.code == "GAME_PARTITION_TABLE_NOT_IN_MANIFEST"


def test_invalid_checkpoint_payload_fails_closed() -> None:
    with pytest.raises(GamePartitionLifecycleError) as raised:
        _receipt_from_row(
            {
                "id": UUID(int=1),
                "game_id": UUID(int=2),
                "operation_kind": "provision",
                "status": "running",
                "next_table_index": 1,
                "completed_tables": [123],
                "failure_code": None,
            }
        )

    assert raised.value.code == "GAME_PARTITION_CHECKPOINT_INVALID"
