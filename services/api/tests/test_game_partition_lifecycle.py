from io import StringIO
from pathlib import Path
from uuid import UUID

import psycopg.errors
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.storage import catalog_repository
from game_predictor_api.storage.game_data_v2_manifest_v8 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    LOCK_RETRY_ATTEMPTS,
    GamePartitionLifecycleError,
    _receipt_from_row,
    is_lock_not_available,
    lock_retry_delay_seconds,
    partition_name,
)
from sqlalchemy.exc import OperationalError

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


def _lock_timeout() -> OperationalError:
    return OperationalError("CREATE TABLE ...", {}, psycopg.errors.LockNotAvailable())


class _RecordingSession:
    def __init__(self) -> None:
        self.events: list[str] = []

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")


def _patch_run_next(monkeypatch: pytest.MonkeyPatch, outcomes: list[object]) -> list[int]:
    calls: list[int] = []

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        def run_next(self, _operation_id: UUID) -> object:
            calls.append(len(calls) + 1)
            outcome = outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    monkeypatch.setattr(catalog_repository, "GamePartitionLifecycleRepository", _Repository)
    return calls


def test_lock_timeout_detection_uses_sqlstate_only() -> None:
    assert is_lock_not_available(_lock_timeout())
    assert is_lock_not_available(psycopg.errors.LockNotAvailable())
    assert not is_lock_not_available(
        OperationalError("SELECT 1", {}, psycopg.errors.DeadlockDetected())
    )
    assert not is_lock_not_available(RuntimeError("canceling statement due to lock timeout"))


def test_lock_retry_backoff_is_bounded() -> None:
    delays = [lock_retry_delay_seconds(attempt) for attempt in range(1, LOCK_RETRY_ATTEMPTS + 1)]

    assert delays == sorted(delays)
    assert delays[0] == 0.5
    assert max(delays) <= 4.0


def test_partition_step_retries_lock_timeout_and_resumes(monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = object()
    calls = _patch_run_next(monkeypatch, [_lock_timeout(), _lock_timeout(), receipt])
    session = _RecordingSession()
    slept: list[float] = []

    result = catalog_repository._run_partition_step_in(
        session,  # type: ignore[arg-type]
        UUID(int=1),
        sleep=slept.append,
    )

    assert result is receipt
    assert len(calls) == 3
    assert session.events == ["rollback", "rollback", "commit"]
    assert slept == [0.5, 1.0]


def test_partition_step_reports_busy_after_bounded_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_run_next(monkeypatch, [_lock_timeout() for _ in range(LOCK_RETRY_ATTEMPTS)])
    session = _RecordingSession()
    slept: list[float] = []

    with pytest.raises(GamePartitionLifecycleError) as raised:
        catalog_repository._run_partition_step_in(
            session,  # type: ignore[arg-type]
            UUID(int=1),
            sleep=slept.append,
        )

    assert raised.value.code == "GAME_PARTITION_LOCK_BUSY"
    assert raised.value.details == {
        "operationId": str(UUID(int=1)),
        "attempts": LOCK_RETRY_ATTEMPTS,
    }
    assert len(calls) == LOCK_RETRY_ATTEMPTS
    assert len(slept) == LOCK_RETRY_ATTEMPTS - 1
    assert "commit" not in session.events


def test_partition_step_does_not_retry_other_database_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_run_next(
        monkeypatch,
        [OperationalError("CREATE TABLE ...", {}, psycopg.errors.DeadlockDetected())],
    )
    session = _RecordingSession()

    with pytest.raises(OperationalError):
        catalog_repository._run_partition_step_in(
            session,  # type: ignore[arg-type]
            UUID(int=1),
            sleep=lambda _seconds: None,
        )

    assert len(calls) == 1
    assert session.events == []


def test_partition_step_persists_blocked_diagnostic_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drift = GamePartitionLifecycleError("GAME_PARTITION_CHECKPOINT_DRIFT", "drift")
    calls = _patch_run_next(monkeypatch, [drift])
    session = _RecordingSession()

    with pytest.raises(GamePartitionLifecycleError):
        catalog_repository._run_partition_step_in(
            session,  # type: ignore[arg-type]
            UUID(int=1),
            sleep=lambda _seconds: None,
        )

    assert len(calls) == 1
    assert session.events == ["commit"]
