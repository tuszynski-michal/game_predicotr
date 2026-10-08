"""Contract coercion and exact compact-snapshot/pin regressions."""

from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.management_public_stakes import (
    create_management_public_stake_router,
)
from game_predictor_api.api.management_stakes import create_management_stake_router
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.domain.board_search import BoardSearchError
from game_predictor_api.domain.management_stakes import (
    ManagementSaveCommand,
    ManagementSearchCommand,
)
from game_predictor_api.schemas.board_search_approximate_win import to_approximate_win_response
from game_predictor_api.schemas.management_stakes import (
    ManagementJournalResponse,
    ManagementStakeResponse,
)
from game_predictor_api.storage.game_storage_routing import game_id_from_request
from game_predictor_api.storage.management_result_snapshots import (
    expand_result,
    freeze_result,
    pin_values,
)
from pydantic import ValidationError
from test_board_search_approximate_win_api import (
    _GAME_ID,
    MemoryBoardSearchApproximateWinRepository,
    _configuration,
    _document,
)


def test_compact_result_roundtrip_dedup_rules_start_and_exact_arbitrary_pins():
    configuration = _configuration()
    result = to_approximate_win_response(
        BoardSearchApproximateWinService(
            MemoryBoardSearchApproximateWinRepository(
                _GAME_ID,
                sequence_length=20,
                configuration=configuration,
                documents=(_document(3, (1,) * 15),),
            )
        ).calculate(game_id=_GAME_ID, start_sequence_number=1, requested_spin_count=8)
    )
    digest, payload, summary = freeze_result(result, configuration, ("A",) * 15, "a" * 64)
    assert expand_result(payload) == result
    assert isinstance(payload["rows"][0], list)
    assert freeze_result(result, configuration, ("A",) * 15, "a" * 64)[0] == digest
    assert freeze_result(result, configuration, (None,) * 15, "a" * 64)[0] != digest
    assert (
        freeze_result(result, replace(configuration, spin_cost=30), ("A",) * 15, "a" * 64)[0]
        != digest
    )
    assert summary["spinCost"] == 20
    assert len(summary["chartPoints"]) <= 256
    assert pin_values(payload, [0, 1, 2, 7, 9]) == [
        {
            "spinNumber": 0,
            "balanceCredits": 0,
            "available": True,
            "requiredStakeCredits": 0,
            "machineCashCredits": 0,
        },
        {
            "spinNumber": 1,
            "balanceCredits": -20,
            "available": True,
            "requiredStakeCredits": 20,
            "machineCashCredits": 0,
        },
        {
            "spinNumber": 2,
            "balanceCredits": 10,
            "available": True,
            "requiredStakeCredits": 40,
            "machineCashCredits": 50,
        },
        {
            "spinNumber": 7,
            "balanceCredits": -90,
            "available": True,
            "requiredStakeCredits": 90,
            "machineCashCredits": 0,
        },
        {
            "spinNumber": 9,
            "balanceCredits": -130,
            "available": False,
            "requiredStakeCredits": None,
            "machineCashCredits": None,
        },
    ]


def test_pins_allow_six_arbitrary_spins_and_forbid_client_results():
    body = dict(
        operation_id=uuid4(),
        expected_revision=0,
        search_context_id=uuid4(),
        start_sequence_number=1,
        spin_count=100000,
        pinned_spin_positions=(0, 7, 200, 4000, 8000, 99999),
    )
    assert ManagementSaveCommand(**body).pinned_spin_positions[-1] == 99999
    with pytest.raises(ValidationError):
        ManagementSaveCommand(**{**body, "pinned_spin_positions": (0, 1, 2, 3, 4, 5, 6)})
    with pytest.raises(ValidationError):
        ManagementSaveCommand(**{**body, "pinned_spin_positions": (7, 7)})
    with pytest.raises(ValidationError):
        ManagementSaveCommand(**{**body, "rows": []})


def test_actual_http_stake_enum_and_journal_query_coercion():
    machine, game = uuid4(), uuid4()

    class Service:
        def slot(self, machine_id, game_id, stake):
            return ManagementStakeResponse(
                machine_id=machine_id, game_id=game_id, stake_grosze=stake, revision=0, empty=True
            )

        def journal(self, machine_id, **options):
            assert options["stake"] == 2000
            return ManagementJournalResponse(entries=(), next_cursor=None)

    app = FastAPI()
    app.include_router(create_management_stake_router(lambda: Service()))
    with TestClient(app) as client:
        base = f"/api/v1/admin/management/machines/{machine}/game/{game}/stakes"
        for stake in (2000, 1000, 600, 400, 200, 120):
            assert client.get(f"{base}/{stake}").status_code == 200
        assert client.get(f"{base}/13").status_code == 422
        assert (
            client.get(
                f"/api/v1/admin/management/machines/{machine}/journal?stakeGrosze=2000"
            ).status_code
            == 200
        )


def test_original_search_pattern_includes_unknown_cells():
    command = ManagementSearchCommand(
        operation_id=uuid4(),
        stake_grosze=2000,
        cells=({"cellIndex": 0, "symbolCode": "A"}, {"cellIndex": 1, "symbolCode": "?"}),
        limit=17,
    )
    assert command.model_dump(by_alias=True)["cells"][1]["symbolCode"] == "?"


def test_management_history_queries_do_not_implicitly_route_unavailable_game_store():
    path = f"/api/v1/admin/management/machines/{uuid4()}/journal"
    assert game_id_from_request(path, {"gameId": str(uuid4())}) is None


def test_rules_snapshot_of_a_game_without_trigger_symbol_keeps_its_old_shape():
    """TASK-0932 adds `super_game_trigger_count` to symbol definitions; frozen
    snapshots (and so content digests) of games without a trigger symbol must
    not change, while a trigger symbol keeps its count in the snapshot."""

    configuration = _configuration()
    result = to_approximate_win_response(
        BoardSearchApproximateWinService(
            MemoryBoardSearchApproximateWinRepository(
                _GAME_ID, sequence_length=20, configuration=configuration
            )
        ).calculate(game_id=_GAME_ID, start_sequence_number=1, requested_spin_count=2)
    )
    _digest, payload, _summary = freeze_result(result, configuration, ("A",) * 15, "a" * 64)
    assert payload["rulesSnapshot"]["symbols"] == [
        {
            "mobile_code": 1,
            "code": "A",
            "name": "Symbol A",
            "is_wildcard": False,
            "display_order": 0,
        }
    ]

    trigger = replace(
        configuration,
        symbols=(replace(configuration.symbols[0], super_game_trigger_count=3),),
    )
    _digest, payload, _summary = freeze_result(result, trigger, ("A",) * 15, "a" * 64)
    assert payload["rulesSnapshot"]["symbols"][0]["super_game_trigger_count"] == 3


def test_public_management_routes_refuse_a_rules_version():
    """TASK-0932: the draft preview is Admin-only, never on the online panel."""

    machine, game = uuid4(), uuid4()
    calls: list[str] = []

    class Service:
        def preview(self, machine_id, game_id, start, count):
            calls.append("preview")
            raise AssertionError("A refused request must not calculate.")

        def detail(self, machine_id, game_id, sequence):
            calls.append("detail")
            raise AssertionError("A refused request must not read the board.")

    app = FastAPI()

    @app.exception_handler(BoardSearchError)
    async def _board_search_error(_request, error):  # type: ignore[no-untyped-def]
        return JSONResponse(status_code=422, content={"code": error.code})

    app.include_router(create_management_public_stake_router(lambda: Service()))
    base = f"/api/v1/management-public/machines/{machine}/game/{game}"
    responses = []
    with TestClient(app) as client:
        # Every spelling the share also refuses, compared case-insensitively.
        for name in ("rulesVersionId", "rules_version_id", "RULES_VERSION_ID"):
            rules_version = f"{name}={uuid4()}"
            responses.append(
                client.get(
                    f"{base}/approximate-win?startSequenceNumber=1&spinCount=5&{rules_version}"
                )
            )
            responses.append(client.get(f"{base}/boards/42?{rules_version}"))
    assert len(responses) == 6
    for response in responses:
        assert response.status_code == 422, response.text
        assert response.json() == {"code": "BOARD_SEARCH_RULES_VERSION_NOT_ALLOWED"}
    assert calls == []
