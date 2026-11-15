"""Large import metadata must not be confused with actual training examples."""

import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import anyio.to_thread
import pytest
from game_predictor_api.domain.grid_correction_incremental_split import solve_incremental_split
from game_predictor_api.domain.grid_correction_split import (
    CorrectionSplitError,
    solve_correction_split,
)
from game_predictor_api.schemas.grid_training_cohorts import GridCohortPrepareCommand
from game_predictor_api.storage.grid_correction_split import population
from game_predictor_api.storage.source_recording_unlimited_sources import (
    remove_source_cap,
    restore_source_cap,
)
from test_grid_correction_learning_api import GAME, PATH, Service, app_for
from test_grid_correction_split import source
from test_grid_learning_source_limit import Connection, definitions


@pytest.mark.parametrize("solve", [solve_correction_split, solve_incremental_split])
def test_more_than_twenty_thousand_sources_reaches_label_minima_not_cardinality(solve):
    sources = [replace(source(i), eligible_boards=0) for i in range(20_001)]
    with pytest.raises(CorrectionSplitError) as error:
        solve(sources)
    assert error.value.code == "GRID_CORRECTION_SPLIT_MINIMA"
    assert error.value.photos == error.value.boards == 0


@pytest.mark.parametrize("solve", [solve_correction_split, solve_incremental_split])
def test_work_budget_still_stops_search(solve):
    with pytest.raises(CorrectionSplitError) as error:
        solve([source(i) for i in range(54)], max_work=1)
    assert error.value.code == "GRID_CORRECTION_SPLIT_WORK_LIMIT"


def test_population_keeps_whole_import_including_unlabelled_tail():
    rows = [
        {
            "source": {"id": str(i), "import_job_id": "import"},
            "logical_name": "",
            "approved": i < 200,
            "pending_correction": False,
        }
        for i in range(20_001)
    ]

    class Session:
        def execute(self, statement, parameters):
            if "to_jsonb(s)" in str(statement):
                assert "LIMIT" not in str(statement)
                assert parameters == {"game": GAME, "imports": ["import"]}
                return SimpleNamespace(mappings=lambda: iter(rows))
            return SimpleNamespace(mappings=lambda: iter(()))

    result = population(SimpleNamespace(session=Session()), GAME, ["import"])
    assert len(result) == 20_001
    assert sum(row["approved"] for row in result) == 200
    assert result[-1]["source"]["id"] == "20000"


def test_migration_removes_only_cardinality_and_restores_exact_definitions():
    originals = definitions(20_000)
    connection = Connection(originals)
    remove_source_cap(connection)
    uncapped = dict(zip(originals, connection.executed, strict=True))
    assert len(uncapped) == 6
    assert all(">20000" not in sql and "uncapped" in sql for sql in uncapped.values())
    restored = Connection(uncapped)
    restore_source_cap(restored)
    assert restored.executed == list(originals.values())
    refused = Connection(uncapped, largest=20_001)
    with pytest.raises(RuntimeError, match="prevents downgrade"):
        restore_source_cap(refused)
    assert refused.executed == []


def test_unexpected_sql_stops_before_any_replacement():
    originals = definitions(20_000)
    originals[next(reversed(originals))] = "unexpected function body"
    connection = Connection(originals)
    with pytest.raises(RuntimeError, match="expected source predicate"):
        remove_source_cap(connection)
    assert connection.executed == []


def test_http_and_cohort_accept_all_validation_assignments(tmp_path, monkeypatch):
    assignments = {str(UUID(int=i)): "BUFFER" for i in range(1, 20_002)}
    command = {
        "trainingMode": "screen+grid",
        "policyVersion": "application-grid-corrections-v4",
        "validationAssignments": assignments,
    }
    service = Service()

    # In-process ASGI request: no sockets, worker threads or live API service.
    async def run_sync(function, *args, **kwargs):
        return function(*args)

    monkeypatch.setattr(anyio.to_thread, "run_sync", run_sync)
    messages = []

    async def receive():
        return {"type": "http.request", "body": json.dumps(command).encode(), "more_body": False}

    async def send(message):
        messages.append(message)

    app = app_for(service, tmp_path, security=False)
    request = app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": f"{PATH}/preview",
            "raw_path": f"{PATH}/preview".encode(),
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "state": {"local_admin_actor": "local-owner"},
        },
        receive,
        send,
    )
    with pytest.raises(StopIteration):
        request.send(None)
    assert messages[0]["status"] == 200, messages
    assert len(service.calls[-1][1][1]["validationAssignments"]) == 20_001
    cohort = GridCohortPrepareCommand.model_validate(
        {
            "idempotencyKey": str(UUID(int=1)),
            "mode": "screen+grid",
            "familyId": str(UUID(int=2)),
            "baseVersionId": str(UUID(int=3)),
            "selector": {"importJobId": str(UUID(int=4))},
            "recordings": [],
            "policyVersion": command["policyVersion"],
            "validationAssignments": assignments,
        }
    )
    assert len(cohort.validation_assignments) == 20_001
