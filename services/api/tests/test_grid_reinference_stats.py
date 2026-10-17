"""Statistics are observations, never inferred repairs or retroactive policy upgrades."""

import copy
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.grid_reinference import digest
from game_predictor_api.application.grid_reinference_stats import (
    STATS_POLICY,
    cell_effects,
    empty_effect,
    empty_scope,
    frozen_target_counts,
    refresh_effect_gap,
    stats_enabled,
)
from game_predictor_api.domain.jobs import JobConflictError, JobStatus
from game_predictor_api.storage import grid_reinference as storage
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceOperationModel as Operation,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.mark.parametrize(
    "document,payload,expected",
    [
        ({}, {}, False),
        ({"statsPolicy": STATS_POLICY}, {"stats_policy": STATS_POLICY}, True),
        ({"statsPolicy": STATS_POLICY}, {}, None),
        ({}, {"stats_policy": STATS_POLICY}, None),
        ({"statsPolicy": None}, {"stats_policy": None}, None),
        ({"statsPolicy": "future"}, {"stats_policy": "future"}, None),
        ({"statsPolicy": STATS_POLICY}, {"stats_policy": "different"}, None),
    ],
)
def test_policy_pin_is_closed_and_never_upgrades_legacy(document, payload, expected):
    before = copy.deepcopy((document, payload))
    if expected is None:
        with pytest.raises(JobConflictError, match="statistics policy"):
            stats_enabled(document, payload)
    else:
        assert stats_enabled(document, payload) is expected
    assert before == (document, payload)


def test_current_frozen_population_differs_from_slot_capacity():
    board = {"id": "board", "geometry_revision": 2, "source_geometry_revision_id": "source-rev"}

    def cell(index, **values):
        return {
            "id": str(index),
            "cell_index": index,
            "geometry_revision": 2,
            "source_geometry_revision_id": "source-rev",
            "source_available": True,
            **values,
        }

    snapshot = {
        "kind": "grid_issue",
        "board": board,
        "cells": [
            cell(0),
            cell(0),
            cell(1, source_available=False),
            cell(2, geometry_revision=1),
        ],
    }
    counts = frozen_target_counts(snapshot, cell_capacity=15, protected=False)
    assert counts["existingBoardCount"] == counts["proposalOnlySlotCount"] == 1
    assert counts["existingCellCount"] == 2 and counts["availableCellCount"] == 1
    assert counts["potentialCellCount"] == 15
    assert counts["automaticCandidateSlotCount"] == counts["protectedSlotCount"] == 0
    deferred = frozen_target_counts(
        {"kind": "deferred", "board": None, "cells": []}, cell_capacity=15, protected=True
    )
    assert deferred["deferredSlotCount"] == deferred["protectedSlotCount"] == 1
    assert deferred["existingCellCount"] == deferred["existingBoardCount"] == 0


def observation(pixels, review="approved"):
    return {"pixels": pixels, "available": True, "verification": None, "review": review}


def test_actual_effects_keep_new_changed_unknown_and_review_overlap_separate():
    effect = cell_effects(
        {0: observation("a"), 1: observation("b"), 2: observation(None), 4: observation("d")},
        {
            0: observation("a"),
            1: observation("c", "pending"),
            2: observation("c"),
            3: observation("new", "pending"),
        },
        created_board=False,
    )
    assert effect == {
        **empty_effect(),
        "recordedTargetCount": 1,
        "automaticWrittenBoardCount": 1,
        "createdCellCount": 1,
        "changedExistingPixelCellCount": 1,
        "unchangedExistingPixelCellCount": 1,
        "newlyRequiresReviewCellCount": 2,
        "pixelComparisonUnavailableCellCount": 2,
    }
    assert (
        cell_effects({}, {0: observation("new", "pending")}, created_board=True)[
            "createdBoardCount"
        ]
        == 1
    )


@pytest.mark.parametrize("new", [False, True])
def test_terminal_report_keeps_exact_old_hash_branch_and_new_pin(monkeypatch, new):
    document = {
        "phase": "infer",
        "sourceCount": 1,
        "processedSources": 1,
        "state": "running",
        "manifestSha256": "a" * 64,
        "outcomes": {"unchanged": 2},
        "sourceStatusCounts": {"not_evaluated": 1},
    }
    payload = {}
    if new:
        document.update(
            statsPolicy=STATS_POLICY,
            scopeStats=empty_scope(),
            targetCount=2,
            effectStats={**empty_effect(), "recordedTargetCount": 2, "notRecordedTargetCount": 99},
        )
        payload["stats_policy"] = STATS_POLICY
    operation = SimpleNamespace(document=copy.deepcopy(document))
    session = SimpleNamespace(scalar=lambda *_: operation)
    monkeypatch.setattr(storage, "is_grid_reinference", lambda _: True)
    monkeypatch.setattr(storage.GameStorageRouter, "bind", lambda *_args, **_kwargs: None)
    job = SimpleNamespace(
        game_id=uuid4(), id=uuid4(), status=JobStatus.COMPLETED, input_payload=payload
    )
    expected = {
        "manifest": document["manifestSha256"],
        "outcomes": document["outcomes"],
        "processed": 1,
        "sourceStatusCounts": document["sourceStatusCounts"],
    }
    if new:
        expected.update(
            statsPolicy=STATS_POLICY,
            scopeStats=document["scopeStats"],
            effectStats={**document["effectStats"], "notRecordedTargetCount": 0},
        )
    storage.synchronize_grid_job(session, job)
    assert operation.document["reportSha256"] == digest(expected)
    before = copy.deepcopy(operation.document)
    storage.synchronize_grid_job(session, job)
    assert operation.document == before
    if not new:
        assert "statsPolicy" not in operation.document and "effectStats" not in operation.document


@pytest.mark.parametrize("status", [JobStatus.FAILED, JobStatus.CANCELLED])
@pytest.mark.parametrize("pin", [STATS_POLICY, "unsupported"])
def test_invalid_pin_can_fail_terminally_without_publishing_stats_or_report(
    monkeypatch, status, pin
):
    document = {
        "phase": "infer",
        "state": "running",
        "statsPolicy": pin,
        "manifestSha256": "a" * 64,
        "targetCount": 3,
        "effectStats": {"untouched": True},
        "reportSha256": None,
    }
    operation = SimpleNamespace(document=copy.deepcopy(document))
    session = SimpleNamespace(scalar=lambda *_: operation)
    monkeypatch.setattr(storage, "is_grid_reinference", lambda _: True)
    monkeypatch.setattr(storage.GameStorageRouter, "bind", lambda *_args, **_kwargs: None)
    job = SimpleNamespace(
        game_id=uuid4(),
        id=uuid4(),
        status=status,
        input_payload={},
        error_code="GRID_REINFERENCE_PAYLOAD_INVALID",
    )
    storage.synchronize_grid_job(session, job)
    assert operation.document == {**document, "state": status.value}


@pytest.mark.parametrize("status", [JobStatus.FAILED, JobStatus.CANCELLED])
def test_not_recorded_gap_survives_partial_terminal_transition(monkeypatch, status):
    effect = {**empty_effect(), "recordedTargetCount": 1, "automaticWrittenBoardCount": 1}
    document = {
        "phase": "infer",
        "state": "running",
        "statsPolicy": STATS_POLICY,
        "targetCount": 3,
        "manifestSha256": "a" * 64,
        "effectStats": effect,
        "reportSha256": None,
    }
    operation = SimpleNamespace(document=copy.deepcopy(document))
    session = SimpleNamespace(scalar=lambda *_: operation)
    monkeypatch.setattr(storage, "is_grid_reinference", lambda _: True)
    monkeypatch.setattr(storage.GameStorageRouter, "bind", lambda *_args, **_kwargs: None)
    job = SimpleNamespace(
        game_id=uuid4(),
        id=uuid4(),
        status=status,
        input_payload={"stats_policy": STATS_POLICY},
        error_code="CONTROLLED_FAILURE",
    )
    storage.synchronize_grid_job(session, job)
    assert operation.document["effectStats"] == {**effect, "notRecordedTargetCount": 2}
    assert operation.document["reportSha256"] is None


def test_not_recorded_gap_is_current_not_additive_and_does_not_upgrade_legacy():
    document = {
        "statsPolicy": STATS_POLICY,
        "manifestSha256": "a" * 64,
        "targetCount": 3,
        "effectStats": empty_effect(),
    }
    refresh_effect_gap(document)
    assert document["effectStats"]["notRecordedTargetCount"] == 3
    document["effectStats"]["recordedTargetCount"] = 1
    refresh_effect_gap(document)
    assert document["effectStats"]["notRecordedTargetCount"] == 2
    before = copy.deepcopy(document)
    refresh_effect_gap(document)  # Replay/resume does not increment the gap.
    assert document == before
    document["effectStats"]["recordedTargetCount"] = 3
    refresh_effect_gap(document)
    assert document["effectStats"]["notRecordedTargetCount"] == 0
    for incomplete in [{}, {"statsPolicy": STATS_POLICY, "manifestSha256": None}]:
        prior = copy.deepcopy(incomplete)
        refresh_effect_gap(incomplete)
        assert incomplete == prior


@pytest.mark.parametrize("recorded", [-1, 4])
def test_not_recorded_gap_rejects_inconsistent_counts_without_clamping(recorded):
    document = {
        "statsPolicy": STATS_POLICY,
        "manifestSha256": "a" * 64,
        "targetCount": 3,
        "effectStats": {**empty_effect(), "recordedTargetCount": recorded},
    }
    before = copy.deepcopy(document)
    with pytest.raises(JobConflictError) as error:
        refresh_effect_gap(document)
    assert error.value.code == "GRID_REINFERENCE_STATS_INVALID"
    assert document == before


@pytest.fixture
def history(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE grid_reinference_operations (
          game_id CHAR(32), id CHAR(32), idempotency_key CHAR(32), command_sha256 VARCHAR(64),
          job_id CHAR(32), document JSON, PRIMARY KEY(game_id,id))""")
    with Session(engine) as session:
        game, other = uuid4(), uuid4()
        for number in range(1, 65):
            session.add(
                Operation(
                    game_id=game,
                    id=UUID(int=number),
                    idempotency_key=uuid4(),
                    command_sha256="a" * 64,
                    job_id=uuid4(),
                    document={
                        "operationId": str(UUID(int=number)),
                        "scopeSignature": "same" if number != 5 else "other",
                        "executionScope": "pilot" if number != 4 else "broader",
                        "state": "completed" if number != 3 else "failed",
                        "sourceCount": 101 if number == 2 else 100,
                        "reportSha256": None if number == 1 else "a" * 64,
                    },
                )
            )
        session.add(
            Operation(
                game_id=other,
                id=UUID(int=999),
                idempotency_key=uuid4(),
                command_sha256="a" * 64,
                job_id=uuid4(),
                document={},
            )
        )
        session.commit()
        repository = storage.SqlAlchemyGridReinferenceRepository(session, Path.cwd())
        monkeypatch.setattr(repository, "bind", lambda *_args, **_kwargs: None)
        yield repository, game, other
    engine.dispose()


def test_history_keyset_and_compatible_pilot_filter_are_game_scoped(history):
    repository, game, other = history
    first = repository.list_operations(game, None, 50)
    second = repository.list_operations(game, first["nextCursor"], 50)
    ids = [item["operationId"] for item in first["items"] + second["items"]]
    assert ids == [str(UUID(int=n)) for n in range(64, 0, -1)]
    assert second["nextCursor"] is None
    for options in [(other, None), (game, UUID(int=64))]:
        with pytest.raises(JobConflictError) as error:
            repository.list_operations(options[0], first["nextCursor"], 50, options[1])
        assert error.value.code == "GRID_REINFERENCE_CURSOR_INVALID"
    pilots = repository.list_operations(game, None, 50, UUID(int=64))
    remaining = repository.list_operations(game, pilots["nextCursor"], 50, UUID(int=64))
    compatible = pilots["items"] + remaining["items"]
    assert len(compatible) == 59 and all(UUID(row["operationId"]).int > 5 for row in compatible)
    with pytest.raises(JobConflictError) as error:
        repository.list_operations(other, None, 50, UUID(int=64))
    assert error.value.code == "GRID_REINFERENCE_NOT_FOUND"


def test_http_history_closed_response_and_bounded_query():
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from game_predictor_api.api.grid_reinference import register_grid_reinference_routes

    game, operation = uuid4(), uuid4()
    calls = []

    def listing(*arguments):
        calls.append(arguments)
        return {
            "items": [
                {
                    "gameId": str(game),
                    "operationId": str(operation),
                    "jobId": str(uuid4()),
                    "state": "prepared",
                    "phase": "prepare",
                    "revision": 1,
                    "manifestSha256": "a" * 64,
                    "reportSha256": None,
                    "sourceCount": 1,
                    "targetCount": 2,
                    "processedSources": 0,
                    "outcomes": {},
                    "modelSnapshot": {},
                    "runtimePolicy": "grid-reinference-runtime-v1",
                    "acceptancePolicy": "v3-engine-acceptance-v1",
                    "membershipCapturedAt": "capture",
                    "preparationStartedAt": "begin",
                    "preparationFinishedAt": "end",
                    "executionScope": "broader",
                    "selector": {"categories": ["grid_issue", "deferred"]},
                    "statsPolicy": STATS_POLICY,
                    "scopeStats": empty_scope(),
                    "effectStats": empty_effect(),
                    "executionQuarantine": None,
                    "pilotAcknowledgement": None,
                }
            ],
            "nextCursor": None,
        }

    app, router = FastAPI(), APIRouter()
    register_grid_reinference_routes(
        router, lambda: SimpleNamespace(grid_reinference=SimpleNamespace(list_operations=listing))
    )
    app.include_router(router)
    with TestClient(app) as client:
        path = f"/grid-reinference/{game}/operations"
        response = client.get(
            path,
            params={
                "limit": 50,
                "cursor": "cursor",
                "compatible_with_operation_id": str(operation),
            },
        )
        assert response.status_code == 200
        assert calls == [(game, "cursor", 50, operation)]
        assert response.json()["items"][0]["scopeStats"] == empty_scope()
        assert client.get(path, params={"limit": 51}).status_code == 422
        assert len(calls) == 1
