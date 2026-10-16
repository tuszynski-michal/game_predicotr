"""Bounded publication guards and fail-closed metadata references; no real database."""

import hashlib
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.storage_retention import cohort_asset_path_identity
from game_predictor_api.storage import grid_cohort_asset_retention as module
from game_predictor_api.storage.game_data_v2_manifest_v16 import GAME_TABLES, VERSION
from game_predictor_api.storage.storage_gc_repository import SqlAlchemyStorageGcRepository
from sqlalchemy.exc import SQLAlchemyError

NOW = datetime(2026, 10, 16, tzinfo=UTC)


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def mappings(self):
        return self

    def one_or_none(self):
        return self.value


class Session:
    def __init__(self, values=()):
        self.values, self.calls, self.info = iter(values), [], {}

    def execute(self, statement, parameters=None):
        self.calls.append((str(statement), parameters))
        return Result(next(self.values, None))

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))


def path(game, cohort):
    return f"data/grid-training-cohorts/{game}/{cohort}/originals/{'a' * 64}.jpg"


def test_guard_key_and_one_budget_shared_exclusive_transaction_functions():
    game, cohort = uuid4(), uuid4()
    expected = int.from_bytes(
        hashlib.sha256(f"grid-cohort-assets-v1:{game}:{cohort}".encode()).digest()[:4],
        "big",
        signed=True,
    )
    assert module.cohort_asset_guard_key(game, cohort) == (0x47504348, expected)
    session = Session()
    module.acquire_cohort_asset_guard(session, game, cohort)
    budget = session.info["grid_cohort_asset_deadline"]
    module.acquire_cohort_asset_guard(session, game, cohort, exclusive=True)
    assert session.info["grid_cohort_asset_deadline"] is budget
    assert any("pg_advisory_xact_lock_shared" in sql for sql, _ in session.calls)
    assert any("pg_advisory_xact_lock(" in sql for sql, _ in session.calls)
    assert any(
        parameters == {"namespace": 0x47504348, "key": expected} for _, parameters in session.calls
    )
    assert any("'5s'" in sql for sql, _ in session.calls)
    budget.end = 0
    with pytest.raises(module.GridCohortError):
        module.acquire_cohort_asset_guard(session, game, cohort)


def test_paths_are_exact_cohort_content_or_publisher_temp_only():
    game, cohort = uuid4(), uuid4()
    relative = path(game, cohort)
    assert cohort_asset_path_identity(relative) == (game, cohort)
    for unsafe in (
        relative.replace("originals", "unknown"),
        relative + "/child",
        "../" + relative,
        relative.replace(str(game), str(game).upper()),
        relative.replace("a" * 64, "a" * 63),
    ):
        assert cohort_asset_path_identity(unsafe) is None


def test_actual_publisher_hard_crash_residue_enters_guarded_gc_after_retention(tmp_path):
    from game_predictor_api.application.storage_gc import StorageGcArtifactStore
    from game_predictor_api.domain.storage_retention import (
        CohortAssetReferenceState,
        StorageRetentionPolicy,
    )

    game, cohort = uuid4(), uuid4()
    artifact, imports = tmp_path / "artifacts", tmp_path / "imports"
    artifact.mkdir()
    imports.mkdir()
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; from pathlib import Path; from uuid import UUID; "
            "from game_predictor_api.storage.grid_training_cohort_artifacts "
            "import GridCohortArtifactStore; "
            "os.replace = lambda *args: os._exit(73); "
            "GridCohortArtifactStore(Path(sys.argv[1])).publish_json("
            "UUID(sys.argv[2]), UUID(sys.argv[3]), {'realPublisher': True})",
            str(artifact),
            str(game),
            str(cohort),
        ],
        timeout=10,
        capture_output=True,
    )
    assert child.returncode == 73, child.stderr.decode(errors="replace")
    (residue,) = artifact.rglob("*.part")
    relative = residue.relative_to(artifact).as_posix()
    assert residue.read_bytes() == b'{"realPublisher":true}'
    assert residue.name.startswith(".tmp-") and len(residue.name) == 42
    assert cohort_asset_path_identity(relative) == (game, cohort)
    old = NOW - timedelta(hours=25)
    os.utime(residue, (old.timestamp(), old.timestamp()))

    class References:
        state = CohortAssetReferenceState(False, old)
        active = False
        reads = 0

        def normalization_dependency_statuses(self, keys):
            return {}

        def browser_staging_sources(self):
            return ()

        @contextmanager
        def cohort_asset_gc_guard(self, candidate):
            assert candidate == relative and not self.active
            self.active = True
            self.reads += 1
            try:
                yield self.state
            finally:
                self.active = False

    repository = References()
    store = StorageGcArtifactStore(artifact, imports)
    policy = StorageRetentionPolicy()
    before = store.scan(repository, policy=policy, now=old + timedelta(hours=23))
    assert before.entries == ()
    assert "retention_not_elapsed" in {
        reason.value for reason in before.protected[0].protection_reasons
    }
    repository.state = CohortAssetReferenceState(True, old)
    retained = store.scan(repository, policy=policy, now=NOW)
    assert retained.entries == ()
    assert "retained_cohort_reference" in {
        reason.value for reason in retained.protected[0].protection_reasons
    }
    repository.state = CohortAssetReferenceState(False, old)
    expired = store.scan(repository, policy=policy, now=NOW)
    assert len(expired.entries) == 1 and expired.entries[0].relative_path == relative
    assert repository.reads == 3 and not repository.active and residue.is_file()


def test_real_scoped_reference_and_latest_event_preserve_canceled_files(monkeypatch):
    game, cohort = uuid4(), uuid4()
    bindings = []
    monkeypatch.setattr(
        module,
        "GameStorageRouter",
        lambda: SimpleNamespace(bind=lambda *a, **kw: bindings.append((a, kw))),
    )
    session = Session(
        [
            "active",
            {
                "manifest_path": None,
                "created_at": NOW,
                "last_event": NOW,
                "invalid_assets": False,
                "page_ref": True,
            },
        ]
    )
    state = module.read_cohort_asset_reference(session, game, cohort, path(game, cohort))
    assert state.referenced and not state.unresolved and state.latest_dependency_at == NOW
    sql, parameters = session.calls[-1]
    assert "game_id=:game" in sql and "cohort_id=:cohort" in sql and parameters["cohort"] == cohort
    assert "status" not in sql  # Canceled/failed headers retain their actual references.
    assert bindings[0][1]["intent"].value == "write"


@pytest.mark.parametrize("route", [None, "deleting", "migrating", "blocked"])
def test_missing_or_transitional_route_is_not_empty_references(route):
    game, cohort = uuid4(), uuid4()
    state = module.read_cohort_asset_reference(
        Session([route, True]), game, cohort, path(game, cohort)
    )
    assert state.unresolved


def test_completed_game_deletion_requires_catalog_route_and_partition_absence():
    game, cohort = uuid4(), uuid4()
    receipt = {
        "operation_kind": "delete",
        "status": "done",
        "manifest_version": VERSION,
        "next_table_index": len(GAME_TABLES),
        "completed_tables": list(GAME_TABLES),
        "updated_at": NOW,
    }
    state = module.read_cohort_asset_reference(
        Session([None, False, receipt, *([None] * 6), False]), game, cohort, path(game, cohort)
    )
    assert not state.unresolved and not state.referenced and state.latest_dependency_at == NOW
    for changed in (
        {**receipt, "status": "running"},
        {**receipt, "completed_tables": []},
        {**receipt, "manifest_version": "old"},
    ):
        state = module.read_cohort_asset_reference(
            Session([None, False, changed]), game, cohort, path(game, cohort)
        )
        assert state.unresolved
    state = module.read_cohort_asset_reference(
        Session([None, False, receipt, "still-present"]), game, cohort, path(game, cohort)
    )
    assert state.unresolved


def test_query_failure_in_optional_repository_guard_protects_without_holding_failed_transaction(
    monkeypatch,
):
    game, cohort = uuid4(), uuid4()
    events = []

    class BrokenSession:
        info = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("closed")

        def rollback(self):
            events.append("rollback")

    monkeypatch.setattr(
        "game_predictor_api.storage.storage_gc_repository.acquire_cohort_asset_guard",
        lambda *a, **kw: (_ for _ in ()).throw(SQLAlchemyError("failure")),
    )
    repository = SqlAlchemyStorageGcRepository(lambda: BrokenSession())
    with repository.cohort_asset_gc_guard(path(game, cohort)) as state:
        assert state.unresolved and not state.referenced
        events.append("protected")
    assert events == ["rollback", "protected", "rollback", "closed"]
