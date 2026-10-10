"""Super game series payouts and per-position cost in the Admin forecast (TASK-0936).

The approximate-win range, the single-board detail (modal) and the frozen
management stake results evaluate positions inside a published
``wild_super_spins`` series with the series board evaluation (expansion of the
super symbol, free spin) and sum the spin cost per position.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.application.board_search_board_detail import (
    BoardSearchBoardDetailService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search_approximate_win import (
    ApproximateWinDocument,
    ApproximateWinSpinEvaluation,
    calculate_approximate_win,
)
from game_predictor_api.domain.board_search_board_detail import PaylineLabel
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.sequence_mode_projection import (
    PositionMode,
    SequenceMode,
    SequenceModeProjection,
)
from game_predictor_api.domain.super_game_markers import (
    SuperGameMarker,
    SuperGameMarkers,
    marker_for_position,
)
from game_predictor_api.domain.super_game_series import (
    RunVerification,
    SeriesCompleteness,
    SuperGameState,
)
from game_predictor_api.main import create_app
from game_predictor_api.schemas.board_search_approximate_win import to_approximate_win_response
from game_predictor_api.storage.management_result_snapshots import (
    expand_result,
    freeze_result,
    pin_values,
)
from game_predictor_worker.domain.contracts import (
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration
from test_board_search_approximate_win_api import MemoryBoardSearchApproximateWinRepository
from test_board_search_board_detail_api import (
    _GAME_ID as DETAIL_GAME_ID,
)
from test_board_search_board_detail_api import (
    MemoryBoardDetailRepository,
    _document,
)

_FIXTURE = Path(__file__).parents[3] / "packages" / "domain-fixtures" / "payout-golden-cases.json"
GAME_ID = UUID(int=0x3036)
RULES_VERSION_ID = UUID(int=0x30361)
SPIN_COST = 100

# Boards of the golden `wildSuperSpinsScenario` (codes: 1=10, 2=J, 3=Q, 4=K,
# 5=A, 6=Sarkofag, 7=Mumia Wild + trigger 3).
WORKED_EXAMPLE = (1, 4, 2, 3, 5, 2, 3, 5, 4, 1, 3, 5, 1, 2, 4)  # K expands: 50
COVERED_A_LINE = (1, 4, 2, 4, 3, 5, 5, 5, 3, 4, 3, 2, 1, 2, 1)  # base 15, K: 50
TRIGGER_BOARD = (7, 4, 1, 4, 2, 1, 3, 7, 3, 4, 7, 5, 3, 7, 1)  # base: Q x4 16 + 200
BASE_A_LINE = (1, 4, 2, 3, 5, 5, 5, 5, 4, 1, 3, 2, 1, 2, 3)  # A x3 = 15
UNKNOWN_CELL = (1, 4, 2, 3, 5, 5, 5, 5, 4, 1, 3, 2, 1, 2, None)  # k = 2 + unknown


def _scenario() -> Mapping[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))["wildSuperSpinsScenario"]  # type: ignore[no-any-return]


def _configuration(game_id: UUID = GAME_ID) -> RulesPayoutConfiguration:
    scenario = _scenario()
    return RulesPayoutConfiguration(
        rules_version_id=RULES_VERSION_ID,
        rules_game_id=game_id,
        version=1,
        status=RulesVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
        spin_cost=SPIN_COST,
        symbols=tuple(
            SymbolDefinition(
                mobile_code=symbol["mobileCode"],
                code=symbol["code"],
                name=symbol["name"],
                is_wildcard=symbol["isWildcard"],
                display_order=symbol["displayOrder"],
                super_game_trigger_count=symbol["superGameTriggerCount"],
            )
            for symbol in scenario["game"]["symbols"]
        ),
        paylines=tuple(
            PaylineDefinition(id=payline["id"], row_path=tuple(payline["rowPath"]))
            for payline in scenario["paylines"]
        ),
        payout_symbols=tuple(
            PayoutSymbolDefinition(
                symbol_mobile_code=value["symbolMobileCode"],
                minimum_match_length=value["minimumMatchLength"],
            )
            for value in scenario["payoutSymbols"]
        ),
        payout_rules=tuple(
            PayoutRuleDefinition(
                symbol_mobile_code=value["symbolMobileCode"],
                match_length=value["matchLength"],
                payout_credits=value["payoutCredits"],
            )
            for value in scenario["payoutRules"]
        ),
    )


def _range_document(sequence_number: int, codes: tuple[int | None, ...]) -> ApproximateWinDocument:
    return ApproximateWinDocument(
        sequence_number=sequence_number,
        status="accepted",
        board_checksum_sha256=f"{sequence_number:0>64}",
        mobile_codes=codes,
    )


class SeriesMarkers:
    """A published generation of ``wild_super_spins`` series in memory."""

    def __init__(
        self,
        series: tuple[tuple[int, int, str | None], ...],
        *,
        fresh: bool = True,
        kind_code: str = "wild_super_spins",
    ) -> None:
        self._series = series
        self._state = SuperGameState(
            input_version=5, generation_input_version=5 if fresh else 4, has_super_game=True
        )
        self._kind_code = kind_code
        self.calls: list[tuple[int, ...]] = []

    def markers(self, game_id: UUID, positions: Collection[int]) -> SuperGameMarkers:
        self.calls.append(tuple(sorted(positions)))
        found: dict[int, SuperGameMarker] = {}
        for position in positions:
            for index, (trigger, length, symbol) in enumerate(self._series):
                marker = marker_for_position(
                    position=position,
                    series_id=UUID(int=index + 1),
                    trigger_sequence_number=trigger,
                    series_length=length,
                    super_symbol_code=symbol,
                    completeness=SeriesCompleteness.COMPLETE,
                    run_verification=RunVerification.VERIFIED,
                )
                if marker is not None:
                    found[position] = marker
        return SuperGameMarkers(
            state=self._state, by_position=MappingProxyType(found), kind_code=self._kind_code
        )


def _range_service(
    markers: SeriesMarkers, documents: tuple[ApproximateWinDocument, ...]
) -> BoardSearchApproximateWinService:
    return BoardSearchApproximateWinService(
        MemoryBoardSearchApproximateWinRepository(
            GAME_ID, sequence_length=200, configuration=_configuration(), documents=documents
        ),
        markers,
    )


# --- domain: per-position cost and provisional summary ----------------------


def _flat_evaluate(_cells: object) -> int:
    return 30


def test_projection_without_a_super_game_kind_is_base_mode_with_the_rules_cost() -> None:
    markers = SeriesMarkers(((10, 10, "K"),), kind_code="none").markers(GAME_ID, {11})
    projection = SequenceModeProjection(markers=markers, spin_cost=SPIN_COST)
    mode = projection.at(11)
    assert (mode.mode, mode.spin_cost_credits, mode.super_symbol_code) == (
        SequenceMode.BASE,
        SPIN_COST,
        None,
    )


def test_projection_marks_series_spins_free_and_keeps_the_trigger_in_base_mode() -> None:
    markers = SeriesMarkers(((10, 10, "K"),)).markers(GAME_ID, set(range(9, 23)))
    projection = SequenceModeProjection(markers=markers, spin_cost=SPIN_COST)
    assert projection.at(10).mode is SequenceMode.BASE
    assert projection.at(10).spin_cost_credits == SPIN_COST
    first = projection.at(11)
    assert (first.mode, first.spin_cost_credits, first.super_symbol_code) == (
        SequenceMode.SUPER,
        0,
        "K",
    )
    assert first.remaining_spins == 9
    assert projection.at(20).remaining_spins == 0
    assert projection.at(21).mode is SequenceMode.BASE


def test_domain_sums_cost_per_position_and_provisional_apart() -> None:
    markers = SeriesMarkers(((3, 2, None),)).markers(GAME_ID, set(range(2, 8)))
    projection = SequenceModeProjection(markers=markers, spin_cost=10)

    def evaluate_super(_cells: object, mode: PositionMode) -> ApproximateWinSpinEvaluation:
        assert mode.is_super
        return ApproximateWinSpinEvaluation(payout_credits=40, payout_kind="provisional")

    documents = tuple(
        _range_document(sequence, WORKED_EXAMPLE) for sequence in (2, 3, 4, 6)
    )  # position 5 (in series) is missing
    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=6,
        sequence_length=50,
        documents=documents,
        evaluate=_flat_evaluate,
        spin_cost=10,
        modes=projection,
        evaluate_super=evaluate_super,
    )
    # Positions 2..7: 3 (trigger) and 2, 6, 7 cost 10; 4 and 5 are free spins.
    assert result.summary.spin_cost_credits == 40
    assert result.summary.provisional_count == 1
    assert result.summary.provisional_payout_credits == 40
    # Base boards 2, 3 and 6 pay 30 each; the provisional 40 is not recognized.
    assert result.summary.recognized_payout_credits == 90
    assert result.summary.balance_credits == 50
    assert result.completeness.missing_board_count == 2
    assert result.super_spin_ranges == ((3, 4),)
    rows = {row.sequence_number: row for row in result.rows}
    assert rows[4].payout_kind == "provisional"
    assert (rows[4].mode, rows[4].spin_cost_credits) == (SequenceMode.SUPER, 0)
    assert (rows[3].mode, rows[3].spin_cost_credits) == (SequenceMode.BASE, 10)
    # The provisional row does not move the cumulative payout.
    assert rows[4].cumulative_payout_credits == rows[3].cumulative_payout_credits


# --- application: the range with the series board evaluation -----------------


def _range(markers: SeriesMarkers, documents: tuple[ApproximateWinDocument, ...]) -> Any:
    calculation = _range_service(markers, documents).calculate(
        game_id=GAME_ID, start_sequence_number=1, requested_spin_count=50
    )
    return to_approximate_win_response(calculation)


def test_series_spins_cost_nothing_and_the_trigger_costs_the_rules_spin_cost() -> None:
    markers = SeriesMarkers(((10, 10, "K"), (40, 10, None)))
    documents = (
        _range_document(10, TRIGGER_BOARD),
        _range_document(11, WORKED_EXAMPLE),
        _range_document(13, UNKNOWN_CELL),
        _range_document(25, BASE_A_LINE),
        _range_document(41, COVERED_A_LINE),
    )
    response = _range(markers, documents)

    # Positions 2..51: 11..20 and 41..50 are free spins, 30 positions pay 100.
    assert response.summary.spin_cost_credits == 30 * SPIN_COST
    rows = {row.sequence_number: row for row in response.rows}
    # The trigger board is base mode: no expansion; line D pays Q x4 = 16
    # (Mumia as Wild) and its 4 Mumias pay 200.
    assert (rows[10].mode, rows[10].spin_cost_credits, rows[10].payout_kind) == (
        "base",
        SPIN_COST,
        "exact",
    )
    assert rows[10].payout_credits == 216
    # The worked example of the plan: K expands over 3 columns, 10 x 5 = 50.
    assert (rows[11].mode, rows[11].spin_cost_credits, rows[11].payout_kind) == (
        "super",
        0,
        "exact",
    )
    assert rows[11].payout_credits == 50
    # An unknown cell makes a series board provisional.
    assert rows[13].payout_kind == "provisional"
    assert rows[13].payout_credits == 15
    # A series without a super symbol: lines with Wild only, provisional.
    assert rows[41].payout_kind == "provisional"
    assert rows[41].payout_credits == 15
    assert rows[25].payout_kind == "exact"
    assert response.summary.provisional_count == 2
    assert response.summary.provisional_payout_credits == 30
    assert response.summary.recognized_payout_credits == 216 + 50 + 15
    assert response.summary.balance_credits == 281 - 30 * SPIN_COST
    # The provisional payouts never enter the cumulative payout.
    assert rows[41].cumulative_payout_credits == rows[25].cumulative_payout_credits
    # One marker read for every evaluated position.
    assert markers.calls == [tuple(range(2, 52))]


def test_a_stale_generation_makes_every_board_of_the_game_provisional() -> None:
    """Lead decision after the audit (plan): with `fresh = false` a new
    trigger may already have put a base-mode board into a series, so every
    evaluated board is provisional, not only series boards."""

    markers = SeriesMarkers(((10, 10, "K"),), fresh=False)
    response = _range(
        markers, (_range_document(11, WORKED_EXAMPLE), _range_document(25, BASE_A_LINE))
    )
    rows = {row.sequence_number: row for row in response.rows}
    assert (rows[11].mode, rows[11].payout_kind, rows[11].payout_credits) == (
        "super",
        "provisional",
        50,
    )
    assert (rows[25].mode, rows[25].payout_kind, rows[25].payout_credits) == (
        "base",
        "provisional",
        15,
    )
    assert response.summary.recognized_payout_credits == 0
    assert response.summary.provisional_count == 2
    assert response.summary.provisional_payout_credits == 65
    # The cost per position is unchanged by staleness.
    assert response.summary.spin_cost_credits == 40 * SPIN_COST
    assert response.super_game_state is not None
    assert response.super_game_state.fresh is False


def test_a_stale_generation_makes_a_base_board_detail_provisional() -> None:
    payload = _detail(BASE_A_LINE, SeriesMarkers(((100, 10, "K"),), fresh=False))
    assert (payload["mode"], payload["payoutKind"], payload["payoutCredits"]) == (
        "base",
        "provisional",
        15,
    )
    fresh = _detail(BASE_A_LINE, SeriesMarkers(((100, 10, "K"),)))
    assert (fresh["mode"], fresh["payoutKind"]) == ("base", "exact")


def test_the_summary_exposes_the_free_spin_ranges() -> None:
    response = _range(SeriesMarkers(((10, 10, "K"), (40, 10, None))), ())
    assert [(value.start_spin, value.end_spin) for value in response.summary.super_spin_ranges] == [
        (10, 19),
        (40, 49),
    ]
    assert response.summary.super_spin_cost == 0
    # Without a super game kind there are no ranges.
    plain = _range(SeriesMarkers(((10, 10, "K"),), kind_code="none"), ())
    assert plain.summary.super_spin_ranges == ()


def test_defining_the_super_symbol_can_lower_a_provisional_result() -> None:
    larger_win = (1, 1, 1, 2, 3, 5, 5, 5, 5, 5, 3, 2, 4, 3, 2)  # 65 without a symbol
    undefined = _range(SeriesMarkers(((10, 10, None),)), (_range_document(11, larger_win),))
    defined = _range(SeriesMarkers(((10, 10, "10"),)), (_range_document(11, larger_win),))
    assert undefined.rows[0].payout_kind == "provisional"
    assert undefined.rows[0].payout_credits == 65
    assert defined.rows[0].payout_kind == "exact"
    assert defined.rows[0].payout_credits == 25


def test_a_series_board_fingerprint_depends_on_the_super_symbol() -> None:
    documents = (_range_document(11, WORKED_EXAMPLE),)
    first = _range(SeriesMarkers(((10, 10, "K"),)), documents)
    second = _range(SeriesMarkers(((10, 10, None),)), documents)
    assert first.data_fingerprint_sha256 != second.data_fingerprint_sha256


def test_the_http_range_carries_mode_cost_and_provisional_summary() -> None:
    markers = SeriesMarkers(((10, 10, None),))
    repository = MemoryBoardSearchApproximateWinRepository(
        GAME_ID,
        sequence_length=200,
        configuration=_configuration(),
        documents=(_range_document(11, COVERED_A_LINE),),
    )
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_approximate_win_service_dependency=(
            lambda: BoardSearchApproximateWinService(repository, markers)
        ),
    )
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/admin/games/{GAME_ID}/board-search/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 20},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["provisionalCount"] == 1
    assert payload["summary"]["provisionalPayoutCredits"] == 15
    assert payload["summary"]["spinCostCredits"] == 10 * SPIN_COST
    row = payload["rows"][0]
    assert (row["mode"], row["spinCostCredits"], row["payoutKind"]) == ("super", 0, "provisional")


# --- frozen management results ------------------------------------------------


def test_frozen_result_keeps_the_free_spins_for_pins_and_rows() -> None:
    markers = SeriesMarkers(((10, 10, "K"),))
    calculation = _range_service(
        markers,
        (_range_document(10, TRIGGER_BOARD), _range_document(11, WORKED_EXAMPLE)),
    ).calculate(game_id=GAME_ID, start_sequence_number=1, requested_spin_count=30)
    response = to_approximate_win_response(calculation)
    configuration = _configuration()
    digest, payload, summary = freeze_result(response, configuration, (None,) * 15, "a" * 64)
    frozen_summary = payload["calculation"]["summary"]  # type: ignore[index]
    assert frozen_summary["superSpinRanges"] == [{"startSpin": 10, "endSpin": 19}]
    assert frozen_summary["superSpinCost"] == 0
    assert summary["summary"]["superSpinRanges"] == [  # type: ignore[index]
        {"startSpin": 10, "endSpin": 19}
    ]
    expanded = expand_result(payload)
    assert expanded.rows == tuple(
        # Frozen rows keep format 1: no markers and no count-match breakdown.
        row.model_copy(update={"super_game": None, "count_matches": ()})
        for row in response.rows
    )
    assert expanded.summary == response.summary
    assert summary["summary"]["spinCostCredits"] == 20 * SPIN_COST
    # Spin 9 is the trigger (position 10), spins 10..19 are free.
    pins = pin_values(payload, [9, 15, 19, 20])
    assert [pin["balanceCredits"] for pin in pins] == [
        216 - 9 * SPIN_COST,
        266 - 9 * SPIN_COST,
        266 - 9 * SPIN_COST,
        266 - 10 * SPIN_COST,
    ]
    assert len(digest) == 64


def test_frozen_provisional_rows_do_not_jump_the_chart() -> None:
    markers = SeriesMarkers(((10, 10, None),))
    calculation = _range_service(markers, (_range_document(11, COVERED_A_LINE),)).calculate(
        game_id=GAME_ID, start_sequence_number=1, requested_spin_count=12
    )
    response = to_approximate_win_response(calculation)
    _digest, payload, summary = freeze_result(response, _configuration(), (None,) * 15, "a" * 64)
    assert payload["calculation"]["summary"]["provisionalCount"] == 1  # type: ignore[index]
    points = summary["chartPoints"]
    assert isinstance(points, list)
    balances = {point["balanceCredits"] for point in points if point["spinNumber"] == 10}
    assert len(balances) == 1


# --- board detail (modal) -----------------------------------------------------


class SeriesBoardDetailRepository(MemoryBoardDetailRepository):
    def payline_labels(self, rules_version_id: UUID) -> Mapping[str, PaylineLabel]:
        return {
            payline["id"]: PaylineLabel(
                payline["id"],
                payline["id"],
                f"Linia {payline['id']}",
                index,
                tuple(payline["rowPath"]),
            )
            for index, payline in enumerate(_scenario()["paylines"])
        }

    def symbol_codes(self, game_id: UUID) -> Mapping[int, str]:
        return {symbol["mobileCode"]: symbol["code"] for symbol in _scenario()["game"]["symbols"]}


def _detail(
    codes: tuple[int | None, ...], markers: SeriesMarkers | None, sequence_number: int = 42
) -> Any:
    repository = SeriesBoardDetailRepository(
        document=_document(codes, sequence_number=sequence_number),
        configuration=_configuration(DETAIL_GAME_ID),
    )
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_board_detail_service_dependency=(
            lambda: BoardSearchBoardDetailService(repository, markers)
        ),
    )
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/admin/games/{DETAIL_GAME_ID}/board-search/boards/{sequence_number}"
        )
    assert response.status_code == 200, response.text
    return response.json()


def test_series_board_detail_returns_the_expanded_board_and_the_expansion_entry() -> None:
    payload = _detail(WORKED_EXAMPLE, SeriesMarkers(((40, 10, "K"),)))
    assert payload["mode"] == "super"
    assert payload["spinCostCredits"] == 0
    assert payload["payoutCredits"] == 50
    assert payload["payoutKind"] == "exact"
    assert payload["expansion"] == {
        "symbolCode": "K",
        "columns": [1, 3, 4],
        "columnCount": 3,
        "linePayoutCredits": 10,
        "paylineCount": 5,
        "payoutCredits": 50,
    }
    expanded = payload["expandedSymbolCodes"]
    assert [expanded[row * 5 + 1] for row in range(3)] == ["K", "K", "K"]
    # symbolCodes stays the original board.
    assert payload["symbolCodes"][6] == "Q"
    assert payload["matches"] == []


def test_series_board_detail_counts_trigger_symbols_on_the_original_board() -> None:
    payload = _detail(TRIGGER_BOARD, SeriesMarkers(((40, 10, "K"),)))
    assert payload["countMatches"] == [
        {"symbolCode": "MUMIA", "count": 4, "cells": [0, 7, 10, 13], "payoutCredits": 200}
    ]
    assert payload["payoutCredits"] == 250
    # Cell 13 holds a Mumia, but the expanded board shows K in column 4.
    assert payload["expandedSymbolCodes"][13] == "K"
    assert payload["symbolCodes"][13] == "MUMIA"


def test_series_board_without_a_super_symbol_is_provisional_even_without_a_payout() -> None:
    payload = _detail(WORKED_EXAMPLE, SeriesMarkers(((40, 10, None),)))
    assert (payload["mode"], payload["payoutCredits"], payload["payoutKind"]) == (
        "super",
        0,
        "provisional",
    )
    assert payload["expansion"] is None
    assert payload["expandedSymbolCodes"] is None


@pytest.mark.parametrize("markers", [None, SeriesMarkers((), kind_code="none")])
def test_board_detail_outside_a_series_is_base_mode(markers: SeriesMarkers | None) -> None:
    payload = _detail(WORKED_EXAMPLE, markers)
    assert (payload["mode"], payload["spinCostCredits"], payload["expansion"]) == (
        "base",
        SPIN_COST,
        None,
    )
    assert payload["payoutKind"] == "none"


def test_the_trigger_board_itself_is_base_mode() -> None:
    payload = _detail(TRIGGER_BOARD, SeriesMarkers(((42, 10, "K"),)))
    assert payload["mode"] == "base"
    assert payload["expansion"] is None
    assert payload["payoutCredits"] == 216


def test_super_symbol_code_outside_the_rules_is_treated_as_undefined() -> None:
    # E.g. a catalog symbol that the evaluated rules version does not contain.
    response = _range(
        SeriesMarkers(((10, 10, "NOT-A-SYMBOL"),)), (_range_document(11, WORKED_EXAMPLE),)
    )
    # Without a usable super symbol the worked example board has no line win.
    assert response.rows == ()
    assert response.summary.provisional_count == 1
    assert response.summary.provisional_payout_credits == 0


def test_super_symbol_that_became_wild_in_the_rules_is_treated_as_undefined() -> None:
    configuration = _configuration()
    symbols = tuple(
        replace(symbol, is_wildcard=True) if symbol.code == "SARKOFAG" else symbol
        for symbol in configuration.symbols
    )
    rules = replace(
        configuration,
        symbols=symbols,
        payout_symbols=tuple(
            value for value in configuration.payout_symbols if value.symbol_mobile_code != 6
        ),
        payout_rules=tuple(
            value for value in configuration.payout_rules if value.symbol_mobile_code != 6
        ),
    )
    service = BoardSearchApproximateWinService(
        MemoryBoardSearchApproximateWinRepository(
            GAME_ID,
            sequence_length=200,
            configuration=rules,
            documents=(_range_document(11, (1, 2, 6, 3, 5, 2, 3, 5, 4, 1, 3, 5, 1, 2, 6)),),
        ),
        SeriesMarkers(((10, 10, "SARKOFAG"),)),
    )
    calculation = service.calculate(
        game_id=GAME_ID, start_sequence_number=1, requested_spin_count=20
    )
    assert calculation.result.summary.provisional_count == 1


class SnapshotRecordingRepository(MemoryBoardSearchApproximateWinRepository):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[str] = []

    def begin_read_snapshot(self) -> None:
        self.calls.append("snapshot")

    def game_sequence_length(self, game_id: UUID) -> int:
        self.calls.append("sequence_length")
        return super().game_sequence_length(game_id)


class SnapshotRecordingDetailRepository(SeriesBoardDetailRepository):
    calls: list[str]

    def begin_read_snapshot(self) -> None:
        self.calls.append("snapshot")

    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None:
        self.calls.append("rules")
        return super().latest_published_rules(game_id)


@pytest.mark.parametrize("read_snapshot", [True, False])
def test_services_open_the_read_snapshot_before_the_first_read(read_snapshot: bool) -> None:
    """Audit TASK-0936 P0-3: rules, boards, markers and state in one snapshot."""

    repository = SnapshotRecordingRepository(
        GAME_ID, sequence_length=200, configuration=_configuration()
    )
    BoardSearchApproximateWinService(
        repository, SeriesMarkers(()), read_snapshot=read_snapshot
    ).calculate(game_id=GAME_ID, start_sequence_number=1, requested_spin_count=5)
    assert repository.calls[0] == ("snapshot" if read_snapshot else "sequence_length")
    assert repository.calls.count("snapshot") == (1 if read_snapshot else 0)

    detail_repository = SnapshotRecordingDetailRepository(
        document=_document(WORKED_EXAMPLE),
        configuration=_configuration(DETAIL_GAME_ID),
    )
    detail_repository.calls = []
    BoardSearchBoardDetailService(
        detail_repository, SeriesMarkers(()), read_snapshot=read_snapshot
    ).detail(game_id=DETAIL_GAME_ID, sequence_number=42)
    assert detail_repository.calls[0] == ("snapshot" if read_snapshot else "rules")
