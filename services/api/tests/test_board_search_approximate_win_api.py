from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_approximate_win import ApproximateWinDocument
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.main import create_app
from game_predictor_worker.domain.contracts import (
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration

_GAME_ID = uuid4()
_RULES_VERSION_ID = uuid4()


def _codes(known: tuple[int | None, ...]) -> tuple[int | None, ...]:
    return known + (None,) * (15 - len(known))


def _document(
    sequence_number: int,
    codes: tuple[int | None, ...],
    *,
    status: str = "pending",
) -> ApproximateWinDocument:
    return ApproximateWinDocument(
        sequence_number=sequence_number,
        status=status,
        board_checksum_sha256=f"{sequence_number:0>64}",
        mobile_codes=_codes(codes),
    )


def _configuration(*, rows: int = 3, columns: int = 5) -> RulesPayoutConfiguration:
    symbol_a = SymbolDefinition(
        mobile_code=1, code="A", name="Symbol A", is_wildcard=False, display_order=0
    )
    payline_top = PaylineDefinition(id="top", row_path=(0, 0, 0, 0, 0))
    payout_symbol_a = PayoutSymbolDefinition(symbol_mobile_code=1, minimum_match_length=2)
    payout_rules = tuple(
        PayoutRuleDefinition(symbol_mobile_code=1, match_length=length, payout_credits=credits)
        for length, credits in zip((2, 3, 4, 5), (5, 10, 25, 50), strict=True)
    )
    return RulesPayoutConfiguration(
        rules_version_id=_RULES_VERSION_ID,
        rules_game_id=_GAME_ID,
        version=3,
        status=RulesVersionStatus.PUBLISHED,
        rows=rows,
        columns=columns,
        spin_cost=20,
        symbols=(symbol_a,),
        paylines=(payline_top,),
        payout_symbols=(payout_symbol_a,),
        payout_rules=payout_rules,
    )


class MemoryBoardSearchApproximateWinRepository:
    def __init__(
        self,
        game_id: UUID,
        *,
        sequence_length: int = 1000,
        configuration: RulesPayoutConfiguration | None = None,
        documents: tuple[ApproximateWinDocument, ...] = (),
        asset_mode: BoardSearchAssetMode = BoardSearchAssetMode.OPERATIONAL_REVIEW,
    ) -> None:
        self.game_id = game_id
        self._sequence_length = sequence_length
        self._configuration = configuration
        self._documents_by_sequence = {document.sequence_number: document for document in documents}
        self._asset_mode = asset_mode
        self.range_calls: list[tuple[int, int]] = []

    def game_sequence_length(self, game_id: UUID) -> int:
        if game_id != self.game_id:
            raise BoardSearchError("GAME_NOT_FOUND", "The selected game does not exist.")
        return self._sequence_length

    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None:
        return self._configuration

    def range_documents(
        self,
        *,
        game_id: UUID,
        first_sequence_number: int,
        last_sequence_number: int,
    ) -> tuple[BoardSearchAssetMode, tuple[ApproximateWinDocument, ...]]:
        self.range_calls.append((first_sequence_number, last_sequence_number))
        documents = tuple(
            document
            for sequence_number, document in self._documents_by_sequence.items()
            if first_sequence_number <= sequence_number <= last_sequence_number
        )
        return self._asset_mode, documents


def _client(repository: MemoryBoardSearchApproximateWinRepository) -> TestClient:
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_approximate_win_service_dependency=(
            lambda: BoardSearchApproximateWinService(repository)
        ),
    )
    return TestClient(app)


def test_approximate_win_endpoint_returns_summary_completeness_and_rows() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID,
        sequence_length=100,
        configuration=_configuration(),
        documents=(
            # complete board (all 15 cells known); "top" payline scores 5
            # consecutive A's -> payout 50 (length-5 rule)
            _document(2, (1,) * 15, status="accepted"),
            # partial board: only the first two "top" cells are known ->
            # confirmed length-2 payout of 5
            _document(3, (1, 1)),
            # position 4 missing
        ),
    )

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 3},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["gameId"] == str(_GAME_ID)
    assert payload["startSequenceNumber"] == 1
    assert payload["startBoardStatus"] is None
    assert payload["requestedSpinCount"] == 3
    assert payload["evaluatedSpinCount"] == 3
    assert payload["sequenceLength"] == 100
    assert payload["wrappedAtSequenceEnd"] is False
    assert payload["dataSource"] == "operational_review"
    assert len(payload["dataFingerprintSha256"]) == 64
    assert payload["rules"] == {
        "rulesVersionId": str(_RULES_VERSION_ID),
        "rulesVersion": 3,
        "spinCost": 20,
        "algorithmVersion": "payout-v3-unknown-prefix-stop",
    }
    assert payload["summary"] == {
        "recognizedPayoutCredits": 55,
        "spinCostCredits": 60,
        "balanceCredits": -5,
    }
    assert payload["completeness"] == {
        "completeBoardCount": 1,
        "partialBoardCount": 1,
        "missingBoardCount": 1,
    }
    rows = payload["rows"]
    assert len(rows) == 2
    assert rows[0]["sequenceNumber"] == 2
    assert rows[0]["payoutCredits"] == 50
    assert rows[0]["payoutKind"] == "exact"
    assert rows[0]["boardStatus"] == "accepted"
    assert rows[1]["sequenceNumber"] == 3
    assert rows[1]["payoutCredits"] == 5
    assert rows[1]["payoutKind"] == "confirmed_minimum"
    # only one range call for an unwrapped, non-start-board lookup, plus one
    # single-position lookup for the start board's status
    assert repository.range_calls == [(2, 4), (1, 1)]


def test_approximate_win_endpoint_reports_pending_start_board_status() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID,
        sequence_length=100,
        configuration=_configuration(),
        documents=(_document(1, (), status="pending"),),
    )

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 1},
        )

    assert response.status_code == 200
    assert response.json()["startBoardStatus"] == "pending"


def test_approximate_win_endpoint_wraps_past_the_sequence_end_with_two_range_reads() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID, sequence_length=10, configuration=_configuration(), documents=()
    )

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 8, "spinCount": 5},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluatedSpinCount"] == 5
    assert payload["wrappedAtSequenceEnd"] is True
    # two contiguous range reads (9..10 and 1..3) plus the start-board lookup
    assert (9, 10) in repository.range_calls
    assert (1, 3) in repository.range_calls
    assert (8, 8) in repository.range_calls


def test_approximate_win_endpoint_requires_query_parameters() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(_GAME_ID, configuration=_configuration())

    with _client(repository) as client:
        missing_both = client.get(f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win")
        zero_spin_count = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 0},
        )
        too_large_spin_count = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 10_001},
        )

    assert missing_both.status_code == 422
    assert zero_spin_count.status_code == 422
    assert too_large_spin_count.status_code == 422


def test_approximate_win_endpoint_maps_start_out_of_range_to_conflict() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID, sequence_length=5, configuration=_configuration()
    )

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 10, "spinCount": 1},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "APPROXIMATE_WIN_START_OUT_OF_RANGE"


def test_approximate_win_endpoint_maps_missing_published_rules_to_conflict() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID, sequence_length=100, configuration=None
    )

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 1},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "APPROXIMATE_WIN_RULES_NOT_PUBLISHED"


def test_approximate_win_endpoint_maps_mismatched_board_dimensions_to_conflict() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID,
        sequence_length=100,
        configuration=_configuration(rows=3, columns=6),
    )

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 1},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "APPROXIMATE_WIN_RULES_INVALID"


def test_approximate_win_endpoint_maps_unrecognized_board_symbol_to_conflict() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID,
        sequence_length=100,
        configuration=_configuration(),
        documents=(_document(2, (999,)),),  # 999 is not a configured symbol
    )

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 1},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES"


def test_approximate_win_endpoint_maps_projection_incomplete_to_conflict() -> None:
    class RebuildingRepository(MemoryBoardSearchApproximateWinRepository):
        def range_documents(
            self, **_kwargs: object
        ) -> tuple[BoardSearchAssetMode, tuple[ApproximateWinDocument, ...]]:
            raise BoardSearchError(
                "BOARD_SEARCH_PROJECTION_INCOMPLETE",
                "The board-search projection is not ready for this game.",
            )

    repository = RebuildingRepository(_GAME_ID, sequence_length=100, configuration=_configuration())

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 1},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "BOARD_SEARCH_PROJECTION_INCOMPLETE"


def test_approximate_win_endpoint_does_not_find_results_in_an_empty_range() -> None:
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID, sequence_length=100, configuration=_configuration(), documents=()
    )

    with _client(repository) as client:
        response = client.get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 5},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == []
    assert payload["summary"]["recognizedPayoutCredits"] == 0
    assert payload["summary"]["spinCostCredits"] == 100
    assert payload["completeness"]["missingBoardCount"] == 5
