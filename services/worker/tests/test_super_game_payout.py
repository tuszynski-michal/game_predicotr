"""Golden cases of the ``wild_super_spins`` series board evaluation (TASK-0936).

The TypeScript mirror in ``packages/shared-ts`` (``evaluateSeriesBoard``)
executes the same ``wildSuperSpinsScenario`` section of
``packages/domain-fixtures/payout-golden-cases.json``; both must agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
from game_predictor_worker.domain.payout import (
    PAYOUT_V4_ALGORITHM_VERSION,
    PreparedPayoutEvaluator,
    payout_algorithm_version,
    prepare_payout_evaluator,
)
from game_predictor_worker.domain.super_games import (
    WILD_SUPER_SPINS,
    SeriesBoardEvaluation,
    SeriesPayoutKind,
    evaluate_series_board,
    get_super_game_kind,
)
from test_payout import (
    _game_from_fixture,
    _load_fixture,
    _paylines_from_fixture,
    _payout_symbols_from_fixture,
    _rules_from_fixture,
)


def _scenario() -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _load_fixture()["wildSuperSpinsScenario"])


def _evaluator() -> PreparedPayoutEvaluator:
    scenario = _scenario()
    return prepare_payout_evaluator(
        _game_from_fixture(scenario["game"]),
        _paylines_from_fixture(scenario["paylines"]),
        _payout_symbols_from_fixture(scenario["payoutSymbols"]),
        _rules_from_fixture(scenario["payoutRules"]),
    )


def _case(case_id: str) -> Mapping[str, Any]:
    return cast(
        Mapping[str, Any],
        next(case for case in _scenario()["cases"] if case["id"] == case_id),
    )


def _evaluate(case: Mapping[str, Any]) -> SeriesBoardEvaluation:
    cells = tuple(cell for row in case["rows"] for cell in row)
    return evaluate_series_board(
        cells,
        case["superSymbolMobileCode"],
        _evaluator(),
        generation_fresh=case.get("generationFresh", True),
    )


def _serialize(result: SeriesBoardEvaluation, columns: int) -> dict[str, Any]:
    cells = result.evaluated_cells
    return {
        "totalPayout": result.total_payout,
        "payoutKind": str(result.payout_kind),
        "evaluatedRows": [
            list(cells[start : start + columns]) for start in range(0, len(cells), columns)
        ],
        "expansion": None
        if result.expansion is None
        else {
            "symbolMobileCode": result.expansion.symbol_mobile_code,
            "columns": list(result.expansion.columns),
            "columnCount": result.expansion.column_count,
            "linePayoutCredits": result.expansion.line_payout_credits,
            "paylineCount": result.expansion.payline_count,
            "payoutCredits": result.expansion.payout_credits,
        },
        "matches": [
            {
                "symbolMobileCode": match.symbol_mobile_code,
                "paylineId": match.payline_id,
                "startColumn": match.start_column,
                "matchedLength": match.matched_length,
                "matchedCells": list(match.matched_cells),
                "jokerCells": list(match.joker_cells),
                "payoutCredits": match.payout_credits,
                "interpretation": [
                    {
                        "cellIndex": value.cell_index,
                        "asSymbolMobileCode": value.as_symbol_mobile_code,
                    }
                    for value in match.interpretation
                ],
            }
            for match in result.matches
        ],
        "countMatches": [
            {
                "symbolMobileCode": match.symbol_mobile_code,
                "count": match.count,
                "matchedCells": list(match.matched_cells),
                "payoutCredits": match.payout_credits,
            }
            for match in result.count_matches
        ],
        "retrigger": result.retrigger,
    }


@pytest.mark.parametrize(
    "case",
    _scenario()["cases"],
    ids=lambda case: cast(Mapping[str, Any], case)["id"],
)
def test_wild_super_spins_golden_cases(case: Mapping[str, Any]) -> None:
    assert case["manualCalculation"], "Golden case must document manual calculation."
    result = _evaluate(case)
    assert _serialize(result, _scenario()["game"]["columns"]) == case["expected"]
    total = (
        sum(match.payout_credits for match in result.matches)
        + sum(match.payout_credits for match in result.count_matches)
        + (0 if result.expansion is None else result.expansion.payout_credits)
    )
    assert result.total_payout == total


def test_scenario_is_a_v4_game_of_the_registered_kind() -> None:
    scenario = _scenario()
    game = _game_from_fixture(scenario["game"])
    assert payout_algorithm_version(game) == scenario["algorithmVersion"]
    assert scenario["algorithmVersion"] == PAYOUT_V4_ALGORITHM_VERSION
    kind = get_super_game_kind(scenario["superGameKind"])
    assert kind is WILD_SUPER_SPINS
    assert kind.evaluate_series_board is evaluate_series_board
    assert kind.free_spin_cost == 0


def test_worked_example_of_the_plan_pays_ten_times_five() -> None:
    result = _evaluate(_case("worked-example-k-in-columns-2-4-5"))
    assert result.expansion is not None
    assert result.expansion.columns == (1, 3, 4)
    assert result.expansion.line_payout_credits == 10
    assert result.expansion.payout_credits == 50
    assert result.payout_kind is SeriesPayoutKind.EXACT


def test_undefined_super_symbol_is_neither_a_lower_nor_an_upper_bound() -> None:
    grows = _evaluate(_case("undefined-super-symbol-is-provisional-and-may-grow"))
    grown = _evaluate(_case("expansion-covers-a-line-win-underneath"))
    shrinks = _evaluate(_case("undefined-super-symbol-is-provisional-and-may-shrink"))
    shrunk = _evaluate(_case("defined-super-symbol-covers-a-larger-win"))

    assert grows.payout_kind is SeriesPayoutKind.PROVISIONAL
    assert shrinks.payout_kind is SeriesPayoutKind.PROVISIONAL
    assert grows.total_payout < grown.total_payout
    assert shrinks.total_payout > shrunk.total_payout


def test_unknown_cell_outside_super_columns_can_cross_the_threshold() -> None:
    before = _evaluate(_case("unknown-cell-outside-super-columns-below-threshold"))
    after = _evaluate(_case("unknown-cell-outside-super-columns-filled-as-super-symbol"))

    assert before.payout_kind is SeriesPayoutKind.PROVISIONAL
    assert before.expansion is None
    assert after.expansion is not None
    assert after.expansion.column_count == 3
    # The covered column removed the base-mode A line: not a lower bound.
    assert [match.symbol_mobile_code for match in before.matches] == [5]
    assert after.matches == ()
    assert before.total_payout != after.total_payout


def test_unknown_cell_in_a_covered_column_still_changes_counts_and_retrigger() -> None:
    before = _evaluate(_case("two-mumias-and-unknown-cell-in-covered-column"))
    after = _evaluate(_case("two-mumias-unknown-cell-filled-as-mumia"))

    assert before.payout_kind is SeriesPayoutKind.PROVISIONAL
    assert after.payout_kind is SeriesPayoutKind.EXACT
    assert before.evaluated_cells == after.evaluated_cells
    assert before.matches == after.matches
    assert before.expansion == after.expansion
    assert (before.retrigger, after.retrigger) == (False, True)
    assert after.total_payout - before.total_payout == 20


def test_super_symbol_that_is_not_a_line_symbol_is_treated_as_undefined() -> None:
    case = _case("worked-example-k-in-columns-2-4-5")
    cells = tuple(cell for row in case["rows"] for cell in row)
    mumia = 7  # Wild and trigger: no line payout of its own.
    result = evaluate_series_board(cells, mumia, _evaluator())
    assert result.expansion is None
    assert result.payout_kind is SeriesPayoutKind.PROVISIONAL


def test_registry_kind_none_has_no_series_evaluator() -> None:
    assert get_super_game_kind("none").evaluate_series_board is None
